"""Teacher roster: CSV import (admin-only) and read-only listing/
capability lookups (any role for listing, admin for the detailed
capability views — mirrors api/subjects.py and api/students.py).

CSV parsing lives in ingestion/teachers_csv.py; this module only handles
HTTP framing and talks to the store.
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

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


@router.get("/teachers/{teacher_id}/timetable")
def get_teacher_timetable(
    teacher_id: str,
    run_id: Optional[int] = Query(default=None, description="Scope to a specific run"),
    store: InMemoryStore = Depends(get_store),
):
    """Return a teacher's full assigned timetable.

    Each section entry includes subject detail, the enriched meeting slots
    (day, start_time, end_time), and the enrolled student roster.

    No admin role required — teachers access their own timetable data.
    Optionally scoped to a single run via ?run_id=.
    """
    teacher = store.get_teacher(teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="Teacher not found")

    # Build slot lookup for time enrichment.
    slot_lookup = {s.key: s for s in store.list_time_slots()}

    def _enrich_meeting(slot_key: Optional[str]) -> dict:
        if not slot_key:
            return {"slot_key": None, "day": None, "start_time": None, "end_time": None}
        slot = slot_lookup.get(slot_key)
        return {
            "slot_key": slot_key,
            "day": slot.day if slot else None,
            "start_time": slot.start_time if slot else None,
            "end_time": slot.end_time if slot else None,
        }

    # Find all sections assigned to this teacher (optionally run-scoped).
    all_sections = (
        store.list_sections_for_run(run_id)
        if run_id is not None
        else list(store.sections.values())
    )
    assigned_sections = [s for s in all_sections if s.teacher_id == teacher_id]

    schedule = []
    for section in assigned_sections:
        subject = store.get_subject(section.subject_code)
        enrolled = store.enrolled_students_for_section(section.id)
        schedule.append({
            "section_id": section.id,
            "run_id": section.run_id,
            "subject_code": section.subject_code,
            "subject_name": subject.subject_name if subject else None,
            "subject_type": subject.type.value if subject else None,
            "section_label": section.label,
            "capacity": section.capacity,
            "enrolled_count": len(enrolled),
            "enrolled_students": enrolled,
            "meetings": [_enrich_meeting(m.slot_key) for m in section.meetings],
        })

    # Sort by section label for stable ordering.
    schedule.sort(key=lambda e: e["section_label"])

    return {
        "teacher_id": teacher_id,
        "teacher_name": teacher.teacher_name,
        "section_count": len(schedule),
        "schedule": schedule,
    }
