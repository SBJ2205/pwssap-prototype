"""Unit tests for domain.section_generation (Phase 8).

These tests exercise the generation logic directly â€” no HTTP, no store.
Run with:
    venv\\Scripts\\python.exe -m tests.test_section_generation
"""
import sys
import math

sys.path.insert(0, ".")

from domain.enums import SubjectType
from domain.models import GenerationRun, Subject
from domain.section_generation import (
    GeneratedSections,
    SlotStructureError,
    generate_sections_for_run,
    parse_slot_structure,
)
from domain.timeslots import build_canonical_grid


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _theory(code, weekly_hours=4, slot_structure=None, capacity=60):
    return Subject(
        subject_code=code,
        subject_name=f"Subject {code}",
        subject_tag="program_core",
        semester=5,
        type=SubjectType.THEORY,
        weekly_hours=weekly_hours,
        capacity=capacity,
        slot_structure=slot_structure,
    )


def _lab(code, weekly_hours=2, capacity=24):
    return Subject(
        subject_code=code,
        subject_name=f"Lab {code}",
        subject_tag="lab",
        semester=5,
        type=SubjectType.LAB,
        weekly_hours=weekly_hours,
        capacity=capacity,
        slot_structure=None,
    )


def _run(run_id=1, semester=5):
    return GenerationRun(id=run_id, semester=semester)


ALL_SLOTS = build_canonical_grid()
THEORY_SLOTS = [s for s in ALL_SLOTS if SubjectType.THEORY in s.allowed_types]
LAB_SLOTS = [s for s in ALL_SLOTS if SubjectType.LAB in s.allowed_types]

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


# â”€â”€ Test 1: parse_slot_structure â€” None/empty defaults â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

print("\n--- parse_slot_structure ---")

result = parse_slot_structure(None, 4)
check("None with weekly_hours=4 â†’ [2, 2]", result == [2, 2])

result = parse_slot_structure("", 4)
check("empty string with weekly_hours=4 â†’ [2, 2]", result == [2, 2])

result = parse_slot_structure(None, 6)
check("None with weekly_hours=6 â†’ [2, 2, 2]", result == [2, 2, 2])

# â”€â”€ Test 2: parse_slot_structure â€” explicit patterns â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

result = parse_slot_structure("2+2", 4)
check('"2+2" with weekly_hours=4 â†’ [2, 2]', result == [2, 2])

result = parse_slot_structure("2+2+2", 6)
check('"2+2+2" with weekly_hours=6 â†’ [2, 2, 2]', result == [2, 2, 2])

result = parse_slot_structure("4", 4)
check('"4" shorthand with weekly_hours=4 â†’ [2, 2]', result == [2, 2])

# â”€â”€ Test 3: parse_slot_structure â€” error cases â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

print("\n--- parse_slot_structure errors ---")

try:
    parse_slot_structure("3+1", 4)
    check("3+1 with non-2 segments raises SlotStructureError", False)
except SlotStructureError:
    check("3+1 with non-2 segments raises SlotStructureError", True)

try:
    parse_slot_structure("2+2", 6)  # sum=4 â‰  weekly_hours=6
    check("2+2 with weekly_hours=6 (mismatch) raises SlotStructureError", False)
except SlotStructureError:
    check("2+2 with weekly_hours=6 (mismatch) raises SlotStructureError", True)

try:
    parse_slot_structure(None, 3)  # odd hours, can't split into 2-h blocks
    check("None with weekly_hours=3 (odd) raises SlotStructureError", False)
except SlotStructureError:
    check("None with weekly_hours=3 (odd) raises SlotStructureError", True)

try:
    parse_slot_structure("2+abc", 4)
    check("non-integer segment raises SlotStructureError", False)
except SlotStructureError:
    check("non-integer segment raises SlotStructureError", True)

# â”€â”€ Test 4: Theory section â€” correct structure â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

print("\n--- Theory section generation ---")

run = _run()
subject = _theory("IT301", weekly_hours=4)
result: GeneratedSections = generate_sections_for_run(
    run=run,
    subjects=[subject],
    all_slots=ALL_SLOTS,
    capable_teacher_ids_for={"IT301": ["T001"]},
    teacher_availability_map={"T001": {}},  # all slots available
    enrolled_counts={"IT301": 0},
)

check("One theory section generated for IT301", len(result.sections) == 1)

sec = result.sections[0]
check("Theory section label is 'IT301-T1'", sec.label == "IT301-T1")
check("Theory section has 2 meetings (4 h / 2-h slots)", len(sec.meetings) == 2)
check("Theory section teacher_id assigned", sec.teacher_id == "T001")
check("Theory section run_id matches run", sec.run_id == run.id)

