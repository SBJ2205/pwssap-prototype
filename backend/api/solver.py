"""Admin API for triggering the solver (Phase 9).

Route:
  POST /admin/runs/{run_id}/solve
      Runs the CP-SAT solver for the given generation run.
      - Requires sections to have been generated first (Phase 8).
      - Sections are regenerated implicitly if none exist.
      - Returns the solver status + section assignments.
      - On success, the run's status transitions to PUBLISHED automatically
        (product decision #13: results are auto-published after solving).

This endpoint is synchronous (runs the solver in the request thread).
For large instances the 30-second CP-SAT time limit is the natural
bound; the solver returns FEASIBLE rather than OPTIMAL if it times out.

Optional query param: ?time_limit=<seconds> (default 30, max 3600).
"""
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from domain.models import Section
from solver.service import run_solver_for_run

router = APIRouter(prefix="/admin/runs", dependencies=[Depends(require_admin)])


def _section_to_dict(section: Section) -> dict:
    return {
        "id": section.id,
        "run_id": section.run_id,
        "subject_code": section.subject_code,
        "label": section.label,
        "teacher_id": section.teacher_id,
        "capacity": section.capacity,
        "meetings": [
            {
                "slot_key": m.slot_key or None,
                "duration_hours": m.duration_hours,
                "slot_part": m.slot_part,
            }
            for m in section.meetings
        ],
    }


def _claim_solve_slot(store: InMemoryStore, run_id: int, kind: str) -> None:
    """Only one solve/feasibility check may run at a time (409 otherwise)."""
    if not store.try_begin_solve(run_id, kind):
        active = store.get_active_solve() or {}
        raise HTTPException(
            status_code=409,
            detail=(
                f"A {active.get('kind', 'solve')} is already running for run #{active.get('run_id')}. "
                "Wait for it to finish or stop it first."
            ),
        )


@router.get("/solve/status")
def get_solve_status(store: InMemoryStore = Depends(get_store)):
    """Whether a solve is currently running (lets a reloaded UI reattach)."""
    active = store.get_active_solve()
    if active is None:
        return {"active": False}
    return {
        "active": True,
        "run_id": active["run_id"],
        "kind": active["kind"],
        "elapsed_seconds": round(time.time() - active["started_at"], 1),
    }


@router.post("/{run_id}/solve")
def solve_run(
    run_id: int,
    time_limit: Optional[float] = Query(default=30.0, ge=1.0, le=3600.0),
    candidates: Optional[int] = Query(default=1, ge=1, le=10),
    store: InMemoryStore = Depends(get_store),
):
    """Trigger the CP-SAT optimisation for a run.

    Returns the solver status, solver diagnostics, updated section list
    (with optimised teacher/slot assignments), candidate solutions, and warnings.

    On OPTIMAL or FEASIBLE: run status is set to PUBLISHED and the store
    is updated.  On INFEASIBLE or UNKNOWN: the store is unchanged and the
    caller should inspect the warnings.
    """
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    _claim_solve_slot(store, run_id, "solve")
    try:
        # Clear any previous cancellation requests for this run
        store.cancel_requested_runs.discard(run_id)
        result = run_solver_for_run(
            run_id=run_id,
            store=store,
            time_limit_seconds=time_limit or 30.0,
            candidate_count=candidates or 1,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        store.cancel_requested_runs.discard(run_id)
        store.end_solve(run_id)

    sections = store.list_sections_for_run(run_id)

    resp = {
        "run_id": run_id,
        "status": result.status,
        "run_status": run.status.value,
        "objective_value": result.objective_value,
        "wall_time_seconds": result.wall_time_seconds,
        "num_conflicts": result.num_conflicts,
        "stage1_status": result.stage1_status,
        "stage2_status": result.stage2_status,
        "blocked_placements": result.blocked_placements,
        "blocked_minimum_proven": result.blocked_minimum_proven,
        "penalty_breakdown": getattr(result, "penalty_breakdown", {}),
        "sections": [_section_to_dict(s) for s in sections],
        "student_section_assignments": result.student_section_assignments,
        "candidates": result.candidates,
        "warnings": result.warnings,
    }

    # Cache for UI persistence across page switches
    store.latest_solve_results[run_id] = resp
    store.active_run_id = run_id
    try:
        from domain.saved_runs import save_run_snapshot
        save_run_snapshot(store, run_id)
    except Exception:
        pass
    return resp


@router.get("/{run_id}/solve-result")
def get_solve_result(run_id: int, store: InMemoryStore = Depends(get_store)):
    """Retrieve the cached solver diagnostics and leaderboard for a run."""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    result = store.latest_solve_results.get(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No solve result recorded for this run")
    return result


@router.post("/{run_id}/cancel")
def cancel_solve(run_id: int, store: InMemoryStore = Depends(get_store)):
    """Request early cancellation of an active solver execution."""
    store.cancel_requested_runs.add(run_id)
    return {"run_id": run_id, "status": "cancellation_requested"}


@router.post("/{run_id}/feasibility")
def check_feasibility(
    run_id: int,
    time_limit: Optional[float] = Query(default=30.0, ge=1.0, le=3600.0),
    store: InMemoryStore = Depends(get_store),
):
    """Check hard constraints without optimizing or publishing results."""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    _claim_solve_slot(store, run_id, "feasibility check")
    try:
        store.cancel_requested_runs.discard(run_id)
        result = run_solver_for_run(
            run_id=run_id,
            store=store,
            time_limit_seconds=time_limit or 30.0,
            feasibility_only=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        store.cancel_requested_runs.discard(run_id)
        store.end_solve(run_id)

    return {
        "run_id": run_id,
        "status": result.status,
        "feasible": result.status in ("OPTIMAL", "FEASIBLE"),
        "wall_time_seconds": result.wall_time_seconds,
        "num_conflicts": result.num_conflicts,
        "warnings": result.warnings,
    }
