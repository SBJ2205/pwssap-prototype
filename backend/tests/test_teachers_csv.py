"""Sanity checks for Phase 4's teacher CSV ingestion.

Run directly with (from backend/):
    venv\\Scripts\\python.exe -m tests.test_teachers_csv
"""
from ingestion.teachers_csv import parse_teachers_csv

KNOWN_SUBJECTS = {"IT301", "IT302", "IT303", "IT305", "IT306", "IT310"}

# Deliberately ragged rows (different subject-column counts per row) and a
# blank cell between two subject codes on the Mehta row, to exercise both
# "variable width" and "non-contiguous non-empty cells still count".
VALID_CSV = (
    "teacher_id,teacher_name,subject_code\n"
    "T001,Dr. Sharma,IT301,IT302,IT305\n"
    "T002,Prof. Mehta,IT301,,IT303\n"
    "T003,Prof. Joshi,IT306\n"
)


def test_valid_csv_parses_with_no_row_errors():
    result = parse_teachers_csv(VALID_CSV, KNOWN_SUBJECTS)
    assert result.is_valid, result.row_errors
    assert len(result.teachers) == 3
    assert result.capabilities["T001"] == ["IT301", "IT302", "IT305"]
    assert result.capabilities["T003"] == ["IT306"]


def test_blank_cell_between_subjects_is_skipped_not_a_stop_marker():
    result = parse_teachers_csv(VALID_CSV, KNOWN_SUBJECTS)
    assert result.capabilities["T002"] == ["IT301", "IT303"]


def test_teacher_with_no_subject_columns_gets_empty_capability_list():
    csv_text = "teacher_id,teacher_name,subject_code\nT004,Dr. Nair\n"
    result = parse_teachers_csv(csv_text, KNOWN_SUBJECTS)
    assert result.is_valid, result.row_errors
    assert result.capabilities["T004"] == []


def test_blank_rows_are_skipped():
    csv_text = "teacher_id,teacher_name,subject_code\nT001,Dr. Sharma,IT301\n,,\n\nT002,Prof. Mehta,IT302\n"
    result = parse_teachers_csv(csv_text, KNOWN_SUBJECTS)
    assert result.is_valid, result.row_errors
    assert len(result.teachers) == 2


def test_duplicate_teacher_id_is_a_row_error():
    csv_text = (
        "teacher_id,teacher_name,subject_code\n"
        "T001,Dr. Sharma,IT301\n"
        "T001,Dr. Sharma Again,IT302\n"
    )
    result = parse_teachers_csv(csv_text, KNOWN_SUBJECTS)
    assert not result.is_valid
    assert len(result.teachers) == 1
    assert any("Duplicate teacher_id" in e for e in result.row_errors[0].errors)


def test_duplicate_subject_code_for_same_teacher_is_a_row_error():
    csv_text = "teacher_id,teacher_name,subject_code\nT001,Dr. Sharma,IT301,IT301\n"
    result = parse_teachers_csv(csv_text, KNOWN_SUBJECTS)
    assert not result.is_valid
    assert any("Duplicate subject_code" in e for e in result.row_errors[0].errors)


def test_missing_teacher_name_is_a_row_error():
    csv_text = "teacher_id,teacher_name,subject_code\nT001,,IT301\n"
    result = parse_teachers_csv(csv_text, KNOWN_SUBJECTS)
    assert not result.is_valid
    assert any("teacher_name" in e for e in result.row_errors[0].errors)


def test_unknown_subject_code_is_a_row_error_when_catalog_given():
    csv_text = "teacher_id,teacher_name,subject_code\nT001,Dr. Sharma,IT999\n"
    result = parse_teachers_csv(csv_text, KNOWN_SUBJECTS)
    assert not result.is_valid
    assert any("Unknown subject_code" in e for e in result.row_errors[0].errors)


def test_unknown_subject_code_allowed_when_no_catalog_given():
    csv_text = "teacher_id,teacher_name,subject_code\nT001,Dr. Sharma,IT999\n"
    result = parse_teachers_csv(csv_text, known_subject_codes=None)
    assert result.is_valid, result.row_errors


def test_wrong_header_is_a_file_level_error():
    csv_text = "id,name,subject_code\nT001,Dr. Sharma,IT301\n"
    result = parse_teachers_csv(csv_text, KNOWN_SUBJECTS)
    assert not result.is_valid
    assert result.row_errors[0].row_number == 0


def test_empty_file_is_a_file_level_error():
    result = parse_teachers_csv("", KNOWN_SUBJECTS)
    assert not result.is_valid
    assert result.row_errors[0].row_number == 0


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
