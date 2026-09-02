"""CSV ingestion for the teacher roster and subject-capability mapping
(product decision #8).

Unlike the fixed-column subject/student CSVs, a teacher CSV row has a
variable width: teacher_id, teacher_name, then zero or more subject
codes (one per remaining cell) — e.g. "T001, Dr. Sharma, IT301, IT302,
IT305". Each non-empty cell after the first two creates a
teacher-subject capability relationship; blank cells in between are
simply skipped rather than treated as an end-of-row marker, since
spreadsheet exports often pad rows to a common width with stray blanks.
This is why plain csv.reader (ragged rows) is used here instead of
csv.DictReader (fixed field names) — see subjects_csv.py/students_csv.py
for the fixed-column style used elsewhere.

Teachers carry no department metadata and no preferred-slot selections
in this version (product decision #8) — a capability is purely "this
teacher CAN teach this subject", nothing about when or how much.
"""
import csv
import io
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from domain.models import Teacher
from domain.validation import validate_teacher

REQUIRED_HEADER_PREFIX = ("teacher_id", "teacher_name")


@dataclass
class RowError:
    row_number: int  # 1-based CSV data row, header excluded (0 = file-level error)
    errors: List[str]


@dataclass
class TeacherCsvResult:
    teachers: List[Teacher] = field(default_factory=list)
    capabilities: Dict[str, List[str]] = field(default_factory=dict)  # teacher_id -> [subject_code, ...]
    row_errors: List[RowError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.row_errors) == 0


def parse_teachers_csv(
    content: str, known_subject_codes: Optional[Set[str]] = None
) -> TeacherCsvResult:
    """known_subject_codes: if provided, every referenced subject_code
    must exist in it or the row is rejected (Phase 2's subject import
    normally runs before this one, so an unknown code here is almost
    always a typo, not a legitimate "not uploaded yet" situation — pass
    None only for isolated testing of this parser alone)."""
    rows = list(csv.reader(io.StringIO(content)))
    if not rows:
        return TeacherCsvResult(row_errors=[RowError(row_number=0, errors=["CSV file is empty."])])

    header = [c.strip().lower() for c in rows[0]]
    if header[:2] != list(REQUIRED_HEADER_PREFIX):
        return TeacherCsvResult(row_errors=[RowError(row_number=0, errors=[
            "First two columns must be teacher_id, teacher_name."
        ])])

    teachers: List[Teacher] = []
    capabilities: Dict[str, List[str]] = {}
    row_errors: List[RowError] = []
    seen_ids: Dict[str, int] = {}

    for row_number, row in enumerate(rows[1:], start=1):
        if not any(cell.strip() for cell in row):
            continue  # skip fully blank rows (common at the end of spreadsheet exports)

        errors: List[str] = []
        teacher_id = row[0].strip() if len(row) > 0 else ""
        teacher_name = row[1].strip() if len(row) > 1 else ""
        subject_cells = row[2:]
        subject_codes = [c.strip() for c in subject_cells if c.strip()]

        if teacher_id and teacher_id in seen_ids:
            errors.append(
                f"Duplicate teacher_id '{teacher_id}' (first seen on row {seen_ids[teacher_id]})."
            )

        deduped_codes: List[str] = []
        for code in subject_codes:
            if code in deduped_codes:
                errors.append(f"Duplicate subject_code '{code}' for this teacher.")
                continue
            deduped_codes.append(code)

        if known_subject_codes is not None:
            unknown = [c for c in deduped_codes if c not in known_subject_codes]
            if unknown:
                errors.append(f"Unknown subject_code(s) not in the catalog: {', '.join(unknown)}.")

        teacher = Teacher(teacher_id=teacher_id, teacher_name=teacher_name)
        errors.extend(validate_teacher(teacher))

        if errors:
            row_errors.append(RowError(row_number=row_number, errors=errors))
            continue

        seen_ids[teacher_id] = row_number
        teachers.append(teacher)
        capabilities[teacher_id] = deduped_codes

    return TeacherCsvResult(teachers=teachers, capabilities=capabilities, row_errors=row_errors)
