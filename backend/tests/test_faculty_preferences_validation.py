"""Sanity checks for Phase 7's faculty preference validation
(product decision #11): secondary, soft, no Blocked value, no
degenerate-matrix warnings (an empty or partial submission is fine).

Run directly with (from backend/):
    venv\\Scripts\\python.exe -m tests.test_faculty_preferences_validation
"""
from domain.validation import FACULTY_RATING_VALUES, validate_faculty_preferences

RANKABLE = {"IT301": ["T001", "T002"], "IT305": ["T003", "T004"]}


def test_faculty_rating_values_exclude_blocked():
    assert FACULTY_RATING_VALUES == {1, 2, 3}


def test_empty_preferences_is_valid():
    result = validate_faculty_preferences({}, RANKABLE)
    assert result.is_valid


def test_valid_single_subject_preference_is_valid():
    result = validate_faculty_preferences({"IT301": {"T001": 1, "T002": 2}}, RANKABLE)
    assert result.is_valid


def test_partial_submission_ranking_only_one_subject_is_valid():
    result = validate_faculty_preferences({"IT305": {"T003": 1}}, RANKABLE)
    assert result.is_valid


def test_non_rankable_subject_is_an_error():
    result = validate_faculty_preferences({"IT304": {"T005": 1}}, RANKABLE)  # not in RANKABLE
    assert not result.is_valid
    assert any("not rankable" in e for e in result.errors)


def test_ineligible_teacher_for_subject_is_an_error():
    result = validate_faculty_preferences({"IT301": {"T003": 1}}, RANKABLE)  # T003 teaches IT305, not IT301
    assert not result.is_valid
    assert any("not eligible" in e for e in result.errors)


def test_blocked_value_is_rejected_for_faculty_preference():
    result = validate_faculty_preferences({"IT301": {"T001": 4}}, RANKABLE)  # 4 = BLOCKED, not allowed here
    assert not result.is_valid
    assert any("must be one of" in e for e in result.errors)


def test_out_of_range_value_is_rejected():
    result = validate_faculty_preferences({"IT301": {"T001": 9}}, RANKABLE)
    assert not result.is_valid


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
