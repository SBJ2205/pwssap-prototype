"""Teacher roster: CSV import (admin-only) and read-only listing/
capability lookups (any role for listing, admin for the detailed
capability views — mirrors api/subjects.py and api/students.py).

CSV parsing lives in ingestion/teachers_csv.py; this module only handles
HTTP framing and talks to the store.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from ingestion.teachers_csv import parse_teachers_csv

router = APIRouter()


def _teacher_to_dict(teacher) -> dict:
    return {"teacher_id": teacher.teacher_id, "teacher_name": teacher.teacher_name}


@router.get("/teachers")
def list_teachers(store: InMemoryStore = Depends(get_store)):
    return [_teacher_to_dict(t) for t in store.list_teachers()]


@router.get("/admin/teachers/{teacher_id}/capabilities", dependencies=[Depends(require_admin)])
def get_teacher_capabilities(teacher_id: str, store: InMemoryStore = Depends(get_store)):
    if store.get_teacher(teacher_id) is None:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return {"teacher_id": teacher_id, "subject_codes": store.capabilities_for_teacher(teacher_id)}


@router.get("/admin/subjects/{subject_code}/teachers", dependencies=[Depends(require_admin)])
def get_teachers_for_subject(subject_code: str, store: InMemoryStore = Depends(get_store)):
    """Which teachers can teach a given subject — the same relationship
    Phase 7 (faculty preference) will need to show students their
    eligible-teacher choices for a subject."""
    if store.get_subject(subject_code) is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return {"subject_code": subject_code, "teacher_ids": store.teachers_for_subject(subject_code)}


@router.post("/admin/teachers/import", dependencies=[Depends(require_admin)])
async def import_teachers(file: UploadFile = File(...), store: InMemoryStore = Depends(get_store)):
    """All-or-nothing import, consistent with subject/student import
    (Phases 2-3): any row error rejects the whole file. Subject codes
    referenced by a teacher must already exist in the catalog — subject
    import (Phase 2) is expected to run before teacher import in the
    normal workflow (see implementation priority order)."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded.")

    known_subject_codes = {s.subject_code for s in store.list_subjects()}
    result = parse_teachers_csv(text, known_subject_codes)
    if not result.is_valid:
        raise HTTPException(status_code=400, detail={
            "status": "rejected",
            "message": "Fix the errors below and re-upload. No rows were imported.",
            "row_errors": [{"row": e.row_number, "errors": e.errors} for e in result.row_errors],
        })

    for teacher in result.teachers:
        store.upsert_teacher(teacher)
    for teacher_id, subject_codes in result.capabilities.items():
        for code in subject_codes:
            store.add_teacher_capability(teacher_id, code)

    total_capabilities = sum(len(codes) for codes in result.capabilities.values())
    return {
        "status": "imported",
        "count": len(result.teachers),
        "capabilities": total_capabilities,
    }
