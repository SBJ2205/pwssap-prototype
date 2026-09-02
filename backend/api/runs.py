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
    semester: int
    choice_tags: List[ChoiceTagConfigPayload] = []


def _run_to_dict(run: GenerationRun) -> dict:
    return {
        "id": run.id,
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
    semester_errors = validate_semester(payload.semester)
    if semester_errors:
        raise HTTPException(status_code=400, detail={"errors": semester_errors})

    configs = _validate_and_build_configs(payload.choice_tags)

    # Soft, non-blocking sanity check: a tag configured with zero matching
    # subjects is probably a typo, but the admin may legitimately be
    # configuring ahead of a subject CSV upload, so this is a warning
    # rather than a hard rejection.
    available_tags = set(store.list_subject_tags(payload.semester))
    warnings = [
        f"Tag '{c.tag}' has no subjects in semester {payload.semester} yet."
        for c in configs if c.tag not in available_tags
    ]

    run = store.create_run(payload.semester)
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
