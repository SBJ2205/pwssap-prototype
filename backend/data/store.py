"""In-memory data store behind a small repository-style interface.

Everything the api/ and solver/ layers need lives behind this class, so the
underlying persistence can move to SQLite later without touching callers —
they only ever depend on InMemoryStore's method signatures, never on how
the data is actually held.
"""
from typing import Dict, List, Optional

from domain.models import Teacher, Subject, Student, Section, TimeSlot


class InMemoryStore:
    def __init__(self) -> None:
        self.teachers: Dict[int, Teacher] = {}
        self.subjects: Dict[str, Subject] = {}
        self.students: Dict[int, Student] = {}
        self.sections: Dict[int, Section] = {}
        self.time_slots: List[TimeSlot] = []

        # Student-submitted preference data. Missing keys are intentionally
        # NOT filled in here — "defaults to indifferent" is a solver-layer
        # concern (see solver/helpers.py), not a storage concern.
        self.student_ts_prefs: Dict[int, Dict[str, int]] = {}
        self.student_faculty_prefs: Dict[int, Dict[str, Dict[int, int]]] = {}

        self.last_result: dict = {}

    # ── Teachers ───────────────────────────────────────────────────────────
    def list_teachers(self) -> List[Teacher]:
        return list(self.teachers.values())

    def get_teacher(self, teacher_id: int) -> Teacher:
        return self.teachers[teacher_id]

    # ── Subjects ───────────────────────────────────────────────────────────
    def list_subjects(self) -> List[Subject]:
        return list(self.subjects.values())

    def get_subject(self, code: str) -> Subject:
        return self.subjects[code]

    # ── Students ───────────────────────────────────────────────────────────
    def list_students(self) -> List[Student]:
        return list(self.students.values())

    def get_student(self, student_id: int) -> Optional[Student]:
        return self.students.get(student_id)

    # ── Sections (hidden concrete timetable data) ─────────────────────────
    def list_sections(self) -> List[Section]:
        return list(self.sections.values())

    def sections_for_subject(self, subject_code: str) -> List[Section]:
        return [s for s in self.sections.values() if s.subject_code == subject_code]

    def get_section(self, section_id: int) -> Section:
        return self.sections[section_id]

    # ── Time slots (abstract, student-facing grid) ────────────────────────
    def list_time_slots(self) -> List[TimeSlot]:
        return self.time_slots

    # ── Preferences ────────────────────────────────────────────────────────
    def get_ts_prefs(self, student_id: int) -> Dict[str, int]:
        return self.student_ts_prefs.get(student_id, {})

    def set_ts_prefs(self, student_id: int, prefs: Dict[str, int]) -> None:
        self.student_ts_prefs[student_id] = prefs

    def get_faculty_prefs(self, student_id: int) -> Dict[str, Dict[int, int]]:
        return self.student_faculty_prefs.get(student_id, {})

    def set_faculty_prefs(self, student_id: int, prefs: Dict[str, Dict[int, int]]) -> None:
        self.student_faculty_prefs[student_id] = prefs

    # ── Solver results ─────────────────────────────────────────────────────
    def get_last_result(self) -> dict:
        return self.last_result

    def set_last_result(self, result: dict) -> None:
        self.last_result = result


# ── Store access ──────────────────────────────────────────────────────────
# A single process-wide instance, lazily seeded on first use. This is the
# one place a future SQLite-backed store would plug in: swap what
# get_store() returns/constructs, and every api/ route (which only ever
# receives a store via this function) keeps working unchanged.
_default_store: Optional[InMemoryStore] = None


def get_store() -> InMemoryStore:
    global _default_store
    if _default_store is None:
        from data.seed import build_default_store
        _default_store = build_default_store()
    return _default_store
