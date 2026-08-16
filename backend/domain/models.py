"""Core domain entities for PWSSAP.

These are persistence-agnostic dataclasses: they know nothing about how
they are stored (an in-memory dict today, SQLite later) or how they are
serialized over HTTP (that's the api/ layer's job — see api/catalog.py).
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Teacher:
    id: int
    name: str
    department: Optional[str] = None


@dataclass
class Subject:
    code: str
    name: str
    department: Optional[str] = None
    year: Optional[int] = None


@dataclass
class Student:
    id: int
    name: str
    roll: str
    department: Optional[str] = None
    year: Optional[int] = None


@dataclass
class Meeting:
    """One weekly occurrence of a section, e.g. Mon 9:00."""
    day: str
    time: str


@dataclass
class Section:
    """One taught section of a subject, e.g. 'IT301 Sec A'.

    This is the concrete, teacher-and-time-assigned timetable data. It must
    stay hidden from students until after the solver runs — students only
    ever see the abstract TimeSlot grid below and (post-solve) their own
    resulting assignment. Access control enforcing that hiding is added in
    Milestone 2; this model just makes the concrete/abstract split explicit.
    """
    id: int
    subject_code: str
    label: str
    teacher_id: int
    room: str
    capacity: int
    meetings: List[Meeting] = field(default_factory=list)


@dataclass
class TimeSlot:
    """One cell of the abstract 6-day x 4-period grid students rate.

    Intentionally decoupled from any real Section so a student rating this
    grid cannot infer which subject or teacher occupies a given period.
    """
    key: str
    day: str
    time: str
    label: str
