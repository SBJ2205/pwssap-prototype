"""Validation helpers for domain entities.

Each `validate_*` function returns a list of human-readable error strings
(an empty list means "valid"). This shape is deliberately reused by the
CSV import layers added in later phases (Phase 2-4), where every row of a
CSV needs its own independent list of errors rather than a single
raise-on-first-problem exception.
"""
from typing import Iterable, List

from domain.enums import SubjectType, VALID_SEMESTERS
from domain.models import ChoiceTagConfig, Student, Subject, Teacher
from domain.timeslots import TimeSlot, is_slot_usable, slot_allows


def validate_semester(semester: int) -> List[str]:
    errors = []
    if semester not in VALID_SEMESTERS:
        errors.append(
            f"Semester {semester} is not valid. Must be one of {list(VALID_SEMESTERS)}."
        )
    return errors


def validate_subject_type(subject_type) -> List[str]:
    value = subject_type.value if isinstance(subject_type, SubjectType) else subject_type
    valid_values = {t.value for t in SubjectType}
    errors = []
    if value not in valid_values:
        errors.append(f"Subject type '{subject_type}' is invalid. Must be one of {sorted(valid_values)}.")
    return errors


def validate_subject(subject: Subject) -> List[str]:
    errors: List[str] = []
    if not subject.subject_code or not subject.subject_code.strip():
        errors.append("subject_code is required.")
    if not subject.subject_name or not subject.subject_name.strip():
        errors.append("subject_name is required.")
    if not subject.subject_tag or not subject.subject_tag.strip():
        errors.append("subject_tag is required.")

    errors.extend(validate_semester(subject.semester))
    errors.extend(validate_subject_type(subject.type))

    if subject.weekly_hours is None or subject.weekly_hours <= 0:
        errors.append("weekly_hours must be a positive integer.")
    if subject.capacity is None or subject.capacity <= 0:
        errors.append("capacity must be a positive integer.")
    return errors


def validate_teacher(teacher: Teacher) -> List[str]:
    errors: List[str] = []
    if not teacher.teacher_id or not teacher.teacher_id.strip():
        errors.append("teacher_id is required.")
    if not teacher.teacher_name or not teacher.teacher_name.strip():
        errors.append("teacher_name is required.")
    return errors


def validate_student(student: Student) -> List[str]:
    errors: List[str] = []
    if not student.roll_number or not student.roll_number.strip():
        errors.append("roll_number is required.")
    if not student.name or not student.name.strip():
        errors.append("name is required.")
    errors.extend(validate_semester(student.semester))
    return errors


def validate_slot_for_subject_type(slot: TimeSlot, subject_type: SubjectType) -> List[str]:
    """Hard structural check used by section generation / the solver:
    can a subject of this type ever legally meet in this slot?"""
    errors: List[str] = []
    if not is_slot_usable(slot):
        errors.append(
            f"{slot.key} ({slot.day} {slot.start_time}-{slot.end_time}) is not usable for any subject."
        )
    elif not slot_allows(slot, subject_type):
        type_value = subject_type.value if isinstance(subject_type, SubjectType) else subject_type
        errors.append(
            f"{slot.key} ({slot.day} {slot.start_time}-{slot.end_time}) does not allow {type_value} subjects."
        )
    return errors


def validate_choice_tag_configs(configs: Iterable[ChoiceTagConfig]) -> List[str]:
    """Structural validation for a run's choice-tag configuration
    (product decision #3): tag names must be non-empty and numeric
    values must be unique within the run."""
    errors: List[str] = []
    seen_values = {}
    seen_tags = set()
    for cfg in configs:
        if not cfg.tag or not cfg.tag.strip():
            errors.append("Choice tag name is required.")
        elif cfg.tag in seen_tags:
            errors.append(f"Tag '{cfg.tag}' is configured more than once for this run.")
        else:
            seen_tags.add(cfg.tag)

        if cfg.numeric_value in seen_values:
            errors.append(
                f"Numeric value {cfg.numeric_value} is used by both "
                f"'{seen_values[cfg.numeric_value]}' and '{cfg.tag}'."
            )
        else:
            seen_values[cfg.numeric_value] = cfg.tag
    return errors
