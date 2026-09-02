"""Student faculty preference submission (product decision #11).

Secondary and explicitly LOWER-weight than time-slot preference — the
eventual solver objective (Phase 9) must never let faculty preference
outweigh time-slot preference. Only subjects with 2+ eligible teachers
are rankable; there is no "Blocked" concept here since this is never a
hard constraint, unlike time-slot preference's Blocked rating.

Not admin-managed — a student submits their own preferences (no real
auth in this local prototype, product decision #14).
"""
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from data.store import InMemoryStore, get_store
from domain.validation import validate_faculty_preferences

router = APIRouter()


class FacultyPreferencesPayload(BaseModel):
    preferences: Dict[str, Dict[str, int]]  # subject_code -> {teacher_id: rating (1-3)}


def _require_student(roll_number: str, store: InMemoryStore):
    student = store.get_student(roll_number)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


@router.get("/students/{roll_number}/rankable-subjects")
def get_rankable_subjects(roll_number: str, store: InMemoryStore = Depends(get_store)):
    """Which subjects this student can even submit a faculty preference
    for, and which teachers are eligible for each — lets the frontend
    build the ranking form without guessing."""
    student = _require_student(roll_number, store)
    result = []
    for code, teacher_ids in store.rankable_subjects_for_semester(student.semester):
        teachers = []
        for tid in teacher_ids:
            teacher = store.get_teacher(tid)
            if teacher is not None:
                teachers.append({"teacher_id": tid, "teacher_name": teacher.teacher_name})
        result.append({"subject_code": code, "teachers": teachers})
    return result


@router.get("/students/{roll_number}/faculty-preferences")
def get_faculty_preferences(roll_number: str, store: InMemoryStore = Depends(get_store)):
    _require_student(roll_number, store)
    return store.get_faculty_preferences(roll_number)


@router.put("/students/{roll_number}/faculty-preferences")
def save_faculty_preferences(
    roll_number: str, payload: FacultyPreferencesPayload, store: InMemoryStore = Depends(get_store)
):
    student = _require_student(roll_number, store)

    rankable = dict(store.rankable_subjects_for_semester(student.semester))
    result = validate_faculty_preferences(payload.preferences, rankable)
    if not result.is_valid:
        raise HTTPException(status_code=400, detail={"errors": result.errors})

    store.set_faculty_preferences(roll_number, payload.preferences)
    return {"status": "saved"}
