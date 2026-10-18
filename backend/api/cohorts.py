"""Traditional Division & Batch scheduling API (admin only).

Traditional mode is an optional layer *per generation run*:

  1. Describe each semester's divisions and lab batches:  POST /admin/cohorts/save
  2. Generate the run's sections from that setup:         POST /admin/cohorts/generate-sections
  3. Solve with the normal solver (POST /admin/runs/{id}/solve). For a run generated
     in traditional mode the solver hook pins every student to their saved
     division/batch and validates the result.
  4. Inspect:  GET /admin/cohorts/status and GET /admin/cohorts/validation

A run is either traditional or standard. Generating sections either way replaces
the previous sections, so the last generation wins; if standard generation
replaces a traditional run's sections the traditional plan retires itself and the
run behaves as a normal preference-weighted run.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from domain.cohorts import (
    CohortConfigError,
    build_config,
    detect_clusters as detect_semester_clusters,
    suggest_classes,
)
from domain.enums import RunStatus
from domain.traditional_plan import (
    BATCH_LAB,
    DISPERSAL,
    DIVISION_THEORY,
    get_live_plan,
    plan_staleness,
)
from domain.traditional_section_generation import generate_traditional_sections
from domain.traditional_validation import validate_traditional_run

router = APIRouter(
    prefix="/admin/cohorts",
    tags=["Cohorts"],
    dependencies=[Depends(require_admin)],
)


class ClassPayload(BaseModel):
    class_id: str = Field(..., description="e.g. Div-A, Div-B")
    class_name: Optional[str] = None
    student_rolls: List[str] = Field(default_factory=list)
    lab_batch_count: int = 3


class SaveCohortConfigPayload(BaseModel):
    semester: int
    classes: List[ClassPayload]


class GenerateSectionsPayload(BaseModel):
    run_id: int


def _bad_request(errors: List[str]) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"message": " ".join(errors), "errors": errors},
    )


def _ensure_idle(store: InMemoryStore) -> None:
    """The store is one shared timetable; never change it under a running solve."""
    active = store.get_active_solve()
    if active:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A {active.get('kind', 'solve')} is running for run #{active.get('run_id')}. "
                "Wait for it to finish or stop it first."
            ),
        )


@router.get("/detect-clusters")
def detect_clusters(
    semester: int = Query(..., ge=1, le=8),
    store: InMemoryStore = Depends(get_store),
):
    """Describe a semester: track electives, dispersal electives, in-class electives."""
    return detect_semester_clusters(store, semester)


@router.get("/suggest")
def suggest(
    semester: int = Query(..., ge=1, le=8),
    max_division_size: Optional[int] = Query(default=None, ge=1),
    store: InMemoryStore = Depends(get_store),
):
    """Suggested divisions (balanced, by roll number, inside each track)."""
    return {"semester": semester, "classes": suggest_classes(store, semester, max_division_size)}


@router.get("")
def get_cohort_config(
    semester: int = Query(..., ge=1, le=8),
    store: InMemoryStore = Depends(get_store),
):
    """The saved division/batch setup for a semester."""
    config = store.cohort_configs.get(semester)
    if not config:
        return {"semester": semester, "classes": []}
    return config.to_dict()


@router.post("/save")
def save_cohort_config(
    payload: SaveCohortConfigPayload,
    store: InMemoryStore = Depends(get_store),
):
    """Validate and save a semester's divisions; lab batches are partitioned automatically."""
    _ensure_idle(store)
    try:
        config, warnings = build_config(
            store, payload.semester, [c.model_dump() for c in payload.classes]
        )
    except CohortConfigError as exc:
        raise _bad_request(exc.errors)
    store.cohort_configs[payload.semester] = config
    return {"status": "ok", "config": config.to_dict(), "warnings": warnings}


@router.delete("")
def delete_cohort_config(
    semester: int = Query(..., ge=1, le=8),
    store: InMemoryStore = Depends(get_store),
):
    """Forget a semester's saved setup (generated sections are left as they are)."""
    _ensure_idle(store)
    store.cohort_configs.pop(semester, None)
    return {"status": "ok", "semester": semester}


@router.post("/generate-sections")
def generate_sections(
    payload: GenerateSectionsPayload,
    store: InMemoryStore = Depends(get_store),
):
    """Generate traditional sections for a run from the saved setup of each of its semesters."""
    _ensure_idle(store)
    try:
        return generate_traditional_sections(store, payload.run_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except CohortConfigError as exc:
        raise _bad_request(exc.errors)


def _require_run(store: InMemoryStore, run_id: int):
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _is_solved(run) -> bool:
    return run.status in (RunStatus.SOLVED, RunStatus.PUBLISHED)


@router.get("/status")
def get_status(
    run_id: int = Query(...),
    store: InMemoryStore = Depends(get_store),
):
    """Which mode a run is in, what was generated, and (once solved) its validation."""
    run = _require_run(store, run_id)
    semesters = list(run.semesters or [run.semester])
    plan = get_live_plan(store, run_id)
    section_count = len(store.list_sections_for_run(run_id))

    if plan is not None:
        mode = "traditional"
    elif section_count:
        mode = "standard"
    else:
        mode = "none"

    configured = [s for s in semesters if s in store.cohort_configs]
    status = {
        "run_id": run_id,
        "run_status": run.status.value,
        "semesters": semesters,
        "mode": mode,
        "stale_reason": plan_staleness(store, run_id),
        "section_count": section_count,
        "configured_semesters": configured,
        "missing_semesters": [s for s in semesters if s not in configured],
        "solved": _is_solved(run),
        "published": run.status == RunStatus.PUBLISHED,
        "config_changed": False,
        "per_semester": {},
        "generation_warnings": [],
        "students_pinned": 0,
        "synchronised_groups": 0,
        "validation": None,
    }
    if plan is None:
        return status

    status["generation_warnings"] = list(plan.warnings)
    status["students_pinned"] = len(plan.pins)
    status["synchronised_groups"] = len(plan.sync_groups)
    for sem in semesters:
        config = store.cohort_configs.get(sem)
        if config is None or config.to_dict() != plan.config_snapshot.get(sem):
            status["config_changed"] = True
        infos = [i for i in plan.sections.values() if i.semester == sem]
        status["per_semester"][str(sem)] = {
            "divisions": len({i.division for i in infos if i.division is not None}),
            "batches": len({i.batch for i in infos if i.batch is not None}),
            "sections": {
                DIVISION_THEORY: sum(1 for i in infos if i.kind == DIVISION_THEORY),
                BATCH_LAB: sum(1 for i in infos if i.kind == BATCH_LAB),
                DISPERSAL: sum(1 for i in infos if i.kind == DISPERSAL),
            },
        }
    if _is_solved(run):
        status["validation"] = validate_traditional_run(store, run, plan)
    return status


@router.get("/validation")
def get_validation(
    run_id: int = Query(...),
    store: InMemoryStore = Depends(get_store),
):
    """Validate a solved traditional run's timetable against every traditional guarantee."""
    run = _require_run(store, run_id)
    plan = get_live_plan(store, run_id)
    if plan is None:
        raise HTTPException(
            status_code=409,
            detail="This run has no live traditional sections. Generate them from the Classes & Batches page.",
        )
    if not _is_solved(run):
        return {"run_id": run_id, "solved": False, "report": None}
    return {
        "run_id": run_id,
        "solved": True,
        "report": validate_traditional_run(store, run, plan),
    }
