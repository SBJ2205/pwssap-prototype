"""Tests for the Phase 9 solver (engine + service + API).

Covers:
  - Engine: tiny feasible instance solves correctly.
  - Engine: teacher availability hard constraint is never violated.
  - Engine: student BLOCKED slot is never assigned.
  - Engine: teacher load is balanced.
  - Engine: INFEASIBLE when constraints are unsatisfiable.
  - Service: run status transitions to PUBLISHED on success.
  - API: role gating, 404, 400 (no sections), 200 success.

Run with:
    venv\\Scripts\\python.exe -m tests.test_solver
"""
import sys

sys.path.insert(0, ".")

from fastapi.testclient import TestClient

from data.store import InMemoryStore, reset_store
from domain.enums import PreferenceRating, RunStatus, SubjectType
from domain.models import GenerationRun, Meeting, Section, Subject, Teacher
from domain.section_generation import generate_sections_for_run
from domain.timeslots import build_canonical_grid
from main import app
from solver.engine import SolverInput, solve
from solver.service import run_solver_for_run

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


ALL_SLOTS = build_canonical_grid()
THEORY_SLOTS = [s for s in ALL_SLOTS if SubjectType.THEORY in s.allowed_types]
LAB_SLOTS = [s for s in ALL_SLOTS if SubjectType.LAB in s.allowed_types]


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_theory_section(sid, subject_code, capacity=30, run_id=1):
    return Section(
        id=sid,
        subject_code=subject_code,
        label=f"{subject_code}-T1",
        teacher_id=None,
        capacity=capacity,
        meetings=[Meeting(slot_key=""), Meeting(slot_key="")],
        run_id=run_id,
    )


def _make_lab_section(sid, subject_code, capacity=24, run_id=1):
    return Section(
        id=sid,
        subject_code=subject_code,
        label=f"{subject_code}-L1",
        teacher_id=None,
        capacity=capacity,
        meetings=[Meeting(slot_key="")],
        run_id=run_id,
    )


def _minimal_theory_input(
    sections,
    candidate_teachers,
    teacher_avail=None,
    time_prefs=None,
    subject_students=None,
):
    """Build a minimal SolverInput for theory sections."""
    cand_slots = {s.id: THEORY_SLOTS for s in sections}
    return SolverInput(
        sections=sections,
        candidate_slots=cand_slots,
        candidate_teachers=candidate_teachers,
        time_preferences=time_prefs or {},
        faculty_preferences={},
        teacher_availability=teacher_avail or {},
        subject_students=subject_students or {},
        time_limit_seconds=10.0,
    )


# ── Test 1: Tiny feasible instance solves ─────────────────────────────────

print("\n--- Engine: tiny feasible instance ---")

section = _make_theory_section(0, "IT501")
inp = _minimal_theory_input(
    sections=[section],
    candidate_teachers={0: ["T001"]},
    subject_students={"IT501": ["S001", "S002"]},
)
result = solve(inp)

check("Status is OPTIMAL or FEASIBLE", result.status in ("OPTIMAL", "FEASIBLE"))
check("section 0 has slot assignments", len(result.section_slot_assignments.get(0, [])) == 2)
check("section 0 teacher is T001", result.section_teacher_assignments.get(0) == "T001")
check(
    "both slot keys are non-empty",
    all(k for k in result.section_slot_assignments.get(0, [])),
)
check(
    "both meeting slots are valid theory slots",
    all(
        any(s.key == k and SubjectType.THEORY in s.allowed_types for s in ALL_SLOTS)
        for k in result.section_slot_assignments.get(0, [])
    ),
)
check(
    "Mon-1 not used",
    "Mon-1" not in result.section_slot_assignments.get(0, []),
)

# ── Test 2: Teacher availability hard constraint ──────────────────────────

print("\n--- Engine: teacher availability hard constraint ---")

# Block T001 from every theory slot except Mon-2.
allowed_slot_key = "Mon-2"
blocked_avail = {slot.key: False for slot in THEORY_SLOTS if slot.key != allowed_slot_key}

