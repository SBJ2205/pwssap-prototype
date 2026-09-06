"""CSV ingestion for the subject catalog (product decision #3).

Parses raw subject CSV text into validated domain.models.Subject rows.
Required columns: subject_code, subject_name (or name), subject_tag (or tag),
semester, type, weekly_hours (or hours), capacity.
Optional columns: subtag, slot_structure (or linked_pattern).
"""
import csv
import io
from dataclasses import dataclass
from typing import Dict, List, Optional

from domain.enums import SubjectType
from domain.models import Subject
from domain.validation import validate_subject

# Canonical column names
REQUIRED_COLUMNS = (
    "subject_code",
    "subject_name",
    "subject_tag",
    "semester",
    "type",
    "weekly_hours",
    "capacity",
)

COLUMN_ALIASES = {
    "name": "subject_name",
    "tag": "subject_tag",
    "hours": "weekly_hours",
    "linked_pattern": "slot_structure",
}


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


def _canonicalize_row(raw_row: Dict[str, str]) -> Dict[str, str]:
    normalized = {}
    for k, v in raw_row.items():
        if not k:
            continue
        clean_k = k.strip()
        canon_k = COLUMN_ALIASES.get(clean_k, clean_k)
        normalized[canon_k] = v.strip() if v else ""
    return normalized


def parse_subjects_csv(content: str) -> SubjectCsvResult:
    reader = csv.DictReader(io.StringIO(content))
    raw_header = reader.fieldnames or []
    canonical_header = {COLUMN_ALIASES.get(h.strip(), h.strip()) for h in raw_header if h}

    missing = [c for c in REQUIRED_COLUMNS if c not in canonical_header]
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

    for row_number, raw_row in enumerate(reader, start=1):
        row = _canonicalize_row(raw_row)
        errors: List[str] = []

        code = row.get("subject_code", "")
        name = row.get("subject_name", "")
        tag = row.get("subject_tag", "")
        subtag = row.get("subtag") or None
        raw_type = row.get("type", "").lower()
        slot_structure = row.get("slot_structure") or None

        semester = _parse_int(row.get("semester", ""), "semester", errors)
        weekly_hours = _parse_int(row.get("weekly_hours", ""), "weekly_hours", errors)
        capacity = _parse_int(row.get("capacity", ""), "capacity", errors)

        if not raw_type:
            errors.append("type is required.")
            subject_type = raw_type
        elif raw_type in valid_type_values:
            subject_type = SubjectType(raw_type)
        else:
            subject_type = raw_type

        if code and code in seen_codes:
            errors.append(f"Duplicate subject_code '{code}' (first seen on row {seen_codes[code]}).")

        if errors:
            row_errors.append(RowError(row_number=row_number, errors=errors))
            continue

        assert semester is not None and weekly_hours is not None and capacity is not None

        subject = Subject(
            subject_code=code,
            subject_name=name,
            subject_tag=tag,
            semester=semester,
            type=subject_type,  # type: ignore[arg-type]
            weekly_hours=weekly_hours,
            capacity=capacity,
            subtag=subtag,
            slot_structure=slot_structure,
        )
        domain_errors = validate_subject(subject)
        if domain_errors:
            row_errors.append(RowError(row_number=row_number, errors=domain_errors))
            continue

        seen_codes[code] = row_number
        subjects.append(subject)

    return SubjectCsvResult(subjects=subjects, row_errors=row_errors)
