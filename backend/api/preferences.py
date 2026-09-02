"""Student time-slot preference submission (product decision #10).

Not admin-managed — a student submits their own preferences here (no
real auth in this local prototype; see product decision #14). Validation
follows the "warn, don't silently accept useless data" rule: a payload
can be rejected outright if it's degenerate enough to make scheduling
nearly impossible (e.g. almost the whole week blocked), or accepted with
warnings if it's merely uninformative (e.g. everything rated the same).
"""
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from data.store import InMemoryStore, get_store
from domain.validation import validate_time_slot_preferences

router = APIRouter(prefix="/students/{roll_number}/time-preferences")


class TimePreferencesPayload(BaseModel):
    ratings: Dict[str, int]  # slot_key -> rating, see domain.enums.PreferenceRating


def _require_student(roll_number: str, store: InMemoryStore) -> None:
    if store.get_student(roll_number) is None:
        raise HTTPException(status_code=404, detail="Student not found")


@router.get("")
def get_time_preferences(roll_number: str, store: InMemoryStore = Depends(get_store)):
    _require_student(roll_number, store)
    saved = store.get_time_preferences(roll_number)
    return [
        {
            "slot_key": slot.key,
            "day": slot.day,
            "slot_index": slot.slot_index,
            "start_time": slot.start_time,
            "end_time": slot.end_time,
            "rating": saved.get(slot.key),
        }
        for slot in store.list_ratable_time_slots()
    ]


@router.put("")
def save_time_preferences(
    roll_number: str, payload: TimePreferencesPayload, store: InMemoryStore = Depends(get_store)
):
    _require_student(roll_number, store)

    ratable_keys = {slot.key for slot in store.list_ratable_time_slots()}
    result = validate_time_slot_preferences(payload.ratings, ratable_keys)
    if not result.is_valid:
        raise HTTPException(status_code=400, detail={"errors": result.errors})

    store.set_time_preferences(roll_number, payload.ratings)
    return {"status": "saved", "warnings": result.warnings}
