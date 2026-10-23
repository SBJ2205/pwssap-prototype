"""HTTP-level tests for run lifecycle safety.

  * Only one solve / feasibility check may run at a time (409), and
    /admin/runs/solve/status reports it so a reloaded UI can reattach.
  * An unsolved (draft) run exposes no placeholder teachers or slots.
  * Regenerating sections never leaves dangling student assignments, never
    reuses section ids, and puts the run back to DRAFT.
  * Teacher timetable without ?run_id never mixes in unsolved/stale runs.

Run with:  venv\\Scripts\\python.exe -m pytest tests/test_api_run_lifecycle.py -q
"""
import sys

sys.path.insert(0, ".")

import pytest
from fastapi.testclient import TestClient

from data.store import get_store, reset_store
from main import app

ADMIN = {"X-Role": "admin"}

SUBJECTS_CSV = (
    "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity\n"
    "IT401,Operating Systems,program_core,5,theory,4,30\n"
    "IT402,OS Lab,lab,5,lab,2,12\n"
)
TEACHERS_CSV = (
    "teacher_id,teacher_name,IT401,IT402\n"
    "T101,Dr. Rho,IT401,IT402\n"
    "T102,Dr. Sigma,IT401\n"
)
STUDENTS_CSV = "roll_number,name,semester\nR001,Carol,5\nR002,Dave,5\n"


@pytest.fixture()
def client():
    reset_store()
    c = TestClient(app, raise_server_exceptions=True)
    c.post("/admin/subjects/import", headers=ADMIN, files={"file": ("s.csv", SUBJECTS_CSV, "text/csv")})
    c.post("/admin/teachers/import", headers=ADMIN, files={"file": ("t.csv", TEACHERS_CSV, "text/csv")})
    c.post("/admin/students/import", headers=ADMIN, files={"file": ("st.csv", STUDENTS_CSV, "text/csv")})
    return c


def _new_run_with_sections(c):
    run_id = c.post("/admin/cycle/initialize", headers=ADMIN).json()["run_id"]
    c.post(f"/admin/runs/{run_id}/generate-sections", headers=ADMIN)
    return run_id


def _solved_run(c):
    run_id = _new_run_with_sections(c)
    assert c.post(f"/admin/runs/{run_id}/solve", headers=ADMIN).json()["run_status"] == "published"
    return run_id


# ── concurrency guard ────────────────────────────────────────────────────

def test_second_solve_while_one_is_running_is_rejected_with_409(client):
    run_id = _new_run_with_sections(client)
    store = get_store()
    assert store.try_begin_solve(run_id, "solve")
    try:
        r = client.post(f"/admin/runs/{run_id}/solve", headers=ADMIN)
        assert r.status_code == 409
        assert "already running" in r.json()["detail"]
        r = client.post(f"/admin/runs/{run_id}/feasibility", headers=ADMIN)
        assert r.status_code == 409
    finally:
        store.end_solve(run_id)


def test_solve_status_reports_active_then_idle_and_slot_is_released(client):
    run_id = _new_run_with_sections(client)
    store = get_store()
    assert client.get("/admin/runs/solve/status", headers=ADMIN).json() == {"active": False}

    store.try_begin_solve(run_id, "solve")
    st = client.get("/admin/runs/solve/status", headers=ADMIN).json()
    assert st["active"] is True and st["run_id"] == run_id and st["kind"] == "solve"
    store.end_solve(run_id)

    # A normal solve claims and then releases the slot (also on the error path).
    assert client.post(f"/admin/runs/{run_id}/solve", headers=ADMIN).status_code == 200
    assert client.get("/admin/runs/solve/status", headers=ADMIN).json() == {"active": False}
    assert client.post("/admin/runs/999/solve", headers=ADMIN).status_code == 404
    assert client.get("/admin/runs/solve/status", headers=ADMIN).json() == {"active": False}


