"""Shared enumerations and small constants for the domain layer.

Kept deliberately tiny — this is a department-scoped app, not a general
academic ERP, so we only encode the distinctions the product actually
needs (subject type, run lifecycle, valid semesters, working days).
"""
from enum import Enum


class SubjectType(str, Enum):
    THEORY = "theory"
    LAB = "lab"


class RunStatus(str, Enum):
    """Lifecycle of one solver run.

    Per product decision #13, publication is automatic once solving
    completes — DRAFT only exists briefly between run-creation and solve.
    Re-running the solver is not the normal path; PUBLISHED results are
    expected to be refined via manual overrides, not by returning to DRAFT.
    """
    DRAFT = "draft"
    SOLVED = "solved"
    PUBLISHED = "published"


# Odd/even semester split (product decision #2). This department app only
# schedules semesters 3-8 — first-year semesters are intentionally out of
# scope unless a future requirement says otherwise.
ODD_SEMESTERS = (3, 5, 7)
EVEN_SEMESTERS = (4, 6, 8)
VALID_SEMESTERS = tuple(sorted(ODD_SEMESTERS + EVEN_SEMESTERS))

# Working week is Monday-Friday only (product decision #4).
WORKING_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")


def is_odd_semester(semester: int) -> bool:
    return semester in ODD_SEMESTERS


def is_even_semester(semester: int) -> bool:
    return semester in EVEN_SEMESTERS
