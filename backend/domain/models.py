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
class ChoiceTagConfig:
    """Run-scoped mapping from a numeric choice value to a subject_tag.

    Only tags with is_choice_based=True participate in the student choice
    columns (choice_1, choice_2, ...) for THIS run. There is no fixed
    limit on how many tags are active at once (product decision #3), and
    this mapping is only meaningful for the run it belongs to.
    """
    tag: str
    numeric_value: int
    is_choice_based: bool = True


@dataclass
class StudentChoiceSelection:
    """One (choice_column -> numeric_value) entry parsed from a student's
    CSV row, e.g. choice_1=2 means "this student's 1st choice column
    holds numeric value 2". Resolving that numeric value to a subject_tag
    requires the run's ChoiceTagConfig list."""
    roll_number: str
    choice_column: int  # 1-based position: choice_1, choice_2, ...
    numeric_value: int


@dataclass
class Meeting:
    """One weekly occurrence of a section, referencing a canonical
    TimeSlot.key (see domain/timeslots.py) rather than a free-form day/time
    string."""
    slot_key: str


@dataclass
class Section:
    """One taught section of a subject (a concrete group of students +
    teacher + meeting time(s)). Theory sections may carry more than one
    Meeting to represent a linked pattern (product decision #6); lab
    sections are typically single-meeting, parallel, repeated sections."""
    id: Optional[int]
    subject_code: str
    label: str
    teacher_id: Optional[str]
    capacity: int
    meetings: List[Meeting] = field(default_factory=list)


@dataclass
class GenerationRun:
    """One semester-scoped solver run (product decision #2 and #3): the
    choice-tag configuration below is only valid for this run."""
    id: int
    semester: int
    status: RunStatus = RunStatus.DRAFT
    choice_tag_configs: List[ChoiceTagConfig] = field(default_factory=list)
