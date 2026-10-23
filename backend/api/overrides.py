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
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from domain.models import Section
from domain.timeslots import get_meeting_times

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
    warnings: List[str] = []

    teacher = store.get_teacher(payload.teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="Teacher not found")

    # Capability check (hard reject 400).
    capable = store.teachers_for_subject(section.subject_code)
    if payload.teacher_id not in capable:
        raise HTTPException(
            status_code=400,
            detail=f"Teacher {payload.teacher_id} is not capable of teaching subject {section.subject_code}.",
        )

    # Availability check (hard reject 400).
    for m in section.meetings:
        if m.slot_key and not store.is_teacher_available(payload.teacher_id, m.slot_key):
            raise HTTPException(
                status_code=400,
                detail=f"Teacher {payload.teacher_id} is marked unavailable for slot '{m.slot_key}'.",
            )

    # Double-booking check (non-blocking warning).
    section_slot_keys = {m.slot_key for m in section.meetings if m.slot_key}
    teacher_occupied = set(
        store.slot_keys_for_teacher(payload.teacher_id, exclude_section_id=section_id)
    )
    clashing = section_slot_keys & teacher_occupied
    if clashing:
        warnings.append(
            f"Teacher {payload.teacher_id} already teaches another section "
            f"in slot(s) {sorted(clashing)}. Assigning anyway as admin override."
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

    Each meeting in the response includes the full canonical slot detail
    (day, start_time, end_time) so the frontend can render a weekly grid
    without a separate /timeslots call (product decision #15).

    No admin role required — students access their own data.
    """
    from domain.saved_runs import ensure_active_run_loaded
    ensure_active_run_loaded(store)

    student = store.get_student(roll_number)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    # Build a lookup from slot_key -> TimeSlot for enrichment.
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

    assignments = store.get_student_sections(roll_number)
    timetable = []
    for subject_code, section_id in assignments.items():
        section = store.get_section(section_id)
        if section is None:
            continue
        subject = store.get_subject(subject_code)
        teacher = store.get_teacher(section.teacher_id) if section.teacher_id else None
        timetable.append({
            "subject_code": subject_code,
            "subject_name": subject.subject_name if subject else None,
            "subject_tag": subject.subject_tag if subject else None,
            "subject_type": subject.type.value if subject else None,
            "section_id": section_id,
            "section_label": section.label,
            "teacher_id": section.teacher_id,
            "teacher_name": teacher.teacher_name if teacher else None,
            "meetings": [_enrich_meeting(m) for m in section.meetings],
        })

    # Sort timetable by subject_code for stable ordering.
    timetable.sort(key=lambda e: e["subject_code"])

    stats = _compute_student_stats(student, timetable, store)

    return {
        "roll_number": roll_number,
        "name": student.name,
        "semester": student.semester,
        "timetable": timetable,
        "stats": stats,
    }


def _compute_student_stats(student, timetable: list, store: InMemoryStore) -> dict:
    time_prefs = store.get_time_preferences(student.roll_number)
    fac_prefs = store.get_faculty_preferences(student.roll_number)

    preferred_cnt = 0
    tolerable_cnt = 0
    unrated_cnt = 0
    disliked_cnt = 0
    blocked_cnt = 0
    total_meetings = 0
    blocked_overrides = []

    days_with_classes = set()
    friday_afternoon_has_class = False
    monday_morning_has_class = False

    for entry in timetable:
        sub_code = entry.get("subject_code")
        sub_name = entry.get("subject_name") or sub_code
        sec_id = entry.get("section_id")
        section = store.get_section(sec_id) if sec_id else None
        run_id = section.run_id if section else None
        parallel_count = len([s for s in store.list_sections_for_run(run_id) if s.subject_code == sub_code]) if run_id else 1
        is_single = parallel_count <= 1

        for m in entry.get("meetings", []):
            sk = m.get("slot_key")
            if not sk:
                continue
            total_meetings += 1
            rating = time_prefs.get(sk)
            if rating == 1:
                preferred_cnt += 1
            elif rating == 2:
                tolerable_cnt += 1
            elif rating == 3:
                disliked_cnt += 1
            elif rating == 4:
                blocked_cnt += 1
                blocked_overrides.append({
                    "subject_code": sub_code,
                    "subject_name": sub_name,
                    "slot_key": sk,
                    "day": m.get("day"),
                    "start_time": m.get("start_time"),
                    "end_time": m.get("end_time"),
                    "duration_hours": m.get("duration_hours", 2),
                    "is_single_section": is_single,
                    "parallel_sections_count": parallel_count,
                    "reason": (
                        "Single-section course: no alternative time slots exist for this offering."
                        if is_single else
                        "Parallel sections conflicted with your other required classes or reached section capacity."
                    ),
                })
            else:
                unrated_cnt += 1

            day = m.get("day")
            if day:
                days_with_classes.add(day)
                slot_idx = int(sk.split("-")[1]) if "-" in sk and sk.split("-")[1].isdigit() else 0
                if day == "Fri" and slot_idx in (3, 4):
                    friday_afternoon_has_class = True
                if day == "Mon" and slot_idx in (1, 2):
                    monday_morning_has_class = True

    if total_meetings > 0:
        raw_score = (preferred_cnt * 100 + (tolerable_cnt + unrated_cnt) * 85 + disliked_cnt * 35) / total_meetings
        satisfaction_score = max(0, min(100, round(raw_score)))
    else:
        satisfaction_score = 100

    top_choice_matches = 0
    total_rated_subjects = 0
    for entry in timetable:
        sub_code = entry.get("subject_code")
        teacher_id = entry.get("teacher_id")
        if sub_code in fac_prefs:
            total_rated_subjects += 1
            ratings = fac_prefs[sub_code]
            if teacher_id and ratings.get(teacher_id) == 1:
                top_choice_matches += 1

    sem_students = [
        s for s in store.list_students(semester=student.semester)
        if s.roll_number in store.student_section_assignments
    ]
    if len(sem_students) > 1:
        cohort_scores = []
        for other in sem_students:
            if other.roll_number == student.roll_number:
                cohort_scores.append(satisfaction_score)
                continue
            o_assigns = store.get_student_sections(other.roll_number)
            o_prefs = store.get_time_preferences(other.roll_number)
            o_tot = 0
            o_pts = 0
            for sc, sid in o_assigns.items():
                sec = store.get_section(sid)
                if not sec:
                    continue
                for om in sec.meetings:
                    if not om.slot_key:
                        continue
                    o_tot += 1
                    r = o_prefs.get(om.slot_key)
                    if r == 1:
                        o_pts += 100
                    elif r == 2 or r is None:
                        o_pts += 85
                    elif r == 3:
                        o_pts += 35
            if o_tot > 0:
                cohort_scores.append(o_pts / o_tot)
        cohort_avg = round(sum(cohort_scores) / len(cohort_scores)) if cohort_scores else satisfaction_score
    else:
        cohort_avg = satisfaction_score

    perks = []
    if blocked_cnt == 0:
        perks.append("100% of blocked slots honored")
    if not friday_afternoon_has_class:
        perks.append("Free Friday afternoon")
    if not monday_morning_has_class:
        perks.append("Free Monday morning")
    if satisfaction_score >= 90:
        perks.append("High preference match")

    return {
        "satisfaction_score": satisfaction_score,
        "cohort_average_satisfaction": cohort_avg,
        "breakdown": {
            "preferred": preferred_cnt,
            "tolerable": tolerable_cnt,
            "unrated": unrated_cnt,
            "disliked": disliked_cnt,
            "blocked": blocked_cnt,
            "total_meetings": total_meetings,
        },
        "blocked_overrides": blocked_overrides,
        "faculty_match": {
            "top_choice_matches": top_choice_matches,
            "total_rated_subjects": total_rated_subjects,
        },
        "perks": perks,
    }

