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
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

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
        self._next_section_id: int = 1

        self.runs: Dict[int, GenerationRun] = {}
        self._next_run_id: int = 1

        # Cycle-level elective configuration: tag -> is_choice_based bool.
        self.cycle_choice_configs: Dict[str, bool] = {}

        # roll_number -> {subject_code -> section_id}.
        # Populated by solver/service.py after solving; refined by Phase 10
        # admin override endpoints (enroll_student / unenroll_student).
        self.student_section_assignments: Dict[str, Dict[str, int]] = {}

        # Cached solve result payloads per run_id for UI state persistence
        self.latest_solve_results: Dict[int, Dict] = {}
        # Set of run_ids for which cancellation has been requested
        self.cancel_requested_runs: set = set()

        # Traditional Division & Batch mode state. Owned by domain/cohorts.py and
        # domain/traditional_*.py; the store only holds it.
        #   cohort_configs:    semester -> SemesterCohortConfig (saved divisions/batches)
        #   traditional_plans: run_id -> TraditionalPlan (pins, sync groups, batch map)
        self.cohort_configs: Dict[int, Any] = {}
        self.traditional_plans: Dict[int, Any] = {}
        self.active_run_id: Optional[int] = None
        # At most one solve (or feasibility check) may run at a time: the
        # store is a single shared timetable and the solver is CPU-bound.
        self._solve_lock = threading.Lock()
        self._active_solve: Optional[Dict] = None

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

    def clear_subjects(self) -> int:
        """Clear the catalog and dependent generated scheduling state.

        Teachers and students remain available for the replacement catalog,
        but old capabilities, sections, runs, choices, and assignments would
        otherwise refer to subjects that no longer exist.
        """
        count = len(self.subjects)
        self.subjects.clear()
        self.teacher_capabilities.clear()
        self.sections.clear()
        self.runs.clear()
        self.student_choice_selections.clear()
        self.student_faculty_preferences.clear()
        self.student_section_assignments.clear()
        self.cycle_choice_configs.clear()
        self.traditional_plans.clear()
        self._next_section_id = 1
        self._next_run_id = 1
        return count

    def list_subject_tags(self, semester: Optional[int] = None) -> List[str]:
        """Distinct subject_tag values currently in the catalog, optionally
        scoped to one semester. Used by the admin choice-tag configuration
        UI (product decision #3) to show which tags exist to choose from."""
        return sorted({s.subject_tag for s in self.list_subjects(semester)})

    def get_choice_groups(self, semester: Optional[int] = None) -> Dict[str, List[str]]:
        """Returns {tag: [subtag1, subtag2, ...]} for tags in the catalog that define subtags."""
        result: Dict[str, set] = {}
        for s in self.list_subjects(semester):
            for subtag in s.supported_subtags:
                result.setdefault(s.subject_tag, set()).add(subtag)
        return {tag: sorted(list(subtags)) for tag, subtags in sorted(result.items())}

    # ── Cycle Choice Configs (department-level) ───────────────────────────
    def set_cycle_choice_configs(self, configs: Dict[str, bool]) -> None:
        self.cycle_choice_configs = dict(configs)

    def get_cycle_choice_configs(self) -> Dict[str, bool]:
        return dict(self.cycle_choice_configs)

    def get_choice_based_tags(self) -> set:
        if self.cycle_choice_configs:
            return {tag for tag, is_cb in self.cycle_choice_configs.items() if is_cb}
        return {tag for tag, subtags in self.get_choice_groups().items() if subtags and tag.upper() != "CORE"}

    def get_choice_based_tags_for_semester(self, semester: int) -> set:
        """Return configured choice tags that have subtags in this semester."""
        configured = self.get_choice_based_tags()
        groups = self.get_choice_groups(semester)
        return {tag for tag in configured if groups.get(tag)}

    # ── Teachers ───────────────────────────────────────────────────────────
    def list_teachers(self) -> List[Teacher]:
        return list(self.teachers.values())

    def get_teacher(self, teacher_id: str) -> Optional[Teacher]:
        return self.teachers.get(teacher_id)

    def upsert_teacher(self, teacher: Teacher) -> Teacher:
        self.teachers[teacher.teacher_id] = teacher
        return teacher

    def add_teacher_capability(
        self, teacher_id: str, subject_code: str, maximum_weekly_hours: Optional[int] = None
    ) -> None:
        existing = next(
            (c for c in self.teacher_capabilities
             if c.teacher_id == teacher_id and c.subject_code == subject_code),
            None,
        )
        if existing is not None:
            existing.maximum_weekly_hours = maximum_weekly_hours
            return
        self.teacher_capabilities.append(
            TeacherSubjectCapability(teacher_id, subject_code, maximum_weekly_hours)
        )

    def replace_teacher_capabilities(
        self, teacher_id: str, subject_loads: Dict[str, Optional[int]]
    ) -> None:
        self.teacher_capabilities = [
            capability for capability in self.teacher_capabilities
            if capability.teacher_id != teacher_id
        ]
        for subject_code, maximum in subject_loads.items():
            self.add_teacher_capability(teacher_id, subject_code, maximum)

    def teacher_subject_load(self, teacher_id: str, subject_code: str) -> Optional[int]:
        for capability in self.teacher_capabilities:
            if capability.teacher_id == teacher_id and capability.subject_code == subject_code:
                return capability.maximum_weekly_hours
        return None

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

    def clear_students(self) -> int:
        """Clear students and invalidate schedules built from the roster."""
        count = len(self.students)
        self.students.clear()
        self.student_choice_selections.clear()
        self.student_time_preferences.clear()
        self.student_faculty_preferences.clear()
        self.student_section_assignments.clear()
        self.cohort_configs.clear()
        self.traditional_plans.clear()
        self.sections.clear()
        self.runs.clear()
        self._next_section_id = 1
        self._next_run_id = 1
        return count

    def clear_teachers(self) -> int:
        """Clear teachers and invalidate schedules using teacher assignments."""
        count = len(self.teachers)
        self.teachers.clear()
        self.teacher_capabilities.clear()
        self.teacher_availability.clear()
        self.sections.clear()
        self.runs.clear()
        self.student_section_assignments.clear()
        self._next_section_id = 1
        self._next_run_id = 1
        return count

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

    # ── Student choice selections & lock-in ─────────────────────────────────
    def set_student_choice_selections(
        self, roll_number: str, selections: List[StudentChoiceSelection]
    ) -> None:
        self.student_choice_selections[roll_number] = list(selections)

    def get_student_choice_selections(self, roll_number: str) -> List[StudentChoiceSelection]:
        return list(self.student_choice_selections.get(roll_number, []))

    def get_lock_in_for_student(self, roll_number: str) -> Dict[str, str]:
        """Returns {tag: subtag} mapping for this student's elective choices."""
        selections = self.get_student_choice_selections(roll_number)
        return {s.tag: s.subtag for s in selections}

    def has_complete_lock_in(self, roll_number: str) -> bool:
        """True if the student has selected a subtag for all choice-based tags in their semester."""
        student = self.get_student(roll_number)
        if not student:
            return False
        cb_tags = self.get_choice_based_tags_for_semester(student.semester)
        sem_subjects = self.list_subjects(semester=student.semester)
        applicable_tags = {s.subject_tag for s in sem_subjects if s.subject_tag in cb_tags}
        if not applicable_tags:
            return True  # No electives required for this semester
        lock_in = self.get_lock_in_for_student(roll_number)
        return all(tag in lock_in and bool(str(lock_in[tag]).strip()) for tag in applicable_tags)

    def get_enrolled_subjects_for_student(self, roll_number: str) -> List[Subject]:
        """List of subjects the student is enrolled in for this cycle.

        - Non-choice subjects: all subjects in student's semester.
        - Choice-based subjects: only those whose subtag matches student's locked-in subtag.
        """
        student = self.get_student(roll_number)
        if not student:
            return []
        cb_tags = self.get_choice_based_tags_for_semester(student.semester)
        sem_subjects = self.list_subjects(semester=student.semester)
        lock_in = self.get_lock_in_for_student(roll_number)
        enrolled: List[Subject] = []
        for s in sem_subjects:
            if s.subject_tag not in cb_tags:
                enrolled.append(s)
            else:
                chosen_subtag = lock_in.get(s.subject_tag)
                if chosen_subtag and s.supports_subtag(chosen_subtag):
                    enrolled.append(s)
        return enrolled

    def rankable_subjects_for_student(self, roll_number: str) -> List[Tuple[str, List[str]]]:
        """(subject_code, [teacher_id, ...]) pairs for student's ENROLLED subjects
        with 2+ eligible teachers."""
        enrolled = self.get_enrolled_subjects_for_student(roll_number)
        result = []
        for subject in enrolled:
            teacher_ids = self.teachers_for_subject(subject.subject_code)
            if len(teacher_ids) >= 2:
                result.append((subject.subject_code, teacher_ids))
        return result

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
        deleted sections, so the caller can log/report how many were cleared.

        Student assignments that pointed at a deleted section are removed too;
        otherwise they would dangle (or, worse, silently attach to an
        unrelated section that later reuses the same id)."""
        to_delete = [sid for sid, s in self.sections.items() if s.run_id == run_id]
        for sid in to_delete:
            del self.sections[sid]
        if to_delete:
            gone = set(to_delete)
            for roll in list(self.student_section_assignments):
                sub_map = self.student_section_assignments[roll]
                for code in [c for c, sid in sub_map.items() if sid in gone]:
                    del sub_map[code]
                if not sub_map:
                    del self.student_section_assignments[roll]
        return len(to_delete)

    # ── Solve concurrency guard ────────────────────────────────────────────
    def try_begin_solve(self, run_id: int, kind: str) -> bool:
        """Claim the single solve slot. Returns False if one is already running."""
        with self._solve_lock:
            if self._active_solve is not None:
                return False
            self._active_solve = {"run_id": run_id, "kind": kind, "started_at": time.time()}
            return True

    def end_solve(self, run_id: int) -> None:
        with self._solve_lock:
            if self._active_solve and self._active_solve["run_id"] == run_id:
                self._active_solve = None

    def get_active_solve(self) -> Optional[Dict]:
        with self._solve_lock:
            return dict(self._active_solve) if self._active_solve else None

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
        self, subject_code: str, run_id: Optional[int] = None
    ) -> int:
        """Count how many students are enrolled in subject_code.

        - Non-choice subjects: all students in that subject's semester.
        - Choice subjects: students whose locked-in subtag matches subject.subtag.
        """
        subject = self.get_subject(subject_code)
        if subject is None:
            return 0

        cb_tags = self.get_choice_based_tags_for_semester(subject.semester)
        semester_students = self.list_students(semester=subject.semester)

        if subject.subject_tag not in cb_tags:
            return len(semester_students)

        # Choice-based: count students whose lock-in matches this subject's subtag
        count = 0
        for student in semester_students:
            lock_in = self.get_lock_in_for_student(student.roll_number)
            if subject.supports_subtag(lock_in.get(subject.subject_tag, "")):
                count += 1
        return count

    # ── Generation runs (department-scoped cycle) ──────────────────────────
    def create_run(
        self,
        semesters: Optional[List[int]] = None,
        semester: Optional[int] = None,
    ) -> GenerationRun:
        if semesters is not None:
            if isinstance(semesters, int):
                sem_list = [semesters]
            else:
                sem_list = list(semesters)
        elif semester is not None:
            sem_list = [semester]
        else:
            sem_list = sorted({s.semester for s in self.subjects.values()})
        run = GenerationRun(id=self._next_run_id, semesters=sem_list)
        self.runs[run.id] = run
        self._next_run_id += 1
        return run

    def get_run(self, run_id: int) -> Optional[GenerationRun]:
        return self.runs.get(run_id)

    def list_runs(self, semester: Optional[int] = None) -> List[GenerationRun]:
        runs = list(self.runs.values())
        if semester is not None:
            runs = [r for r in runs if semester in r.semesters]
        return runs

    def set_run_choice_tags(self, run_id: int, configs: List[ChoiceTagConfig]) -> GenerationRun:
        """Legacy method kept for backward compatibility."""
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
