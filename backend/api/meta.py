"""Read-only structural metadata: the canonical time-slot grid and the
valid semester list. Both are fixed, department-wide constants (see
domain/timeslots.py and domain/enums.py), not per-run data.

Subject/student/teacher CSV import, choice-tag configuration, preference
submission, and solver endpoints are added in later phases as those data
flows land — see backend/PROGRESS.md for the phase plan.
"""
from fastapi import APIRouter, Depends

from data.store import InMemoryStore, get_store
from domain.enums import EVEN_SEMESTERS, ODD_SEMESTERS, VALID_SEMESTERS

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/timeslots")
def get_timeslots(store: InMemoryStore = Depends(get_store)):
    """The fixed Mon-Fri x 4-slot department grid — identical for every
    run regardless of semester."""
    return [
        {
            "key": slot.key,
            "day": slot.day,
            "slot_index": slot.slot_index,
            "start_time": slot.start_time,
            "end_time": slot.end_time,
            "allowed_types": [t.value for t in slot.allowed_types],
        }
        for slot in store.list_time_slots()
    ]


@router.get("/semesters")
def get_semesters():
    return {
        "odd": list(ODD_SEMESTERS),
        "even": list(EVEN_SEMESTERS),
        "valid": list(VALID_SEMESTERS),
    }
