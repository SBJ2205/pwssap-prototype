"""Unit tests for timetable run snapshot persistence, activation, and comparison."""
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from data.store import get_store, reset_store
from domain.enums import RunStatus
from domain.models import Meeting, Section
from domain.saved_runs import (
    SAVED_RUNS_DIR,
    activate_saved_run,
    compare_saved_runs,
    delete_saved_snapshot,
    get_saved_snapshot,
    list_saved_snapshots,
    save_run_snapshot,
)
from main import app

ADMIN_HEADERS = {"X-Role": "admin"}


@pytest.fixture(autouse=True)
def clean_saved_runs():
    """Ensure clean saved_runs directory for isolated tests."""
    SAVED_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    yield
    # Clean up test artifacts
    for f in SAVED_RUNS_DIR.glob("run_test_*.json"):
        f.unlink(missing_ok=True)


def test_save_and_retrieve_run_snapshot():
    reset_store()
    store = get_store()

    # Create run and sections
    run = store.create_run(semesters=[4, 6])
    sec1 = Section(id=101, run_id=run.id, subject_code="CS401", label="CS401-T1", teacher_id="T01", capacity=30,
                   meetings=[Meeting(slot_key="Mon-1", duration_hours=2)])
    store.sections[sec1.id] = sec1
    store.enroll_student("25101A0001", "CS401", sec1.id)
    store.latest_solve_results[run.id] = {
        "status": "OPTIMAL",
        "objective_value": 42000,
        "blocked_placements": 5,
        "wall_time_seconds": 12.3,
        "num_conflicts": 100,
    }

    # Save snapshot
    snap = save_run_snapshot(store, run.id, label="Even Sem Elective Test")
    assert snap is not None
    assert snap["run_id"] == run.id
    assert snap["mode"] == "elective"
    assert snap["semesters"] == [4, 6]
    assert snap["metrics"]["blocked_placements"] == 5

    # Retrieve from list
    snapshots = list_saved_snapshots()
    found = next((s for s in snapshots if s["snapshot_id"] == snap["snapshot_id"]), None)
    assert found is not None
    assert found["label"] == "Even Sem Elective Test"

    # Clean up
    delete_saved_snapshot(snap["snapshot_id"])


def test_activate_saved_run_restores_store_state():
    reset_store()
    store = get_store()

    run = store.create_run(semesters=[3, 5, 7])
    sec = Section(id=201, run_id=run.id, subject_code="CS501", label="CS501-T1", teacher_id="T02", capacity=40,
                  meetings=[Meeting(slot_key="Tue-2", duration_hours=2)])
    store.sections[sec.id] = sec
    store.enroll_student("23101A0005", "CS501", sec.id)
    store.latest_solve_results[run.id] = {
        "status": "FEASIBLE",
        "objective_value": 85000,
        "blocked_placements": 18,
    }

    snap = save_run_snapshot(store, run.id, label="Odd Sem Baseline")
    assert snap is not None

    # Clear current sections and student assignments to simulate switching to another run
    store.clear_sections_for_run(run.id)
    store.student_section_assignments.clear()
    assert store.list_sections_for_run(run.id) == []
    assert store.student_section_assignments == {}

    # Activate saved snapshot
    res = activate_saved_run(store, snap["snapshot_id"])
    assert res["ok"] is True
    assert res["active_run_id"] == run.id

    # Verify sections and enrollments were restored
    restored_sec = store.sections.get(201)
    assert restored_sec is not None
    assert restored_sec.subject_code == "CS501"
    assert store.student_section_assignments.get("23101A0005", {}).get("CS501") == 201

    delete_saved_snapshot(snap["snapshot_id"])


def test_compare_saved_runs():
    reset_store()
    store = get_store()

    # Traditional run mock
    run1 = store.create_run(semesters=[4, 6])
    store.latest_solve_results[run1.id] = {
        "status": "FEASIBLE",
        "objective_value": 500000,
        "blocked_placements": 200,
        "wall_time_seconds": 45.0,
    }
    snap1 = save_run_snapshot(store, run1.id, label="Traditional")

    # Elective run mock
    run2 = store.create_run(semesters=[4, 6])
    store.latest_solve_results[run2.id] = {
        "status": "OPTIMAL",
        "objective_value": 50000,
        "blocked_placements": 10,
        "wall_time_seconds": 60.0,
    }
    snap2 = save_run_snapshot(store, run2.id, label="Elective")

    comparison = compare_saved_runs(store, snap1["snapshot_id"], snap2["snapshot_id"])
    assert comparison["run_a"]["blocked_placements"] == 200
    assert comparison["run_b"]["blocked_placements"] == 10
    # 200 -> 10 is 95% reduction
    assert comparison["deltas"]["blocked_improvement_pct"] == 95.0
    assert "reduced student blocked-slot violations by 95.0%" in comparison["takeaway"]

    delete_saved_snapshot(snap1["snapshot_id"])
    delete_saved_snapshot(snap2["snapshot_id"])


def test_saved_runs_api_endpoints():
    client = TestClient(app, raise_server_exceptions=True)
    reset_store()
    store = get_store()

    run = store.create_run(semesters=[4, 6])
    sec = Section(id=301, run_id=run.id, subject_code="PCIT05T", label="PCIT05T-T1", teacher_id="T01", capacity=30,
                  meetings=[Meeting(slot_key="Wed-3", duration_hours=2)])
    store.sections[sec.id] = sec
    store.latest_solve_results[run.id] = {
        "status": "OPTIMAL",
        "objective_value": 15000,
        "blocked_placements": 2,
    }

    # Save via API
    resp = client.post(f"/admin/runs/{run.id}/save-snapshot", headers=ADMIN_HEADERS, json={"label": "API Test Run"})
    assert resp.status_code == 200
    snap_id = resp.json()["snapshot"]["snapshot_id"]

    # List via API
    list_resp = client.get("/admin/runs/saved", headers=ADMIN_HEADERS)
    assert list_resp.status_code == 200
    snaps = list_resp.json()["snapshots"]
    assert any(s["snapshot_id"] == snap_id for s in snaps)

    # Activate via API
    act_resp = client.post(f"/admin/runs/saved/{snap_id}/activate", headers=ADMIN_HEADERS)
    assert act_resp.status_code == 200
    assert act_resp.json()["ok"] is True

    # Delete via API
    del_resp = client.delete(f"/admin/runs/saved/{snap_id}", headers=ADMIN_HEADERS)
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True
