"""HTTP-level sanity checks for Phase 7's API surface: student faculty
preference submission.

Run directly with (from backend/):
    venv\\Scripts\\python.exe -m tests.test_api_phase7
"""
from fastapi.testclient import TestClient

from data.store import reset_store
from main import app

ADMIN_HEADERS = {"X-Role": "admin"}

SUBJECTS_CSV = (
    "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity\n"
    "IT301,Data Structures,program_core,5,theory,4,60\n"
    "IT304,CN Lab,lab,5,lab,2,24\n"
)

# IT301 has two capable teachers (rankable); IT304 has only one (not rankable).
TEACHERS_CSV = (
    "teacher_id,teacher_name,subject_code\n"
    "T001,Dr. Sharma,IT301\n"
    "T002,Prof. Mehta,IT301\n"
    "T003,Prof. Rao,IT304\n"
)

STUDENTS_CSV = "roll_number,name,semester\n23101A0001,Asha Rao,5\n"


def _client() -> TestClient:
    reset_store()
    client = TestClient(app)
    assert client.post(
        "/admin/subjects/import", headers=ADMIN_HEADERS,
        files={"file": ("s.csv", SUBJECTS_CSV, "text/csv")},
    ).status_code == 200
    assert client.post(
        "/admin/teachers/import", headers=ADMIN_HEADERS,
        files={"file": ("t.csv", TEACHERS_CSV, "text/csv")},
    ).status_code == 200
    run = client.post("/admin/runs", headers=ADMIN_HEADERS, json={"semester": 5, "choice_tags": []}).json()
    assert client.post(
        f"/admin/students/import?run_id={run['id']}", headers=ADMIN_HEADERS,
        files={"file": ("st.csv", STUDENTS_CSV, "text/csv")},
    ).status_code == 200
    return client


def test_rankable_subjects_excludes_single_teacher_subjects():
    client = _client()
    r = client.get("/students/23101A0001/rankable-subjects")
    assert r.status_code == 200, r.text
    codes = {entry["subject_code"] for entry in r.json()}
    assert codes == {"IT301"}  # IT304 has only one teacher, excluded
    it301 = next(e for e in r.json() if e["subject_code"] == "IT301")
    teacher_names = sorted(t["teacher_name"] for t in it301["teachers"])
    assert teacher_names == ["Dr. Sharma", "Prof. Mehta"]


def test_get_and_put_requires_known_student():
    client = _client()
    r = client.get("/students/99999999/rankable-subjects")
    assert r.status_code == 404, r.text
    r2 = client.put(
        "/students/99999999/faculty-preferences", json={"preferences": {}}
    )
    assert r2.status_code == 404, r2.text


def test_put_valid_faculty_preference_saves():
    client = _client()
    r = client.put(
        "/students/23101A0001/faculty-preferences",
        json={"preferences": {"IT301": {"T001": 1, "T002": 2}}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "saved"

    saved = client.get("/students/23101A0001/faculty-preferences").json()
    assert saved == {"IT301": {"T001": 1, "T002": 2}}


def test_put_preference_for_non_rankable_subject_is_rejected():
    client = _client()
    r = client.put(
        "/students/23101A0001/faculty-preferences",
        json={"preferences": {"IT304": {"T003": 1}}},  # only one teacher -> not rankable
    )
    assert r.status_code == 400, r.text
    assert client.get("/students/23101A0001/faculty-preferences").json() == {}


def test_put_ineligible_teacher_is_rejected():
    client = _client()
    r = client.put(
        "/students/23101A0001/faculty-preferences",
        json={"preferences": {"IT301": {"T003": 1}}},  # T003 doesn't teach IT301
    )
    assert r.status_code == 400, r.text


def test_put_empty_preferences_is_accepted():
    client = _client()
    r = client.put("/students/23101A0001/faculty-preferences", json={"preferences": {}})
    assert r.status_code == 200, r.text


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
