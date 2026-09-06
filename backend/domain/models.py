"""Core domain entities for the department timetable system.

These are persistence-agnostic dataclasses: they know nothing about how
they are stored (an in-memory store today, a real DB later) or how they
are serialized over HTTP (that's the api/ layer's job).

Department-only scope (product decision #1): Student and Teacher
deliberately have NO department/branch field — one running instance of
this app already corresponds to exactly one department.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from domain.enums import RunStatus, SubjectType


@dataclass
class Subject:
    """One subject taught in a given semester.

    subject_tag is mandatory and is a free-form string (program_core, mdm,
    open_elective, professional_elective, lab, ...). The admin decides,
    per run, which tags are choice-based — see ChoiceTagConfig.

    slot_structure / linked_pattern describe how a theory subject's
    weekly_hours are split into linked meetings (e.g. a 4-hour subject
    taught as two linked 2-hour blocks). Labs do not use linked meeting
    patterns the same way (product decision #6) — each lab section is
    simply a standalone repeated practical section.
    """
    subject_code: str
    subject_name: str
    subject_tag: str
    semester: int
    type: SubjectType
    weekly_hours: int
    capacity: int
    subtag: Optional[str] = None
    slot_structure: Optional[str] = None
    linked_pattern: Optional[List[str]] = None


@dataclass
class Teacher:
    """A teacher. No department field, no preferred-slot selections in
    this initial version (product decision #8)."""
    teacher_id: str
    teacher_name: str


@dataclass
class TeacherSubjectCapability:
    """One row of the teacher-subject capability relationship produced by
    parsing the teacher CSV (product decision #8): teacher_id is capable
    of teaching subject_code."""
    teacher_id: str
    subject_code: str


@dataclass
class TeacherAvailability:
    """Admin-managed hard constraint (product decision #9): whether
    teacher_id can be scheduled in the slot identified by slot_key.
    This is never a soft preference — the solver must treat `available =
    False` as forbidden, not merely undesirable."""
    teacher_id: str
    slot_key: str
    available: bool = True


@dataclass
class Student:
    """A student. No department/branch field (product decision #1)."""
    roll_number: str
    name: str
    semester: int


@dataclass
class CycleChoiceConfig:
    """Department-level configuration for a subject tag in the current cycle."""
    tag: str
    is_choice_based: bool = True


@dataclass
class ChoiceTagConfig:
    """Legacy run-scoped mapping kept for compatibility."""
    tag: str
    numeric_value: int = 1
    is_choice_based: bool = True


@dataclass
class StudentChoiceSelection:
    """One (tag -> subtag) choice selection locked in by a student."""
    roll_number: str
    tag: str
    subtag: str


@dataclass
class Meeting:
    """One weekly occurrence of a section, referencing a canonical
    TimeSlot.key (see domain/timeslots.py) rather than a free-form day/time
    string.

    For 3-hour subjects:
      - one 2-hour meeting: duration_hours=2, slot_part=None
      - one 1-hour remainder: duration_hours=1, slot_part=1 (first hour) or 2 (second hour)
    """
    slot_key: str
    duration_hours: int = 2
    slot_part: Optional[int] = None


@dataclass
class Section:
    """One taught section of a subject (a concrete group of students +
    teacher + meeting time(s)). Theory sections may carry more than one
    Meeting to represent a linked pattern (product decision #6); lab
    sections are typically single-meeting, parallel, repeated sections.

    run_id links the section to the GenerationRun it was produced for,
    so sections can be cleared/regenerated per run without affecting
    sections from other runs.
    """
    id: Optional[int]
    subject_code: str
    label: str
    teacher_id: Optional[str]
    capacity: int
    meetings: List[Meeting] = field(default_factory=list)
    run_id: Optional[int] = None


@dataclass
class GenerationRun:
    """One department-scoped solver run covering all active semesters together."""
    id: int
    semesters: List[int] = field(default_factory=list)
    status: RunStatus = RunStatus.DRAFT
    choice_tag_configs: List[ChoiceTagConfig] = field(default_factory=list)

    def __init__(
        self,
        id: int,
        semesters: Optional[List[int]] = None,
        status: RunStatus = RunStatus.DRAFT,
        choice_tag_configs: Optional[List[ChoiceTagConfig]] = None,
        semester: Optional[int] = None,
    ):
        self.id = id
        if semesters is not None:
            self.semesters = list(semesters)
        elif semester is not None:
            self.semesters = [semester]
        else:
            self.semesters = []
        self.status = status
        self.choice_tag_configs = choice_tag_configs or []

    @property
    def semester(self) -> int:
        """Compatibility property for code expecting a single semester."""
        return self.semesters[0] if self.semesters else 0

    @semester.setter
    def semester(self, val: int) -> None:
        if self.semesters:
            self.semesters[0] = val
        else:
            self.semesters = [val]
