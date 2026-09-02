"""CSV ingestion for the subject catalog (product decision #3).

Parses raw subject CSV text into validated domain.models.Subject rows.
Deliberately kept separate from:
- the api/ layer, which only handles HTTP framing (file upload, status
  codes, JSON shaping);
- domain/validation.py, which only knows how to validate an
  already-constructed Subject, not how to read/convert raw CSV columns.

Required columns: subject_code, subject_name, subject_tag, semester,
type, weekly_hours, capacity.
Optional columns: slot_structure (or linked_pattern, an accepted alias
for the same column — later phases decide how to parse it into concrete
linked meetings; Phase 2 only captures the raw value).
"""
import csv
import io
from dataclasses import dataclass
from typing import List, Optional

from domain.enums import SubjectType
from domain.models import Subject
from domain.validation import validate_subject

REQUIRED_COLUMNS = (
    "subject_code",
    "subject_name",
    "subject_tag",
    "semester",
    "type",
    "weekly_hours",
    "capacity",
)


@dataclass
class RowError:
    row_number: int  # 1-based CSV data row, header excluded (0 = file-level error)
    errors: List[str]


@dataclass
class SubjectCsvResult:
    subjects: List[Subject]
    row_errors: List[RowError]

    @property
    def is_valid(self) -> bool:
        return len(self.row_errors) == 0


def _parse_int(raw: str, field_name: str, errors: List[str]) -> Optional[int]:
    raw = (raw or "").strip()
    if not raw:
        errors.append(f"{field_name} is required.")
        return None
    try:
        return int(raw)
    except ValueError:
        errors.append(f"{field_name} '{raw}' is not a whole number.")
        return None


def parse_subjects_csv(content: str) -> SubjectCsvResult:
    reader = csv.DictReader(io.StringIO(content))
    header = reader.fieldnames or []
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        return SubjectCsvResult(
            subjects=[],
            row_errors=[RowError(row_number=0, errors=[
                f"Missing required column(s): {', '.join(missing)}"
            ])],
        )

    subjects: List[Subject] = []
    row_errors: List[RowError] = []
    seen_codes = {}
    valid_type_values = {t.value for t in SubjectType}

    for row_number, row in enumerate(reader, start=1):
        errors: List[str] = []

        code = (row.get("subject_code") or "").strip()
        name = (row.get("subject_name") or "").strip()
        tag = (row.get("subject_tag") or "").strip()
        raw_type = (row.get("type") or "").strip().lower()
        slot_structure = (row.get("slot_structure") or row.get("linked_pattern") or "").strip() or None

        semester = _parse_int(row.get("semester", ""), "semester", errors)
        weekly_hours = _parse_int(row.get("weekly_hours", ""), "weekly_hours", errors)
        capacity = _parse_int(row.get("capacity", ""), "capacity", errors)

        if not raw_type:
            errors.append("type is required.")
            subject_type = raw_type
        elif raw_type in valid_type_values:
            subject_type = SubjectType(raw_type)
        else:
            subject_type = raw_type  # kept as-is so validate_subject reports the exact bad value

        if code and code in seen_codes:
            errors.append(f"Duplicate subject_code '{code}' (first seen on row {seen_codes[code]}).")

        if errors:
            row_errors.append(RowError(row_number=row_number, errors=errors))
            continue

        # errors is empty at this point, so _parse_int already guaranteed
        # these three are not None -- narrow the type for the checker.
        assert semester is not None and weekly_hours is not None and capacity is not None

        subject = Subject(
            subject_code=code,
            subject_name=name,
            subject_tag=tag,
            semester=semester,
            type=subject_type,  # type: ignore[arg-type]  -- may be an invalid raw string here; validate_subject below reports it
            weekly_hours=weekly_hours,
            capacity=capacity,
            slot_structure=slot_structure,
        )
        domain_errors = validate_subject(subject)
        if domain_errors:
            row_errors.append(RowError(row_number=row_number, errors=domain_errors))
            continue

        seen_codes[code] = row_number
        subjects.append(subject)

    return SubjectCsvResult(subjects=subjects, row_errors=row_errors)