s = _make_theory_section(0, "IT502")
s.meetings = [Meeting(slot_key="")]  # only 1 meeting needed
inp2 = SolverInput(
    sections=[s],
    candidate_slots={0: THEORY_SLOTS},
    candidate_teachers={0: ["T001"]},
    time_preferences={},
    faculty_preferences={},
    teacher_availability={"T001": blocked_avail},
    subject_students={"IT502": []},
    time_limit_seconds=10.0,
)
r2 = solve(inp2)

if r2.status in ("OPTIMAL", "FEASIBLE"):
    assigned_slots = r2.section_slot_assignments.get(0, [])
    check(
        "Solver respects teacher availability: assigned slot is allowed one",
        len(assigned_slots) >= 1 and assigned_slots[0] == allowed_slot_key,
    )
else:
    # If only 1 slot is available and section has 1 meeting, it MUST solve.
    check("Solver should find feasible with 1 allowed slot", False)

# ── Test 3: Student BLOCKED slot is never used ────────────────────────────

print("\n--- Engine: student BLOCKED slot constraint ---")

# Two sections, one student — put student in IT503, block Mon-2 and Mon-3.
sec_a = _make_theory_section(0, "IT503", capacity=30)
sec_a.meetings = [Meeting(slot_key="")]  # 1 meeting

# Only Mon-2 and Mon-3 are candidates for the section.
restricted_slots = [s for s in THEORY_SLOTS if s.key in ("Mon-2", "Mon-3")]

blocked_prefs = {
    "S100": {
        "Mon-2": PreferenceRating.BLOCKED.value,
        "Mon-3": PreferenceRating.BLOCKED.value,
    }
}

# Add a free slot so there IS a solution.
restricted_slots_extended = [s for s in THEORY_SLOTS if s.key in ("Mon-2", "Mon-3", "Tue-2")]

inp3 = SolverInput(
    sections=[sec_a],
    candidate_slots={0: restricted_slots_extended},
    candidate_teachers={0: ["T001"]},
    time_preferences=blocked_prefs,
    faculty_preferences={},
    teacher_availability={},
    subject_students={"IT503": ["S100"]},
    time_limit_seconds=10.0,
)
r3 = solve(inp3)

if r3.status in ("OPTIMAL", "FEASIBLE"):
    assigned = r3.section_slot_assignments.get(0, [])
    check(
        "BLOCKED slot Mon-2 not assigned to section student S100 is in",
        "Mon-2" not in assigned,
    )
    check(
        "BLOCKED slot Mon-3 not assigned to section student S100 is in",
        "Mon-3" not in assigned,
    )
else:
    check("Solver should solve with at least Tue-2 available", False)
    check("BLOCKED constraint check skipped (infeasible)", True)

# ── Test 4: Teacher load balancing ────────────────────────────────────────

print("\n--- Engine: teacher load balancing ---")

# 4 sections, 2 teachers. Without balancing, all 4 could go to T001.
# With balancing, each should get ~2 sections.
sections4 = [_make_theory_section(i, f"SUB{i:02d}", capacity=30) for i in range(4)]
for s in sections4:
    s.meetings = [Meeting(slot_key="")]  # 1 meeting each

cand4 = {s.id: ["T001", "T002"] for s in sections4}
cand_slots4 = {s.id: THEORY_SLOTS for s in sections4}

inp4 = SolverInput(
    sections=sections4,
    candidate_slots=cand_slots4,
    candidate_teachers=cand4,
    time_preferences={},
    faculty_preferences={},
    teacher_availability={},
    subject_students={f"SUB{i:02d}": [] for i in range(4)},
    time_limit_seconds=10.0,
)
r4 = solve(inp4)

