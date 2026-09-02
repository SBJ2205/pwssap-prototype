"""HTTP-level sanity checks for Phase 4's API surface: teacher CSV
import and subject-capability lookups.

Run directly with (from backend/):
    venv\\Scripts\\python.exe -m tests.test_api_phase4
"""
from fastapi.testclient import TestClient

from data.store import reset_store
from main import app

ADMIN_HEADERS = {"X-Role": "admin"}

SUBJECTS_CSV = (
    "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity\n"
    "IT301,Data Structures,program_core,5,theory,4,60\n"
    "IT302,OS Concepts,program_core,5,theory,4,60\n"
    "IT304,CN Lab,lab,5,lab,2,24\n"
)

TEACHERS_CSV = (
    "teacher_id,teacher_name,subject_code\n"
    "T001,Dr. Sharma,IT301,IT302\n"
    "T002,Prof. Mehta,IT301\n"
    "T003,Prof. Rao,IT304\n"
)


def _client() -> TestClient:
    reset_store()
    return TestClient(app)


def _import_subjects(client: TestClient) -> None:
    r = client.post(
        "/admin/subjects/import",
        headers=ADMIN_HEADERS,
        files={"file": ("subjects.csv", SUBJECTS_CSV, "text/csv")},
    )
    assert r.status_code == 200, r.text


def test_import_requires_admin_role():
    client = _client()
    r = client.post(
        "/admin/teachers/import",
        files={"file": ("teachers.csv", TEACHERS_CSV, "text/csv")},
    )
    assert r.status_code == 403, r.text


def test_import_rejects_subject_codes_not_yet_in_catalog():
    client = _client()  # subjects NOT imported first
    r = client.post(
        "/admin/teachers/import",
        headers=ADMIN_HEADERS,
        files={"file": ("teachers.csv", TEACHERS_CSV, "text/csv")},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["status"] == "rejected"
    assert client.get("/teachers").json() == []


def test_import_valid_csv_then_list_and_lookup_capabilities():
    client = _client()
    _import_subjects(client)

    r = client.post(
        "/admin/teachers/import",
        headers=ADMIN_HEADERS,
        files={"file": ("teachers.csv", TEACHERS_CSV, "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "imported"
    assert body["count"] == 3
    assert body["capabilities"] == 4  # 2 + 1 + 1

    teachers = client.get("/teachers").json()
    assert len(teachers) == 3

    caps = client.get("/admin/teachers/T001/capabilities", headers=ADMIN_HEADERS).json()
    assert caps["subject_codes"] == ["IT301", "IT302"]

    by_subject = client.get("/admin/subjects/IT301/teachers", headers=ADMIN_HEADERS).json()
    assert sorted(by_subject["teacher_ids"]) == ["T001", "T002"]


def test_capabilities_lookup_404_for_unknown_teacher():
    client = _client()
    _import_subjects(client)
    r = client.get("/admin/teachers/T999/capabilities", headers=ADMIN_HEADERS)
    assert r.status_code == 404, r.text


def test_teachers_for_subject_404_for_unknown_subject():
    client = _client()
    r = client.get("/admin/subjects/IT999/teachers", headers=ADMIN_HEADERS)
    assert r.status_code == 404, r.text


def test_import_rejects_duplicate_teacher_id_without_committing_anything():
    client = _client()
    _import_subjects(client)
    bad_csv = (
        "teacher_id,teacher_name,subject_code\n"
        "T001,Dr. Sharma,IT301\n"
        "T001,Dr. Sharma Again,IT302\n"
    )
    r = client.post(
        "/admin/teachers/import",
        headers=ADMIN_HEADERS,
        files={"file": ("teachers.csv", bad_csv, "text/csv")},
    )
    assert r.status_code == 400, r.text
    assert client.get("/teachers").json() == []


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
