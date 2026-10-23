"""Independent validator for a solved Traditional (division/batch) timetable.

It does not trust the solver: it re-derives every guarantee from the final
sections and student assignments in the store.

Checks (each violation has a ``kind``):
  unscheduled          a meeting has no slot
  illegal_slot         a meeting sits in a slot its subject type may not use
  teacher_unassigned   a section has no teacher
  teacher_clash        a teacher is in two sections at the same time
  teacher_unavailable  a teacher teaches in a slot the admin blocked
  division_theory_clash  two theory sections of one student's division overlap
  batch_lab_clash      two lab sections of one lab batch overlap
  batch_division_clash a batch's lab overlaps its division's theory
  dispersal_not_synchronised  dispersal electives are not at identical times
  missing_section      an enrolled subject has no section
  pins_overridden      a student's live assignment differs from their saved division/batch
  split_unit           members of a division/batch do not share one section
"""
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple

from domain.cohorts import enrolled_codes, is_lab
from domain.traditional_plan import BATCH_LAB, DISPERSAL, DIVISION_THEORY, TraditionalPlan

MAX_LISTED_VIOLATIONS = 100


def _periods(section: Any) -> List[Tuple[str, int]]:
    """(slot_key, hour-part) pairs a section occupies. Unscheduled meetings are skipped."""
    periods: List[Tuple[str, int]] = []
    for m in section.meetings:
        if not m.slot_key:
            continue
        if m.duration_hours == 1:
            periods.append((m.slot_key, m.slot_part or 1))
        else:
            periods.append((m.slot_key, 1))
            periods.append((m.slot_key, 2))
    return periods


def _meeting_signature(section: Any) -> List[Tuple[str, int, int]]:
    return sorted(
        (m.slot_key, m.duration_hours, (m.slot_part or 1) if m.duration_hours == 1 else 0)
        for m in section.meetings
    )


