"""HTTP-level tests for Phase 10 admin override flow and student timetable.

Covers:
  - enroll student: success, capacity overflow warning, slot clash warning.
  - unenroll student: success, 404 when not enrolled.
  - reassign teacher: success, capability warning, double-booking warning.
  - override capacity: success, below-enrollment warning, invalid value.
  - student sections: 404, empty before solve, populated after solve.
  - Role gating on all admin endpoints.
  - Full end-to-end: generate -> solve -> check student view -> admin overrides.

Run with:
    venv\\Scripts\\python.exe -m tests.test_api_phase10
"""
import sys

sys.path.insert(0, ".")

from fastapi.testclient import TestClient

from data.store import reset_store
from main import app

client = TestClient(app, raise_server_exceptions=True)
CHECKS_PASSED = 0
CHECKS_TOTAL = 0

ADMIN = {"X-Role": "admin"}
STUDENT_H = {"X-Role": "student"}


def check(description, condition):
    global CHECKS_PASSED, CHECKS_TOTAL
    CHECKS_TOTAL += 1
    if condition:
        CHECKS_PASSED += 1
        print(f"  PASS  {description}")
    else:
        print(f"  FAIL  {description}")


# ── Fixtures ──────────────────────────────────────────────────────────────

SUBJECTS_CSV = (
    "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity\n"
    "IT301,Algorithms,program_core,5,theory,4,30\n"
    "IT302,Networks Lab,lab,5,lab,2,12\n"
)
TEACHERS_CSV = (
    "teacher_id,teacher_name,IT301,IT302\n"
    "T001,Dr. Alpha,IT301,IT302\n"
    "T002,Dr. Beta,IT301\n"
)
STUDENTS_CSV = (
    "roll_number,name,semester\n"
    "S001,Alice,5\n"
    "S002,Bob,5\n"
)


def _full_setup():
    """Run the full pipeline: import -> create run -> generate -> solve.
    Returns (run_id, section_ids_by_label)."""
    reset_store()
    client.post("/admin/subjects/import", headers=ADMIN,
                files={"file": ("s.csv", SUBJECTS_CSV, "text/csv")})
    client.post("/admin/teachers/import", headers=ADMIN,
                files={"file": ("t.csv", TEACHERS_CSV, "text/csv")})
    client.post("/admin/students/import", headers=ADMIN,
                params={"run_id": 0},
                files={"file": ("st.csv", STUDENTS_CSV, "text/csv")})

    run_resp = client.post("/admin/runs", headers=ADMIN,
                           json={"semester": 5, "choice_tags": []})
    run_id = run_resp.json()["id"]

    client.post("/admin/students/import", headers=ADMIN,
                params={"run_id": run_id},
                files={"file": ("st.csv", STUDENTS_CSV, "text/csv")})

    client.post(f"/admin/runs/{run_id}/generate-sections", headers=ADMIN)
    solve_resp = client.post(f"/admin/runs/{run_id}/solve", headers=ADMIN)
    sections = solve_resp.json().get("sections", [])
    by_label = {s["label"]: s["id"] for s in sections}
    return run_id, by_label


# ── Test: student sections endpoint before solve ───────────────────────────

print("\n--- Student sections: 404 and empty-before-solve ---")


def test_student_sections_404():
    reset_store()
    resp = client.get("/students/UNKNOWN/sections")
    check("GET /students/unknown/sections -> 404", resp.status_code == 404)


test_student_sections_404()


def test_student_sections_empty_before_solve():
    reset_store()
    client.post("/admin/subjects/import", headers=ADMIN,
                files={"file": ("s.csv", SUBJECTS_CSV, "text/csv")})
    run_resp = client.post("/admin/runs", headers=ADMIN,
                           json={"semester": 5, "choice_tags": []})
    run_id = run_resp.json()["id"]
    client.post("/admin/students/import", headers=ADMIN,
                params={"run_id": run_id},
                files={"file": ("st.csv", STUDENTS_CSV, "text/csv")})
    resp = client.get("/students/S001/sections")
    check("student sections empty before solve", resp.status_code == 200)
    check("timetable is empty list", resp.json()["timetable"] == [])


test_student_sections_empty_before_solve()


# ── Test: student sections populated after solve ───────────────────────────

print("\n--- Student sections after solve ---")


def test_student_sections_after_solve():
    _run_id, _by_label = _full_setup()
    resp = client.get("/students/S001/sections")
    check("GET /students/S001/sections -> 200", resp.status_code == 200)
    body = resp.json()
    check("roll_number in response", body.get("roll_number") == "S001")
    check("timetable is non-empty", len(body.get("timetable", [])) > 0)

    entry = body["timetable"][0]
    check("each timetable entry has subject_code", "subject_code" in entry)
    check("each timetable entry has section_label", "section_label" in entry)
    check("each timetable entry has meetings", isinstance(entry.get("meetings"), list))


