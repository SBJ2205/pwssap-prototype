"""Validation helpers for domain entities.

Each `validate_*` function returns a list of human-readable error strings
(an empty list means "valid"). This shape is deliberately reused by the
CSV import layers added in later phases (Phase 2-4), where every row of a
CSV needs its own independent list of errors rather than a single
raise-on-first-problem exception.
"""
from dataclasses import dataclass, field
from typing import Dict, Iterable, List

from domain.enums import PreferenceRating, SubjectType, VALID_SEMESTERS
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


def validate_slot_keys(slot_keys: Iterable[str], valid_slot_keys: Iterable[str]) -> List[str]:
    """Used by teacher-availability updates (product decision #9) to
    reject any slot_key that isn't one of the canonical grid's keys
    before writing anything."""
    unknown = sorted(set(slot_keys) - set(valid_slot_keys))
    if unknown:
        return [f"Unknown slot_key(s): {', '.join(unknown)}"]
    return []


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


# ── Student time-slot preference validation (product decision #10) ─────────
# A student should never be able to save a matrix that's effectively empty
# or uninformative. BLOCKED_REJECT_RATIO is a hard cutoff (rejected outright,
# since near-total blocking makes scheduling that student nearly
# impossible); the others are soft signals that only produce a warning so
# the student can still save if they mean it.
BLOCKED_REJECT_RATIO = 0.7
LOW_PREFERENCE_WARN_RATIO = 0.8
UNIFORM_WARN_MIN_RATED = 5


@dataclass
class PreferenceValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def validate_time_slot_preferences(
    ratings: Dict[str, int], ratable_slot_keys: Iterable[str]
) -> PreferenceValidationResult:
    errors: List[str] = []
    warnings: List[str] = []
    ratable_keys = set(ratable_slot_keys)

    if not ratings:
        errors.append(
            "You haven't rated any time slots yet. Rate at least a few slots before saving."
        )
        return PreferenceValidationResult(errors=errors, warnings=warnings)

    unknown_keys = sorted(set(ratings.keys()) - ratable_keys)
    if unknown_keys:
        errors.append(f"Unknown or unratable slot_key(s): {', '.join(unknown_keys)}")

    valid_values = {r.value for r in PreferenceRating}
    bad_values = sorted({str(v) for v in ratings.values() if v not in valid_values})
    if bad_values:
        errors.append(
            f"Rating values must be one of {sorted(valid_values)}; got: {', '.join(bad_values)}"
        )

    if errors:
        return PreferenceValidationResult(errors=errors, warnings=warnings)

    total_ratable = len(ratable_keys)
    rated_count = len(ratings)
    blocked_count = sum(1 for v in ratings.values() if v == PreferenceRating.BLOCKED.value)
    low_count = sum(
        1 for v in ratings.values()
        if v in (PreferenceRating.DISLIKED.value, PreferenceRating.BLOCKED.value)
    )

    if total_ratable and (blocked_count / total_ratable) > BLOCKED_REJECT_RATIO:
        errors.append(
            f"Too many slots are marked Blocked (more than {int(BLOCKED_REJECT_RATIO * 100)}% "
            "of the week). This would make it nearly impossible to schedule you -- please "
            "unblock some slots and try again."
        )
        return PreferenceValidationResult(errors=errors, warnings=warnings)

    if rated_count and (low_count / rated_count) >= LOW_PREFERENCE_WARN_RATIO:
        warnings.append(
            "Most of your rated slots are marked Disliked or Blocked. Consider marking a few "
            "more slots as Preferred or Tolerable so we can find you a better schedule."
        )

    if rated_count >= UNIFORM_WARN_MIN_RATED and len(set(ratings.values())) == 1:
        warnings.append(
            "You rated every slot the same. Try spreading your preferences across a few "
            "different ratings so we know which times you actually prefer."
        )

    return PreferenceValidationResult(errors=errors, warnings=warnings)