def validate_traditional_run(store: Any, run: Any, plan: TraditionalPlan) -> dict:
    violations: List[dict] = []

    def add(kind: str, message: str) -> None:
        violations.append({"kind": kind, "message": message})

    slots = {s.key: s for s in store.list_time_slots()}
    sections = {sid: store.get_section(sid) for sid in plan.sections}
    sections = {sid: s for sid, s in sections.items() if s is not None}
    subject_is_lab = {
        sid: is_lab(store.get_subject(s.subject_code)) for sid, s in sections.items()
        if store.get_subject(s.subject_code) is not None
    }

    def name(sid: int) -> str:
        return sections[sid].label

    # ── Per-section checks ────────────────────────────────────────────────
    for sid, section in sections.items():
        info = plan.sections[sid]
        for m in section.meetings:
            if not m.slot_key:
                add("unscheduled", f"{name(sid)} has a meeting with no slot.")
                continue
            slot = slots.get(m.slot_key)
            subject = store.get_subject(section.subject_code)
            if slot is None or (subject is not None and subject.type not in slot.allowed_types):
                add("illegal_slot", f"{name(sid)} meets in {m.slot_key}, which its subject type may not use.")
        if not section.teacher_id:
            add("teacher_unassigned", f"{name(sid)} has no teacher.")
            continue
        availability = store.get_teacher_availability(section.teacher_id)
        for m in section.meetings:
            if m.slot_key and not availability.get(m.slot_key, True):
                add(
                    "teacher_unavailable",
                    f"{name(sid)}: teacher {section.teacher_id} is blocked in {m.slot_key}.",
                )

    # ── Teacher clashes ───────────────────────────────────────────────────
    by_teacher: Dict[Tuple[str, Tuple[str, int]], List[int]] = defaultdict(list)
    for sid, section in sections.items():
        if section.teacher_id:
            for period in set(_periods(section)):
                by_teacher[(section.teacher_id, period)].append(sid)
    reported: Set[Tuple[str, Tuple[int, ...]]] = set()
    for (teacher, (slot_key, _part)), sids in sorted(by_teacher.items()):
        key = (teacher, tuple(sorted(sids)))
        if len(sids) > 1 and key not in reported:
            reported.add(key)
            add(
                "teacher_clash",
                f"Teacher {teacher} is in {' and '.join(name(s) for s in sorted(sids))} at {slot_key}.",
            )

    # ── Student-level clashes, classified by unit ─────────────────────────
    pair_counts: Dict[Tuple[str, int, int, str], Dict[str, Any]] = {}
    for roll, mapping in plan.pins.items():
        unit = plan.student_units.get(roll)
        by_period: Dict[Tuple[str, int], List[int]] = defaultdict(list)
        for sid in set(mapping.values()):
            if sid in sections:
                for period in set(_periods(sections[sid])):
                    by_period[period].append(sid)
        for (slot_key, _part), sids in by_period.items():
            if len(sids) < 2:
                continue
            ordered = sorted(sids)
            for i in range(len(ordered)):
                for j in range(i + 1, len(ordered)):
                    a, b = ordered[i], ordered[j]
                    labs = (subject_is_lab.get(a, False), subject_is_lab.get(b, False))
                    if all(labs):
                        kind, scope = "batch_lab_clash", unit.batch_id if unit else "?"
                    elif not any(labs):
                        kind, scope = "division_theory_clash", unit.class_id if unit else "?"
                    else:
                        kind, scope = "batch_division_clash", unit.batch_id if unit else "?"
                    entry = pair_counts.setdefault(
                        (kind, a, b, scope), {"students": set(), "slot": slot_key}
                    )
                    entry["students"].add(roll)
    for (kind, a, b, scope), entry in sorted(pair_counts.items(), key=lambda kv: kv[0]):
        add(
            kind,
            f"{scope}: {name(a)} and {name(b)} overlap at {entry['slot']} "
            f"({len(entry['students'])} student(s)).",
        )

    # ── Dispersal synchronisation ─────────────────────────────────────────
    for group in plan.sync_groups:
        live = [sid for sid in group if sid in sections]
        if len(live) < 2:
            continue
        signatures = {sid: _meeting_signature(sections[sid]) for sid in live}
        if len({tuple(sig) for sig in signatures.values()}) > 1:
            detail = "; ".join(f"{name(sid)}: {[s[0] for s in signatures[sid]]}" for sid in live)
            add("dispersal_not_synchronised", f"Dispersal electives are not at identical times ({detail}).")

    # ── Enrollment completeness and pinning ───────────────────────────────
    overridden = 0
    missing_total = 0
    split: Dict[Tuple[str, str, str], Set[int]] = defaultdict(set)
    for roll, pinned in plan.pins.items():
        live = store.get_student_sections(roll)
        if live != pinned:
            overridden += 1
        for code in enrolled_codes(store, roll):
            if code not in live:
                missing_total += 1
                if missing_total <= 20:
                    add("missing_section", f"Student {roll} has no section for {code}.")
        unit = plan.student_units.get(roll)
        if unit is None:
            continue
        for code, sid in live.items():
            info = plan.sections.get(sid)
            if info is None:
                continue
            if info.kind == DIVISION_THEORY:
                split[("division", unit.class_id, code)].add(sid)
            elif info.kind == BATCH_LAB:
                split[("batch", unit.batch_id, code)].add(sid)
    if missing_total > 20:
        add("missing_section", f"... and {missing_total - 20} more missing sections.")
    if overridden:
        add(
            "pins_overridden",
            f"{overridden} student(s) are no longer in the sections of their saved division/batch.",
        )
    for (scope, unit_id, code), sids in sorted(split.items()):
        if len(sids) > 1:
            add("split_unit", f"{scope} {unit_id} is split across {len(sids)} sections of {code}.")

    counts: Dict[str, int] = defaultdict(int)
    for v in violations:
        counts[v["kind"]] += 1
    return {
        "ok": not violations,
        "violation_count": len(violations),
        "counts": dict(counts),
        "violations": violations[:MAX_LISTED_VIOLATIONS],
        "truncated": len(violations) > MAX_LISTED_VIOLATIONS,
        "checked": {
            "students": len(plan.pins),
            "sections": len(sections),
            "teachers": len({s.teacher_id for s in sections.values() if s.teacher_id}),
            "sync_groups": len(plan.sync_groups),
        },
    }


def summarise_report(report: dict) -> List[str]:
    """Short lines for the solver's warnings list."""
    checked = report["checked"]
    if report["ok"]:
        return [
            "Traditional timetable verified: no division, batch or teacher clashes, dispersal electives "
            f"synchronised, all {checked['students']} students placed in their saved division/batch."
        ]
    lines = [
        f"Traditional timetable has {report['violation_count']} violation(s) and was NOT published: "
        + ", ".join(f"{kind} x{n}" for kind, n in sorted(report["counts"].items())) + "."
    ]
    lines.extend(v["message"] for v in report["violations"][:5])
    return lines
