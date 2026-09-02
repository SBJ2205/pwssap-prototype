"""Admin-managed hard constraint: which slots each teacher can be
scheduled in (product decision #9).

This is explicitly NOT a soft preference and NOT teacher-submitted — the
admin marks yes/no per teacher per slot, and the solver (Phase 9) must
treat available=False as forbidden, never merely undesirable. Slots
default to available=True until the admin explicitly blocks one (see
InMemoryStore.is_teacher_available), so the admin only has to click the
exceptions rather than opt every cell in first.
"""
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from domain.validation import validate_slot_keys

router = APIRouter(
    prefix="/admin/teachers/{teacher_id}/availability",
    dependencies=[Depends(require_admin)],
)


class AvailabilityUpdatePayload(BaseModel):
    slots: Dict[str, bool]  # slot_key -> available


def _require_teacher(teacher_id: str, store: InMemoryStore) -> None:
    if store.get_teacher(teacher_id) is None:
        raise HTTPException(status_code=404, detail="Teacher not found")


def _availability_grid(teacher_id: str, store: InMemoryStore) -> list:
    overrides = store.get_teacher_availability(teacher_id)
    return [
        {
            "slot_key": slot.key,
            "day": slot.day,
            "slot_index": slot.slot_index,
            "start_time": slot.start_time,
            "end_time": slot.end_time,
            "available": overrides.get(slot.key, True),
        }
        for slot in store.list_time_slots()
    ]


@router.get("")
def get_availability(teacher_id: str, store: InMemoryStore = Depends(get_store)):
    _require_teacher(teacher_id, store)
    return _availability_grid(teacher_id, store)


@router.put("")
def update_availability(
    teacher_id: str, payload: AvailabilityUpdatePayload, store: InMemoryStore = Depends(get_store)
):
    """Bulk-set one or more slot_key -> available pairs in one call — a
    real admin UI submits a whole grid's worth of toggles at once, not
    one request per cell."""
    _require_teacher(teacher_id, store)

    valid_slot_keys = {slot.key for slot in store.list_time_slots()}
    errors = validate_slot_keys(payload.slots.keys(), valid_slot_keys)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    for slot_key, available in payload.slots.items():
        store.set_teacher_availability(teacher_id, slot_key, available)

    return _availability_grid(teacher_id, store)
