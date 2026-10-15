"""HTTP-level sanity checks for realigned Student API:
department-level student roster import (roll_number, name, semester)
and student elective lock-in endpoints.

Run directly with (from backend/):
    venv\\Scripts\\python.exe -m tests.test_api_phase3
"""
import sys
from fastapi.testclient import TestClient

from data.store import reset_store
from main import app

ADMIN_HEADERS = {"X-Role": "admin"}
STUDENT_HEADERS = {"X-Role": "student"}

VALID_STUDENTS_CSV = (
    "roll_number,name,semester\n"
    "23101A0001,Asha Rao,5\n"
    "23101A0002,Vivek Nair,6\n"
)

SUBJECTS_CSV = (
    "subject_code,subject_name,subject_tag,subtag,semester,type,weekly_hours,capacity\n"
    "CS501,Database Systems,program_core,,5,theory,4,60\n"
    "CS502,AI,professional_elective_1,CS_PE1_AI,5,theory,3,30\n"
    "CS503,Data Science,professional_elective_1,CS_PE1_DS,5,theory,3,30\n"
)


def _client() -> TestClient:
    reset_store()
    c = TestClient(app)
    # Import subjects and configure cycle choice tag
    c.post("/admin/subjects/import", headers=ADMIN_HEADERS, files={"file": ("subjects.csv", SUBJECTS_CSV, "text/csv")})
    c.put("/admin/cycle/choice-tags", headers=ADMIN_HEADERS, json={"configs": {"professional_elective_1": True}})
    return c


def test_import_requires_admin_role():
    client = _client()
    r = client.post(
        "/admin/students/import",
        headers=STUDENT_HEADERS,
        files={"file": ("students.csv", VALID_STUDENTS_CSV, "text/csv")},
    )
    assert r.status_code == 403, r.text


def test_import_valid_csv_multi_semester():
    client = _client()
    r = client.post(
        "/admin/students/import",
        headers=ADMIN_HEADERS,
        files={"file": ("students.csv", VALID_STUDENTS_CSV, "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "imported"
    assert body["count"] == 2

    # Listing all or by semester
    all_students = client.get("/students").json()
    assert len(all_students) == 2

    sem5_students = client.get("/students", params={"semester": 5}).json()
    assert len(sem5_students) == 1
    assert sem5_students[0]["roll_number"] == "23101A0001"


def test_import_rejects_invalid_csv_duplicate_roll():
    client = _client()
    bad_csv = "roll_number,name,semester\n23101A0001,Asha Rao,5\n23101A0001,Duplicate Rao,5\n"
    r = client.post(
        "/admin/students/import",
        headers=ADMIN_HEADERS,
        files={"file": ("students.csv", bad_csv, "text/csv")},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["status"] == "rejected"
    assert client.get("/students").json() == []


def test_student_available_choices_and_lock_in():
    client = _client()
    client.post(
        "/admin/students/import",
        headers=ADMIN_HEADERS,
        files={"file": ("students.csv", VALID_STUDENTS_CSV, "text/csv")},
    )

    # 1. Check available choices for student in sem 5
    r_avail = client.get("/students/23101A0001/available-choices")
    assert r_avail.status_code == 200, r_avail.text
    avail = r_avail.json()["available_choices"]
    assert "professional_elective_1" in avail
    assert set(avail["professional_elective_1"]) == {"CS_PE1_AI", "CS_PE1_DS"}

    # 2. Check initial lock-in status
    r_status = client.get("/students/23101A0001/lock-in")
    assert r_status.status_code == 200
    assert r_status.json()["complete"] is False

    # 3. Submit lock-in choice
    r_lock = client.put(
        "/students/23101A0001/lock-in",
        headers=STUDENT_HEADERS,
        json={"choices": {"professional_elective_1": "CS_PE1_AI"}},
    )
    assert r_lock.status_code == 200, r_lock.text
    assert r_lock.json()["complete"] is True

    # 4. Check enrolled subjects includes core and chosen elective only
    r_enrolled = client.get("/students/23101A0001/enrolled-subjects")
    assert r_enrolled.status_code == 200
    codes = [s["subject_code"] for s in r_enrolled.json()]
    assert "CS501" in codes
    assert "CS502" in codes
    assert "CS503" not in codes


def test_lock_in_validation_rejects_unknown_subtag():
    client = _client()
    client.post(
        "/admin/students/import",
        headers=ADMIN_HEADERS,
        files={"file": ("students.csv", VALID_STUDENTS_CSV, "text/csv")},
    )
    r_lock = client.put(
        "/students/23101A0001/lock-in",
        headers=STUDENT_HEADERS,
        json={"choices": {"professional_elective_1": "UNKNOWN_SUBTAG"}},
    )
    assert r_lock.status_code == 400, r_lock.text


if __name__ == "__main__":
    tests = [
        test_import_requires_admin_role,
        test_import_valid_csv_multi_semester,
        test_import_rejects_invalid_csv_duplicate_roll,
        test_student_available_choices_and_lock_in,
        test_lock_in_validation_rejects_unknown_subtag,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    if passed < len(tests):
        sys.exit(1)
