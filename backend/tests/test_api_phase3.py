"""HTTP-level sanity checks for Phase 3's API surface: run-scoped student
CSV import.

Run directly with (from backend/):
    venv\\Scripts\\python.exe -m tests.test_api_phase3
"""
from fastapi.testclient import TestClient

from data.store import reset_store
from main import app

ADMIN_HEADERS = {"X-Role": "admin"}

VALID_STUDENTS_CSV = (
    "roll_number,name,semester,choice_1,choice_2\n"
    "23101A0001,Asha Rao,5,1,2\n"
    "23101A0002,Vivek Nair,5,2,1\n"
)


def _client() -> TestClient:
    reset_store()
    return TestClient(app)


def _create_run(client: TestClient, semester: int = 5) -> int:
    r = client.post("/admin/runs", headers=ADMIN_HEADERS, json={
        "semester": semester,
        "choice_tags": [
            {"tag": "open_elective", "numeric_value": 1},
            {"tag": "mdm", "numeric_value": 2},
        ],
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_import_requires_admin_role():
    client = _client()
    run_id = _create_run(client)
    r = client.post(
        f"/admin/students/import?run_id={run_id}",
        files={"file": ("students.csv", VALID_STUDENTS_CSV, "text/csv")},
    )
    assert r.status_code == 403, r.text


def test_import_with_unknown_run_id_is_404():
    client = _client()
    r = client.post(
        "/admin/students/import?run_id=999",
        headers=ADMIN_HEADERS,
        files={"file": ("students.csv", VALID_STUDENTS_CSV, "text/csv")},
    )
    assert r.status_code == 404, r.text


def test_import_rejects_invalid_csv_without_committing_anything():
    client = _client()
    run_id = _create_run(client)
    bad_csv = "roll_number,name,semester,choice_1,choice_2\n23101A0001,Asha Rao,5,9,2\n"
    r = client.post(
        f"/admin/students/import?run_id={run_id}",
        headers=ADMIN_HEADERS,
        files={"file": ("students.csv", bad_csv, "text/csv")},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["status"] == "rejected"
    assert client.get("/students").json() == []


def test_import_valid_csv_then_list_and_fetch_choices():
    client = _client()
    run_id = _create_run(client)
    r = client.post(
        f"/admin/students/import?run_id={run_id}",
        headers=ADMIN_HEADERS,
        files={"file": ("students.csv", VALID_STUDENTS_CSV, "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "imported"
    assert body["count"] == 2

    students = client.get("/students", params={"semester": 5}).json()
    assert len(students) == 2

    choices = client.get(
        "/admin/students/23101A0001/choices", headers=ADMIN_HEADERS, params={"run_id": run_id}
    ).json()
    assert choices == [
        {"choice_column": 1, "numeric_value": 1, "tag": "open_elective"},
        {"choice_column": 2, "numeric_value": 2, "tag": "mdm"},
    ]


def test_import_rejects_students_from_a_different_semester():
    client = _client()
    run_id = _create_run(client, semester=5)
    csv_text = "roll_number,name,semester,choice_1,choice_2\n23101A0001,Asha Rao,6,1,2\n"
    r = client.post(
        f"/admin/students/import?run_id={run_id}",
        headers=ADMIN_HEADERS,
        files={"file": ("students.csv", csv_text, "text/csv")},
    )
    assert r.status_code == 400, r.text
    errors = r.json()["detail"]["row_errors"][0]["errors"]
    assert any("does not match run semester" in e for e in errors)


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
