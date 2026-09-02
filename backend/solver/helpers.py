"""Pure helper functions shared by the solver engine and heuristics.

None of these mutate state or touch the data store directly — they only
read a Section and a student's preference maps. Keeping them pure and
store-agnostic makes them trivial to unit test and reuse across engine.py,
heuristics.py, and (previously) the CP-SAT objective construction.
"""
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from domain.models import Section

PERIODS = ["9:00", "11:00", "14:00", "16:00"]  # 4 canonical periods per day

# Times that don't exactly match a canonical period map to the nearest one
# (e.g. a slot at 10:00 is treated as the same rated period as 9:00).
TIME_REMAP = {
    "10:00": "9:00",
    "12:00": "11:00",
    "15:00": "14:00",
}

# Shared 1=Preferred / 2=Tolerable / 3=Disliked rating scale for BOTH the
# time-slot dimension and the faculty dimension. Rating 4 (time only) means
# blocked/pruned and is handled separately by slot_blocked(), never scored.
PENALTY = {1: 0, 2: 1, 3: 3}


def ts_key_for(day: str, time: str) -> str:
    """Canonical time-slot key for a raw (day, time) pair, e.g. 'Mon|9:00'."""
    t = TIME_REMAP.get(time, time)
    return f"{day}|{t}"


def slot_time_keys(section: Section) -> List[str]:
    """Canonical time-slot key for EVERY meeting of a section. A multi-
    meeting section (e.g. a Mon + Wed lecture) yields one key per meeting."""
    return [ts_key_for(m.day, m.time) for m in section.meetings]


def slot_blocked(section: Section, ts_prefs: Dict[str, int]) -> bool:
    """A section is blocked for a student if ANY of its meetings falls in a
    period the student rated 4 (cannot attend). Missing ratings default to
    1 (indifferent/preferred), never to blocked."""
    return any(ts_prefs.get(k, 1) == 4 for k in slot_time_keys(section))


def slot_time_penalty(section: Section, ts_prefs: Dict[str, int]) -> int:
    """Sum of time-preference penalty across every meeting of a section —
    a twice-weekly lecture in a disliked period costs the student twice."""
    return sum(PENALTY.get(ts_prefs.get(k, 1), 0) for k in slot_time_keys(section))


def slot_faculty_penalty(
    section: Section, faculty_prefs: Dict[str, Dict[int, int]], faculty_weight: int
) -> Tuple[int, int]:
    """Returns (faculty_rating, weighted_penalty) for a section.
    faculty_prefs is keyed subject-first: {subject_code: {teacher_id: rating}}.
    Missing ratings default to 1 (indifferent), matching the time-slot
    default — a student who never rates a subject's faculty pays no penalty."""
    subj_prefs = faculty_prefs.get(section.subject_code, {})
    rating = subj_prefs.get(section.teacher_id, 1)
    return rating, faculty_weight * PENALTY.get(rating, 0)


def gap_count(daytimes: Iterable[Tuple[str, str]]) -> int:
    """Count idle canonical periods strictly between a student's first and
    last class on each day, summed across the week."""
    by_day = defaultdict(set)
    for day, time in daytimes:
        t = TIME_REMAP.get(time, time)
        if t in PERIODS:
            by_day[day].add(PERIODS.index(t))
    total = 0
    for idxs in by_day.values():
        if len(idxs) > 1:
            total += (max(idxs) - min(idxs) + 1) - len(idxs)
    return total
