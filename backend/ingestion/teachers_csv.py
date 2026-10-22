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

Teachers carry no department metadata and no preferred-slot selections.
Each explicit subject-load pair also declares the maximum weekly hours the
teacher may teach for that subject.
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
    passwords: Dict[str, str] = field(default_factory=dict)
    capabilities: Dict[str, List[str]] = field(default_factory=dict)  # teacher_id -> [subject_code, ...]
    loads: Dict[str, Dict[str, int]] = field(default_factory=dict)  # teacher_id -> subject_code -> max hours
    row_errors: List[RowError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.row_errors) == 0


def parse_teachers_csv(
    content: str,
    known_subject_codes: Optional[Set[str]] = None,
    require_password: bool = False,
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
    password_columns = [index for index, name in enumerate(header) if name == "password"]
    if len(password_columns) > 1 or (require_password and len(password_columns) != 1):
        return TeacherCsvResult(row_errors=[RowError(row_number=0, errors=[
            "A single password column is required."
        ])])

    teachers: List[Teacher] = []
    capabilities: Dict[str, List[str]] = {}
    loads: Dict[str, Dict[str, int]] = {}
    passwords: Dict[str, str] = {}
    row_errors: List[RowError] = []
    seen_ids: Dict[str, int] = {}

    for row_number, row in enumerate(rows[1:], start=1):
        if not any(cell.strip() for cell in row):
            continue  # skip fully blank rows (common at the end of spreadsheet exports)

        errors: List[str] = []
        teacher_id = row[0].strip() if len(row) > 0 else ""
        teacher_name = row[1].strip() if len(row) > 1 else ""
        subject_cells = row[2:]
        header_cells = header[2:]
        password_index = password_columns[0] if password_columns else None
        password = row[password_index].strip() if password_index is not None and password_index < len(row) else ""
        if require_password and not password:
            errors.append("password is required.")
        if len(password) > 1024:
            errors.append("password must not exceed 1024 characters.")
        parsed_pairs: List[tuple[str, Optional[int]]] = []
        pair_format = any(cell.endswith("_load") for cell in header_cells)

        if pair_format:
            for index, cell in enumerate(subject_cells):
                if (
                    index >= len(header_cells)
                    or header_cells[index].endswith("_load")
                    or header_cells[index] == "password"
                ):
                    continue
                code = cell.strip()
                load_index = index + 1
                raw_load = subject_cells[load_index].strip() if load_index < len(subject_cells) else ""
                if not code and not raw_load:
                    continue
                if code and not raw_load:
                    errors.append(f"Missing load for subject_code '{code}'.")
                    continue
                if not code and raw_load:
                    errors.append("A subject load cannot be provided without a subject_code.")
                    continue
                try:
                    numeric_load = float(raw_load)
                    if not numeric_load.is_integer() or numeric_load <= 0:
                        raise ValueError
                    load = int(numeric_load)
                except ValueError:
                    errors.append(f"Load for subject_code '{code}' must be a positive whole number.")
                    continue
                parsed_pairs.append((code, load))
        else:
            parsed_pairs = [
                (cell.strip(), None)
                for index, cell in enumerate(subject_cells)
                if cell.strip() and (index >= len(header_cells) or header_cells[index] != "password")
            ]

        subject_codes = [code for code, _ in parsed_pairs]

        normalized_teacher_id = teacher_id.casefold()
        if teacher_id and normalized_teacher_id in seen_ids:
            errors.append(
                f"Duplicate teacher_id '{teacher_id}' (first seen on row {seen_ids[normalized_teacher_id]})."
            )

        deduped_codes: List[str] = []
        teacher_loads: Dict[str, int] = {}
        for code, load in parsed_pairs:
            if code in deduped_codes:
                errors.append(f"Duplicate subject_code '{code}' for this teacher.")
                continue
            deduped_codes.append(code)
            if load is not None:
                teacher_loads[code] = load

        if known_subject_codes is not None:
            unknown = [c for c in deduped_codes if c not in known_subject_codes]
            if unknown:
                errors.append(f"Unknown subject_code(s) not in the catalog: {', '.join(unknown)}.")

        teacher = Teacher(teacher_id=teacher_id, teacher_name=teacher_name)
        errors.extend(validate_teacher(teacher))

        if errors:
            row_errors.append(RowError(row_number=row_number, errors=errors))
            continue

        seen_ids[normalized_teacher_id] = row_number
        teachers.append(teacher)
        if password:
            passwords[teacher_id] = password
        capabilities[teacher_id] = deduped_codes
        loads[teacher_id] = teacher_loads

    return TeacherCsvResult(
        teachers=teachers,
        passwords=passwords,
        capabilities=capabilities,
        loads=loads,
        row_errors=row_errors,
    )
