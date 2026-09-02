"""Admin-only CRUD for the catalog data that feeds the solver: teachers,
subjects, students, and sections (the concrete teacher timetable).

Every route here requires the `admin` role (see api/deps.require_admin).
Students never call these — they only read the student-safe catalog routes
in api/catalog.py and submit preferences via api/preferences.py.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from domain.models import Meeting

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


# ── Teachers ─────────────────────────────────────────────────────────────
class TeacherPayload(BaseModel):
    name: str
    department: Optional[str] = None


@router.get("/teachers")
def list_teachers(store: InMemoryStore = Depends(get_store)):
    return [{"id": t.id, "name": t.name, "department": t.department} for t in store.list_teachers()]


@router.post("/teachers")
def create_teacher(payload: TeacherPayload, store: InMemoryStore = Depends(get_store)):
    teacher = store.add_teacher(payload.name, payload.department)
    return {"id": teacher.id, "name": teacher.name, "department": teacher.department}


@router.put("/teachers/{teacher_id}")
def update_teacher(teacher_id: int, payload: TeacherPayload, store: InMemoryStore = Depends(get_store)):
    try:
        teacher = store.update_teacher(teacher_id, payload.name, payload.department)
    except KeyError:
        raise HTTPException(status_code=404, detail="Teacher not found")
    return {"id": teacher.id, "name": teacher.name, "department": teacher.department}


@router.delete("/teachers/{teacher_id}")
def delete_teacher(teacher_id: int, store: InMemoryStore = Depends(get_store)):
    try:
        store.delete_teacher(teacher_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Teacher not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "deleted"}


# ── Subjects ─────────────────────────────────────────────────────────────
class SubjectPayload(BaseModel):
    code: str
    name: str
    department: Optional[str] = None
    year: Optional[int] = None


class SubjectUpdatePayload(BaseModel):
    name: Optional[str] = None
    department: Optional[str] = None
    year: Optional[int] = None


@router.post("/subjects")
def create_subject(payload: SubjectPayload, store: InMemoryStore = Depends(get_store)):
    try:
        subject = store.add_subject(payload.code, payload.name, payload.department, payload.year)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"code": subject.code, "name": subject.name, "department": subject.department, "year": subject.year}


@router.put("/subjects/{code}")
def update_subject(code: str, payload: SubjectUpdatePayload, store: InMemoryStore = Depends(get_store)):
    try:
        subject = store.update_subject(code, payload.name, payload.department, payload.year)
    except KeyError:
        raise HTTPException(status_code=404, detail="Subject not found")
    return {"code": subject.code, "name": subject.name, "department": subject.department, "year": subject.year}


@router.delete("/subjects/{code}")
def delete_subject(code: str, store: InMemoryStore = Depends(get_store)):
    try:
        store.delete_subject(code)
    except KeyError:
        raise HTTPException(status_code=404, detail="Subject not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "deleted"}


# ── Students ─────────────────────────────────────────────────────────────
class StudentPayload(BaseModel):
    name: str
    roll: str
    department: Optional[str] = None
    year: Optional[int] = None


class StudentUpdatePayload(BaseModel):
    name: Optional[str] = None
    roll: Optional[str] = None
    department: Optional[str] = None
    year: Optional[int] = None


@router.post("/students")
def create_student(payload: StudentPayload, store: InMemoryStore = Depends(get_store)):
    student = store.add_student(payload.name, payload.roll, payload.department, payload.year)
    return {"id": student.id, "name": student.name, "roll": student.roll,
            "department": student.department, "year": student.year}


@router.put("/students/{student_id}")
def update_student(student_id: int, payload: StudentUpdatePayload, store: InMemoryStore = Depends(get_store)):
    try:
        student = store.update_student(student_id, payload.name, payload.roll, payload.department, payload.year)
    except KeyError:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"id": student.id, "name": student.name, "roll": student.roll,
            "department": student.department, "year": student.year}


@router.delete("/students/{student_id}")
def delete_student(student_id: int, store: InMemoryStore = Depends(get_store)):
    if store.get_student(student_id) is None:
        raise HTTPException(status_code=404, detail="Student not found")
    store.delete_student(student_id)
    return {"status": "deleted"}


# ── Sections (the concrete teacher timetable) ───────────────────────────
class MeetingPayload(BaseModel):
    day: str
    time: str


class SectionPayload(BaseModel):
    subject_code: str
    label: str
    teacher_id: int
    room: str
    capacity: int
    meetings: List[MeetingPayload]


class SectionUpdatePayload(BaseModel):
    subject_code: Optional[str] = None
    label: Optional[str] = None
    teacher_id: Optional[int] = None
    room: Optional[str] = None
    capacity: Optional[int] = None
    meetings: Optional[List[MeetingPayload]] = None


def _section_to_dict(section) -> dict:
    return {
        "id": section.id,
        "subject_code": section.subject_code,
        "label": section.label,
        "teacher_id": section.teacher_id,
        "room": section.room,
        "capacity": section.capacity,
        "meetings": [{"day": m.day, "time": m.time} for m in section.meetings],
    }


@router.get("/sections")
def list_sections(store: InMemoryStore = Depends(get_store)):
    return [_section_to_dict(s) for s in store.list_sections()]


@router.post("/sections")
def create_section(payload: SectionPayload, store: InMemoryStore = Depends(get_store)):
    meetings = [Meeting(day=m.day, time=m.time) for m in payload.meetings]
    try:
        section = store.add_section(payload.subject_code, payload.label, payload.teacher_id,
                                     payload.room, payload.capacity, meetings)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _section_to_dict(section)


@router.put("/sections/{section_id}")
def update_section(section_id: int, payload: SectionUpdatePayload, store: InMemoryStore = Depends(get_store)):
    meetings = [Meeting(day=m.day, time=m.time) for m in payload.meetings] if payload.meetings is not None else None
    try:
        section = store.update_section(section_id, payload.subject_code, payload.label, payload.teacher_id,
                                        payload.room, payload.capacity, meetings)
    except KeyError:
        raise HTTPException(status_code=404, detail="Section not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _section_to_dict(section)


@router.delete("/sections/{section_id}")
def delete_section(section_id: int, store: InMemoryStore = Depends(get_store)):
    try:
        store.delete_section(section_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Section not found")
    return {"status": "deleted"}