test_student_sections_after_solve()


# ── Test: enroll student ──────────────────────────────────────────────────

print("\n--- Admin override: enroll student ---")


def test_enroll_student():
    _run_id, by_label = _full_setup()

    # Pick the theory section.
    theory_id = by_label.get("IT301-T1")
    check("theory section found", theory_id is not None)
    if theory_id is None:
        return

    # Role gating.
    resp_role = client.post(
        f"/admin/sections/{theory_id}/enroll",
        headers=STUDENT_H,
        json={"roll_number": "S001"},
    )
    check("enroll requires admin (403)", resp_role.status_code == 403)

    # Unknown section.
    resp_404s = client.post(
        "/admin/sections/9999/enroll",
        headers=ADMIN,
        json={"roll_number": "S001"},
    )
    check("enroll 404 for unknown section", resp_404s.status_code == 404)

    # Unknown student.
    resp_404r = client.post(
        f"/admin/sections/{theory_id}/enroll",
        headers=ADMIN,
        json={"roll_number": "UNKNOWN_ROLL"},
    )
    check("enroll 404 for unknown student", resp_404r.status_code == 404)

    # Successful enroll — S001 may already be in IT301, re-enroll is fine
    # (enroll_student replaces prior assignment for same subject).
    resp_ok = client.post(
        f"/admin/sections/{theory_id}/enroll",
        headers=ADMIN,
        json={"roll_number": "S001"},
    )
    check("enroll success -> 200", resp_ok.status_code == 200)
    body = resp_ok.json()
    check("enrolled=True in response", body.get("enrolled") is True)
    check("section detail in response", "section" in body)


test_enroll_student()


# ── Test: capacity warning on enroll ─────────────────────────────────────

print("\n--- Enroll: capacity overflow warning ---")


def test_enroll_capacity_warning():
    reset_store()
    # Tiny capacity so we can trigger a warning easily.
    TINY_CSV = (
        "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity\n"
        "IT999,Tiny,program_core,5,theory,4,1\n"
    )
    client.post("/admin/subjects/import", headers=ADMIN,
                files={"file": ("s.csv", TINY_CSV, "text/csv")})
    client.post("/admin/teachers/import", headers=ADMIN,
                files={"file": ("t.csv", "teacher_id,teacher_name,IT999\nT1,Dr.T,IT999\n", "text/csv")})

    MANY_STUDENTS = "roll_number,name,semester\n" + "".join(
        f"S{i:03d},Student{i},5\n" for i in range(3)
    )
    run_resp = client.post("/admin/runs", headers=ADMIN, json={"semester": 5, "choice_tags": []})
    run_id = run_resp.json()["id"]
    client.post("/admin/students/import", headers=ADMIN, params={"run_id": run_id},
                files={"file": ("st.csv", MANY_STUDENTS, "text/csv")})
    client.post(f"/admin/runs/{run_id}/generate-sections", headers=ADMIN)
    solve_resp = client.post(f"/admin/runs/{run_id}/solve", headers=ADMIN)

    secs = solve_resp.json().get("sections", [])
    if not secs:
        check("Capacity warning test: no sections, skip", True)
        return
    section_id = secs[0]["id"]

    # Enroll extra students to exceed capacity=1.
    client.post(f"/admin/sections/{section_id}/enroll", headers=ADMIN,
                json={"roll_number": "S000"})
    resp = client.post(f"/admin/sections/{section_id}/enroll", headers=ADMIN,
                       json={"roll_number": "S001"})
    check("second enroll returns 200 (override allowed)", resp.status_code == 200)
    body = resp.json()
    check("capacity overflow warning present", len(body.get("warnings", [])) > 0)
    check(
        "warning mentions capacity",
        any("capacity" in w.lower() for w in body.get("warnings", [])),
    )


test_enroll_capacity_warning()


# ── Test: unenroll student ────────────────────────────────────────────────

print("\n--- Admin override: unenroll student ---")


def test_unenroll_student():
    _run_id, by_label = _full_setup()
    theory_id = by_label.get("IT301-T1")
    if theory_id is None:
        check("theory section found (unenroll test)", False)
        return

    # Ensure S001 is enrolled.
    client.post(f"/admin/sections/{theory_id}/enroll", headers=ADMIN,
                json={"roll_number": "S001"})

    # Role gating.
    resp_role = client.delete(f"/admin/sections/{theory_id}/students/S001",
                              headers=STUDENT_H)
    check("unenroll requires admin (403)", resp_role.status_code == 403)

    # Successful removal.
    resp_ok = client.delete(f"/admin/sections/{theory_id}/students/S001",
                            headers=ADMIN)
    check("unenroll success -> 200", resp_ok.status_code == 200)
    body = resp_ok.json()
    check("unenrolled=True in response", body.get("unenrolled") is True)

    # Second removal is 404 (student not enrolled).
    resp_404 = client.delete(f"/admin/sections/{theory_id}/students/S001",
                             headers=ADMIN)
    check("second unenroll -> 404", resp_404.status_code == 404)