# Verify slots are valid for theory.
for meeting in sec.meetings:
    slot = next((s for s in ALL_SLOTS if s.key == meeting.slot_key), None)
    check(
        f"Meeting slot '{meeting.slot_key}' allows theory",
        slot is not None and SubjectType.THEORY in slot.allowed_types,
    )

# â”€â”€ Test 5: Theory section â€” Monday slot 1 never assigned â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

print("\n--- Monday slot 1 blocked for theory ---")

sec_slots = {m.slot_key for m in sec.meetings}
check("Theory section does not use Mon-1", "Mon-1" not in sec_slots)

# â”€â”€ Test 6: Theory section â€” slot 4 never assigned to theory â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

slot4_keys = {s.key for s in ALL_SLOTS if s.slot_index == 4}
check(
    "Theory section does not use any slot-4 slot",
    len(sec_slots & slot4_keys) == 0,
)

# â”€â”€ Test 7: Lab sections â€” parallelism from enrollment â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

print("\n--- Lab section generation (parallelism) ---")

lab_subject = _lab("IT401", weekly_hours=2, capacity=24)

for enrolled, expected_sections in [(24, 1), (48, 2), (73, 4), (0, 1)]:
    res = generate_sections_for_run(
        run=_run(),
        subjects=[lab_subject],
        all_slots=ALL_SLOTS,
        capable_teacher_ids_for={"IT401": ["T002"]},
        teacher_availability_map={"T002": {}},
        enrolled_counts={"IT401": enrolled},
    )
    expected = math.ceil(enrolled / 24) if enrolled > 0 else 1
    check(
        f"Enrolled={enrolled} â†’ {expected} lab section(s), got {len(res.sections)}",
        len(res.sections) == expected,
    )

# â”€â”€ Test 8: Lab section â€” slot always valid for lab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

print("\n--- Lab section slot validity ---")

lab_res = generate_sections_for_run(
    run=_run(),
    subjects=[_lab("IT402")],
    all_slots=ALL_SLOTS,
    capable_teacher_ids_for={"IT402": ["T003"]},
    teacher_availability_map={"T003": {}},
    enrolled_counts={"IT402": 24},
)
for lab_sec in lab_res.sections:
    for meeting in lab_sec.meetings:
        if meeting.slot_key:
            slot = next((s for s in ALL_SLOTS if s.key == meeting.slot_key), None)
            check(
                f"Lab meeting slot '{meeting.slot_key}' allows lab",
                slot is not None and SubjectType.LAB in slot.allowed_types,
            )
        # Mon-1 must not appear.
        check(
            f"Lab meeting slot '{meeting.slot_key}' is not Mon-1",
            meeting.slot_key != "Mon-1",
        )

# â”€â”€ Test 9: No capable teacher â†’ teacher_id=None + warning â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

print("\n--- No capable teacher warning ---")

no_teacher_res = generate_sections_for_run(
    run=_run(),
    subjects=[_theory("IT303")],
    all_slots=ALL_SLOTS,
    capable_teacher_ids_for={"IT303": []},  # nobody can teach this
    teacher_availability_map={},
    enrolled_counts={"IT303": 0},
)
check("Section created even with no teacher", len(no_teacher_res.sections) == 1)
check("teacher_id is None when no teacher available", no_teacher_res.sections[0].teacher_id is None)
check("Warning emitted when no teacher available", len(no_teacher_res.warnings) >= 1)

# â”€â”€ Test 10: Multiple subjects, correct label conventions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

print("\n--- Label convention for multiple subjects ---")

multi_res = generate_sections_for_run(
    run=_run(),
    subjects=[_theory("IT310"), _lab("IT311")],
    all_slots=ALL_SLOTS,
    capable_teacher_ids_for={"IT310": ["T004"], "IT311": ["T005"]},
    teacher_availability_map={"T004": {}, "T005": {}},
    enrolled_counts={"IT310": 0, "IT311": 24},
)
labels = {s.label for s in multi_res.sections}
check("Theory label 'IT310-T1' present", "IT310-T1" in labels)
check("Lab label 'IT311-L1' present", "IT311-L1" in labels)

# â”€â”€ Summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

print(f"\nSection generation: {CHECKS_PASSED}/{CHECKS_TOTAL} checks passed.")
if CHECKS_PASSED < CHECKS_TOTAL:
    sys.exit(1)

