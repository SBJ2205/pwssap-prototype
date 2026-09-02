"""Sanity checks for the Phase 1 domain model, time-slot grid, and
validation helpers.

No test framework is installed in this project's venv yet, so this file
is written as plain assertions with a small runner at the bottom. Once
pytest is added as a dependency, these functions are already
pytest-discoverable (test_* naming) with no changes needed.

Run directly with:
    venv\\Scripts\\python.exe -m tests.test_domain      (from backend/)
"""
from domain.enums import SubjectType, VALID_SEMESTERS, is_even_semester, is_odd_semester
from domain.models import ChoiceTagConfig, Student, Subject, Teacher
from domain.timeslots import build_canonical_grid, is_slot_usable, slot_allows
from domain.validation import (
    validate_choice_tag_configs,
    validate_semester,
    validate_student,
    validate_subject,
    validate_teacher,
)


def test_grid_has_20_slots_five_days_four_periods():
    grid = build_canonical_grid()
    assert len(grid) == 20, f"expected 5 days x 4 slots = 20, got {len(grid)}"
    days = {slot.day for slot in grid}
    assert days == {"Mon", "Tue", "Wed", "Thu", "Fri"}, days


def test_monday_first_slot_is_blocked_for_everything():
    grid = build_canonical_grid()
    mon1 = next(s for s in grid if s.key == "Mon-1")
    assert not is_slot_usable(mon1)
    assert not slot_allows(mon1, SubjectType.THEORY)
    assert not slot_allows(mon1, SubjectType.LAB)


def test_slot_four_is_lab_only_every_day():
    grid = build_canonical_grid()
    for slot in grid:
        if slot.slot_index == 4:
            assert slot_allows(slot, SubjectType.LAB), slot.key
            assert not slot_allows(slot, SubjectType.THEORY), slot.key


def test_ordinary_slots_allow_both_theory_and_lab():
    grid = build_canonical_grid()
    tue1 = next(s for s in grid if s.key == "Tue-1")
    assert slot_allows(tue1, SubjectType.THEORY)
    assert slot_allows(tue1, SubjectType.LAB)


def test_semester_validity_matches_product_spec():
    assert set(VALID_SEMESTERS) == {3, 4, 5, 6, 7, 8}
    assert is_odd_semester(5) and not is_even_semester(5)
    assert is_even_semester(6) and not is_odd_semester(6)
    assert validate_semester(1) != []   # out of scope semester -> invalid
    assert validate_semester(5) == []


def test_valid_subject_passes():
    subject = Subject(
        subject_code="IT301", subject_name="Data Structures", subject_tag="program_core",
        semester=3, type=SubjectType.THEORY, weekly_hours=4, capacity=60,
    )
    assert validate_subject(subject) == []


def test_subject_missing_tag_fails():
    subject = Subject(
        subject_code="IT301", subject_name="Data Structures", subject_tag="",
        semester=3, type=SubjectType.THEORY, weekly_hours=4, capacity=60,
    )
    errors = validate_subject(subject)
    assert any("subject_tag" in e for e in errors)


def test_subject_bad_semester_and_capacity_fails():
    subject = Subject(
        subject_code="IT301", subject_name="Data Structures", subject_tag="lab",
        semester=2, type=SubjectType.LAB, weekly_hours=2, capacity=0,
    )
    errors = validate_subject(subject)
    assert any("Semester" in e for e in errors)
    assert any("capacity" in e for e in errors)


def test_valid_teacher_and_student_pass():
    assert validate_teacher(Teacher(teacher_id="T001", teacher_name="Dr. Sharma")) == []
    assert validate_student(Student(roll_number="23101C0006", name="Pranav", semester=5)) == []


def test_missing_teacher_fields_fail():
    errors = validate_teacher(Teacher(teacher_id="", teacher_name=""))
    assert len(errors) == 2


def test_choice_tag_config_duplicate_numeric_value_fails():
    configs = [
        ChoiceTagConfig(tag="open_elective", numeric_value=1),
        ChoiceTagConfig(tag="mdm", numeric_value=1),
    ]
    errors = validate_choice_tag_configs(configs)
    assert any("used by both" in e for e in errors)


def test_choice_tag_config_unique_values_pass():
    configs = [
        ChoiceTagConfig(tag="open_elective", numeric_value=1),
        ChoiceTagConfig(tag="mdm", numeric_value=2),
    ]
    assert validate_choice_tag_configs(configs) == []


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
