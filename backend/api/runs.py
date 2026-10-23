"""Admin choice-tag configuration for one semester-scoped generation run
(product decisions #2 and #3).

A run's choice_tag_configs mapping (which subject_tag values are
choice-based, and what numeric value each maps to) is only ever valid
for that one run. It is NOT a global setting reused across semesters or
across repeated runs of the same semester — a new run always starts from
an explicit, fresh configuration.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from domain.models import ChoiceTagConfig, GenerationRun
from domain.validation import validate_choice_tag_configs, validate_semester

router = APIRouter(prefix="/admin/runs", dependencies=[Depends(require_admin)])


class ChoiceTagConfigPayload(BaseModel):
    tag: str
    numeric_value: int
    is_choice_based: bool = True


class CreateRunPayload(BaseModel):
    semester: Optional[int] = None
    semesters: Optional[List[int]] = None
    choice_tags: List[ChoiceTagConfigPayload] = []


def _run_to_dict(run: GenerationRun) -> dict:
    return {
        "id": run.id,
        "semesters": run.semesters,
        "semester": run.semester,
        "status": run.status.value if hasattr(run.status, "value") else run.status,
        "choice_tag_configs": [
            {"tag": c.tag, "numeric_value": c.numeric_value, "is_choice_based": c.is_choice_based}
            for c in run.choice_tag_configs
        ],
    }


def _validate_and_build_configs(payload_tags: List[ChoiceTagConfigPayload]) -> List[ChoiceTagConfig]:
    configs = [
        ChoiceTagConfig(tag=c.tag, numeric_value=c.numeric_value, is_choice_based=c.is_choice_based)
        for c in payload_tags
    ]
    errors = validate_choice_tag_configs(configs)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    return configs


class SaveSnapshotPayload(BaseModel):
    label: Optional[str] = None


@router.get("/saved")
def get_saved_runs(store: InMemoryStore = Depends(get_store)):
    """List all saved timetable runs across all semester cycles."""
    from domain.saved_runs import list_saved_snapshots, get_active_snapshot_id
    active_snap = get_active_snapshot_id(store)
    return {
        "snapshots": list_saved_snapshots(store),
        "active_snapshot_id": active_snap,
    }


@router.get("/compare")
def compare_runs(run_a: str, run_b: str, store: InMemoryStore = Depends(get_store)):
    """Generate a side-by-side comparison between two saved run snapshots."""
    from domain.saved_runs import compare_saved_runs
    try:
        return compare_saved_runs(store, run_a, run_b)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/saved/{snapshot_id}/activate")
def activate_run(snapshot_id: str, store: InMemoryStore = Depends(get_store)):
    """Set a saved run snapshot as the active timetable in the live portal."""
    from domain.saved_runs import activate_saved_run
    try:
        return activate_saved_run(store, snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/saved/{snapshot_id}")
def delete_run_snapshot(snapshot_id: str):
    """Delete a saved run snapshot file."""
    from domain.saved_runs import delete_saved_snapshot
    if not delete_saved_snapshot(snapshot_id):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"ok": True, "deleted": snapshot_id}


@router.post("/{run_id}/save-snapshot")
def save_snapshot_endpoint(
    run_id: int, payload: Optional[SaveSnapshotPayload] = None, store: InMemoryStore = Depends(get_store)
):
    """Explicitly save or re-label a snapshot of a run."""
    from domain.saved_runs import save_run_snapshot
    label = payload.label if payload else None
    res = save_run_snapshot(store, run_id, label=label)
    if res is None:
        raise HTTPException(status_code=400, detail=f"Failed to create snapshot for run {run_id}. Run might not exist.")
    return {"ok": True, "snapshot": res}


@router.get("")
def list_runs(semester: Optional[int] = None, store: InMemoryStore = Depends(get_store)):
    return [_run_to_dict(r) for r in store.list_runs(semester)]


@router.get("/{run_id}")
def get_run(run_id: int, store: InMemoryStore = Depends(get_store)):
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_dict(run)


@router.post("")
def create_run(payload: CreateRunPayload, store: InMemoryStore = Depends(get_store)):
    if payload.semesters:
        sem_list = payload.semesters
    elif payload.semester is not None:
        sem_list = [payload.semester]
    else:
        sem_list = sorted({s.semester for s in store.subjects.values()})

    for s in sem_list:
        errors = validate_semester(s)
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})

    configs = _validate_and_build_configs(payload.choice_tags)

    available_tags = set(store.list_subject_tags())
    warnings = [
        f"Tag '{c.tag}' has no subjects in the catalog yet."
        for c in configs if c.tag not in available_tags
    ]

    run = store.create_run(semesters=sem_list)
    store.set_run_choice_tags(run.id, configs)

    response = _run_to_dict(run)
    response["warnings"] = warnings
    return response


@router.put("/{run_id}/choice-tags")
def update_run_choice_tags(
    run_id: int, payload: List[ChoiceTagConfigPayload], store: InMemoryStore = Depends(get_store)
):
    """Replace a run's choice-tag configuration wholesale (e.g. the admin
    adjusting the mapping before students start submitting choices)."""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    configs = _validate_and_build_configs(payload)
    store.set_run_choice_tags(run_id, configs)
    return _run_to_dict(run)
