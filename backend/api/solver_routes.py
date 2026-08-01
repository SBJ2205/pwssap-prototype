"""Admin-triggered solver run and result retrieval.

NOTE: there is no admin/student role check yet (see Milestone 2) — anyone
can currently call /solve. This endpoint is conceptually admin-only.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from data.store import InMemoryStore, get_store
from solver.service import run_solve

router = APIRouter()


class SolvePayload(BaseModel):
    fairness_index: int = 12
    faculty_weight: int = 1
    enable_gap_reduction: bool = True


@router.post("/solve")
def solve(payload: SolvePayload, store: InMemoryStore = Depends(get_store)):
    return run_solve(store, payload.fairness_index, payload.faculty_weight, payload.enable_gap_reduction)


@router.get("/results")
def get_results(store: InMemoryStore = Depends(get_store)):
    return store.get_last_result() or {"status": "NOT_RUN"}
