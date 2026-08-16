"""In-memory data store behind a small repository-style interface.

Everything the api/ and solver/ layers need lives behind this class, so the
underlying persistence can move to SQLite later without touching callers —
they only ever depend on InMemoryStore's method signatures, never on how
the data is actually held.
"""
from typing import Dict, List, Optional

from domain.models import Teacher, Subject, Student, Section, Meeting, TimeSlot


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

    def add_teacher(self, name: str, department: Optional[str] = None) -> Teacher:
        new_id = (max(self.teachers.keys()) + 1) if self.teachers else 0
        teacher = Teacher(id=new_id, name=name, department=department)
        self.teachers[new_id] = teacher
        return teacher

    def update_teacher(self, teacher_id: int, name: Optional[str] = None,
                        department: Optional[str] = None) -> Teacher:
        teacher = self.teachers[teacher_id]
        if name is not None:
            teacher.name = name
        if department is not None:
            teacher.department = department
        return teacher

    def delete_teacher(self, teacher_id: int) -> None:
        if any(s.teacher_id == teacher_id for s in self.sections.values()):
            raise ValueError("Cannot delete a teacher assigned to an existing section")
        del self.teachers[teacher_id]

    # ── Subjects ───────────────────────────────────────────────────────────
    def list_subjects(self) -> List[Subject]:
        return list(self.subjects.values())

    def get_subject(self, code: str) -> Subject:
        return self.subjects[code]

    def add_subject(self, code: str, name: str, department: Optional[str] = None,
                     year: Optional[int] = None) -> Subject:
        if code in self.subjects:
            raise ValueError(f"Subject {code} already exists")
        subject = Subject(code=code, name=name, department=department, year=year)
        self.subjects[code] = subject
        return subject

    def update_subject(self, code: str, name: Optional[str] = None,
                        department: Optional[str] = None, year: Optional[int] = None) -> Subject:
        subject = self.subjects[code]
        if name is not None:
            subject.name = name
        if department is not None:
            subject.department = department
        if year is not None:
            subject.year = year
        return subject

    def delete_subject(self, code: str) -> None:
        if self.sections_for_subject(code):
            raise ValueError("Cannot delete a subject with existing sections")
        del self.subjects[code]

    # ── Students ───────────────────────────────────────────────────────────
    def list_students(self) -> List[Student]:
        return list(self.students.values())

    def get_student(self, student_id: int) -> Optional[Student]:
        return self.students.get(student_id)

    def add_student(self, name: str, roll: str, department: Optional[str] = None,
                     year: Optional[int] = None) -> Student:
        new_id = (max(self.students.keys()) + 1) if self.students else 0
        student = Student(id=new_id, name=name, roll=roll, department=department, year=year)
        self.students[new_id] = student
        return student

    def update_student(self, student_id: int, name: Optional[str] = None, roll: Optional[str] = None,
                        department: Optional[str] = None, year: Optional[int] = None) -> Student:
        student = self.students[student_id]
        if name is not None:
            student.name = name
        if roll is not None:
            student.roll = roll
        if department is not None:
            student.department = department
        if year is not None:
            student.year = year
        return student

    def delete_student(self, student_id: int) -> None:
        del self.students[student_id]
        self.student_ts_prefs.pop(student_id, None)
        self.student_faculty_prefs.pop(student_id, None)

    # ── Sections (hidden concrete timetable data) ─────────────────────────
    def list_sections(self) -> List[Section]:
        return list(self.sections.values())

    def sections_for_subject(self, subject_code: str) -> List[Section]:
        return [s for s in self.sections.values() if s.subject_code == subject_code]

    def get_section(self, section_id: int) -> Section:
        return self.sections[section_id]

    def add_section(self, subject_code: str, label: str, teacher_id: int, room: str,
                     capacity: int, meetings: List[Meeting]) -> Section:
        if subject_code not in self.subjects:
            raise ValueError(f"Unknown subject {subject_code}")
        if teacher_id not in self.teachers:
            raise ValueError(f"Unknown teacher {teacher_id}")
        new_id = (max(self.sections.keys()) + 1) if self.sections else 0
        section = Section(id=new_id, subject_code=subject_code, label=label, teacher_id=teacher_id,
                           room=room, capacity=capacity, meetings=meetings)
        self.sections[new_id] = section
        return section

    def update_section(self, section_id: int, subject_code: Optional[str] = None, label: Optional[str] = None,
                        teacher_id: Optional[int] = None, room: Optional[str] = None,
                        capacity: Optional[int] = None, meetings: Optional[List[Meeting]] = None) -> Section:
        section = self.sections[section_id]
        if subject_code is not None:
            if subject_code not in self.subjects:
                raise ValueError(f"Unknown subject {subject_code}")
            section.subject_code = subject_code
        if label is not None:
            section.label = label
        if teacher_id is not None:
            if teacher_id not in self.teachers:
                raise ValueError(f"Unknown teacher {teacher_id}")
            section.teacher_id = teacher_id
        if room is not None:
            section.room = room
        if capacity is not None:
            section.capacity = capacity
        if meetings is not None:
            section.meetings = meetings
        return section

    def delete_section(self, section_id: int) -> None:
        del self.sections[section_id]

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
