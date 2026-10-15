"""HTTP-level sanity checks for Phase 6's API surface: student time-slot
preference submission.

Run directly with (from backend/):
    venv\\Scripts\\python.exe -m tests.test_api_phase6
"""
from fastapi.testclient import TestClient

from data.store import reset_store
from domain.enums import PreferenceRating
from domain.timeslots import build_canonical_grid, is_slot_usable
from main import app

RATABLE_KEYS = [s.key for s in build_canonical_grid() if is_slot_usable(s)]

ADMIN_HEADERS = {"X-Role": "admin"}

STUDENTS_CSV = "roll_number,name,semester\n23101A0001,Asha Rao,5\n"


def _client() -> TestClient:
    reset_store()
    client = TestClient(app)
    run = client.post("/admin/runs", headers=ADMIN_HEADERS, json={"semester": 5, "choice_tags": []}).json()
    r = client.post(
        f"/admin/students/import?run_id={run['id']}",
        headers=ADMIN_HEADERS,
        files={"file": ("students.csv", STUDENTS_CSV, "text/csv")},
    )
    assert r.status_code == 200, r.text
    return client


def test_get_preferences_404_for_unknown_student():
    client = _client()
    r = client.get("/students/99999999/time-preferences")
    assert r.status_code == 404, r.text


def test_get_preferences_defaults_to_19_unrated_slots():
    client = _client()
    r = client.get("/students/23101A0001/time-preferences")
    assert r.status_code == 200, r.text
    grid = r.json()
    assert len(grid) == 19
    assert all(slot["rating"] is None for slot in grid)
    assert all(slot["slot_key"] != "Mon-1" for slot in grid)


def test_put_empty_ratings_is_rejected():
    client = _client()
    r = client.put("/students/23101A0001/time-preferences", json={"ratings": {}})
    assert r.status_code == 400, r.text


def test_put_valid_spread_ratings_saves_with_no_warnings():
    client = _client()
    ratings = {k: [1, 2, 3][i % 3] for i, k in enumerate(RATABLE_KEYS)}
    r = client.put("/students/23101A0001/time-preferences", json={"ratings": ratings})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "saved"
    assert body["warnings"] == []

    saved = client.get("/students/23101A0001/time-preferences").json()
    saved_ratings = {s["slot_key"]: s["rating"] for s in saved}
    assert saved_ratings[RATABLE_KEYS[0]] == 1


def test_put_mostly_blocked_ratings_is_rejected_and_not_saved():
    client = _client()
    ratings = {k: PreferenceRating.BLOCKED.value for k in RATABLE_KEYS[:15]}  # > 70% of 19
    r = client.put("/students/23101A0001/time-preferences", json={"ratings": ratings})
    assert r.status_code == 400, r.text

    saved = client.get("/students/23101A0001/time-preferences").json()
    assert all(slot["rating"] is None for slot in saved)


def test_put_uniform_ratings_saves_with_a_warning():
    client = _client()
    ratings = {k: PreferenceRating.TOLERABLE.value for k in RATABLE_KEYS[:6]}
    r = client.put("/students/23101A0001/time-preferences", json={"ratings": ratings})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "saved"
    assert any("rated every slot the same" in w for w in body["warnings"])


def _run_all():
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_")]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {name}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    _run_all()
