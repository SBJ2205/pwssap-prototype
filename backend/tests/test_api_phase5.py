"""HTTP-level sanity checks for Phase 5's API surface: admin-managed
teacher availability (a hard constraint, not a preference).

Run directly with (from backend/):
    venv\\Scripts\\python.exe -m tests.test_api_phase5
"""
from fastapi.testclient import TestClient

from data.store import reset_store
from domain.validation import validate_slot_keys
from main import app

ADMIN_HEADERS = {"X-Role": "admin"}

TEACHERS_CSV = "teacher_id,teacher_name,subject_code\nT001,Dr. Sharma\n"


def _client() -> TestClient:
    reset_store()
    return TestClient(app)


def _import_teacher(client: TestClient) -> None:
    r = client.post(
        "/admin/teachers/import",
        headers=ADMIN_HEADERS,
        files={"file": ("teachers.csv", TEACHERS_CSV, "text/csv")},
    )
    assert r.status_code == 200, r.text


def test_validate_slot_keys_rejects_unknown_keys():
    assert validate_slot_keys(["Mon-2"], {"Mon-1", "Mon-2"}) == []
    errors = validate_slot_keys(["Mon-2", "Xyz-9"], {"Mon-1", "Mon-2"})
    assert errors and "Xyz-9" in errors[0]


def test_get_availability_requires_admin_role():
    client = _client()
    _import_teacher(client)
    r = client.get("/admin/teachers/T001/availability")
    assert r.status_code == 403, r.text


def test_get_availability_404_for_unknown_teacher():
    client = _client()
    r = client.get("/admin/teachers/T999/availability", headers=ADMIN_HEADERS)
    assert r.status_code == 404, r.text


def test_get_availability_defaults_all_20_slots_to_available():
    client = _client()
    _import_teacher(client)
    r = client.get("/admin/teachers/T001/availability", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    grid = r.json()
    assert len(grid) == 20
    assert all(slot["available"] is True for slot in grid)
    mon1 = next(s for s in grid if s["slot_key"] == "Mon-1")
    assert mon1["day"] == "Mon" and mon1["slot_index"] == 1


def test_put_availability_blocks_specific_slots_and_persists():
    client = _client()
    _import_teacher(client)
    r = client.put(
        "/admin/teachers/T001/availability",
        headers=ADMIN_HEADERS,
        json={"slots": {"Tue-1": False, "Wed-3": False}},
    )
    assert r.status_code == 200, r.text
    grid = {s["slot_key"]: s["available"] for s in r.json()}
    assert grid["Tue-1"] is False
    assert grid["Wed-3"] is False
    assert grid["Mon-2"] is True  # untouched slot stays available

    # Persists across a fresh GET.
    r2 = client.get("/admin/teachers/T001/availability", headers=ADMIN_HEADERS)
    grid2 = {s["slot_key"]: s["available"] for s in r2.json()}
    assert grid2["Tue-1"] is False
    assert grid2["Wed-3"] is False


def test_put_availability_can_re_enable_a_previously_blocked_slot():
    client = _client()
    _import_teacher(client)
    client.put(
        "/admin/teachers/T001/availability", headers=ADMIN_HEADERS, json={"slots": {"Tue-1": False}}
    )
    r = client.put(
        "/admin/teachers/T001/availability", headers=ADMIN_HEADERS, json={"slots": {"Tue-1": True}}
    )
    grid = {s["slot_key"]: s["available"] for s in r.json()}
    assert grid["Tue-1"] is True


def test_put_availability_rejects_unknown_slot_key():
    client = _client()
    _import_teacher(client)
    r = client.put(
        "/admin/teachers/T001/availability",
        headers=ADMIN_HEADERS,
        json={"slots": {"Mon-1": False, "Xyz-9": False}},
    )
    assert r.status_code == 400, r.text
    assert "Xyz-9" in r.json()["detail"]["errors"][0]


def test_put_availability_404_for_unknown_teacher():
    client = _client()
    r = client.put(
        "/admin/teachers/T999/availability", headers=ADMIN_HEADERS, json={"slots": {"Mon-2": False}}
    )
    assert r.status_code == 404, r.text


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
