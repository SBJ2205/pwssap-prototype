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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from domain.enums import RunStatus

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
        tags_detail.append({
            "tag": tag,
            "is_choice_based": choice_configs.get(tag, False),
            "subtags": choice_groups.get(tag, []),
        })

    lock_in_complete = sum(1 for s in students if store.has_complete_lock_in(s.roll_number))

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
        "lock_in_complete_count": lock_in_complete,
        "lock_in_total_students": len(students),
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

    return {
        "run_id": run.id,
        "semesters": run.semesters,
        "status": run.status.value,
    }
