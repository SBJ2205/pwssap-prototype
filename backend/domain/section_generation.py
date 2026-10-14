"""Section generation from the subject catalog (Phase 8).

This module turns Subject + Teacher/slot catalog data into a concrete list
of schedulable Section objects. It is deliberately NOT the optimizer — it
produces a feasible-looking first-pass assignment:

  - The right number and kind of sections for each subject.
  - Theory sections carry a linked meeting pattern parsed from
    subject.slot_structure / subject.linked_pattern (product decision #6).
  - Lab sections are parallel, independent, single-meeting repeated
    practicals whose count comes from ceil(enrolled / capacity)
    (product decision #6).
  - Teacher assignment and slot assignment here are "first available"
    placeholders; Phase 9 (the CP-SAT solver) replaces them with the
    optimal assignments under the weighted objectives from product
    decisions #9, #11, #12.

Separation of concerns (product decision #16):
  - This module only knows about domain models (Subject, Section, Meeting,
    Teacher) and the canonical slot grid.  It does NOT touch HTTP, CSV
    ingestion, or the in-memory store.  The api/sections.py layer calls
    generate_sections_for_run() and then calls store.add_section() for
    each result — the generation logic itself is store-agnostic.
"""
import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set

from domain.enums import SubjectType
from domain.models import GenerationRun, Meeting, Section, Subject
from domain.timeslots import TimeSlot
from domain.validation import validate_slot_for_subject_type


# ── slot_structure parser ──────────────────────────────────────────────────

class SlotStructureError(ValueError):
    """Raised when a subject's slot_structure string cannot be parsed into
    a valid list of 2-hour meeting blocks for the department's slot grid."""


def parse_slot_structure(raw: Optional[str], weekly_hours: int) -> List[int]:
    """Parse a raw slot_structure string into a list of per-meeting hour counts.

    The department's slot grid uses 2-hour physical blocks.
    A 3-hour subject is represented as one 2-hour meeting + one 1-hour remainder: [2, 1].
    A 4-hour subject is represented as two 2-hour meetings: [2, 2].
    A 2-hour subject is represented as one 2-hour meeting: [2].
    A 1-hour subject is represented as one 1-hour meeting: [1].

    Valid string forms:
      - None / "" → default: pairs of 2 plus 1 if odd (e.g. 4 → [2, 2], 3 → [2, 1])
      - "3"       → shorthand for [2, 1]
      - "4"       → shorthand for [2, 2]
      - "2+1"     → [2, 1]
      - "1+2"     → [1, 2]
      - "2+2"     → [2, 2]

    Raises SlotStructureError if:
      - Any element is not 1 or 2.
      - The total hours in the pattern don't equal weekly_hours.
      - The string contains non-numeric, non-'+' characters.
    """
    if weekly_hours <= 0:
        raise SlotStructureError(f"weekly_hours={weekly_hours} must be a positive integer.")

    if not raw or not raw.strip():
        num_2s = weekly_hours // 2
        remainder = weekly_hours % 2
        result = [2] * num_2s
        if remainder:
            result.append(1)
        return result

    raw = raw.strip()

    # Single numeric value: treat as entire-block shorthand.
    if raw.isdigit():
        total = int(raw)
        if total != weekly_hours:
            raise SlotStructureError(
                f"slot_structure '{raw}' ({total} h) does not match "
                f"weekly_hours={weekly_hours}."
            )
        num_2s = total // 2
        remainder = total % 2
        result = [2] * num_2s
        if remainder:
            result.append(1)
        return result

    # "N+N+..." form.
    parts_raw = raw.split("+")
    parts: List[int] = []
    for part in parts_raw:
        part = part.strip()
        if not part.isdigit():
            raise SlotStructureError(
                f"slot_structure '{raw}' contains non-integer segment '{part}'."
            )
        parts.append(int(part))

    bad = [p for p in parts if p not in (1, 2)]
    if bad:
        raise SlotStructureError(
            f"slot_structure '{raw}' contains invalid segments {bad}. "
            "Only 2-hour meeting blocks and 1-hour remainders are supported."
        )

    total = sum(parts)
    if total != weekly_hours:
        raise SlotStructureError(
            f"slot_structure '{raw}' sums to {total} h but weekly_hours "
            f"is {weekly_hours}."
        )

    return parts


# ── Result types ───────────────────────────────────────────────────────────

@dataclass
class SectionGenerationWarning:
    """A non-fatal issue encountered during section generation.  The
    section is still produced (possibly with teacher_id=None or a
    meeting with slot_key=None), but the admin should review it before
    publishing."""
    subject_code: str
    message: str


@dataclass
class GeneratedSections:
    sections: List[Section] = field(default_factory=list)
    warnings: List[SectionGenerationWarning] = field(default_factory=list)


# ── Slot helpers ───────────────────────────────────────────────────────────

def _valid_slots_for_type(
    all_slots: List[TimeSlot], subject_type: SubjectType
) -> List[TimeSlot]:
    """Return only the canonical slots where this subject type is allowed."""
    return [s for s in all_slots if not validate_slot_for_subject_type(s, subject_type)]


