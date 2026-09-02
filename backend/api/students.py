"""Student roster: CSV import (admin-only, run-scoped) and read-only
listing (any role — mirrors api/subjects.py).

CSV parsing lives in ingestion/students_csv.py; this module only handles
HTTP framing and talks to the store. Unlike subject import, student
import is scoped to one GenerationRun (product decision #3): the
choice_1..choice_N columns and their legal values come entirely from
that run's choice_tag_configs, so a run_id is required.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from ingestion.students_csv import parse_students_csv

router = APIRouter()


def _student_to_dict(student) -> dict:
    return {"roll_number": student.roll_number, "name": student.name, "semester": student.semester}


@router.get("/students")
def list_students(semester: Optional[int] = None, store: InMemoryStore = Depends(get_store)):
    return [_student_to_dict(s) for s in store.list_students(semester)]


@router.post("/admin/students/import", dependencies=[Depends(require_admin)])
async def import_students(
    run_id: int, file: UploadFile = File(...), store: InMemoryStore = Depends(get_store)
):
    """All-or-nothing import, consistent with subject import (Phase 2):
    if any row fails validation, nothing is committed and the full list
    of row errors is returned so the admin fixes the CSV once."""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded.")

    result = parse_students_csv(text, run)
    if not result.is_valid:
        raise HTTPException(status_code=400, detail={
            "status": "rejected",
            "message": "Fix the errors below and re-upload. No rows were imported.",
            "row_errors": [{"row": e.row_number, "errors": e.errors} for e in result.row_errors],
        })

    for student in result.students:
        store.upsert_student(student)
    for roll_number, selections in result.choice_selections.items():
        store.set_student_choice_selections(roll_number, selections)

    return {
        "status": "imported",
        "count": len(result.students),
        "run_id": run.id,
        "semester": run.semester,
    }


@router.get("/admin/students/{roll_number}/choices", dependencies=[Depends(require_admin)])
def get_student_choices(roll_number: str, run_id: int, store: InMemoryStore = Depends(get_store)):
    """Admin sanity-check view: a student's choice selections for one
    run, resolved back to the tag names they represent."""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    tag_by_value = {c.numeric_value: c.tag for c in run.choice_tag_configs}
    selections = sorted(store.get_student_choice_selections(roll_number), key=lambda s: s.choice_column)
    return [
        {
            "choice_column": s.choice_column,
            "numeric_value": s.numeric_value,
            "tag": tag_by_value.get(s.numeric_value),
        }
        for s in selections
    ]
