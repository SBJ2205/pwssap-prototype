"""Student roster: CSV import (admin-only) and read-only listing,
plus elective lock-in endpoints (student-facing).
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from domain.models import StudentChoiceSelection
from domain.validation import validate_lock_in
from ingestion.students_csv import parse_students_csv

router = APIRouter()


def _student_to_dict(student) -> dict:
    return {"roll_number": student.roll_number, "name": student.name, "semester": student.semester}


def _subject_to_dict(subject) -> dict:
    return {
        "subject_code": subject.subject_code,
        "subject_name": subject.subject_name,
        "subject_tag": subject.subject_tag,
        "subtag": subject.subtag,
        "semester": subject.semester,
        "type": subject.type.value if hasattr(subject.type, "value") else str(subject.type),
        "weekly_hours": subject.weekly_hours,
        "capacity": subject.capacity,
    }


class LockInRequest(BaseModel):
    choices: Dict[str, str]  # tag -> subtag


@router.get("/students")
def list_students(semester: Optional[int] = None, store: InMemoryStore = Depends(get_store)):
    return [_student_to_dict(s) for s in store.list_students(semester)]


@router.post("/admin/students/import", dependencies=[Depends(require_admin)])
async def import_students(
    run_id: Optional[int] = None,
    file: UploadFile = File(...),
    store: InMemoryStore = Depends(get_store),
):
    """Import student roster CSV (roll_number, name, semester).

    run_id is optional and ignored for department-wide roster import.
    All-or-nothing: returns 400 if any row errors exist.
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded.")

    result = parse_students_csv(text)
    if not result.is_valid:
        raise HTTPException(status_code=400, detail={
            "status": "rejected",
            "message": "Fix the errors below and re-upload. No rows were imported.",
            "row_errors": [{"row": e.row_number, "errors": e.errors} for e in result.row_errors],
        })

    for student in result.students:
        store.upsert_student(student)

    return {
        "status": "imported",
        "count": len(result.students),
    }


# ── Student Elective Lock-in Endpoints ──────────────────────────────────────

@router.get("/students/{roll_number}/available-choices")
def get_available_choices(roll_number: str, store: InMemoryStore = Depends(get_store)):
    """Returns available elective choices (grouped by tag) for the student's semester."""
    student = store.get_student(roll_number)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    cb_tags = store.get_choice_based_tags()
    sem_subjects = store.list_subjects(semester=student.semester)

    # Collect tags that are choice-based and present in this semester
    available_choices: Dict[str, List[str]] = {}
    elective_subjects = []

    for s in sem_subjects:
        if s.subject_tag in cb_tags:
            elective_subjects.append(s)
            for subtag in s.supported_subtags:
                available_choices.setdefault(s.subject_tag, set()).add(subtag)

    sorted_choices = {tag: sorted(list(subtags)) for tag, subtags in sorted(available_choices.items())}

    return {
        "roll_number": roll_number,
        "semester": student.semester,
        "available_choices": sorted_choices,
        "subjects": [_subject_to_dict(s) for s in elective_subjects],
    }


@router.get("/students/{roll_number}/lock-in")
def get_student_lock_in(roll_number: str, store: InMemoryStore = Depends(get_store)):
    """Fetch current elective lock-in selections for a student."""
    student = store.get_student(roll_number)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    locked_in = store.get_lock_in_for_student(roll_number)
    complete = store.has_complete_lock_in(roll_number)

    return {
        "roll_number": roll_number,
        "locked_in": locked_in,
        "complete": complete,
    }


@router.put("/students/{roll_number}/lock-in")
def save_student_lock_in(
    roll_number: str,
    body: LockInRequest,
    store: InMemoryStore = Depends(get_store),
):
    """Save student elective lock-in choices.

    Validates that:
    - exactly one subtag is chosen per choice-based tag applicable to student's semester.
    - all subtags are valid.
    If lock-in changes, clears existing time and faculty preferences since enrolled
    subjects changed.
    """
    student = store.get_student(roll_number)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    cb_tags = store.get_choice_based_tags()
    sem_subjects = store.list_subjects(semester=student.semester)
    applicable_tags = {s.subject_tag for s in sem_subjects if s.subject_tag in cb_tags}

    available_choices: Dict[str, List[str]] = {}
    for s in sem_subjects:
        if s.subject_tag in applicable_tags:
            for subtag in s.supported_subtags:
                available_choices.setdefault(s.subject_tag, set()).add(subtag)
    sorted_choices = {tag: sorted(list(subtags)) for tag, subtags in available_choices.items()}

    errors = validate_lock_in(body.choices, sorted_choices, applicable_tags)
    if errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "Invalid lock-in selections", "errors": errors},
        )

    # Check if lock-in selections changed
    old_lock_in = store.get_lock_in_for_student(roll_number)
    cleared_prefs = False
    if old_lock_in and old_lock_in != body.choices:
        # Clear time and faculty preferences as enrolled subjects changed
        store.student_time_preferences.pop(roll_number, None)
        store.student_faculty_preferences.pop(roll_number, None)
        cleared_prefs = True

    # Persist selections
    selections = [
        StudentChoiceSelection(roll_number=roll_number, tag=tag, subtag=subtag)
        for tag, subtag in body.choices.items()
    ]
    store.set_student_choice_selections(roll_number, selections)

    return {
        "status": "saved",
        "cleared_prefs": cleared_prefs,
        "locked_in": body.choices,
        "complete": True,
    }


@router.get("/students/{roll_number}/enrolled-subjects")
def get_enrolled_subjects(roll_number: str, store: InMemoryStore = Depends(get_store)):
    """Fetch all subjects the student is enrolled in (core + locked-in electives)."""
    student = store.get_student(roll_number)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    enrolled = store.get_enrolled_subjects_for_student(roll_number)
    return [_subject_to_dict(s) for s in enrolled]


@router.get("/admin/students/{roll_number}/choices", dependencies=[Depends(require_admin)])
def get_student_choices_legacy(
    roll_number: str,
    run_id: Optional[int] = None,
    store: InMemoryStore = Depends(get_store),
):
    """Legacy admin inspection endpoint."""
    student = store.get_student(roll_number)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    selections = store.get_student_choice_selections(roll_number)
    return [
        {
            "tag": s.tag,
            "subtag": s.subtag,
        }
        for s in selections
    ]
