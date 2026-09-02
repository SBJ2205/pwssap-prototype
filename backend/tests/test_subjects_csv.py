"""Sanity checks for Phase 2's subject CSV ingestion.

Run directly with (from backend/):
    venv\\Scripts\\python.exe -m tests.test_subjects_csv
"""
from domain.enums import SubjectType
from ingestion.subjects_csv import parse_subjects_csv

VALID_CSV = """subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity,slot_structure
IT301,Data Structures,program_core,5,theory,4,60,2+2
IT304,CN Lab,lab,5,lab,2,24,
IT310,Cloud Computing,open_elective,5,THEORY,3,40,
"""


def test_valid_csv_parses_with_no_row_errors():
    result = parse_subjects_csv(VALID_CSV)
    assert result.is_valid, result.row_errors
    assert len(result.subjects) == 3
    ds = next(s for s in result.subjects if s.subject_code == "IT301")
    assert ds.subject_name == "Data Structures"
    assert ds.subject_tag == "program_core"
    assert ds.semester == 5
    assert ds.type == SubjectType.THEORY
    assert ds.weekly_hours == 4
    assert ds.capacity == 60
    assert ds.slot_structure == "2+2"


def test_type_column_is_case_insensitive():
    result = parse_subjects_csv(VALID_CSV)
    cloud = next(s for s in result.subjects if s.subject_code == "IT310")
    assert cloud.type == SubjectType.THEORY


def test_lab_row_with_blank_slot_structure_is_none():
    result = parse_subjects_csv(VALID_CSV)
    lab = next(s for s in result.subjects if s.subject_code == "IT304")
    assert lab.type == SubjectType.LAB
    assert lab.slot_structure is None


def test_missing_required_column_is_a_file_level_error():
    csv_text = "subject_code,subject_name,semester,type,weekly_hours,capacity\nIT301,DS,5,theory,4,60\n"
    result = parse_subjects_csv(csv_text)
    assert not result.is_valid
    assert result.row_errors[0].row_number == 0
    assert "subject_tag" in result.row_errors[0].errors[0]


def test_duplicate_subject_code_is_a_row_error():
    csv_text = (
        "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity\n"
        "IT301,Data Structures,program_core,5,theory,4,60\n"
        "IT301,Data Structures Redo,program_core,5,theory,4,60\n"
    )
    result = parse_subjects_csv(csv_text)
    assert not result.is_valid
    assert len(result.subjects) == 1
    assert any("Duplicate subject_code" in e for e in result.row_errors[0].errors)
    assert result.row_errors[0].row_number == 2


def test_invalid_semester_is_a_row_error():
    csv_text = (
        "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity\n"
        "IT301,Data Structures,program_core,2,theory,4,60\n"
    )
    result = parse_subjects_csv(csv_text)
    assert not result.is_valid
    assert any("Semester" in e for e in result.row_errors[0].errors)


def test_invalid_type_is_a_row_error():
    csv_text = (
        "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity\n"
        "IT301,Data Structures,program_core,5,seminar,4,60\n"
    )
    result = parse_subjects_csv(csv_text)
    assert not result.is_valid
    assert any("type" in e.lower() for e in result.row_errors[0].errors)


def test_non_numeric_capacity_is_a_row_error():
    csv_text = (
        "subject_code,subject_name,subject_tag,semester,type,weekly_hours,capacity\n"
        "IT301,Data Structures,program_core,5,theory,4,many\n"
    )
    result = parse_subjects_csv(csv_text)
    assert not result.is_valid
    assert any("capacity" in e for e in result.row_errors[0].errors)


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