def _pick_slot(
    candidate_slots: List[TimeSlot],
    teacher_id: Optional[str],
    teacher_availability: Dict[str, bool],  # slot_key -> available
    used_by_teacher: Set[str],              # slot_keys already taken by this teacher
    used_globally: Set[str],               # slot_keys already taken (same subject, same slot = clash)
) -> Optional[TimeSlot]:
    """First-available slot selection (Phase 8 feasibility placeholder).

    Picks the first slot from candidate_slots that:
      1. Passes teacher availability (hard constraint from Phase 5).
      2. Is not already used by this teacher in another section.
      3. Is not already used for the same subject in the same slot
         (prevents two sections of the same subject meeting at the
         same time — legitimate parallel lab sections are fine because
         lab slots are all slot 4 on different days).

    Returns None if no suitable slot exists, which becomes a warning.
    """
    for slot in candidate_slots:
        if teacher_id is not None:
            if not teacher_availability.get(slot.key, True):
                continue
            if slot.key in used_by_teacher:
                continue
        if slot.key in used_globally:
            continue
        return slot
    return None


# ── Core generation functions ──────────────────────────────────────────────

def _generate_theory_sections(
    subject: Subject,
    run_id: int,
    valid_slots: List[TimeSlot],
    capable_teacher_ids: List[str],
    teacher_availability_map: Dict[str, Dict[str, bool]],  # teacher_id -> {slot_key: bool}
    enrolled_count: int,
    section_id_start: int,
) -> GeneratedSections:
    """Generate one or more theory sections for a subject.

    Generate enough parallel sections to cover enrollment capacity. Each
    section gets the same linked meeting pattern derived from weekly hours.
    """
    result = GeneratedSections()
    warnings = result.warnings

    try:
        meeting_hours_list = parse_slot_structure(subject.slot_structure, subject.weekly_hours)
    except SlotStructureError as exc:
        warnings.append(SectionGenerationWarning(
            subject_code=subject.subject_code,
            message=f"Cannot parse slot_structure: {exc}. Section skipped.",
        ))
        return result

    num_sections = max(1, math.ceil(enrolled_count / subject.capacity)) if enrolled_count > 0 else 1
    num_meetings = len(meeting_hours_list)

    for section_number in range(1, num_sections + 1):
        section_label = f"{subject.subject_code}-T{section_number}"
        assigned_teacher: Optional[str] = None
        teacher_avail: Dict[str, bool] = {}

        # This is only an initial placeholder. The solver later considers
        # every capable teacher and enforces availability and load limits.
        if capable_teacher_ids:
            candidate_teacher = capable_teacher_ids[(section_number - 1) % len(capable_teacher_ids)]
            candidate_avail = teacher_availability_map.get(candidate_teacher, {})
            if sum(1 for s in valid_slots if candidate_avail.get(s.key, True)) >= num_meetings:
                assigned_teacher = candidate_teacher
                teacher_avail = candidate_avail

        if assigned_teacher is None:
            warnings.append(SectionGenerationWarning(
                subject_code=subject.subject_code,
                message=(
                    f"No capable teacher with sufficient available slots for "
                    f"'{section_label}' ({num_meetings} meeting(s) needed). "
                    "Section created with teacher_id=None."
                ),
            ))

        used_by_teacher: Set[str] = set()
        used_globally: Set[str] = set()
        meetings: List[Meeting] = []
        for duration in meeting_hours_list:
            slot = _pick_slot(
                valid_slots, assigned_teacher, teacher_avail,
                used_by_teacher, used_globally
            )
            slot_part = 1 if duration == 1 else None
            if slot is None:
                warnings.append(SectionGenerationWarning(
                    subject_code=subject.subject_code,
                    message=(
                        f"Could not find a valid slot for one meeting of "
                        f"'{section_label}'. Meeting stored with slot_key=None."
                    ),
                ))
                meetings.append(Meeting(slot_key="", duration_hours=duration, slot_part=slot_part))
            else:
                meetings.append(Meeting(slot_key=slot.key, duration_hours=duration, slot_part=slot_part))
                used_by_teacher.add(slot.key)
                used_globally.add(slot.key)

        result.sections.append(Section(
            id=section_id_start + section_number - 1,
            subject_code=subject.subject_code,
            label=section_label,
            teacher_id=assigned_teacher,
            capacity=subject.capacity,
            meetings=meetings,
            run_id=run_id,
        ))
    return result