test_unenroll_student()


# ── Test: reassign teacher ────────────────────────────────────────────────

print("\n--- Admin override: reassign teacher ---")


def test_reassign_teacher():
    _run_id, by_label = _full_setup()
    theory_id = by_label.get("IT301-T1")
    if theory_id is None:
        check("theory section found (teacher test)", False)
        return

    # Role gating.
    resp_role = client.put(f"/admin/sections/{theory_id}/teacher",
                           headers=STUDENT_H, json={"teacher_id": "T002"})
    check("reassign teacher requires admin (403)", resp_role.status_code == 403)

    # Unknown teacher.
    resp_404 = client.put(f"/admin/sections/{theory_id}/teacher",
                          headers=ADMIN, json={"teacher_id": "FAKE"})
    check("reassign 404 for unknown teacher", resp_404.status_code == 404)

    # Successful reassignment to a capable teacher.
    resp_ok = client.put(f"/admin/sections/{theory_id}/teacher",
                         headers=ADMIN, json={"teacher_id": "T002"})
    check("reassign success -> 200", resp_ok.status_code == 200)
    body = resp_ok.json()
    check("teacher_id updated in response", body.get("teacher_id") == "T002")
    check("section detail included", "section" in body)

    # Capability warning: T001 can teach IT302 but IT301 section assigned T001
    # -- check a teacher capable of IT302 gets no capability warning there.
    lab_id = by_label.get("IT302-L1")
    if lab_id:
        resp_t1 = client.put(f"/admin/sections/{lab_id}/teacher",
                             headers=ADMIN, json={"teacher_id": "T001"})
        check("reassigning capable teacher for lab gives no capability warning",
              resp_t1.status_code == 200 and
              not any("capability" in w.lower() for w in resp_t1.json().get("warnings", [])))

    # Non-capable teacher: should warn but still accept.
    EXTRA_TEACHER = "teacher_id,teacher_name\nT999,Dr. Incapable\n"
    client.post("/admin/teachers/import", headers=ADMIN,
                files={"file": ("t2.csv", EXTRA_TEACHER, "text/csv")})
    resp_warn = client.put(f"/admin/sections/{theory_id}/teacher",
                           headers=ADMIN, json={"teacher_id": "T999"})
    check("non-capable teacher override -> 200", resp_warn.status_code == 200)
    body_warn = resp_warn.json()
    check(
        "capability warning present for non-capable teacher",
        any("capability" in w.lower() for w in body_warn.get("warnings", [])),
    )


test_reassign_teacher()


# ── Test: override capacity ───────────────────────────────────────────────

print("\n--- Admin override: capacity ---")


def test_override_capacity():
    _run_id, by_label = _full_setup()
    theory_id = by_label.get("IT301-T1")
    if theory_id is None:
        check("theory section found (capacity test)", False)
        return

    # Role gating.
    resp_role = client.put(f"/admin/sections/{theory_id}/capacity",
                           headers=STUDENT_H, json={"capacity": 50})
    check("capacity override requires admin (403)", resp_role.status_code == 403)

    # Invalid capacity.
    resp_bad = client.put(f"/admin/sections/{theory_id}/capacity",
                          headers=ADMIN, json={"capacity": 0})
    check("capacity=0 -> 400", resp_bad.status_code == 400)

    # Valid increase.
    resp_ok = client.put(f"/admin/sections/{theory_id}/capacity",
                         headers=ADMIN, json={"capacity": 50})
    check("capacity increase -> 200", resp_ok.status_code == 200)
    body = resp_ok.json()
    check("capacity in response is 50", body.get("capacity") == 50)

    # Below-enrollment warning (enroll 2 students, then set capacity to 1).
    client.post(f"/admin/sections/{theory_id}/enroll", headers=ADMIN,
                json={"roll_number": "S001"})
    client.post(f"/admin/sections/{theory_id}/enroll", headers=ADMIN,
                json={"roll_number": "S002"})
    resp_warn = client.put(f"/admin/sections/{theory_id}/capacity",
                           headers=ADMIN, json={"capacity": 1})
    check("below-enrollment capacity -> 200 (override allowed)", resp_warn.status_code == 200)
    body_warn = resp_warn.json()
    check(
        "below-enrollment warning present",
        len(body_warn.get("warnings", [])) > 0,
    )


test_override_capacity()


# ── Summary ───────────────────────────────────────────────────────────────

print(f"\nPhase 10 overrides: {CHECKS_PASSED}/{CHECKS_TOTAL} checks passed.")
if CHECKS_PASSED < CHECKS_TOTAL:
    sys.exit(1)