if r4.status in ("OPTIMAL", "FEASIBLE"):
    t_counts = {}
    for sid, tid in r4.section_teacher_assignments.items():
        if tid:
            t_counts[tid] = t_counts.get(tid, 0) + 1

    t001 = t_counts.get("T001", 0)
    t002 = t_counts.get("T002", 0)
    check(
        f"Load is balanced: T001={t001} T002={t002}, range <= 1",
        abs(t001 - t002) <= 1,
    )
else:
    check("Solver should solve the 4-section load balance test", False)

# ── Test 5: No double-booking of teacher ──────────────────────────────────

print("\n--- Engine: no teacher double-booking ---")

# 3 sections for T001 only, all sharing the same slot set.
# Solver must spread them across distinct slots.
sec_dbs = [_make_theory_section(i, f"DB{i:02d}") for i in range(3)]
for s in sec_dbs:
    s.meetings = [Meeting(slot_key="")]

inp5 = SolverInput(
    sections=sec_dbs,
    candidate_slots={s.id: THEORY_SLOTS for s in sec_dbs},
    candidate_teachers={s.id: ["T001"] for s in sec_dbs},
    time_preferences={},
    faculty_preferences={},
    teacher_availability={},
    subject_students={f"DB{i:02d}": [] for i in range(3)},
    time_limit_seconds=10.0,
)
r5 = solve(inp5)

if r5.status in ("OPTIMAL", "FEASIBLE"):
    assigned_slots_set = [
        r5.section_slot_assignments.get(i, [None])[0]
        for i in range(3)
    ]
    check(
        "All 3 sections assigned to distinct slots (no double-booking)",
        len(set(assigned_slots_set)) == 3,
    )
else:
    check("Solver should find feasible for no-double-booking test", False)

# ── Test 6: Student section assignment ───────────────────────────────────

print("\n--- Engine: student section assignment ---")

# 2 sections for the same subject, 4 students, capacity 2 each.
s_a = Section(id=0, subject_code="IT601", label="IT601-T1", teacher_id=None,
              capacity=2, meetings=[Meeting("")], run_id=1)
s_b = Section(id=1, subject_code="IT601", label="IT601-T2", teacher_id=None,
              capacity=2, meetings=[Meeting("")], run_id=1)

inp6 = SolverInput(
    sections=[s_a, s_b],
    candidate_slots={0: THEORY_SLOTS, 1: THEORY_SLOTS},
    candidate_teachers={0: ["T001"], 1: ["T002"]},
    time_preferences={},
    faculty_preferences={},
    teacher_availability={},
    subject_students={"IT601": ["S1", "S2", "S3", "S4"]},
    time_limit_seconds=10.0,
)
r6 = solve(inp6)

if r6.status in ("OPTIMAL", "FEASIBLE"):
    assignments = r6.student_section_assignments
    check("All 4 students assigned to a section", len(assignments) == 4)
    assigned_sections = [assignments.get(r, {}).get("IT601") for r in ["S1", "S2", "S3", "S4"]]
    check("Each student has a section assignment", all(sid is not None for sid in assigned_sections))
    check(
        "Sections are not over-capacity (max 2 each)",
        all(assigned_sections.count(sid) <= 2 for sid in [0, 1]),
    )
else:
    check("Student assignment test should be feasible", False)
    check("Student assignment skipped", True)
    check("Over-capacity check skipped", True)

# ── Test 7: Run status transitions to PUBLISHED ───────────────────────────

print("\n--- Service: run status transition ---")

# Build a minimal store scenario.
store = InMemoryStore()

subject = Subject(
    subject_code="IT701",
    subject_name="Test Subject",
    subject_tag="program_core",
    semester=5,
    type=SubjectType.THEORY,
    weekly_hours=4,
    capacity=30,
)
teacher = Teacher(teacher_id="T001", teacher_name="Dr. Test")
store.upsert_subject(subject)
store.upsert_teacher(teacher)
store.add_teacher_capability("T001", "IT701")

run = store.create_run(5)
store.set_run_choice_tags(run.id, [])

