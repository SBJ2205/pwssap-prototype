"""HTTP-level tests for Phase 8 section generation API.

Run with:
    venv\\Scripts\\python.exe -m tests.test_api_phase8
"""
import sys

sys.path.insert(0, ".")

from fastapi.testclient import TestClient

from data.store import reset_store
from main import app

client = TestClient(app, raise_server_exceptions=True)

CHECKS_PASSED = 0
CHECKS_TOTAL = 0


def check(description, condition):
    global CHECKS_PASSED, CHECKS_TOTAL
    CHECKS_TOTAL += 1
    if condition:
        CHECKS_PASSED += 1
        print(f"  PASS  {description}")
    else:
        print(f"  FAIL  {description}")


# ── Shared fixtures ───────────────────────────────────────────────────────

SUBJECTS_CSV = (
    "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity\n"
    "IT501,Algorithms,program_core,5,theory,4,60\n"
    "IT502,Networks Lab,lab,5,lab,2,24\n"
)

TEACHERS_CSV = (
    "teacher_id,teacher_name,IT501,IT502\n"
    "T001,Dr. Alpha,IT501,IT502\n"
    "T002,Dr. Beta,IT501\n"
)

ADMIN_HEADERS = {"X-Role": "admin"}
STUDENT_HEADERS = {"X-Role": "student"}


def _setup_run():
    """Import subjects + teachers, create a run. Returns run_id."""
    # Import subjects.
    client.post(
        "/admin/subjects/import",
        headers=ADMIN_HEADERS,
        files={"file": ("subjects.csv", SUBJECTS_CSV, "text/csv")},
    )
    # Import teachers.
    client.post(
        "/admin/teachers/import",
        headers=ADMIN_HEADERS,
        files={"file": ("teachers.csv", TEACHERS_CSV, "text/csv")},
    )
    # Create a run for semester 5.
    resp = client.post(
        "/admin/runs",
        headers=ADMIN_HEADERS,
        json={"semester": 5, "choice_tags": []},
    )
    return resp.json()["id"]


# ── Test suite ────────────────────────────────────────────────────────────

print("\n--- Phase 8 API tests ---")


# Test 1: generate-sections requires admin role.
def test_role_gating():
    reset_store()
    run_id = _setup_run()

    resp = client.post(
        f"/admin/runs/{run_id}/generate-sections",
        headers=STUDENT_HEADERS,
    )
    check("generate-sections requires admin (403)", resp.status_code == 403)

    resp = client.get(f"/admin/runs/{run_id}/sections", headers=STUDENT_HEADERS)
    check("list sections requires admin (403)", resp.status_code == 403)

    resp = client.get(f"/admin/runs/{run_id}/sections/0", headers=STUDENT_HEADERS)
    check("get section requires admin (403)", resp.status_code == 403)


test_role_gating()


# Test 2: Unknown run_id returns 404.
def test_unknown_run_404():
    reset_store()

    resp = client.post("/admin/runs/999/generate-sections", headers=ADMIN_HEADERS)
    check("generate-sections 404 for unknown run", resp.status_code == 404)

    resp = client.get("/admin/runs/999/sections", headers=ADMIN_HEADERS)
    check("list sections 404 for unknown run", resp.status_code == 404)

    resp = client.get("/admin/runs/999/sections/0", headers=ADMIN_HEADERS)
    check("get section 404 for unknown run", resp.status_code == 404)


test_unknown_run_404()


# Test 3: Generate sections for a run with one theory + one lab subject.
def test_generate_sections_success():
    reset_store()
    run_id = _setup_run()

    resp = client.post(
        f"/admin/runs/{run_id}/generate-sections",
        headers=ADMIN_HEADERS,
    )
    check("generate-sections returns 200", resp.status_code == 200)

    body = resp.json()
    check("run_id in response", body.get("run_id") == run_id)
    check("generated_count is 2 (1 theory + 1 lab)", body.get("generated_count") == 2)

    sections = body.get("sections", [])
    labels = {s["label"] for s in sections}
    check("theory section label 'IT501-T1' present", "IT501-T1" in labels)
    check("lab section label 'IT502-L1' present", "IT502-L1" in labels)


test_generate_sections_success()


