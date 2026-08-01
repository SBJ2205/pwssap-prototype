"""Solver run (admin-only) and result retrieval (anyone).

Running the solver is an admin action — it operates on the hidden teacher
timetable and should only happen once the preference window has closed.
Reading the last result is open to any caller: students need it to see
their own post-solve timetable (api/catalog.py's /sections stays hidden,
but the solved assignments themselves are the "curated" view they're
meant to see).
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from solver.service import run_solve

router = APIRouter()


class SolvePayload(BaseModel):
    fairness_index: int = 12
    faculty_weight: int = 1
    enable_gap_reduction: bool = True


@router.post("/solve", dependencies=[Depends(require_admin)])
def solve(payload: SolvePayload, store: InMemoryStore = Depends(get_store)):
    return run_solve(store, payload.fairness_index, payload.faculty_weight, payload.enable_gap_reduction)


@router.get("/results")
def get_results(store: InMemoryStore = Depends(get_store)):
    return store.get_last_result() or {"status": "NOT_RUN"}
