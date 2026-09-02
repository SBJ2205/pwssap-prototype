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

Optional query param: ?time_limit=<seconds> (default 30, max 120).
"""
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
        "meetings": [{"slot_key": m.slot_key or None} for m in section.meetings],
    }


@router.post("/{run_id}/solve")
def solve_run(
    run_id: int,
    time_limit: Optional[float] = Query(default=30.0, ge=1.0, le=120.0),
    store: InMemoryStore = Depends(get_store),
):
    """Trigger the CP-SAT optimisation for a run.

    Returns the solver status, solver diagnostics, updated section list
    (with optimised teacher/slot assignments), and warnings.

    On OPTIMAL or FEASIBLE: run status is set to PUBLISHED and the store
    is updated.  On INFEASIBLE or UNKNOWN: the store is unchanged and the
    caller should inspect the warnings.
    """
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    try:
        result = run_solver_for_run(
            run_id=run_id, store=store, time_limit_seconds=time_limit or 30.0
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    sections = store.list_sections_for_run(run_id)

    return {
        "run_id": run_id,
        "status": result.status,
        "run_status": run.status.value,
        "objective_value": result.objective_value,
        "wall_time_seconds": result.wall_time_seconds,
        "num_conflicts": result.num_conflicts,
        "sections": [_section_to_dict(s) for s in sections],
        "student_section_assignments": result.student_section_assignments,
        "warnings": result.warnings,
    }
