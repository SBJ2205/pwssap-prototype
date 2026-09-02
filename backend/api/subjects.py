"""Subject catalog: CSV import (admin-only) and read-only listing (any
role — students/teachers need to see the subject list too).

CSV parsing itself lives in ingestion/subjects_csv.py; this module only
handles HTTP framing (file upload, status codes, response shaping) and
talks to the store.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from ingestion.subjects_csv import parse_subjects_csv

router = APIRouter()


def _subject_to_dict(subject) -> dict:
    return {
        "subject_code": subject.subject_code,
        "subject_name": subject.subject_name,
        "subject_tag": subject.subject_tag,
        "semester": subject.semester,
        "type": subject.type.value if hasattr(subject.type, "value") else subject.type,
        "weekly_hours": subject.weekly_hours,
        "capacity": subject.capacity,
        "slot_structure": subject.slot_structure,
    }


@router.get("/subjects")
def list_subjects(semester: Optional[int] = None, store: InMemoryStore = Depends(get_store)):
    return [_subject_to_dict(s) for s in store.list_subjects(semester)]


@router.get("/admin/subjects/tags", dependencies=[Depends(require_admin)])
def list_subject_tags(semester: Optional[int] = None, store: InMemoryStore = Depends(get_store)):
    """Distinct subject_tag values in the catalog, for the admin's
    choice-tag configuration screen (product decision #3)."""
    return {"tags": store.list_subject_tags(semester)}


@router.post("/admin/subjects/import", dependencies=[Depends(require_admin)])
async def import_subjects(file: UploadFile = File(...), store: InMemoryStore = Depends(get_store)):
    """All-or-nothing import: if ANY row fails validation, nothing is
    committed and the full list of row-level errors is returned so the
    admin can fix the CSV and re-upload once, instead of ending up with a
    partially-imported catalog."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded.")

    result = parse_subjects_csv(text)
    if not result.is_valid:
        raise HTTPException(status_code=400, detail={
            "status": "rejected",
            "message": "Fix the errors below and re-upload. No rows were imported.",
            "row_errors": [{"row": e.row_number, "errors": e.errors} for e in result.row_errors],
        })

    for subject in result.subjects:
        store.upsert_subject(subject)

    semesters = sorted({s.semester for s in result.subjects})
    return {
        "status": "imported",
        "count": len(result.subjects),
        "semesters": semesters,
    }