# Test 4: GET list sections for a run.
def test_list_sections():
    reset_store()
    run_id = _setup_run()
    client.post(f"/admin/runs/{run_id}/generate-sections", headers=ADMIN_HEADERS)

    resp = client.get(f"/admin/runs/{run_id}/sections", headers=ADMIN_HEADERS)
    check("list sections returns 200", resp.status_code == 200)

    body = resp.json()
    check("count == 2", body.get("count") == 2)
    check("sections list has 2 items", len(body.get("sections", [])) == 2)


test_list_sections()


# Test 5: GET single section.
def test_get_section():
    reset_store()
    run_id = _setup_run()
    gen_resp = client.post(
        f"/admin/runs/{run_id}/generate-sections", headers=ADMIN_HEADERS
    )
    sections = gen_resp.json()["sections"]
    section_id = sections[0]["id"]

    resp = client.get(
        f"/admin/runs/{run_id}/sections/{section_id}", headers=ADMIN_HEADERS
    )
    check("get section returns 200", resp.status_code == 200)

    body = resp.json()
    check("section id matches", body.get("id") == section_id)
    check("section has meetings list", isinstance(body.get("meetings"), list))

    # Section from a different run should be 404.
    resp2 = client.post(
        "/admin/runs",
        headers=ADMIN_HEADERS,
        json={"semester": 3, "choice_tags": []},
    )
    other_run_id = resp2.json()["id"]
    resp3 = client.get(
        f"/admin/runs/{other_run_id}/sections/{section_id}",
        headers=ADMIN_HEADERS,
    )
    check("section from wrong run returns 404", resp3.status_code == 404)


test_get_section()


# Test 6: Regenerating sections is idempotent (old ones cleared).
def test_regeneration_is_idempotent():
    reset_store()
    run_id = _setup_run()

    resp1 = client.post(
        f"/admin/runs/{run_id}/generate-sections", headers=ADMIN_HEADERS
    )
    count_after_first = resp1.json()["generated_count"]

    resp2 = client.post(
        f"/admin/runs/{run_id}/generate-sections", headers=ADMIN_HEADERS
    )
    body2 = resp2.json()
    check("second generate returns 200", resp2.status_code == 200)
    check(
        "cleared_count equals first generation count",
        body2.get("cleared_count") == count_after_first,
    )

    # Total stored sections should be the same as after the first run.
    list_resp = client.get(f"/admin/runs/{run_id}/sections", headers=ADMIN_HEADERS)
    check(
        "stored section count unchanged after regeneration",
        list_resp.json()["count"] == count_after_first,
    )


test_regeneration_is_idempotent()


# Test 7: subject_code filter on list sections.
def test_list_sections_filter():
    reset_store()
    run_id = _setup_run()
    client.post(f"/admin/runs/{run_id}/generate-sections", headers=ADMIN_HEADERS)

    resp = client.get(
        f"/admin/runs/{run_id}/sections?subject_code=IT501",
        headers=ADMIN_HEADERS,
    )
    check("filter by subject_code returns 200", resp.status_code == 200)
    body = resp.json()
    codes = {s["subject_code"] for s in body.get("sections", [])}
    check("filter returns only IT501 sections", codes == {"IT501"})


test_list_sections_filter()


# Test 8: Meetings in response have correct shape.
def test_meetings_shape():
    reset_store()
    run_id = _setup_run()
    gen = client.post(
        f"/admin/runs/{run_id}/generate-sections", headers=ADMIN_HEADERS
    )
    sections = gen.json()["sections"]

    theory_section = next(s for s in sections if s["label"].endswith("-T1"))
    check(
        "theory section has 2 meetings",
        len(theory_section["meetings"]) == 2,
    )
    lab_section = next(s for s in sections if s["label"].endswith("-L1"))
    check("lab section has 1 meeting", len(lab_section["meetings"]) == 1)

    for meeting in theory_section["meetings"]:
        check("each meeting has a slot_key key", "slot_key" in meeting)


test_meetings_shape()


# ── Summary ───────────────────────────────────────────────────────────────

print(f"\nPhase 8 API: {CHECKS_PASSED}/{CHECKS_TOTAL} checks passed.")
if CHECKS_PASSED < CHECKS_TOTAL:
    sys.exit(1)
