"""Read-only 'what exists' endpoints: sections, students, timeslots, and
which faculty teach a given subject. No preference or solver-run state here.
"""
from fastapi import APIRouter, Depends

from data.store import InMemoryStore, get_store

router = APIRouter()


def _section_to_dict(section, store: InMemoryStore) -> dict:
    subject = store.get_subject(section.subject_code)
    teacher = store.get_teacher(section.teacher_id)
    return {
        "id": section.id,
        "subject": subject.name,
        "code": section.subject_code,
        "section": section.label,
        "faculty": teacher.name,
        "room": section.room,
        "capacity": section.capacity,
        "meetings": [{"day": m.day, "time": m.time} for m in section.meetings],
    }


@router.get("/sections")
def get_sections(store: InMemoryStore = Depends(get_store)):
    # NOTE: this currently exposes full teacher/time data to any caller.
    # Milestone 2 adds access control so this concrete timetable stays
    # hidden from students until after the solver runs.
    return [_section_to_dict(s, store) for s in store.list_sections()]


@router.get("/students")
def get_students(store: InMemoryStore = Depends(get_store)):
    return [{"id": s.id, "name": s.name, "roll": s.roll} for s in store.list_students()]


@router.get("/timeslots")
def get_timeslots(store: InMemoryStore = Depends(get_store)):
    """The abstract 6-day x 4-period grid students rate — never reveals
    which subject or teacher occupies a given period."""
    return [{"key": t.key, "day": t.day, "time": t.time, "label": t.label} for t in store.list_time_slots()]


@router.get("/faculty-by-subject")
def get_faculty_by_subject(store: InMemoryStore = Depends(get_store)):
    """{subject_code: [{id, name}, ...]} so the UI can build a per-subject
    faculty ranking form. A subject taught by only one teacher naturally
    yields a single-item list — the frontend treats that as "nothing to
    rank" for that subject."""
    result = {}
    for subject in store.list_subjects():
        sections = store.sections_for_subject(subject.code)
        teacher_ids = sorted({sec.teacher_id for sec in sections})
        result[subject.code] = [
            {"id": tid, "name": store.get_teacher(tid).name} for tid in teacher_ids
        ]
    return result
