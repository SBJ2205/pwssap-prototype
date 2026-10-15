"""Sanity checks for simple department-level student CSV ingestion.

Run directly with (from backend/):
    venv\\Scripts\\python.exe -m tests.test_students_csv
"""
from ingestion.students_csv import parse_students_csv

VALID_CSV = (
    "roll_number,name,semester\n"
    "23101A0001,Asha Rao,5\n"
    "23101A0002,Vivek Nair,5\n"
)


def test_valid_csv_parses_with_no_row_errors():
    result = parse_students_csv(VALID_CSV)
    assert result.is_valid, result.row_errors
    assert len(result.students) == 2
    asha = next(s for s in result.students if s.roll_number == "23101A0001")
    assert asha.name == "Asha Rao"
    assert asha.semester == 5


def test_missing_required_column_is_a_file_level_error():
    csv_text = "roll_number,name\n23101A0001,Asha Rao\n"
    result = parse_students_csv(csv_text)
    assert not result.is_valid
    assert result.row_errors[0].row_number == 0
    assert "semester" in result.row_errors[0].errors[0]


def test_duplicate_roll_number_is_a_row_error():
    csv_text = (
        "roll_number,name,semester\n"
        "23101A0001,Asha Rao,5\n"
        "23101A0001,Asha Rao Again,5\n"
    )
    result = parse_students_csv(csv_text)
    assert not result.is_valid
    assert len(result.students) == 1
    assert any("Duplicate roll_number" in e for e in result.row_errors[0].errors)
    assert result.row_errors[0].row_number == 2


def test_invalid_semester_is_a_row_error():
    csv_text = "roll_number,name,semester\n23101A0001,Asha Rao,invalid\n"
    result = parse_students_csv(csv_text)
    assert not result.is_valid
    assert any("whole number" in e for e in result.row_errors[0].errors)


def test_out_of_range_semester_is_a_row_error():
    csv_text = "roll_number,name,semester\n23101A0001,Asha Rao,1\n"
    result = parse_students_csv(csv_text)
    assert not result.is_valid
    assert any("Semester 1 is not valid" in e for e in result.row_errors[0].errors)


def test_whitespace_is_trimmed():
    csv_text = " roll_number , name , semester \n 23101A0001 , Asha Rao , 5 \n"
    result = parse_students_csv(csv_text)
    assert result.is_valid, result.row_errors
    assert result.students[0].roll_number == "23101A0001"
    assert result.students[0].name == "Asha Rao"
    assert result.students[0].semester == 5


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
