"""In-memory data store behind a small repository-style interface.

Everything the api/ (and later solver/) layers need lives behind this
class, so the underlying persistence can move to a real DB later without
touching callers — they only ever depend on InMemoryStore's method
signatures, never on how the data is actually held.

Unlike the earlier prototype, this store starts EMPTY of subjects,
teachers, and students: this is a CSV-driven, department-scoped system
(see product decisions #1 and #7-#8), so fabricating demo rows here would
misrepresent how the real app is populated. The only thing built eagerly
is the canonical time-slot grid, which is a fixed structural constant,
not demo data — see domain/timeslots.py.
"""
from typing import Dict, List, Optional

from domain.models import (
    ChoiceTagConfig,
    GenerationRun,
    Section,
    Student,
    StudentChoiceSelection,
    Subject,
    Teacher,
    TeacherSubjectCapability,
)
from domain.timeslots import TimeSlot, build_canonical_grid, is_slot_usable


class InMemoryStore:
    def __init__(self) -> None:
        # Fixed structural constant, shared by every run.
        self.time_slots: List[TimeSlot] = build_canonical_grid()

        self.subjects: Dict[str, Subject] = {}

        self.teachers: Dict[str, Teacher] = {}
        self.teacher_capabilities: List[TeacherSubjectCapability] = []
        # teacher_id -> slot_key -> available (hard constraint, admin-managed).
        # Missing entries default to available=True; the admin only needs
        # to mark the slots that are actually blocked.
        self.teacher_availability: Dict[str, Dict[str, bool]] = {}

        self.students: Dict[str, Student] = {}
        self.student_choice_selections: Dict[str, List[StudentChoiceSelection]] = {}
        # roll_number -> slot_key -> rating (1-4, see domain.enums.PreferenceRating).
        # Missing entries default to indifferent, not to any particular
        # rating -- that default lives with whatever reads this (the
        # solver, later), not here.
        self.student_time_preferences: Dict[str, Dict[str, int]] = {}

        self.sections: Dict[int, Section] = {}
        self._next_section_id: int = 0

        self.runs: Dict[int, GenerationRun] = {}
        self._next_run_id: int = 0

    # ── Time slots (fixed, structural) ─────────────────────────────────────
    def list_time_slots(self) -> List[TimeSlot]:
        return self.time_slots

    def get_time_slot(self, key: str) -> Optional[TimeSlot]:
        return next((s for s in self.time_slots if s.key == key), None)

    def list_ratable_time_slots(self) -> List[TimeSlot]:
        """Slots a student can actually rate -- excludes Monday's first
        slot, which is blocked for everything and would be meaningless
        to ask a student to rate (product decision #4)."""
        return [s for s in self.time_slots if is_slot_usable(s)]

    # ── Subjects ─────────────────────────────────────────────────────────────
    def list_subjects(self, semester: Optional[int] = None) -> List[Subject]:
        subjects = list(self.subjects.values())
        if semester is not None:
            subjects = [s for s in subjects if s.semester == semester]
        return subjects

    def get_subject(self, code: str) -> Optional[Subject]:
        return self.subjects.get(code)

    def upsert_subject(self, subject: Subject) -> Subject:
        self.subjects[subject.subject_code] = subject
        return subject

    def delete_subject(self, code: str) -> None:
        self.subjects.pop(code, None)

    def list_subject_tags(self, semester: Optional[int] = None) -> List[str]:
        """Distinct subject_tag values currently in the catalog, optionally
        scoped to one semester. Used by the admin choice-tag configuration
        UI (product decision #3) to show which tags exist to choose from."""
        return sorted({s.subject_tag for s in self.list_subjects(semester)})

    # ── Teachers ───────────────────────────────────────────────────────────
    def list_teachers(self) -> List[Teacher]:
        return list(self.teachers.values())

    def get_teacher(self, teacher_id: str) -> Optional[Teacher]:
        return self.teachers.get(teacher_id)

    def upsert_teacher(self, teacher: Teacher) -> Teacher:
        self.teachers[teacher.teacher_id] = teacher
        return teacher

    def add_teacher_capability(self, teacher_id: str, subject_code: str) -> None:
        exists = any(
            c.teacher_id == teacher_id and c.subject_code == subject_code
            for c in self.teacher_capabilities
        )
        if not exists:
            self.teacher_capabilities.append(TeacherSubjectCapability(teacher_id, subject_code))

    def capabilities_for_teacher(self, teacher_id: str) -> List[str]:
        return [c.subject_code for c in self.teacher_capabilities if c.teacher_id == teacher_id]

    def teachers_for_subject(self, subject_code: str) -> List[str]:
        return [c.teacher_id for c in self.teacher_capabilities if c.subject_code == subject_code]

    # ── Teacher availability (hard constraint) ──────────────────────────────
    def set_teacher_availability(self, teacher_id: str, slot_key: str, available: bool) -> None:
        self.teacher_availability.setdefault(teacher_id, {})[slot_key] = available

    def is_teacher_available(self, teacher_id: str, slot_key: str) -> bool:
        return self.teacher_availability.get(teacher_id, {}).get(slot_key, True)

    def get_teacher_availability(self, teacher_id: str) -> Dict[str, bool]:
        return dict(self.teacher_availability.get(teacher_id, {}))

    # ── Students ───────────────────────────────────────────────────────────
    def list_students(self, semester: Optional[int] = None) -> List[Student]:
        students = list(self.students.values())
        if semester is not None:
            students = [s for s in students if s.semester == semester]
        return students

    def get_student(self, roll_number: str) -> Optional[Student]:
        return self.students.get(roll_number)

    def upsert_student(self, student: Student) -> Student:
        self.students[student.roll_number] = student
        return student

    def delete_student(self, roll_number: str) -> None:
        self.students.pop(roll_number, None)
        self.student_choice_selections.pop(roll_number, None)
        self.student_time_preferences.pop(roll_number, None)

    # ── Student time-slot preferences ────────────────────────────────────
    def get_time_preferences(self, roll_number: str) -> Dict[str, int]:
        return dict(self.student_time_preferences.get(roll_number, {}))

    def set_time_preferences(self, roll_number: str, ratings: Dict[str, int]) -> None:
        self.student_time_preferences[roll_number] = dict(ratings)

    # ── Student choice selections (per-run) ─────────────────────────────────
    def set_student_choice_selections(
        self, roll_number: str, selections: List[StudentChoiceSelection]
    ) -> None:
        self.student_choice_selections[roll_number] = selections

    def get_student_choice_selections(self, roll_number: str) -> List[StudentChoiceSelection]:
        return list(self.student_choice_selections.get(roll_number, []))

    # ── Sections (concrete teacher/time timetable data) ─────────────────────
    def list_sections(self, subject_code: Optional[str] = None) -> List[Section]:
        sections = list(self.sections.values())
        if subject_code is not None:
            sections = [s for s in sections if s.subject_code == subject_code]
        return sections

    def get_section(self, section_id: int) -> Optional[Section]:
        return self.sections.get(section_id)

    def add_section(self, section: Section) -> Section:
        if section.id is None:
            section.id = self._next_section_id
        self._next_section_id = max(self._next_section_id, section.id + 1)
        self.sections[section.id] = section
        return section

    def delete_section(self, section_id: int) -> None:
        self.sections.pop(section_id, None)

    # ── Generation runs (semester-scoped, product decision #2) ─────────────
    def create_run(self, semester: int) -> GenerationRun:
        run = GenerationRun(id=self._next_run_id, semester=semester)
        self.runs[run.id] = run
        self._next_run_id += 1
        return run

    def get_run(self, run_id: int) -> Optional[GenerationRun]:
        return self.runs.get(run_id)

    def list_runs(self, semester: Optional[int] = None) -> List[GenerationRun]:
        runs = list(self.runs.values())
        if semester is not None:
            runs = [r for r in runs if r.semester == semester]
        return runs

    def set_run_choice_tags(self, run_id: int, configs: List[ChoiceTagConfig]) -> GenerationRun:
        """Replace a run's choice-tag configuration wholesale. The mapping
        is only ever meaningful for this one run (product decision #3), so
        there is no merge semantics here — the admin submits the full set
        each time."""
        run = self.runs[run_id]
        run.choice_tag_configs = list(configs)
        return run


# ── Store access ──────────────────────────────────────────────────────────
# A single process-wide instance. This is the one place a future DB-backed
# store would plug in: swap what get_store() returns/constructs, and every
# api/ route (which only ever receives a store via this function) keeps
# working unchanged.
_default_store: Optional[InMemoryStore] = None


def get_store() -> InMemoryStore:
    global _default_store
    if _default_store is None:
        _default_store = InMemoryStore()
    return _default_store


def reset_store() -> None:
    """Reset the process-wide store. Mainly useful for tests."""
    global _default_store
    _default_store = None
