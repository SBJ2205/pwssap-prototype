"""Student preference submission: time-slot ratings and subject-scoped
faculty rankings. Missing ratings are read elsewhere (solver/helpers.py) as
defaulting to indifferent — this module just stores whatever was submitted.
"""
from typing import Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from data.store import InMemoryStore, get_store
from solver.helpers import slot_blocked

router = APIRouter()


@router.get("/prefs/{student_id}")
def get_prefs(student_id: int, store: InMemoryStore = Depends(get_store)):
    """Return the student's time-slot preferences as {day|time: rating}."""
    return store.get_ts_prefs(student_id)


class PrefsPayload(BaseModel):
    prefs: Dict[str, int]  # "Day|Time" -> rating


@router.post("/prefs/{student_id}")
def save_prefs(student_id: int, payload: PrefsPayload, store: InMemoryStore = Depends(get_store)):
    store.set_ts_prefs(student_id, payload.prefs)
    # Quick feasibility check: for each subject, at least one section must
    # survive block-pruning (no meeting rated 4).
    warnings = []
    for subject in store.list_subjects():
        sections = store.sections_for_subject(subject.code)
        available = [sec for sec in sections if not slot_blocked(sec, payload.prefs)]
        if not available:
            warnings.append(f"All slots for {subject.code} are blocked — assignment will be INFEASIBLE.")
    return {"status": "saved", "warnings": warnings}


@router.get("/faculty-prefs/{student_id}")
def get_faculty_prefs(student_id: int, store: InMemoryStore = Depends(get_store)):
    """Return the student's faculty preferences as {subject_code: {teacher_id: rating}}."""
    return store.get_faculty_prefs(student_id)


class FacultyPrefsPayload(BaseModel):
    prefs: Dict[str, Dict[int, int]]  # subject_code -> {teacher_id -> rating (1-3)}


@router.post("/faculty-prefs/{student_id}")
def save_faculty_prefs(student_id: int, payload: FacultyPrefsPayload, store: InMemoryStore = Depends(get_store)):
    store.set_faculty_prefs(student_id, payload.prefs)
    return {"status": "saved"}
