"""The canonical weekly time-slot grid.

Fixed structural rules (product decision #4), the same for every run
regardless of semester or subject:

- Working days are Monday-Friday only.
- There are 4 lecture slots per day (09:00-11:00, 11:15-13:15,
  13:45-15:45, 15:45-17:45).
- Monday 09:00-11:00 is not used for theory or lab at all.
- Slot 4 (15:45-17:45) is lab-only; theory is never scheduled there.

This grid is generated once and shared read-only by every part of the
system (student preference forms, teacher availability, section
generation, the solver). Nothing here is per-run or per-semester data.
"""
from dataclasses import dataclass
from typing import Tuple

from domain.enums import SubjectType, WORKING_DAYS

# (slot_index, start_time, end_time)
SLOT_TIMES = (
    (1, "09:00", "11:00"),
    (2, "11:15", "13:15"),
    (3, "13:45", "15:45"),
    (4, "15:45", "17:45"),
)


@dataclass(frozen=True)
class TimeSlot:
    key: str                       # e.g. "Mon-1"
    day: str                       # one of domain.enums.WORKING_DAYS
    slot_index: int                # 1-4
    start_time: str
    end_time: str
    allowed_types: Tuple[SubjectType, ...]  # empty => not usable by any subject


def _allowed_types_for(day: str, slot_index: int) -> Tuple[SubjectType, ...]:
    if day == "Mon" and slot_index == 1:
        return tuple()  # blocked entirely for theory or lab
    if slot_index == 4:
        return (SubjectType.LAB,)  # theory is never allowed here
    return (SubjectType.THEORY, SubjectType.LAB)


def build_canonical_grid():
    """Build the fixed Mon-Fri x 4-slot grid. Pure function, no I/O."""
    grid = []
    for day in WORKING_DAYS:
        for slot_index, start, end in SLOT_TIMES:
            grid.append(TimeSlot(
                key=f"{day}-{slot_index}",
                day=day,
                slot_index=slot_index,
                start_time=start,
                end_time=end,
                allowed_types=_allowed_types_for(day, slot_index),
            ))
    return grid


def is_slot_usable(slot: TimeSlot) -> bool:
    return len(slot.allowed_types) > 0


def slot_allows(slot: TimeSlot, subject_type: SubjectType) -> bool:
    return subject_type in slot.allowed_types