def test_solve_response_carries_stage_statuses_and_blocked_count(client):
    run_id = _new_run_with_sections(client)
    body = client.post(f"/admin/runs/{run_id}/solve", headers=ADMIN).json()
    assert body["stage1_status"] in ("OPTIMAL", "FEASIBLE")
    assert body["stage2_status"] in ("OPTIMAL", "FEASIBLE")
    assert body["blocked_placements"] == 0
    assert {"stage1_status", "blocked_placements"} <= set(body["candidates"][0])


def test_multi_candidate_solve_serialises_through_the_api(client):
    run_id = _new_run_with_sections(client)
    r = client.post(f"/admin/runs/{run_id}/solve", headers=ADMIN, params={"candidates": 2, "time_limit": 60})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["run_status"] == "published"
    best = [c for c in body["candidates"] if c["is_best"]]
    assert len(best) == 1 and best[0]["objective_value"] == body["objective_value"]
    for c in body["candidates"]:
        if not c["is_best"]:
            assert c["objective_value"] is None
    assert client.get("/students/R001/sections").json()["timetable"]


# ── unsolved runs expose no placeholders ─────────────────────────────────

def test_unsolved_run_summary_hides_placeholder_teachers_and_slots(client):
    run_id = _new_run_with_sections(client)
    summary = client.get(f"/admin/runs/{run_id}/summary", headers=ADMIN).json()

    assert summary["solved"] is False and summary["run_status"] == "draft"
    assert summary["section_count"] > 0
    assert summary["weekly_grid"] == {}
    for sec in summary["sections"]:
        assert sec["teacher_id"] is None
        assert all(m["slot_key"] is None and m["day"] is None for m in sec["meetings"])


def test_teacher_timetable_is_empty_for_unsolved_run(client):
    run_id = _new_run_with_sections(client)
    for kwargs in ({}, {"params": {"run_id": run_id}}):
        d = client.get("/teachers/T101/timetable", **kwargs).json()
        assert d["solved"] is False
        assert d["section_count"] == 0 and d["schedule"] == []


def test_solved_run_shows_real_teachers_and_slots(client):
    run_id = _solved_run(client)
    summary = client.get(f"/admin/runs/{run_id}/summary", headers=ADMIN).json()
    assert summary["solved"] is True
    assert summary["weekly_grid"]
    assert all(sec["teacher_id"] for sec in summary["sections"])
    assert client.get("/teachers/T101/timetable").json()["solved"] is True


# ── regeneration / multiple runs ─────────────────────────────────────────

def test_regenerating_sections_clears_assignments_and_resets_run(client):
    run_id = _solved_run(client)
    store = get_store()
    old_ids = {s.id for s in store.list_sections_for_run(run_id)}
    assert client.get("/students/R001/sections").json()["timetable"]

    client.post(f"/admin/runs/{run_id}/generate-sections", headers=ADMIN)

    assert client.get(f"/admin/runs/{run_id}", headers=ADMIN).json()["status"] == "draft"
    assert client.get("/students/R001/sections").json()["timetable"] == []
    assert store.student_section_assignments == {}
    new_ids = {s.id for s in store.list_sections_for_run(run_id)}
    assert new_ids and not (new_ids & old_ids), "section ids must never be reused"
    assert client.get(f"/admin/runs/{run_id}/solve-result", headers=ADMIN).status_code == 404


def test_new_run_supersedes_the_old_runs_sections(client):
    first = _solved_run(client)
    store = get_store()
    second = store.create_run(semesters=[5]).id

    client.post(f"/admin/runs/{second}/generate-sections", headers=ADMIN)

    assert store.list_sections_for_run(first) == []
    assert client.get(f"/admin/runs/{first}", headers=ADMIN).json()["status"] == "draft"
    assert client.get("/students/R001/sections").json()["timetable"] == []
    # Teacher view without run_id falls back to nothing, not to a stale run.
    d = client.get("/teachers/T101/timetable").json()
    assert d["schedule"] == [] and d["solved"] is False

    client.post(f"/admin/runs/{second}/solve", headers=ADMIN)
    d = client.get("/teachers/T101/timetable").json()
    assert d["run_id"] == second and d["solved"] is True
    assert {s["run_id"] for s in d["schedule"]} <= {second}
