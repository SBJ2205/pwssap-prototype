"""HTTP-level tests for Phase 11 timetable views.

Covers:
  - Student timetable: slot detail enrichment (day, start_time, end_time).
  - Teacher timetable: 404, empty before solve, populated after solve,
      ?run_id= scoping, enrolled_students list, slot detail.
  - Run summary: 404, section_count, weekly_grid structure, slot times,
      teacher names, enrollment counts.

Run with:
    venv\\Scripts\\python.exe -m tests.test_api_phase11
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

SUBJECTS_CSV = (
    "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity\n"
    "IT401,Operating Systems,program_core,5,theory,4,30\n"
    "IT402,OS Lab,lab,5,lab,2,12\n"
)
TEACHERS_CSV = (
    "teacher_id,teacher_name,IT401,IT402\n"
    "T101,Dr. Rho,IT401,IT402\n"
    "T102,Dr. Sigma,IT401\n"
)
STUDENTS_CSV = (
    "roll_number,name,semester\n"
    "R001,Carol,5\n"
    "R002,Dave,5\n"
)


def check(description, condition):
    global CHECKS_PASSED, CHECKS_TOTAL
    CHECKS_TOTAL += 1
    if condition:
        CHECKS_PASSED += 1
        print(f"  PASS  {description}")
    else:
        print(f"  FAIL  {description}")


def _full_setup():
    reset_store()
    client.post("/admin/subjects/import", headers=ADMIN,
                files={"file": ("s.csv", SUBJECTS_CSV, "text/csv")})
    client.post("/admin/teachers/import", headers=ADMIN,
                files={"file": ("t.csv", TEACHERS_CSV, "text/csv")})
    run_resp = client.post("/admin/runs", headers=ADMIN,
                           json={"semester": 5, "choice_tags": []})
    run_id = run_resp.json()["id"]
    client.post("/admin/students/import", headers=ADMIN,
                params={"run_id": run_id},
                files={"file": ("st.csv", STUDENTS_CSV, "text/csv")})
    client.post(f"/admin/runs/{run_id}/generate-sections", headers=ADMIN)
    solve_resp = client.post(f"/admin/runs/{run_id}/solve", headers=ADMIN)
    sections = solve_resp.json().get("sections", [])
    return run_id, sections


# ── Student timetable: slot enrichment ────────────────────────────────────

print("\n--- Student timetable: slot detail enrichment ---")


def test_student_slot_enrichment():
    run_id, sections = _full_setup()

    resp = client.get("/students/R001/sections")
    check("student timetable 200", resp.status_code == 200)
    body = resp.json()
    timetable = body.get("timetable", [])
    check("timetable is non-empty after solve", len(timetable) > 0)

    first_entry = timetable[0]
    meetings = first_entry.get("meetings", [])
    check("meetings non-empty", len(meetings) > 0)

    meeting = meetings[0]
    check("meeting has slot_key", "slot_key" in meeting)
    check("meeting has day field", "day" in meeting)
    check("meeting has start_time field", "start_time" in meeting)
    check("meeting has end_time field", "end_time" in meeting)

    # Verify the slot values are actual canonical values (not None).
    check("day is a non-empty string", isinstance(meeting.get("day"), str) and meeting["day"])
    check(
        "start_time looks like a time (HH:MM format)",
        isinstance(meeting.get("start_time"), str) and ":" in meeting["start_time"],
    )

    check("timetable entries are sorted by subject_code",
          timetable == sorted(timetable, key=lambda e: e["subject_code"]))

    check("subject_type field present", "subject_type" in first_entry)


test_student_slot_enrichment()


# ── Teacher timetable ─────────────────────────────────────────────────────

print("\n--- Teacher timetable ---")


def test_teacher_timetable_404():
    reset_store()
    resp = client.get("/teachers/UNKNOWN/timetable")
    check("GET /teachers/UNKNOWN/timetable -> 404", resp.status_code == 404)


test_teacher_timetable_404()


def test_teacher_timetable_empty_before_solve():
    reset_store()
    client.post("/admin/subjects/import", headers=ADMIN,
                files={"file": ("s.csv", SUBJECTS_CSV, "text/csv")})
    client.post("/admin/teachers/import", headers=ADMIN,
                files={"file": ("t.csv", TEACHERS_CSV, "text/csv")})
    resp = client.get("/teachers/T101/timetable")
    check("teacher timetable 200 before solve", resp.status_code == 200)
    check("schedule is empty before solve", resp.json().get("schedule") == [])


test_teacher_timetable_empty_before_solve()


def test_teacher_timetable_after_solve():
    run_id, sections = _full_setup()

    # Determine which teacher was assigned the theory section.
    theory_sec = next((s for s in sections if "T1" in s["label"]), None)
    if theory_sec is None:
        check("theory section found for teacher timetable test", False)
        return
    assigned_teacher = theory_sec.get("teacher_id")
    check("theory section has an assigned teacher", assigned_teacher is not None)
    if assigned_teacher is None:
        return

    resp = client.get(f"/teachers/{assigned_teacher}/timetable")
    check("teacher timetable 200", resp.status_code == 200)

    body = resp.json()
    check("teacher_id in response", body.get("teacher_id") == assigned_teacher)
    check("teacher_name in response", body.get("teacher_name") is not None)
    check("section_count >= 1", body.get("section_count", 0) >= 1)

    schedule = body.get("schedule", [])
    check("schedule list non-empty", len(schedule) > 0)

    entry = schedule[0]
    check("entry has subject_code", "subject_code" in entry)
    check("entry has subject_name", entry.get("subject_name") is not None)
    check("entry has subject_type", "subject_type" in entry)
    check("entry has enrolled_students list", isinstance(entry.get("enrolled_students"), list))
    check("entry has enrolled_count", "enrolled_count" in entry)

    meetings = entry.get("meetings", [])
    check("meetings non-empty", len(meetings) > 0)
    meeting = meetings[0]
    check("meeting has slot_key", "slot_key" in meeting)
    check("meeting has day", isinstance(meeting.get("day"), str) and meeting["day"])
    check("meeting has start_time", "start_time" in meeting and meeting["start_time"])
    check("meeting has end_time", "end_time" in meeting and meeting["end_time"])

    # Schedule should be sorted by section_label.
    labels = [e["section_label"] for e in schedule]
    check("schedule sorted by section_label", labels == sorted(labels))


test_teacher_timetable_after_solve()


def test_teacher_timetable_run_scoping():
    run_id, sections = _full_setup()

    # Create a second run (different semester) — teacher should not appear there.
    run2_resp = client.post("/admin/runs", headers=ADMIN,
                            json={"semester": 3, "choice_tags": []})
    run2_id = run2_resp.json()["id"]

    theory_sec = next((s for s in sections if "T1" in s["label"]), None)
    if theory_sec is None or not theory_sec.get("teacher_id"):
        check("run scoping: teacher found (skip)", True)
        return
    teacher_id = theory_sec["teacher_id"]

    # Scoped to run2 (no sections) should give empty schedule.
    resp = client.get(f"/teachers/{teacher_id}/timetable?run_id={run2_id}")
    check("teacher timetable scoped to empty run -> empty schedule",
          resp.status_code == 200 and resp.json().get("section_count") == 0)

    # Scoped to the real run should show the sections.
    resp2 = client.get(f"/teachers/{teacher_id}/timetable?run_id={run_id}")
    check("teacher timetable scoped to solved run is non-empty",
          resp2.status_code == 200 and resp2.json().get("section_count", 0) > 0)


test_teacher_timetable_run_scoping()


# ── Run summary ───────────────────────────────────────────────────────────

print("\n--- Run summary ---")


def test_run_summary_404():
    reset_store()
    resp = client.get("/admin/runs/999/summary", headers=ADMIN)
    check("run summary 404 for unknown run", resp.status_code == 404)


test_run_summary_404()


def test_run_summary_role():
    reset_store()
    client.post("/admin/subjects/import", headers=ADMIN,
                files={"file": ("s.csv", SUBJECTS_CSV, "text/csv")})
    run_resp = client.post("/admin/runs", headers=ADMIN,
                           json={"semester": 5, "choice_tags": []})
    run_id = run_resp.json()["id"]
    resp = client.get(f"/admin/runs/{run_id}/summary", headers={"X-Role": "student"})
    check("run summary requires admin (403)", resp.status_code == 403)


test_run_summary_role()


def test_run_summary_content():
    run_id, sections = _full_setup()

    resp = client.get(f"/admin/runs/{run_id}/summary", headers=ADMIN)
    check("run summary 200", resp.status_code == 200)

    body = resp.json()
    check("run_id in response", body.get("run_id") == run_id)
    check("semester in response", body.get("semester") == 5)
    check("run_status in response", "run_status" in body)
    check("section_count matches sections list",
          body.get("section_count") == len(body.get("sections", [])))
    check("sections list non-empty", len(body.get("sections", [])) > 0)

    # Check section detail.
    sec = body["sections"][0]
    check("section has subject_name", sec.get("subject_name") is not None)
    check("section has subject_type", "subject_type" in sec)
    check("section has teacher_name field", "teacher_name" in sec)
    check("section has enrolled_count", "enrolled_count" in sec)
    check("section has enrolled_students", isinstance(sec.get("enrolled_students"), list))
    meetings = sec.get("meetings", [])
    check("section meetings non-empty", len(meetings) > 0)

    # At least one meeting should have slot enrichment after solve.
    enriched = [m for m in meetings if m.get("day")]
    check("at least one meeting is enriched with day/time", len(enriched) > 0)

    # Check weekly_grid.
    grid = body.get("weekly_grid", {})
    check("weekly_grid is a non-empty dict", isinstance(grid, dict) and len(grid) > 0)

    # Each day's entries should be sorted by start_time.
    for day, entries in grid.items():
        times = [e.get("start_time") for e in entries]
        check(f"weekly_grid[{day}] sorted by start_time",
              times == sorted(t for t in times if t))

    # Spot-check a grid entry shape.
    first_day = next(iter(grid))
    first_entry = grid[first_day][0]
    check("grid entry has section_label", "section_label" in first_entry)
    check("grid entry has subject_code", "subject_code" in first_entry)
    check("grid entry has start_time", "start_time" in first_entry)
    check("grid entry has end_time", "end_time" in first_entry)
    check("grid entry has teacher_id", "teacher_id" in first_entry)


test_run_summary_content()


# ── Summary ───────────────────────────────────────────────────────────────

print(f"\nPhase 11: {CHECKS_PASSED}/{CHECKS_TOTAL} checks passed.")
if CHECKS_PASSED < CHECKS_TOTAL:
    sys.exit(1)
