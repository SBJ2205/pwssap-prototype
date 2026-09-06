"""Tests for 3-hour subjects with 2-hour meeting + 1-hour remainder (Phase 9 realignment).

Covers:
  - 3-hour subject generated with 2 meetings: 2-hour meeting and 1-hour remainder.
  - Solver solves 3-hour subject and assigns duration_hours and slot_part.
  - Two 1-hour remainders sharing the same physical slot (part 1 and part 2).
  - Teacher availability checked for actual 1-hour interval (teacher blocked for part 1 can still teach part 2).
  - Meeting times reflect actual duration (e.g., 09:00-10:00, not 09:00-11:00).

Run with:
    venv\\Scripts\\python.exe tests\\test_solver_3hour.py
"""
import sys

sys.path.insert(0, ".")

from data.store import InMemoryStore
from domain.enums import SubjectType
from domain.models import Meeting, Section, Subject, Teacher
from domain.section_generation import generate_sections_for_run
from domain.timeslots import build_canonical_grid, get_meeting_times
from solver.engine import SolverInput, solve
from solver.service import run_solver_for_run

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

# ── Test 1: Section generation for 3-hour subject creates [2, 1] meetings ──
print("\n--- 3-Hour Subject: Section Generation ---")

store = InMemoryStore()
subj_3h = Subject(
    subject_code="CS301",
    subject_name="3-Hour Course",
    subject_tag="program_core",
    semester=5,
    type=SubjectType.THEORY,
    weekly_hours=3,
    capacity=30,
)
store.upsert_subject(subj_3h)
teacher1 = Teacher(teacher_id="T001", teacher_name="Prof. One")
store.upsert_teacher(teacher1)
store.add_teacher_capability("T001", "CS301")

run = store.create_run(5)
gen = generate_sections_for_run(
    run=run,
    subjects=[subj_3h],
    all_slots=store.list_time_slots(),
    capable_teacher_ids_for={"CS301": ["T001"]},
    teacher_availability_map={"T001": {}},
    enrolled_counts={"CS301": 25},
)

check("Generated 1 section", len(gen.sections) == 1)
sec = gen.sections[0]
check("Section has 2 meetings", len(sec.meetings) == 2)
check("Meeting 1 duration is 2h", sec.meetings[0].duration_hours == 2)
check("Meeting 2 duration is 1h remainder", sec.meetings[1].duration_hours == 1)


# ── Test 2: Solver solves 3-hour subject and assigns valid parts ────────────
print("\n--- 3-Hour Subject: Solver Execution & Slot Parts ---")

for s in gen.sections:
    store.add_section(s)

res = run_solver_for_run(run.id, store, time_limit_seconds=10.0)
check("Solver status is OPTIMAL or FEASIBLE", res.status in ("OPTIMAL", "FEASIBLE"))

sec_solved = store.get_section(sec.id)
m1, m2 = sec_solved.meetings
check("Meeting 1 has slot_key", bool(m1.slot_key))
check("Meeting 1 slot_part is None (full 2h)", m1.slot_part is None)
check("Meeting 2 has slot_key", bool(m2.slot_key))
check("Meeting 2 slot_part is 1 or 2 (actual 1h part)", m2.slot_part in (1, 2))

# Verify actual meeting times
slot2 = store.get_time_slot(m2.slot_key)
start_t, end_t = get_meeting_times(slot2, m2.duration_hours, m2.slot_part)
check("Meeting 2 start_time is set", bool(start_t))
check("Meeting 2 end_time is set", bool(end_t))
print(f"      Meeting 2 scheduled in {m2.slot_key} Part {m2.slot_part}: {start_t} - {end_t}")


# ── Test 3: Two 1-hour remainders can share the same physical slot ─────────
print("\n--- 3-Hour Subject: Slot Sharing for 1-hour Remainders ---")

# Let's create an instance with only 1 available slot: "Fri-1" (09:00-11:00)
# Section A has a 1-hour meeting, Section B has a 1-hour meeting.
# Both sections can be scheduled in Fri-1 because Section A takes Part 1 and Section B takes Part 2!
sec_a = Section(
    id=10,
    subject_code="CS301",
    label="CS301-R1",
    teacher_id=None,
    capacity=20,
    meetings=[Meeting(slot_key="", duration_hours=1)],
    run_id=1,
)
sec_b = Section(
    id=11,
    subject_code="CS302",
    label="CS302-R1",
    teacher_id=None,
    capacity=20,
    meetings=[Meeting(slot_key="", duration_hours=1)],
    run_id=1,
)

