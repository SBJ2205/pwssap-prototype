"""Admin API for department-level timetable cycle management.

Routes:
  GET  /admin/cycle
      Returns current cycle status: active semesters derived from catalog,
      subject and student counts per semester, teacher counts, choice tag
      configs, student lock-in progress, and current generation run info.

  PUT  /admin/cycle/choice-tags
      Configure which subject tags are choice-based (electives) for the cycle.

  POST /admin/cycle/initialize
      Auto-creates or refreshes the generation run covering all active
      semesters in the subject catalog.
"""
import random
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from domain.enums import RunStatus
from domain.models import StudentChoiceSelection

router = APIRouter(
    prefix="/admin/cycle",
    dependencies=[Depends(require_admin)],
)


class ChoiceTagItem(BaseModel):
    tag: str
    is_choice_based: bool = True


def _get_cycle_status_dict(store: InMemoryStore) -> Dict[str, Any]:
    subjects = list(store.subjects.values())
    students = list(store.students.values())

    active_semesters = sorted({s.semester for s in subjects})
    subjects_per_sem = {}
    for sem in active_semesters:
        subjects_per_sem[sem] = len([s for s in subjects if s.semester == sem])

    students_per_sem = {}
    for s in students:
        students_per_sem[s.semester] = students_per_sem.get(s.semester, 0) + 1

    choice_configs = store.get_cycle_choice_configs()
    all_tags = store.list_subject_tags()
    choice_groups = store.get_choice_groups()

    tags_detail = []
    for tag in all_tags:
        subtags = choice_groups.get(tag, [])
        default_is_choice = bool(subtags and tag.upper() != "CORE")
        tags_detail.append({
            "tag": tag,
            "is_choice_based": choice_configs.get(tag, default_is_choice),
            "subtags": subtags,
        })

    lock_in_complete = 0
    students_lock_in = []
    for s in students:
        is_complete = store.has_complete_lock_in(s.roll_number)
        if is_complete:
            lock_in_complete += 1
        locked = store.get_lock_in_for_student(s.roll_number)
        sem_subjects = store.list_subjects(semester=s.semester)
        cb_tags = store.get_choice_based_tags_for_semester(s.semester)
        applicable_tags = sorted(list({sub.subject_tag for sub in sem_subjects if sub.subject_tag in cb_tags}))
        missing_tags = [t for t in applicable_tags if not locked.get(t)]
        students_lock_in.append({
            "roll_number": s.roll_number,
            "name": s.name,
            "semester": s.semester,
            "is_complete": is_complete,
            "locked_in": locked,
            "applicable_tags": applicable_tags,
            "missing_tags": missing_tags,
        })

    # Find the current (latest) generation run
    latest_run = None
    if store.runs:
        latest_run_obj = max(store.runs.values(), key=lambda r: r.id)
        latest_run = {
            "id": latest_run_obj.id,
            "semesters": latest_run_obj.semesters,
            "semester": latest_run_obj.semester,
            "status": latest_run_obj.status.value,
        }

    return {
        "active_semesters": active_semesters,
        "subjects_per_semester": subjects_per_sem,
        "students_per_semester": students_per_sem,
        "teachers_count": len(store.teachers),
        "choice_tags": tags_detail,
        "tags_detail": tags_detail,
        "lock_in_complete_count": lock_in_complete,
        "lock_in_total_students": len(students),
        "students_lock_in": students_lock_in,
        "current_run": latest_run,
    }


@router.get("")
def get_cycle_status(store: InMemoryStore = Depends(get_store)):
    return _get_cycle_status_dict(store)


@router.put("/choice-tags")
def update_cycle_choice_tags(
    payload: Any = Body(...),
    store: InMemoryStore = Depends(get_store),
):
    existing_tags = set(store.list_subject_tags())
    new_configs: Dict[str, bool] = {}

    items = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        if "configs" in payload:
            cfg = payload["configs"]
            if isinstance(cfg, list):
                items = cfg
            elif isinstance(cfg, dict):
                for k, v in cfg.items():
                    items.append({"tag": k, "is_choice_based": bool(v)})
        else:
            for k, v in payload.items():
                items.append({"tag": k, "is_choice_based": bool(v)})

    for item in items:
        if isinstance(item, dict):
            tag = item.get("tag")
            is_cb = item.get("is_choice_based", True)
        else:
            tag = getattr(item, "tag", None)
            is_cb = getattr(item, "is_choice_based", True)

        if not tag:
            continue
        if tag not in existing_tags:
            raise HTTPException(
                status_code=400,
                detail=f"Tag '{tag}' does not exist in the subject catalog.",
            )
        new_configs[tag] = bool(is_cb)

    store.set_cycle_choice_configs(new_configs)
    return _get_cycle_status_dict(store)


@router.post("/initialize")
def initialize_cycle(store: InMemoryStore = Depends(get_store)):
    """Initialize or update a generation run covering all active semesters."""
    active_semesters = sorted({s.semester for s in store.subjects.values()})
    if not active_semesters:
        raise HTTPException(
            status_code=400,
            detail="No subjects found in catalog. Upload subjects before initializing a cycle.",
        )

    # If there is an existing DRAFT run, reuse and update it
    draft_run = next((r for r in store.runs.values() if r.status == RunStatus.DRAFT), None)
    if draft_run is not None:
        draft_run.semesters = active_semesters
        run = draft_run
    else:
        run = store.create_run(semesters=active_semesters)

    run_dict = {
        "id": run.id,
        "semesters": run.semesters,
        "semester": run.semester,
        "status": run.status.value,
    }

    return {
        "run_id": run.id,
        "semesters": run.semesters,
        "semester": run.semester,
        "status": run.status.value,
        "current_run": run_dict,
    }


@router.post("/auto-lock-in")
def auto_lock_in_pending_students(store: InMemoryStore = Depends(get_store)):
    """Auto-assign a random available elective choice per tag to pending students."""
    cb_tags = store.get_choice_based_tags()
    subjects = list(store.subjects.values())
    count = 0
    for s in store.students.values():
        if store.has_complete_lock_in(s.roll_number):
            continue
        sem_subs = [sub for sub in subjects if sub.semester == s.semester and sub.subject_tag in cb_tags]
        tag_subtags = {}
        for sub in sem_subs:
            for subtag in sub.supported_subtags:
                tag_subtags.setdefault(sub.subject_tag, set()).add(subtag)

        choices = {}
        for tag, subtags in tag_subtags.items():
            if subtags:
                choices[tag] = random.choice(sorted(subtags))

        if choices:
            selections = [
                StudentChoiceSelection(roll_number=s.roll_number, tag=tag, subtag=subtag)
                for tag, subtag in choices.items()
            ]
            store.set_student_choice_selections(s.roll_number, selections)
            count += 1

    return {
        "status": "completed",
        "auto_locked_count": count,
        "cycle": _get_cycle_status_dict(store),
    }
