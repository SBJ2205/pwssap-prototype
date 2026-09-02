"""CSV ingestion for the student roster (product decision #7).

Parses raw student CSV text into validated domain.models.Student rows
plus their per-run choice selections. Unlike the subject CSV (Phase 2),
this parser is inherently run-scoped: the number and meaning of the
choice_1..choice_N columns depends entirely on which subject_tag values
the admin marked choice-based for THIS run, and what numeric value each
was assigned (domain.models.ChoiceTagConfig) — see product decision #3.

Required columns: roll_number, name, semester, then exactly one
choice_<n> column per active (is_choice_based=True) tag configured on
the run, in rank order (choice_1 = 1st preference, choice_2 = 2nd, ...).
A run with zero active choice tags requires no choice_* columns at all.
"""
import csv
import io
import re
from dataclasses import dataclass, field
from typing import Dict, List

from domain.models import GenerationRun, Student, StudentChoiceSelection
from domain.validation import validate_student

_CHOICE_COLUMN_RE = re.compile(r"^choice_(\d+)$")


@dataclass
class RowError:
    row_number: int  # 1-based CSV data row, header excluded (0 = file-level error)
    errors: List[str]


@dataclass
class StudentCsvResult:
    students: List[Student] = field(default_factory=list)
    choice_selections: Dict[str, List[StudentChoiceSelection]] = field(default_factory=dict)
    row_errors: List[RowError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.row_errors) == 0


def parse_students_csv(content: str, run: GenerationRun) -> StudentCsvResult:
    active_configs = [c for c in run.choice_tag_configs if c.is_choice_based]
    expected_choice_columns = [f"choice_{i}" for i in range(1, len(active_configs) + 1)]
    valid_numeric_values = {c.numeric_value for c in active_configs}
    tag_by_value = {c.numeric_value: c.tag for c in active_configs}

    reader = csv.DictReader(io.StringIO(content))
    header = reader.fieldnames or []

    required = ["roll_number", "name", "semester"] + expected_choice_columns
    missing = [c for c in required if c not in header]
    if missing:
        return StudentCsvResult(row_errors=[RowError(row_number=0, errors=[
            f"Missing required column(s): {', '.join(missing)}"
        ])])

    extra_choice_columns = sorted(
        c for c in header if _CHOICE_COLUMN_RE.match(c) and c not in expected_choice_columns
    )
    if extra_choice_columns:
        expected_desc = ", ".join(expected_choice_columns) or "(none)"
        return StudentCsvResult(row_errors=[RowError(row_number=0, errors=[
            f"Unexpected column(s) {', '.join(extra_choice_columns)}: this run has "
            f"{len(active_configs)} active choice-based tag(s), so only {expected_desc} "
            f"are expected."
        ])])

    students: List[Student] = []
    choice_selections: Dict[str, List[StudentChoiceSelection]] = {}
    row_errors: List[RowError] = []
    seen_rolls: Dict[str, int] = {}

    for row_number, row in enumerate(reader, start=1):
        errors: List[str] = []

        roll_number = (row.get("roll_number") or "").strip()
        name = (row.get("name") or "").strip()

        raw_semester = (row.get("semester") or "").strip()
        semester = None
        if not raw_semester:
            errors.append("semester is required.")
        else:
            try:
                semester = int(raw_semester)
            except ValueError:
                errors.append(f"semester '{raw_semester}' is not a whole number.")

        if roll_number and roll_number in seen_rolls:
            errors.append(
                f"Duplicate roll_number '{roll_number}' (first seen on row {seen_rolls[roll_number]})."
            )

        selections: List[StudentChoiceSelection] = []
        seen_values_this_row: Dict[int, str] = {}
        for i, column in enumerate(expected_choice_columns, start=1):
            raw_value = (row.get(column) or "").strip()
            if not raw_value:
                errors.append(f"{column} is required.")
                continue
            try:
                value = int(raw_value)
            except ValueError:
                errors.append(f"{column} '{raw_value}' is not a whole number.")
                continue
            if value not in valid_numeric_values:
                errors.append(
                    f"{column} value {value} does not match any active choice-tag numeric "
                    f"value for this run ({sorted(valid_numeric_values)})."
                )
                continue
            if value in seen_values_this_row:
                errors.append(
                    f"{column} repeats value {value} already used in "
                    f"{seen_values_this_row[value]} (tag '{tag_by_value[value]}')."
                )
                continue
            seen_values_this_row[value] = column
            selections.append(
                StudentChoiceSelection(roll_number=roll_number, choice_column=i, numeric_value=value)
            )

        if errors:
            row_errors.append(RowError(row_number=row_number, errors=errors))
            continue

        assert semester is not None  # errors would be non-empty above otherwise

        student = Student(roll_number=roll_number, name=name, semester=semester)
        domain_errors = validate_student(student)
        if semester != run.semester:
            domain_errors.append(
                f"Student semester {semester} does not match run semester {run.semester}."
            )
        if domain_errors:
            row_errors.append(RowError(row_number=row_number, errors=domain_errors))
            continue

        seen_rolls[roll_number] = row_number
        students.append(student)
        choice_selections[roll_number] = selections

    return StudentCsvResult(students=students, choice_selections=choice_selections, row_errors=row_errors)
