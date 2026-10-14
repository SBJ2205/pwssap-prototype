"""Solver orchestration layer (Phase 9).

Thin wrapper that:
  1. Reads everything the engine needs from InMemoryStore.
  2. Calls solver.engine.solve().
  3. Writes the result (slot/teacher/student assignments) back to the store.
  4. Transitions run status: DRAFT -> SOLVED -> PUBLISHED (product decision #13).

This layer is deliberately store-aware so api/solver.py stays thin.
The engine itself (solver/engine.py) is store-agnostic for testability.
"""
from typing import Dict, List, Optional

from data.store import InMemoryStore
from domain.enums import RunStatus, SubjectType
from domain.models import Meeting, Section
from domain.timeslots import TimeSlot
from solver.engine import SolverInput, SolverResult, solve


def _valid_slots_for_type(
    all_slots: List[TimeSlot], subject_type: SubjectType
) -> List[TimeSlot]:
    """Return only slots where this subject type is allowed."""
    return [s for s in all_slots if subject_type in s.allowed_types]


def run_solver_for_run(
    run_id: int,
    store: InMemoryStore,
    time_limit_seconds: float = 30.0,
    feasibility_only: bool = False,
) -> SolverResult:
    """Orchestrate the full solve cycle for one generation run.

    Steps:
      1. Validate the run exists and is in DRAFT/SOLVED state.
      2. Load sections, preferences, availability from the store across all run semesters.
      3. Build SolverInput and call solve().
      4. Write assignments back to each Section in the store.
      5. Build and store student-section enrollment records.
      6. Transition run status to PUBLISHED.
      7. Return the SolverResult for the API layer to serialise.
    """
    run = store.get_run(run_id)
    if run is None:
        raise ValueError(f"Run {run_id} does not exist.")

    # Re-running the solver is not the normal path (product decision #13),
    # but we allow it on SOLVED/PUBLISHED too in case the admin explicitly
    # triggers it again after changing availability or subjects.
    sections = store.list_sections_for_run(run_id)
    if not sections:
        raise ValueError(
            f"Run {run_id} has no sections yet. "
            "Run POST /admin/runs/{run_id}/generate-sections first."
        )

    all_slots = store.list_time_slots()
    semesters = run.semesters if hasattr(run, "semesters") and run.semesters else [run.semester]

    semester_students = []
    seen_rolls = set()
    for sem in semesters:
        for s in store.list_students(semester=sem):
            if s.roll_number not in seen_rolls:
                seen_rolls.add(s.roll_number)
                semester_students.append(s)

    semester_subjects = []
    seen_codes = set()
    for sem in semesters:
        for subj in store.list_subjects(semester=sem):
            if subj.subject_code not in seen_codes:
                seen_codes.add(subj.subject_code)
                semester_subjects.append(subj)

    # Candidate slots per section (type-legal).
    candidate_slots: Dict[int, List[TimeSlot]] = {}
    for section in sections:
        subject = store.get_subject(section.subject_code)
        if subject is None:
            candidate_slots[section.id] = []
            continue
        candidate_slots[section.id] = _valid_slots_for_type(all_slots, subject.type)

    # Candidate teachers per section.
    candidate_teachers: Dict[int, List[str]] = {
        section.id: store.teachers_for_subject(section.subject_code)
        for section in sections
    }
    teacher_subject_loads: Dict[tuple[str, str], Optional[int]] = {
        (teacher_id, subject_code): store.teacher_subject_load(teacher_id, subject_code)
        for subject_code in {section.subject_code for section in sections}
        for teacher_id in store.teachers_for_subject(subject_code)
    }

    # Pre-feasibility checks for warnings.
    pre_warnings: List[str] = []
    for section in sections:
        cand_t = candidate_teachers.get(section.id, [])
        if not cand_t:
            pre_warnings.append(
                f"Section {section.label} ({section.subject_code}) has no capable teachers."
            )
        cand_s = candidate_slots.get(section.id, [])
        if not cand_s:
            pre_warnings.append(
                f"Section {section.label} ({section.subject_code}) has no valid time slots."
            )

    # Teacher availability map.
    all_teacher_ids = sorted({
        tid
        for tids in candidate_teachers.values()
        for tid in tids
    })
    teacher_availability: Dict[str, Dict[str, bool]] = {
        tid: store.get_teacher_availability(tid)
        for tid in all_teacher_ids
    }

    # Time and faculty preferences.
    time_preferences: Dict[str, Dict[str, int]] = {
        student.roll_number: store.get_time_preferences(student.roll_number)
        for student in semester_students
    }
    faculty_preferences: Dict[str, Dict[str, Dict[str, int]]] = {
        student.roll_number: store.get_faculty_preferences(student.roll_number)
        for student in semester_students
    }

    # Subject -> student list (who gets enrolled in which subject).
    # Choice-based subjects: students who selected matching subtag or tag.
    # Non-choice subjects: all students in that subject's semester.
    cb_tags = store.get_choice_based_tags()
    if not cb_tags and getattr(run, "choice_tag_configs", None):
        cb_tags = {c.tag for c in run.choice_tag_configs if c.is_choice_based}

    subject_students: Dict[str, List[str]] = {}
    for subject in semester_subjects:
        is_choice = subject.subject_tag in cb_tags
        enrolled: List[str] = []
        for student in semester_students:
            if student.semester != subject.semester:
                continue
            if not is_choice:
                enrolled.append(student.roll_number)
            else:
                lock_in = store.get_lock_in_for_student(student.roll_number)
                chosen_subtag = lock_in.get(subject.subject_tag)
                if chosen_subtag and subject.supports_subtag(chosen_subtag):
                    enrolled.append(student.roll_number)
                elif not subject.supported_subtags:
                    selections = store.get_student_choice_selections(student.roll_number)
                    choice_numeric_values = {
                        c.numeric_value
                        for c in getattr(run, "choice_tag_configs", [])
                        if c.tag == subject.subject_tag and c.is_choice_based
                    }
                    if choice_numeric_values and any(sel.numeric_value in choice_numeric_values for sel in selections):
                        enrolled.append(student.roll_number)
                    elif not choice_numeric_values and chosen_subtag:
                        enrolled.append(student.roll_number)
        subject_students[subject.subject_code] = enrolled

    # Explain common structural infeasibility before CP-SAT returns only its
    # generic status. These checks are diagnostics; the solver remains final.
    sections_by_subject: Dict[str, List[Section]] = {}
    for section in sections:
        sections_by_subject.setdefault(section.subject_code, []).append(section)

    for subject in semester_subjects:
        subject_sections = sections_by_subject.get(subject.subject_code, [])
        demand = len(subject_students.get(subject.subject_code, []))
        total_capacity = sum(section.capacity for section in subject_sections)
        if demand > total_capacity:
            pre_warnings.append(
                f"{subject.subject_code} has {demand} eligible student(s), "
                f"but generated sections provide only {total_capacity} seat(s). "
                "Increase capacity or generate more sections."
            )
        if demand > 0 and not subject_sections:
            pre_warnings.append(
                f"{subject.subject_code} has {demand} eligible student(s) but no generated sections."
            )

        capable_teachers = store.teachers_for_subject(subject.subject_code)
        declared_loads = [
            store.teacher_subject_load(teacher_id, subject.subject_code)
            for teacher_id in capable_teachers
        ]
        if declared_loads and all(load is not None for load in declared_loads):
            available_hours = sum(load or 0 for load in declared_loads)
            required_hours = len(subject_sections) * subject.weekly_hours
            if available_hours < required_hours:
                pre_warnings.append(
                    f"{subject.subject_code} requires {required_hours} teacher-hour(s) "
                    f"for {len(subject_sections)} section(s), but declared teacher loads "
                    f"provide only {available_hours}. Increase a subject load or add a capable teacher."
                )
            if subject_sections and not any(
                (load or 0) >= subject.weekly_hours for load in declared_loads
            ):
                pre_warnings.append(
                    f"No capable teacher has enough declared weekly load to teach one complete "
                    f"{subject.weekly_hours}-hour section of {subject.subject_code}."
                )

    inp = SolverInput(
        sections=sections,
        candidate_slots=candidate_slots,
        candidate_teachers=candidate_teachers,
        time_preferences=time_preferences,
        faculty_preferences=faculty_preferences,
        teacher_availability=teacher_availability,
        teacher_subject_loads=teacher_subject_loads,
        subject_students=subject_students,
        feasibility_only=feasibility_only,
        time_limit_seconds=time_limit_seconds,
    )

    result = solve(inp)
    if pre_warnings:
        result.warnings.extend(pre_warnings)

    if result.status in ("OPTIMAL", "FEASIBLE"):
        _write_assignments_to_store(store, sections, result)
        run.status = RunStatus.PUBLISHED  # DRAFT -> PUBLISHED (product decision #13)

    return result