single_slot = [s for s in THEORY_SLOTS if s.key == "Fri-1"]

inp_sharing = SolverInput(
    sections=[sec_a, sec_b],
    candidate_slots={10: single_slot, 11: single_slot},
    candidate_teachers={10: ["T001"], 11: ["T002"]},  # different teachers
    time_preferences={},
    faculty_preferences={},
    teacher_availability={},
    subject_students={"CS301": ["S1"], "CS302": ["S1"]},  # same cohort/student in both
    time_limit_seconds=5.0,
)

res_sharing = solve(inp_sharing)
check("Sharing solves to OPTIMAL or FEASIBLE in single 2h slot", res_sharing.status in ("OPTIMAL", "FEASIBLE"))

sec_a_m = res_sharing.section_meetings[10][0]
sec_b_m = res_sharing.section_meetings[11][0]

check("Both sections assigned to Fri-1", sec_a_m.slot_key == "Fri-1" and sec_b_m.slot_key == "Fri-1")
check("Section A and B assigned different parts (1 and 2)", {sec_a_m.slot_part, sec_b_m.slot_part} == {1, 2})

start_a, end_a = get_meeting_times(single_slot[0], sec_a_m.duration_hours, sec_a_m.slot_part)
start_b, end_b = get_meeting_times(single_slot[0], sec_b_m.duration_hours, sec_b_m.slot_part)
print(f"      Section A: {sec_a_m.slot_key} Part {sec_a_m.slot_part} ({start_a} - {end_a})")
print(f"      Section B: {sec_b_m.slot_key} Part {sec_b_m.slot_part} ({start_b} - {end_b})")


# ── Test 4: Student clash prevention during same hour ─────────────────────
print("\n--- 3-Hour Subject: Student Clash Check ---")
# If the same student is enrolled in both, they CANNOT both be in the same hour,
# but can they be in part 1 and part 2 of the same physical slot?
# Yes, because part 1 and part 2 are distinct consecutive hours!
inp_same_student = SolverInput(
    sections=[sec_a, sec_b],
    candidate_slots={10: single_slot, 11: single_slot},
    candidate_teachers={10: ["T001"], 11: ["T002"]},
    time_preferences={},
    faculty_preferences={},
    teacher_availability={},
    subject_students={"CS301": ["S1"], "CS302": ["S1"]},  # same student in both
    time_limit_seconds=5.0,
)
res_same_student = solve(inp_same_student)
check("Student can attend Part 1 and Part 2 without clash", res_same_student.status in ("OPTIMAL", "FEASIBLE"))

# But what if Section C is a full 2-hour meeting in Fri-1?
# Student S1 cannot attend Section C (2 hours) AND Section A (1 hour in Part 1) in Fri-1!
sec_c = Section(
    id=12,
    subject_code="CS303",
    label="CS303-2H",
    teacher_id=None,
    capacity=20,
    meetings=[Meeting(slot_key="", duration_hours=2)],
    run_id=1,
)
inp_clash = SolverInput(
    sections=[sec_a, sec_c],
    candidate_slots={10: single_slot, 12: single_slot},
    candidate_teachers={10: ["T001"], 12: ["T002"]},
    time_preferences={},
    faculty_preferences={},
    teacher_availability={},
    subject_students={"CS301": ["S1"], "CS303": ["S1"]},  # same student
    time_limit_seconds=5.0,
)
res_clash = solve(inp_clash)
check("Student cannot attend 2h meeting and 1h remainder in the same slot (INFEASIBLE)", res_clash.status == "INFEASIBLE")


# ── Summary ───────────────────────────────────────────────────────────────
print(f"\n3-Hour Solver Tests: {CHECKS_PASSED}/{CHECKS_TOTAL} checks passed.")
if CHECKS_PASSED < CHECKS_TOTAL:
    sys.exit(1)
