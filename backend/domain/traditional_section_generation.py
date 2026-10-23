"""Traditional Division & Batch section generation.

Generates the sections of one run from the saved division/batch setup of each of
its semesters, and records a TraditionalPlan (see domain.traditional_plan).

Conventions shared with the solver engine (it parses labels with regexes):

- Theory for division k is labelled ``{code}-T{k}``; lab for batch b ``{code}-L{b}``.
  k counts the semester's divisions in saved order. b counts its lab batches
  across all divisions in saved order.
- The batch -> division relationship is passed to the solver explicitly (the
  engine's own heuristic only works when every division has the same number of
  batches).
- Dispersal electives (a choice tag whose subjects are all theory with >= 2
  subtags) get ONE section per subject, labelled ``{code}-T1`` so the engine keeps
  them clear of core classes, and are registered as a synchronisation group so
  they run at identical times.

Student memberships are *not* written to the live assignments here. They are kept
in the plan and applied only after a successful solve, so an unsolved run never
leaks placeholder timetables.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from domain.cohorts import (
    CohortConfigError,
    SemesterCohortConfig,
    classify_semester,
    enrolled_codes,
    is_lab,
    roster_mismatch,
    semester_students,
)
from domain.enums import RunStatus
from domain.models import Meeting, Section
from domain.section_generation import SlotStructureError, parse_slot_structure
from domain.traditional_plan import (
    BATCH_LAB,
    DIVISION_THEORY,
    DISPERSAL,
    SectionInfo,
    StudentUnit,
    TraditionalPlan,
)


def _meeting_template(subject: Any) -> List[Meeting]:
    """Unscheduled meetings (slot_key blank) for the solver to place."""
    try:
        hours = parse_slot_structure(subject.slot_structure, subject.weekly_hours)
    except SlotStructureError:
        hours = [2] * (subject.weekly_hours // 2) + ([1] if subject.weekly_hours % 2 else [])
    if not hours:
        hours = [max(1, min(subject.weekly_hours, 2))]
    return [
        Meeting(slot_key="", duration_hours=h, slot_part=1 if h == 1 else None)
        for h in hours
    ]


@dataclass
class _Pending:
    section: Section
    info: SectionInfo
    rolls: List[str]
    durations: Tuple[int, ...] = ()


@dataclass
class _SemesterBuild:
    pending: List[_Pending] = field(default_factory=list)
    units: Dict[str, StudentUnit] = field(default_factory=dict)
    batch_division_map: Dict[Tuple[int, int], int] = field(default_factory=dict)
    division_names: Dict[Tuple[int, int], str] = field(default_factory=dict)
    batch_names: Dict[Tuple[int, int], str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    sync_pending: List[List[_Pending]] = field(default_factory=list)


def _placeholder_teacher(store: Any, subject_code: str) -> Optional[str]:
    capable = store.teachers_for_subject(subject_code)
    return capable[0] if capable else None


def _build_semester(store: Any, semester: int, config: SemesterCohortConfig) -> _SemesterBuild:
    structure = classify_semester(store, semester)
    if structure.unsupported_track_tags:
        raise CohortConfigError([
            f"Semester {semester} has several track elective tags "
            f"({structure.track_tag}, {', '.join(structure.unsupported_track_tags)}); only one is supported."
        ])

    out = _SemesterBuild()
    students = semester_students(store, semester)
    enrolled: Dict[str, Set[str]] = {s.roll_number: enrolled_codes(store, s.roll_number) for s in students}

    # Division / batch indices exactly as the solver will see them.
    divisions: List[Tuple[int, Any, List[Tuple[int, Any]]]] = []
    batch_counter = 0
    for k, cls in enumerate(config.classes, start=1):
        out.division_names[(semester, k)] = cls.class_id
        batch_list = []
        for batch in cls.batches:
            batch_counter += 1
            out.batch_division_map[(semester, batch_counter)] = k
            out.batch_names[(semester, batch_counter)] = batch.batch_id
            batch_list.append((batch_counter, batch))
            for roll in batch.student_rolls:
                out.units[roll] = StudentUnit(
                    semester=semester, class_id=cls.class_id, division=k,
                    batch_id=batch.batch_id, batch=batch_counter,
                )
        divisions.append((k, cls, batch_list))

    dispersal_codes = structure.dispersal_codes

    for subject in store.list_subjects(semester=semester):
        code = subject.subject_code
        if code in dispersal_codes:
            continue
        if not store.teachers_for_subject(code):
            out.warnings.append(f"{code} has no capable teacher.")

        if not is_lab(subject):
            for k, cls, _ in divisions:
                rolls = [r for r in cls.student_rolls if code in enrolled.get(r, ())]
                if rolls:
                    meetings = _meeting_template(subject)
                    out.pending.append(_Pending(
                        section=Section(
                            id=None, subject_code=code, label=f"{code}-T{k}",
                            teacher_id=_placeholder_teacher(store, code),
                            capacity=len(rolls), meetings=meetings,
                        ),
                        info=SectionInfo(
                            section_id=-1, semester=semester, subject_code=code,
                            label=f"{code}-T{k}", kind=DIVISION_THEORY,
                            division=k, class_id=cls.class_id,
                        ),
                        rolls=rolls,
                    ))
        else:
            for k, cls, batch_list in divisions:
                for b, batch in batch_list:
                    rolls = [r for r in batch.student_rolls if code in enrolled.get(r, ())]
                    if rolls:
                        meetings = _meeting_template(subject)
                        out.pending.append(_Pending(
                            section=Section(
                                id=None, subject_code=code, label=f"{code}-L{b}",
                                teacher_id=_placeholder_teacher(store, code),
                                capacity=len(rolls), meetings=meetings,
                            ),
                            info=SectionInfo(
                                section_id=-1, semester=semester, subject_code=code,
                                label=f"{code}-L{b}", kind=BATCH_LAB,
                                division=k, batch=b, class_id=cls.class_id, batch_id=batch.batch_id,
                            ),
                            rolls=rolls,
                        ))

    for tag, group in structure.dispersal_groups:
        built: List[_Pending] = []
        for subject in group:
            code = subject.subject_code
            rolls = [s.roll_number for s in students if code in enrolled[s.roll_number]]
            if not rolls:
                out.warnings.append(f"Nobody chose {code} ({tag}); no section generated for it.")
                continue
            if not store.teachers_for_subject(code):
                out.warnings.append(f"{code} has no capable teacher.")
            if len(rolls) > subject.capacity:
                out.warnings.append(
                    f"{code} has {len(rolls)} students for a capacity of {subject.capacity}."
                )
            meetings = _meeting_template(subject)
            built.append(_Pending(
                section=Section(
                    id=None, subject_code=code, label=f"{code}-T1",
                    teacher_id=_placeholder_teacher(store, code),
                    capacity=len(rolls), meetings=meetings,
                ),
                info=SectionInfo(
                    section_id=-1, semester=semester, subject_code=code,
                    label=f"{code}-T1", kind=DISPERSAL,
                ),
                rolls=rolls,
                durations=tuple(m.duration_hours for m in meetings),
            ))
        out.pending.extend(built)

        by_structure: Dict[Tuple[int, ...], List[_Pending]] = {}
        for item in built:
            by_structure.setdefault(item.durations, []).append(item)
        if len(by_structure) > 1:
            out.warnings.append(
                f"Dispersal electives of tag {tag} have different weekly structures; only electives "
                "with identical structures can be synchronised, the rest are scheduled independently."
            )
        for members in by_structure.values():
            if len(members) >= 2:
                out.sync_pending.append(members)

    for tag in sorted(store.get_choice_based_tags_for_semester(semester)):
        missing = sum(
            1 for s in students
            if not str(store.get_lock_in_for_student(s.roll_number).get(tag, "")).strip()
        )
        if missing:
            out.warnings.append(
                f"{missing} student(s) have no '{tag}' choice locked in and get no section for it."
            )
    return out


def generate_traditional_sections(store: Any, run_id: int) -> dict:
    """Generate traditional sections for every semester of a run.

    Idempotent: previously generated sections are cleared first, mirroring
    POST /admin/runs/{id}/generate-sections (which also clears every other run's
    sections, because student assignments are department-wide). Everything is
    validated and built in memory first, so a failure leaves the store untouched.
    """
    run = store.get_run(run_id)
    if run is None:
        raise LookupError(f"Run {run_id} does not exist.")
    semesters = list(run.semesters or [run.semester])

    missing = [s for s in semesters if s not in store.cohort_configs]
    if missing:
        raise CohortConfigError([
            f"Save the division setup for semester(s) {', '.join(map(str, missing))} first "
            f"(run #{run_id} covers semesters {', '.join(map(str, semesters))})."
        ])
    errors: List[str] = []
    for sem in semesters:
        for problem in roster_mismatch(store, store.cohort_configs[sem]):
            errors.append(f"Semester {sem}: {problem}. Re-save the divisions.")
    if errors:
        raise CohortConfigError(errors)

    builds = {sem: _build_semester(store, sem, store.cohort_configs[sem]) for sem in semesters}

    # ── Commit: clear the old state exactly like standard generation ──────
    cleared = store.clear_sections_for_run(run_id)
    store.traditional_plans.pop(run_id, None)
    for other in store.list_runs():
        if other.id != run_id and store.clear_sections_for_run(other.id):
            other.status = RunStatus.DRAFT
            store.latest_solve_results.pop(other.id, None)
            store.traditional_plans.pop(other.id, None)
    run.status = RunStatus.DRAFT
    store.latest_solve_results.pop(run_id, None)

    plan = TraditionalPlan(run_id=run_id, semesters=semesters)
    saved: List[Section] = []
    for sem in semesters:
        build = builds[sem]
        plan.warnings.extend(f"Semester {sem}: {w}" for w in build.warnings)
        plan.student_units.update(build.units)
        plan.batch_division_map.update(build.batch_division_map)
        plan.division_names.update(build.division_names)
        plan.batch_names.update(build.batch_names)
        plan.config_snapshot[sem] = store.cohort_configs[sem].to_dict()

        for item in build.pending:
            item.section.run_id = run_id
            section = store.add_section(item.section)
            item.info.section_id = section.id
            plan.sections[section.id] = item.info
            saved.append(section)
            for roll in item.rolls:
                plan.pins.setdefault(roll, {})[section.subject_code] = section.id
        for members in build.sync_pending:
            plan.sync_groups.append([m.info.section_id for m in members])

    for sem in semesters:
        for student in store.list_students(semester=sem):
            expected = enrolled_codes(store, student.roll_number)
            have = set(plan.pins.get(student.roll_number, {}))
            lacking = sorted(expected - have)
            if lacking:
                plan.warnings.append(
                    f"Student {student.roll_number} has no section for {', '.join(lacking)}."
                )

    store.traditional_plans[run_id] = plan

    return {
        "run_id": run_id,
        "mode": "traditional",
        "cleared_count": cleared,
        "generated_count": len(saved),
        "students_pinned": len(plan.pins),
        "synchronised_groups": len(plan.sync_groups),
        "sections": [
            {
                "id": s.id,
                "subject_code": s.subject_code,
                "label": s.label,
                "capacity": s.capacity,
                "kind": plan.sections[s.id].kind,
            }
            for s in saved
        ],
        "warnings": list(plan.warnings),
    }
