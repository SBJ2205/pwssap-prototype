"""Teacher roster: CSV import (admin-only) and read-only listing/
capability lookups (any role for listing, admin for the detailed
capability views — mirrors api/subjects.py and api/students.py).

CSV parsing lives in ingestion/teachers_csv.py; this module only handles
HTTP framing and talks to the store.
"""
import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from domain.timeslots import get_meeting_times
from ingestion.teachers_csv import parse_teachers_csv

router = APIRouter()


def _teacher_to_dict(teacher) -> dict:
    return {"teacher_id": teacher.teacher_id, "teacher_name": teacher.teacher_name}


@router.get("/teachers")
def list_teachers(store: InMemoryStore = Depends(get_store)):
    return [_teacher_to_dict(t) for t in store.list_teachers()]


@router.delete("/admin/teachers", dependencies=[Depends(require_admin)])
def clear_teacher_roster(store: InMemoryStore = Depends(get_store)):
    """Clear teachers and schedules generated with their assignments."""
    cleared_count = store.clear_teachers()
    return {"status": "cleared", "cleared_count": cleared_count}


@router.get("/admin/teachers/{teacher_id}/capabilities", dependencies=[Depends(require_admin)])
def get_teacher_capabilities(teacher_id: str, store: InMemoryStore = Depends(get_store)):
    if store.get_teacher(teacher_id) is None:
        raise HTTPException(status_code=404, detail="Teacher not found")
    subject_codes = store.capabilities_for_teacher(teacher_id)
    return {
        "teacher_id": teacher_id,
        "subject_codes": subject_codes,
        "subject_loads": {
            code: store.teacher_subject_load(teacher_id, code)
            for code in subject_codes
        },
    }


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
        subject_loads = {
            code: result.loads.get(teacher_id, {}).get(code)
            for code in subject_codes
        }
        store.replace_teacher_capabilities(teacher_id, subject_loads)

    total_capabilities = sum(len(codes) for codes in result.capabilities.values())
    return {
        "status": "imported",
        "count": len(result.teachers),
        "capabilities": total_capabilities,
        "loads": result.loads,
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

    def _enrich_meeting(m) -> dict:
        slot_key = m.slot_key
        if not slot_key:
            return {
                "slot_key": None,
                "duration_hours": m.duration_hours,
                "slot_part": m.slot_part,
                "day": None,
                "start_time": None,
                "end_time": None,
            }
        slot = slot_lookup.get(slot_key)
        start_t, end_t = get_meeting_times(slot, m.duration_hours, m.slot_part)
        return {
            "slot_key": slot_key,
            "duration_hours": m.duration_hours,
            "slot_part": m.slot_part,
            "day": slot.day if slot else None,
            "start_time": start_t,
            "end_time": end_t,
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
        roster = []
        for roll in sorted(enrolled):
            stu = store.get_student(roll)
            roster.append({
                "roll_number": roll,
                "name": stu.name if stu else "Unknown",
                "semester": stu.semester if stu else None,
                "email": getattr(stu, "email", None),
            })
        schedule.append({
            "section_id": section.id,
            "run_id": section.run_id,
            "subject_code": section.subject_code,
            "subject_name": subject.subject_name if subject else None,
            "subject_type": (subject.type.value if hasattr(subject.type, "value") else str(subject.type)) if subject else None,
            "section_label": section.label,
            "capacity": section.capacity,
            "enrolled_count": len(enrolled),
            "enrolled_students": enrolled,
            "enrolled_roster": roster,
            "meetings": [_enrich_meeting(m) for m in section.meetings],
        })

    # Sort by section label for stable ordering.
    schedule.sort(key=lambda e: e["section_label"])

    return {
        "teacher_id": teacher_id,
        "teacher_name": teacher.teacher_name,
        "section_count": len(schedule),
        "schedule": schedule,
    }


@router.get("/teachers/{teacher_id}/sections/{section_id}/roster.csv")
def download_section_roster_csv(
    teacher_id: str,
    section_id: int,
    store: InMemoryStore = Depends(get_store),
):
    """Download the enrolled student roster for a specific section as a CSV file.

    Format: roll_number,student_name,semester
    """
    teacher = store.get_teacher(teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="Teacher not found")

    section = store.get_section(section_id)
    if section is None or section.teacher_id != teacher_id:
        raise HTTPException(status_code=404, detail="Section not found or not assigned to this teacher")

    enrolled = store.enrolled_students_for_section(section_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["roll_number", "student_name", "semester"])
    for roll in sorted(enrolled):
        stu = store.get_student(roll)
        writer.writerow([roll, stu.name if stu else "Unknown", stu.semester if stu else ""])

    filename = f"{section.label}_roster.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/teachers/{teacher_id}/timetable.csv")
def download_teacher_timetable_csv(
    teacher_id: str,
    run_id: Optional[int] = Query(default=None, description="Scope to a specific run"),
    store: InMemoryStore = Depends(get_store),
):
    """Download the complete weekly schedule for a teacher as a CSV file."""
    teacher = store.get_teacher(teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="Teacher not found")

    data = get_teacher_timetable(teacher_id=teacher_id, run_id=run_id, store=store)
    schedule = data.get("schedule", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "day",
        "start_time",
        "end_time",
        "duration_hours",
        "subject_code",
        "subject_name",
        "subject_type",
        "section_label",
        "enrolled_count",
    ])

    rows = []
    for sec in schedule:
        for m in sec.get("meetings", []):
            if m.get("slot_key"):
                rows.append({
                    "day": m.get("day") or "",
                    "start_time": m.get("start_time") or "",
                    "end_time": m.get("end_time") or "",
                    "duration_hours": m.get("duration_hours") or 2,
                    "subject_code": sec.get("subject_code") or "",
                    "subject_name": sec.get("subject_name") or "",
                    "subject_type": sec.get("subject_type") or "",
                    "section_label": sec.get("section_label") or "",
                    "enrolled_count": sec.get("enrolled_count") or 0,
                })

    day_order = {"Mon": 1, "Tue": 2, "Wed": 3, "Thu": 4, "Fri": 5}
    rows.sort(key=lambda r: (day_order.get(r["day"], 99), r["start_time"]))

    for r in rows:
        writer.writerow([
            r["day"],
            r["start_time"],
            r["end_time"],
            r["duration_hours"],
            r["subject_code"],
            r["subject_name"],
            r["subject_type"],
            r["section_label"],
            r["enrolled_count"],
        ])

    filename = f"{teacher_id}_timetable.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
