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
from typing import Dict, List, Optional, Tuple

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
        # roll_number -> subject_code -> teacher_id -> rating (1-3, no
        # Blocked -- faculty preference is secondary/soft, never a hard
        # constraint; see domain.validation.FACULTY_RATING_VALUES).
        self.student_faculty_preferences: Dict[str, Dict[str, Dict[str, int]]] = {}

        self.sections: Dict[int, Section] = {}
        self._next_section_id: int = 0

        self.runs: Dict[int, GenerationRun] = {}
        self._next_run_id: int = 0

        # roll_number -> {subject_code -> section_id}.
        # Populated by solver/service.py after solving; refined by Phase 10
        # admin override endpoints (enroll_student / unenroll_student).
        self.student_section_assignments: Dict[str, Dict[str, int]] = {}

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

    def rankable_subjects_for_semester(self, semester: Optional[int] = None) -> List[Tuple[str, List[str]]]:
        """(subject_code, [teacher_id, ...]) pairs for subjects with 2+
        eligible teachers, optionally scoped to one semester -- a subject
        taught by only one teacher has nothing to rank (product decision
        #11), so it's excluded here rather than left for callers to filter."""
        result = []
        for subject in self.list_subjects(semester):
            teacher_ids = self.teachers_for_subject(subject.subject_code)
            if len(teacher_ids) >= 2:
                result.append((subject.subject_code, teacher_ids))
        return result

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
        self.student_faculty_preferences.pop(roll_number, None)

    # ── Student time-slot preferences ────────────────────────────────────
    def get_time_preferences(self, roll_number: str) -> Dict[str, int]:
        return dict(self.student_time_preferences.get(roll_number, {}))

    def set_time_preferences(self, roll_number: str, ratings: Dict[str, int]) -> None:
        self.student_time_preferences[roll_number] = dict(ratings)

    # ── Student faculty preferences (secondary, soft -- product decision #11) ──
    def get_faculty_preferences(self, roll_number: str) -> Dict[str, Dict[str, int]]:
        return {
            code: dict(ratings)
            for code, ratings in self.student_faculty_preferences.get(roll_number, {}).items()
        }

    def set_faculty_preferences(self, roll_number: str, preferences: Dict[str, Dict[str, int]]) -> None:
        self.student_faculty_preferences[roll_number] = {
            code: dict(ratings) for code, ratings in preferences.items()
        }

    # ── Student choice selections (per-run) ─────────────────────────────────
    def set_student_choice_selections(
        self, roll_number: str, selections: List[StudentChoiceSelection]
    ) -> None:
        self.student_choice_selections[roll_number] = selections

    def get_student_choice_selections(self, roll_number: str) -> List[StudentChoiceSelection]:
        return list(self.student_choice_selections.get(roll_number, []))

    # ── Sections (concrete teacher/time timetable data) ─────────────────────
    def list_sections(
        self,
        subject_code: Optional[str] = None,
        run_id: Optional[int] = None,
    ) -> List[Section]:
        sections = list(self.sections.values())
        if subject_code is not None:
            sections = [s for s in sections if s.subject_code == subject_code]
        if run_id is not None:
            sections = [s for s in sections if s.run_id == run_id]
        return sections

    def list_sections_for_run(self, run_id: int) -> List[Section]:
        """All sections produced for a specific generation run."""
        return [s for s in self.sections.values() if s.run_id == run_id]

    def clear_sections_for_run(self, run_id: int) -> int:
        """Remove every section belonging to run_id.  Returns the count of
        deleted sections, so the caller can log/report how many were cleared."""
        to_delete = [sid for sid, s in self.sections.items() if s.run_id == run_id]
        for sid in to_delete:
            del self.sections[sid]
        return len(to_delete)

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

    def enrolled_count_for_subject(
        self, subject_code: str, run_id: int
    ) -> int:
        """Count how many students in the run's semester are enrolled in
        subject_code for Phase 8 lab-parallelism calculation.

        Enrollment logic (Phase 8 approximation):
        - For choice-based subjects: count students whose choice selections
          for this run map to the subject's tag.
        - For non-choice subjects: count all students in the run's semester
          (every student takes non-choice subjects).
        - If the subject or run doesn't exist, returns 0.

        Phase 10 (manual overrides) can refine actual enrollment later.
        """
        run = self.get_run(run_id)
        subject = self.get_subject(subject_code)
        if run is None or subject is None:
            return 0

        # Build the set of numeric values that map to this subject's tag.
        choice_numeric_values = {
            c.numeric_value
            for c in run.choice_tag_configs
            if c.tag == subject.subject_tag and c.is_choice_based
        }

        semester_students = self.list_students(semester=run.semester)

        if not choice_numeric_values:
            # Non-choice-based subject: all semester students are enrolled.
            return len(semester_students)

        # Choice-based: count students who selected this subject's tag.
        count = 0
        for student in semester_students:
            selections = self.get_student_choice_selections(student.roll_number)
            if any(sel.numeric_value in choice_numeric_values for sel in selections):
                count += 1
        return count

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

    # ── Student-section enrollment (Phase 10) ─────────────────────────────

    def get_student_sections(self, roll_number: str) -> Dict[str, int]:
        """subject_code -> section_id mapping for one student.

        Returns an empty dict if the student has no assignments yet (solver
        has not run, or student was added post-solving)."""
        return dict(self.student_section_assignments.get(roll_number, {}))

    def enroll_student(
        self, roll_number: str, subject_code: str, section_id: int
    ) -> None:
        """Assign a student to a section for one subject.

        Replaces any prior assignment for the same subject (one section
        per student per subject at a time)."""
        self.student_section_assignments.setdefault(roll_number, {})[subject_code] = section_id

    def unenroll_student(self, roll_number: str, subject_code: str) -> bool:
        """Remove a student's section assignment for a subject.

        Returns True if an assignment existed and was removed, False otherwise."""
        sub_map = self.student_section_assignments.get(roll_number, {})
        if subject_code in sub_map:
            del sub_map[subject_code]
            return True
        return False

    def enrolled_students_for_section(self, section_id: int) -> List[str]:
        """Roll numbers of all students currently enrolled in section_id."""
        return [
            roll
            for roll, sub_map in self.student_section_assignments.items()
            if section_id in sub_map.values()
        ]

    def current_enrollment_count(self, section_id: int) -> int:
        """Current enrolled headcount for a section."""
        return sum(
            1 for sub_map in self.student_section_assignments.values()
            if section_id in sub_map.values()
        )

    def slot_keys_for_student(self, roll_number: str) -> List[str]:
        """Slot keys occupied by every section the student is enrolled in.

        Used for student-level conflict detection: if the admin moves a
        student into a section meeting at a slot already occupied by another
        of their sections, we warn (but still allow the override)."""
        occupied: List[str] = []
        for section_id in self.get_student_sections(roll_number).values():
            section = self.get_section(section_id)
            if section:
                occupied.extend(m.slot_key for m in section.meetings if m.slot_key)
        return occupied

    def slot_keys_for_teacher(
        self, teacher_id: str, exclude_section_id: Optional[int] = None
    ) -> List[str]:
        """Slot keys occupied by every section the teacher is assigned to.

        Used for teacher double-booking detection when the admin reassigns
        a teacher post-publication.  Pass exclude_section_id to omit the
        section currently being reassigned (otherwise the teacher's current
        slot would always clash with itself)."""
        occupied: List[str] = []
        for section in self.sections.values():
            if section.teacher_id == teacher_id and section.id != exclude_section_id:
                occupied.extend(m.slot_key for m in section.meetings if m.slot_key)
        return occupied


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
