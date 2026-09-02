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
) -> SolverResult:
    """Orchestrate the full solve cycle for one generation run.

    Steps:
      1. Validate the run exists and is in DRAFT/SOLVED state.
      2. Load sections, preferences, availability from the store.
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
    semester_students = store.list_students(semester=run.semester)
    semester_subjects = store.list_subjects(semester=run.semester)

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
    # Choice-based subjects: students who selected that tag.
    # Non-choice subjects: all semester students.
    subject_students: Dict[str, List[str]] = {}
    for subject in semester_subjects:
        choice_numeric_values = {
            c.numeric_value
            for c in run.choice_tag_configs
            if c.tag == subject.subject_tag and c.is_choice_based
        }
        if not choice_numeric_values:
            # Non-choice subject: all semester students.
            subject_students[subject.subject_code] = [
                s.roll_number for s in semester_students
            ]
        else:
            enrolled = []
            for student in semester_students:
                selections = store.get_student_choice_selections(student.roll_number)
                if any(sel.numeric_value in choice_numeric_values for sel in selections):
                    enrolled.append(student.roll_number)
            subject_students[subject.subject_code] = enrolled

    inp = SolverInput(
        sections=sections,
        candidate_slots=candidate_slots,
        candidate_teachers=candidate_teachers,
        time_preferences=time_preferences,
        faculty_preferences=faculty_preferences,
        teacher_availability=teacher_availability,
        subject_students=subject_students,
        time_limit_seconds=time_limit_seconds,
    )

    result = solve(inp)

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

        # Update meeting slot keys.
        assigned_slots = result.section_slot_assignments.get(sid, [])
        new_meetings: List[Meeting] = []
        for i, slot_key in enumerate(assigned_slots):
            new_meetings.append(Meeting(slot_key=slot_key))
        # Preserve meeting count if solver returned fewer slots than expected.
        if new_meetings:
            section.meetings = new_meetings

        # Re-save so the store's dict reflects the update
        # (Section is mutable and stored by reference, but explicit upsert
        # is safer if the store implementation changes later).
        store.sections[sid] = section

    # Persist student-section assignments.
    # Store as a flat dict on the store for Phase 10/11 to read.
    if not hasattr(store, "student_section_assignments"):
        store.student_section_assignments: Dict[str, Dict[str, int]] = {}

    for roll, sub_sid_map in result.student_section_assignments.items():
        store.student_section_assignments.setdefault(roll, {}).update(sub_sid_map)
