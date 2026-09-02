"""HTTP-level sanity checks for Phase 2's API surface: subject CSV import
and admin choice-tag/run configuration.

Run directly with (from backend/):
    venv\\Scripts\\python.exe -m tests.test_api_phase2
"""
from fastapi.testclient import TestClient

from data.store import reset_store
from main import app

VALID_CSV = (
    "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity,slot_structure\n"
    "IT301,Data Structures,program_core,5,theory,4,60,2+2\n"
    "IT304,CN Lab,lab,5,lab,2,24,\n"
    "IT310,Cloud Computing,open_elective,5,theory,3,40,\n"
    "IT320,Ethics,mdm,5,theory,2,50,\n"
)

ADMIN_HEADERS = {"X-Role": "admin"}


def _client() -> TestClient:
    reset_store()
    return TestClient(app)


def test_import_requires_admin_role():
    client = _client()
    r = client.post(
        "/admin/subjects/import",
        files={"file": ("subjects.csv", VALID_CSV, "text/csv")},
    )
    assert r.status_code == 403, r.text


def test_import_rejects_invalid_csv_without_committing_anything():
    client = _client()
    bad_csv = "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity\nIT301,DS,tag,2,theory,4,60\n"
    r = client.post(
        "/admin/subjects/import",
        headers=ADMIN_HEADERS,
        files={"file": ("subjects.csv", bad_csv, "text/csv")},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["status"] == "rejected"
    assert client.get("/subjects").json() == []


def test_import_valid_csv_then_list_and_filter_by_semester():
    client = _client()
    r = client.post(
        "/admin/subjects/import",
        headers=ADMIN_HEADERS,
        files={"file": ("subjects.csv", VALID_CSV, "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "imported"
    assert body["count"] == 4
    assert body["semesters"] == [5]

    all_subjects = client.get("/subjects").json()
    assert len(all_subjects) == 4

    sem5 = client.get("/subjects", params={"semester": 5}).json()
    assert len(sem5) == 4
    sem6 = client.get("/subjects", params={"semester": 6}).json()
    assert sem6 == []


def test_admin_can_list_distinct_subject_tags_for_semester():
    client = _client()
    client.post(
        "/admin/subjects/import",
        headers=ADMIN_HEADERS,
        files={"file": ("subjects.csv", VALID_CSV, "text/csv")},
    )
    r = client.get("/admin/subjects/tags", headers=ADMIN_HEADERS, params={"semester": 5})
    assert r.status_code == 200, r.text
    assert sorted(r.json()["tags"]) == ["lab", "mdm", "open_elective", "program_core"]


def test_create_run_with_choice_tags_and_warning_for_unknown_tag():
    client = _client()
    client.post(
        "/admin/subjects/import",
        headers=ADMIN_HEADERS,
        files={"file": ("subjects.csv", VALID_CSV, "text/csv")},
    )
    payload = {
        "semester": 5,
        "choice_tags": [
            {"tag": "open_elective", "numeric_value": 1, "is_choice_based": True},
            {"tag": "mdm", "numeric_value": 2, "is_choice_based": True},
            {"tag": "professional_elective", "numeric_value": 3, "is_choice_based": True},
        ],
    }
    r = client.post("/admin/runs", headers=ADMIN_HEADERS, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["semester"] == 5
    assert len(body["choice_tag_configs"]) == 3
    assert any("professional_elective" in w for w in body["warnings"])

    fetched = client.get(f"/admin/runs/{body['id']}", headers=ADMIN_HEADERS).json()
    assert fetched["choice_tag_configs"] == body["choice_tag_configs"]


def test_create_run_rejects_duplicate_numeric_values():
    client = _client()
    payload = {
        "semester": 5,
        "choice_tags": [
            {"tag": "open_elective", "numeric_value": 1},
            {"tag": "mdm", "numeric_value": 1},
        ],
    }
    r = client.post("/admin/runs", headers=ADMIN_HEADERS, json=payload)
    assert r.status_code == 400, r.text
    assert "used by both" in r.json()["detail"]["errors"][0]


def test_create_run_rejects_invalid_semester():
    client = _client()
    payload = {"semester": 2, "choice_tags": []}
    r = client.post("/admin/runs", headers=ADMIN_HEADERS, json=payload)
    assert r.status_code == 400, r.text


def test_update_run_choice_tags_replaces_mapping():
    client = _client()
    create = client.post("/admin/runs", headers=ADMIN_HEADERS, json={
        "semester": 5,
        "choice_tags": [{"tag": "open_elective", "numeric_value": 1}],
    }).json()

    update_payload = [
        {"tag": "mdm", "numeric_value": 1},
        {"tag": "professional_elective", "numeric_value": 2},
    ]
    r = client.put(f"/admin/runs/{create['id']}/choice-tags", headers=ADMIN_HEADERS, json=update_payload)
    assert r.status_code == 200, r.text
    tags = {c["tag"] for c in r.json()["choice_tag_configs"]}
    assert tags == {"mdm", "professional_elective"}


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