def _generate_lab_sections(
    subject: Subject,
    run_id: int,
    valid_slots: List[TimeSlot],
    capable_teacher_ids: List[str],
    teacher_availability_map: Dict[str, Dict[str, bool]],
    enrolled_count: int,
    section_id_start: int,
) -> GeneratedSections:
    """Generate parallel lab sections.

    Number of sections = ceil(enrolled_count / subject.capacity).
    Minimum 1 section (placeholder when no enrollment data yet).
    Each lab section is a single-meeting standalone practical.
    """
    result = GeneratedSections()
    warnings = result.warnings

    num_sections = max(1, math.ceil(enrolled_count / subject.capacity)) if enrolled_count > 0 else 1

    # Track teacher workload within this batch so we distribute across teachers.
    teacher_section_counts: Dict[str, int] = {tid: 0 for tid in capable_teacher_ids}
    # Track used slots per teacher across all sections.
    teacher_used_slots: Dict[str, Set[str]] = {tid: set() for tid in capable_teacher_ids}
    used_globally: Set[str] = set()

    for n in range(1, num_sections + 1):
        label = f"{subject.subject_code}-L{n}"

        # Pick the least-loaded capable teacher with a free lab slot.
        assigned_teacher = None
        teacher_avail: Dict[str, bool] = {}

        # Sort by load ascending so we spread across teachers.
        for tid in sorted(capable_teacher_ids, key=lambda t: teacher_section_counts.get(t, 0)):
            avail = teacher_availability_map.get(tid, {})
            # Check if this teacher has at least one free valid slot not yet globally used.
            has_free = any(
                avail.get(s.key, True) and s.key not in teacher_used_slots.get(tid, set())
                for s in valid_slots
            )
            if has_free:
                assigned_teacher = tid
                teacher_avail = avail
                break

        if assigned_teacher is None:
            warnings.append(SectionGenerationWarning(
                subject_code=subject.subject_code,
                message=(
                    f"No capable teacher with a free lab slot for '{label}'. "
                    "Section created with teacher_id=None."
                ),
            ))
            teacher_avail = {}

        # Pick a slot for this lab section (single meeting).
        slot = _pick_slot(
            valid_slots, assigned_teacher, teacher_avail,
            teacher_used_slots.get(assigned_teacher, set()) if assigned_teacher else set(),
            set(),  # parallel lab sections CAN share the same wall-clock slot (different groups)
        )

        if slot is None:
            warnings.append(SectionGenerationWarning(
                subject_code=subject.subject_code,
                message=f"No valid slot found for lab section '{label}'. slot_key=None.",
            ))
            meeting_slot_key = ""
        else:
            meeting_slot_key = slot.key
            if assigned_teacher:
                teacher_used_slots.setdefault(assigned_teacher, set()).add(slot.key)
                teacher_section_counts[assigned_teacher] = teacher_section_counts.get(assigned_teacher, 0) + 1

        section = Section(
            id=section_id_start + n - 1,
            subject_code=subject.subject_code,
            label=label,
            teacher_id=assigned_teacher,
            capacity=subject.capacity,
            meetings=[Meeting(slot_key=meeting_slot_key, duration_hours=min(subject.weekly_hours, 2), slot_part=None)],
            run_id=run_id,
        )
        result.sections.append(section)

    return result


# ── Public entry point ─────────────────────────────────────────────────────

def generate_sections_for_run(
    run: GenerationRun,
    subjects: Iterable[Subject],
    all_slots: List[TimeSlot],
    capable_teacher_ids_for: Dict[str, List[str]],       # subject_code -> [teacher_id]
    teacher_availability_map: Dict[str, Dict[str, bool]], # teacher_id -> {slot_key: bool}
    enrolled_counts: Dict[str, int],                       # subject_code -> enrolled student count
    section_id_start: int = 0,
) -> GeneratedSections:
    """Generate all sections for every subject in the run's semester.

    Parameters
    ----------
    run:
        The GenerationRun (provides run.id and run.semester).
    subjects:
        All subjects for the run's semester.
    all_slots:
        The full canonical TimeSlot grid (all 20 slots).
    capable_teacher_ids_for:
        Mapping from subject_code to list of teacher_ids that can teach it.
    teacher_availability_map:
        Mapping from teacher_id to {slot_key: available_bool}. Missing
        entries default to available=True (matches InMemoryStore semantics).
    enrolled_counts:
        Mapping from subject_code to student enrollment count.  0 means
        no students known yet (Phase 8 still generates a placeholder section).
    section_id_start:
        Starting value for auto-assigned section IDs (allows the caller to
        offset new IDs above existing ones).

    Returns
    -------
    GeneratedSections with .sections and .warnings populated.
    """
    overall = GeneratedSections()
    next_id = section_id_start

    theory_slots = _valid_slots_for_type(all_slots, SubjectType.THEORY)
    lab_slots = _valid_slots_for_type(all_slots, SubjectType.LAB)

    for subject in subjects:
        capable = capable_teacher_ids_for.get(subject.subject_code, [])
        enrolled = enrolled_counts.get(subject.subject_code, 0)

        if subject.type == SubjectType.THEORY:
            partial = _generate_theory_sections(
                subject=subject,
                run_id=run.id,
                valid_slots=theory_slots,
                capable_teacher_ids=capable,
                teacher_availability_map=teacher_availability_map,
                enrolled_count=enrolled,
                section_id_start=next_id,
            )
        else:  # LAB
            partial = _generate_lab_sections(
                subject=subject,
                run_id=run.id,
                valid_slots=lab_slots,
                capable_teacher_ids=capable,
                teacher_availability_map=teacher_availability_map,
                enrolled_count=enrolled,
                section_id_start=next_id,
            )

        overall.sections.extend(partial.sections)
        overall.warnings.extend(partial.warnings)
        next_id += len(partial.sections)

    return overall
