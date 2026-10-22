"""CSV ingestion for the student roster (department-level).

Parses raw student CSV text into validated domain.models.Student rows.
Required columns: roll_number, name, semester.
Duplicate roll_number in the same CSV is rejected as a row error.
"""
import csv
import io
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from domain.models import GenerationRun, Student, StudentChoiceSelection
from domain.validation import validate_student


@dataclass
class RowError:
    row_number: int  # 1-based CSV data row, header excluded (0 = file-level error)
    errors: List[str]


@dataclass
class StudentCsvResult:
    students: List[Student] = field(default_factory=list)
    passwords: Dict[str, str] = field(default_factory=dict)
    choice_selections: Dict[str, List[StudentChoiceSelection]] = field(default_factory=dict)
    row_errors: List[RowError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.row_errors) == 0


def parse_students_csv(
    content: str, run: Optional[GenerationRun] = None, require_password: bool = False
) -> StudentCsvResult:
    """Parse a student roster, optionally requiring login credentials."""
    reader = csv.DictReader(io.StringIO(content))
    header = [h.strip() for h in (reader.fieldnames or [])]
    reader.fieldnames = header

    # Strip header whitespace
    header = [h.strip() for h in header]
    required = ["roll_number", "name", "semester"]
    if require_password:
        required.append("password")
    missing = [c for c in required if c not in header]
    if missing:
        return StudentCsvResult(row_errors=[RowError(row_number=0, errors=[
            f"Missing required column(s): {', '.join(missing)}"
        ])])

    students: List[Student] = []
    passwords: Dict[str, str] = {}
    row_errors: List[RowError] = []
    seen_rolls: Dict[str, int] = {}

    for row_number, raw_row in enumerate(reader, start=1):
        errors: List[str] = []
        row = {k.strip() if k else "": (v.strip() if v else "") for k, v in raw_row.items()}

        roll_number = row.get("roll_number", "")
        name = row.get("name", "")
        raw_semester = row.get("semester", "")
        password = row.get("password", "")

        if not roll_number:
            errors.append("roll_number is required.")
        if not name:
            errors.append("name is required.")
        if require_password and not password:
            errors.append("password is required.")
        if len(password) > 1024:
            errors.append("password must not exceed 1024 characters.")

        semester = None
        if not raw_semester:
            errors.append("semester is required.")
        else:
            try:
                semester = int(raw_semester)
            except ValueError:
                errors.append(f"semester '{raw_semester}' is not a whole number.")

        if roll_number:
            normalized_roll = roll_number.casefold()
            if normalized_roll in seen_rolls:
                errors.append(
                    f"Duplicate roll_number '{roll_number}' (first seen on row {seen_rolls[normalized_roll]})."
                )
            else:
                seen_rolls[normalized_roll] = row_number

        if errors:
            row_errors.append(RowError(row_number=row_number, errors=errors))
            continue

        assert semester is not None
        student = Student(roll_number=roll_number, name=name, semester=semester)
        domain_errors = validate_student(student)
        if domain_errors:
            row_errors.append(RowError(row_number=row_number, errors=domain_errors))
            continue

        students.append(student)
        if password:
            passwords[roll_number] = password

    return StudentCsvResult(students=students, passwords=passwords, row_errors=row_errors)