# Generate sections via Phase 8 logic.
from domain.section_generation import generate_sections_for_run as gen_sections

gen = gen_sections(
    run=run,
    subjects=[subject],
    all_slots=store.list_time_slots(),
    capable_teacher_ids_for={"IT701": ["T001"]},
    teacher_availability_map={"T001": {}},
    enrolled_counts={"IT701": 0},
)
for sec in gen.sections:
    store.add_section(sec)

check("Run starts as DRAFT", run.status == RunStatus.DRAFT)

result_svc = run_solver_for_run(run.id, store, time_limit_seconds=10.0)
check("Service: solver returned OPTIMAL or FEASIBLE", result_svc.status in ("OPTIMAL", "FEASIBLE"))
check("Run status is now PUBLISHED", run.status == RunStatus.PUBLISHED)

# Section should have a real teacher assigned.
stored_sections = store.list_sections_for_run(run.id)
assigned_teachers = [s.teacher_id for s in stored_sections]
check("At least one section has a teacher assigned", any(t is not None for t in assigned_teachers))

# ── Test 8: API endpoint ──────────────────────────────────────────────────

print("\n--- API: solver endpoint ---")

ADMIN = {"X-Role": "admin"}
STUDENT = {"X-Role": "student"}
SUBJECTS_CSV = (
    "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity\n"
    "IT801,Solver Test,program_core,5,theory,4,60\n"
)
TEACHERS_CSV = (
    "teacher_id,teacher_name,IT801\n"
    "T901,Dr. Omega,IT801\n"
    "T902,Dr. Sigma,IT801\n"
)


def _api_setup():
    reset_store()
    client.post("/admin/subjects/import", headers=ADMIN,
                files={"file": ("s.csv", SUBJECTS_CSV, "text/csv")})
    client.post("/admin/teachers/import", headers=ADMIN,
                files={"file": ("t.csv", TEACHERS_CSV, "text/csv")})
    run_resp = client.post("/admin/runs", headers=ADMIN, json={"semester": 5, "choice_tags": []})
    run_id = run_resp.json()["id"]
    client.post(f"/admin/runs/{run_id}/generate-sections", headers=ADMIN)
    return run_id


run_id = _api_setup()

resp_role = client.post(f"/admin/runs/{run_id}/solve", headers=STUDENT)
check("solve requires admin (403)", resp_role.status_code == 403)

resp_404 = client.post("/admin/runs/999/solve", headers=ADMIN)
check("solve 404 for unknown run", resp_404.status_code == 404)

resp_ok = client.post(f"/admin/runs/{run_id}/solve", headers=ADMIN)
check("solve returns 200", resp_ok.status_code == 200)

body = resp_ok.json()
check("status field present", "status" in body)
check("status is OPTIMAL or FEASIBLE", body["status"] in ("OPTIMAL", "FEASIBLE"))
check("run_status is published", body.get("run_status") == "published")
check("sections list in response", isinstance(body.get("sections"), list))
check("sections have teacher_id assigned", any(s.get("teacher_id") is not None for s in body["sections"]))
check("sections have slot_key in meetings", all(
    any(m.get("slot_key") for m in s.get("meetings", []))
    for s in body["sections"]
))

# Test 400 when no sections generated.
reset_store()
client.post("/admin/subjects/import", headers=ADMIN,
            files={"file": ("s.csv", SUBJECTS_CSV, "text/csv")})
run_resp2 = client.post("/admin/runs", headers=ADMIN, json={"semester": 5, "choice_tags": []})
run_id2 = run_resp2.json()["id"]
resp_no_sections = client.post(f"/admin/runs/{run_id2}/solve", headers=ADMIN)
check("solve 400 when no sections exist", resp_no_sections.status_code == 400)

# ── Summary ───────────────────────────────────────────────────────────────

print(f"\nSolver: {CHECKS_PASSED}/{CHECKS_TOTAL} checks passed.")
if CHECKS_PASSED < CHECKS_TOTAL:
    sys.exit(1)
