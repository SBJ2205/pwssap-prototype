"""Sanity checks for Phase 3's run-scoped student CSV ingestion.

Run directly with (from backend/):
    venv\\Scripts\\python.exe -m tests.test_students_csv
"""
from domain.models import ChoiceTagConfig, GenerationRun
from ingestion.students_csv import parse_students_csv


def _run(semester=5, configs=None):
    if configs is None:
        configs = [
            ChoiceTagConfig(tag="open_elective", numeric_value=1),
            ChoiceTagConfig(tag="mdm", numeric_value=2),
        ]
    return GenerationRun(id=1, semester=semester, choice_tag_configs=configs)


VALID_CSV = (
    "roll_number,name,semester,choice_1,choice_2\n"
    "23101A0001,Asha Rao,5,1,2\n"
    "23101A0002,Vivek Nair,5,2,1\n"
)


def test_valid_csv_parses_with_no_row_errors():
    result = parse_students_csv(VALID_CSV, _run())
    assert result.is_valid, result.row_errors
    assert len(result.students) == 2
    asha = next(s for s in result.students if s.roll_number == "23101A0001")
    assert asha.name == "Asha Rao"
    assert asha.semester == 5

    selections = result.choice_selections["23101A0001"]
    assert [(s.choice_column, s.numeric_value) for s in selections] == [(1, 1), (2, 2)]


def test_run_with_zero_active_tags_requires_no_choice_columns():
    run = _run(configs=[])
    csv_text = "roll_number,name,semester\n23101A0001,Asha Rao,5\n"
    result = parse_students_csv(csv_text, run)
    assert result.is_valid, result.row_errors
    assert result.choice_selections["23101A0001"] == []


def test_inactive_tag_does_not_count_toward_expected_columns():
    run = _run(configs=[
        ChoiceTagConfig(tag="open_elective", numeric_value=1, is_choice_based=True),
        ChoiceTagConfig(tag="mdm", numeric_value=2, is_choice_based=False),
    ])
    csv_text = "roll_number,name,semester,choice_1\n23101A0001,Asha Rao,5,1\n"
    result = parse_students_csv(csv_text, run)
    assert result.is_valid, result.row_errors


def test_missing_required_column_is_a_file_level_error():
    csv_text = "roll_number,name,semester\n23101A0001,Asha Rao,5\n"  # missing choice_1, choice_2
    result = parse_students_csv(csv_text, _run())
    assert not result.is_valid
    assert result.row_errors[0].row_number == 0
    assert "choice_1" in result.row_errors[0].errors[0]


def test_extra_choice_column_is_a_file_level_error():
    csv_text = (
        "roll_number,name,semester,choice_1,choice_2,choice_3\n"
        "23101A0001,Asha Rao,5,1,2,1\n"
    )
    result = parse_students_csv(csv_text, _run())  # run only has 2 active tags
    assert not result.is_valid
    assert result.row_errors[0].row_number == 0
    assert "choice_3" in result.row_errors[0].errors[0]


def test_choice_value_outside_run_config_is_a_row_error():
    csv_text = "roll_number,name,semester,choice_1,choice_2\n23101A0001,Asha Rao,5,9,2\n"
    result = parse_students_csv(csv_text, _run())
    assert not result.is_valid
    assert any("choice_1" in e for e in result.row_errors[0].errors)


def test_duplicate_value_within_same_row_is_a_row_error():
    csv_text = "roll_number,name,semester,choice_1,choice_2\n23101A0001,Asha Rao,5,1,1\n"
    result = parse_students_csv(csv_text, _run())
    assert not result.is_valid
    assert any("repeats value" in e for e in result.row_errors[0].errors)


def test_duplicate_roll_number_is_a_row_error():
    csv_text = (
        "roll_number,name,semester,choice_1,choice_2\n"
        "23101A0001,Asha Rao,5,1,2\n"
        "23101A0001,Asha Rao Again,5,2,1\n"
    )
    result = parse_students_csv(csv_text, _run())
    assert not result.is_valid
    assert len(result.students) == 1
    assert any("Duplicate roll_number" in e for e in result.row_errors[0].errors)
    assert result.row_errors[0].row_number == 2


def test_student_semester_mismatch_with_run_is_a_row_error():
    csv_text = "roll_number,name,semester,choice_1,choice_2\n23101A0001,Asha Rao,6,1,2\n"
    result = parse_students_csv(csv_text, _run(semester=5))
    assert not result.is_valid
    assert any("does not match run semester" in e for e in result.row_errors[0].errors)


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
