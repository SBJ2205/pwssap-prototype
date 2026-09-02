"""Admin manual override endpoints for published timetable results (Phase 10).

After the solver auto-publishes a result (product decision #13), the admin
can refine it without re-running the solver. This module provides four
override operations on sections, plus a student-facing lookup used by
Phase 11's timetable view.

Admin-only routes (product decision #14):
  POST /admin/sections/{section_id}/enroll
      Add a student to a section.  Warns on capacity overflow and slot clash,
      but ALLOWS the override -- the admin understands the context.

  DELETE /admin/sections/{section_id}/students/{roll_number}
      Remove a student from a section.

  PUT /admin/sections/{section_id}/teacher
      Reassign the teacher on a section.  Warns on double-booking.

  PUT /admin/sections/{section_id}/capacity
      Override the section's capacity ceiling.

Student-facing route (no admin role required — product decision #14):
  GET /students/{roll_number}/sections
      Return the student's section assignments and the full timetable
      detail for each (used by Phase 11 student timetable view).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from domain.models import Section

admin_router = APIRouter(prefix="/admin/sections", dependencies=[Depends(require_admin)])
student_router = APIRouter(prefix="/students")


# ── Shared serialisers ────────────────────────────────────────────────────

def _section_detail(section: Section, store: InMemoryStore) -> dict:
    enrolled = store.enrolled_students_for_section(section.id)
    return {
        "id": section.id,
        "run_id": section.run_id,
        "subject_code": section.subject_code,
        "label": section.label,
        "teacher_id": section.teacher_id,
        "capacity": section.capacity,
        "enrolled_count": len(enrolled),
        "enrolled_students": enrolled,
        "meetings": [{"slot_key": m.slot_key or None} for m in section.meetings],
    }


def _get_section_or_404(section_id: int, store: InMemoryStore) -> Section:
    section = store.get_section(section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


# ── Admin override: enroll a student ─────────────────────────────────────

class EnrollPayload(BaseModel):
    roll_number: str


@admin_router.post("/{section_id}/enroll")
def enroll_student(
    section_id: int,
    payload: EnrollPayload,
    store: InMemoryStore = Depends(get_store),
):
    """Add a student to a section post-publication.

    Warns on:
      - capacity overflow (enrolled_count >= section.capacity)
      - slot clash (the student is already in a section that meets at
        the same time)

    Both warnings are non-blocking: the admin override is always honoured.
    """
    section = _get_section_or_404(section_id, store)

    student = store.get_student(payload.roll_number)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    warnings = []

    # Capacity check.
    current = store.current_enrollment_count(section_id)
    if current >= section.capacity:
        warnings.append(
            f"Section {section.label} is already at capacity "
            f"({current}/{section.capacity}). Enrolling anyway as this is "
            "an admin override."
        )

    # Slot clash check.
    section_slot_keys = {m.slot_key for m in section.meetings if m.slot_key}
    student_slot_keys = set(store.slot_keys_for_student(payload.roll_number))
    clashing = section_slot_keys & student_slot_keys
    if clashing:
        warnings.append(
            f"Student {payload.roll_number} already has a section meeting "
            f"in slot(s) {sorted(clashing)}. Enrolling anyway."
        )

    store.enroll_student(payload.roll_number, section.subject_code, section_id)

    return {
        "enrolled": True,
        "roll_number": payload.roll_number,
        "section_id": section_id,
        "subject_code": section.subject_code,
        "warnings": warnings,
        "section": _section_detail(section, store),
    }


# ── Admin override: remove a student ─────────────────────────────────────

@admin_router.delete("/{section_id}/students/{roll_number}")
def unenroll_student(
    section_id: int,
    roll_number: str,
    store: InMemoryStore = Depends(get_store),
):
    """Remove a student from a section post-publication."""
    section = _get_section_or_404(section_id, store)

    student = store.get_student(roll_number)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    removed = store.unenroll_student(roll_number, section.subject_code)
    if not removed:
        raise HTTPException(
            status_code=404,
            detail=f"Student {roll_number} is not enrolled in section {section_id}",
        )

    return {
        "unenrolled": True,
        "roll_number": roll_number,
        "section_id": section_id,
        "subject_code": section.subject_code,
        "section": _section_detail(section, store),
    }


# ── Admin override: reassign teacher ─────────────────────────────────────

class TeacherPayload(BaseModel):
    teacher_id: str


@admin_router.put("/{section_id}/teacher")
def reassign_teacher(
    section_id: int,
    payload: TeacherPayload,
    store: InMemoryStore = Depends(get_store),
):
    """Change the teacher assigned to a section post-publication.

    Warns if the new teacher is not in the capability list for the subject,
    or if the teacher would be double-booked (already teaches another section
    meeting at the same slot).  Both warnings are non-blocking.
    """
    section = _get_section_or_404(section_id, store)

    teacher = store.get_teacher(payload.teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="Teacher not found")

    warnings = []

    # Capability check (warn, not reject — admin override).
    capable = store.teachers_for_subject(section.subject_code)
    if payload.teacher_id not in capable:
        warnings.append(
            f"Teacher {payload.teacher_id} is not in the capability list for "
            f"subject {section.subject_code}. Assigning anyway as admin override."
        )

    # Double-booking check.
    section_slot_keys = {m.slot_key for m in section.meetings if m.slot_key}
    teacher_occupied = set(
        store.slot_keys_for_teacher(payload.teacher_id, exclude_section_id=section_id)
    )
    clashing = section_slot_keys & teacher_occupied
    if clashing:
        warnings.append(
            f"Teacher {payload.teacher_id} already teaches another section "
            f"in slot(s) {sorted(clashing)}. Assigning anyway."
        )

    section.teacher_id = payload.teacher_id
    store.sections[section_id] = section

    return {
        "teacher_id": payload.teacher_id,
        "section_id": section_id,
        "warnings": warnings,
        "section": _section_detail(section, store),
    }


# ── Admin override: adjust capacity ──────────────────────────────────────

class CapacityPayload(BaseModel):
    capacity: int


@admin_router.put("/{section_id}/capacity")
def override_capacity(
    section_id: int,
    payload: CapacityPayload,
    store: InMemoryStore = Depends(get_store),
):
    """Override the capacity ceiling on a section (product decision #5).

    The admin can raise or lower capacity after publication.  Warns if the
    new capacity is below the current enrollment count (no students are
    removed — it's just a warning).
    """
    section = _get_section_or_404(section_id, store)

    if payload.capacity <= 0:
        raise HTTPException(status_code=400, detail="capacity must be a positive integer")

    warnings = []
    current_enrollment = store.current_enrollment_count(section_id)
    if payload.capacity < current_enrollment:
        warnings.append(
            f"New capacity {payload.capacity} is below the current enrollment "
            f"count {current_enrollment}. No students have been removed; "
            "resolve this manually."
        )

    section.capacity = payload.capacity
    store.sections[section_id] = section

    return {
        "capacity": payload.capacity,
        "section_id": section_id,
        "warnings": warnings,
        "section": _section_detail(section, store),
    }


# ── Student-facing: get enrolled sections ────────────────────────────────

@student_router.get("/{roll_number}/sections")
def get_student_sections(
    roll_number: str,
    store: InMemoryStore = Depends(get_store),
):
    """Return a student's full personalised timetable.

    Resolves each section assignment to its full section detail (subject,
    teacher, meeting slots, label).  Used by Phase 11's student timetable
    view.  No admin role required (students access their own data).
    """
    student = store.get_student(roll_number)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    assignments = store.get_student_sections(roll_number)  # {subject_code: section_id}
    timetable = []
    for subject_code, section_id in assignments.items():
        section = store.get_section(section_id)
        if section is None:
            continue
        subject = store.get_subject(subject_code)
        timetable.append({
            "subject_code": subject_code,
            "subject_name": subject.subject_name if subject else None,
            "subject_tag": subject.subject_tag if subject else None,
            "section_id": section_id,
            "section_label": section.label,
            "teacher_id": section.teacher_id,
            "teacher_name": (
                store.get_teacher(section.teacher_id).teacher_name
                if section.teacher_id and store.get_teacher(section.teacher_id)
                else None
            ),
            "meetings": [{"slot_key": m.slot_key or None} for m in section.meetings],
        })

    return {
        "roll_number": roll_number,
        "name": student.name,
        "semester": student.semester,
        "timetable": timetable,
    }