def _write_assignments_to_store(
    store: InMemoryStore,
    sections: List[Section],
    result: SolverResult,
) -> None:
    """Update each Section in the store with the solver's assignments."""
    for section in sections:
        sid = section.id

        # Update teacher assignment.
        teacher_id = result.section_teacher_assignments.get(sid)
        section.teacher_id = teacher_id

        # Update meetings preserving duration_hours and slot_part.
        if sid in result.section_meetings and result.section_meetings[sid]:
            section.meetings = result.section_meetings[sid]
        else:
            assigned_slots = result.section_slot_assignments.get(sid, [])
            new_meetings: List[Meeting] = []
            for i, slot_key in enumerate(assigned_slots):
                orig_m = section.meetings[i] if i < len(section.meetings) else None
                dur = getattr(orig_m, "duration_hours", 2) if orig_m else 2
                sp = getattr(orig_m, "slot_part", None) if orig_m else None
                new_meetings.append(Meeting(slot_key=slot_key, duration_hours=dur, slot_part=sp))
            if new_meetings:
                section.meetings = new_meetings

        # Re-save so the store's dict reflects the update.
        store.sections[sid] = section

    # Persist student-section assignments via the store's proper CRUD methods.
    for roll, sub_sid_map in result.student_section_assignments.items():
        for subject_code, section_id in sub_sid_map.items():
            store.enroll_student(roll, subject_code, section_id)


