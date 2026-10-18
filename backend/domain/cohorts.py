"""Domain models and rules for Traditional Division & Batch scheduling mode.

In this mode students are structured into:

- Divisions (Div-A, Div-B, ...). Membership is fixed once saved and theory is
  taught per division.
- Lab batches (A1, A2, ...). Each division is split into a configurable number
  of batches; labs are taught per batch.

How a semester's subjects behave is derived from their *shape* in the catalog
(tag, subtag, type) and from the cycle's choice-based tag configuration, never
from a tag that happens to be called "PE" or "MDM":

- Track electives: a choice-based tag with >= 2 distinct subtags where at least
  one subject is a lab (e.g. Sem 6 PE: AIML / CSEC, each with theory + labs).
  Students are partitioned by their locked-in subtag, and every division is
  formed *inside* one track.
- Dispersal electives: a choice-based tag with >= 2 distinct subtags where every
  subject is theory (e.g. Sem 4 MDM). One section per subject, all running at
  the same time across every division so students can split between them.
- Single-offering electives: a choice-based tag with only one subtag. Taught
  in-class like core.
- Everything else (core, and non-choice electives such as a lab tagged OE) is
  taught in-class: theory per division, labs per batch.

This module is pure domain logic: it takes the store as a duck-typed argument and
does not import it, so ``data.store`` never has to depend on traditional mode.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

MIN_BATCHES = 2
MAX_BATCHES = 6
DEFAULT_DIVISION_SIZE = 60
DEFAULT_LAB_BATCH_SIZE = 20
UNASSIGNED_TRACK = "UNASSIGNED"


class CohortConfigError(ValueError):
    """Raised when a cohort configuration is invalid. Carries every problem found."""

    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


# ── Configuration models ───────────────────────────────────────────────────


@dataclass
class LabBatch:
    batch_id: str                      # e.g. "A1", "A2", "B1"
    batch_name: str                    # e.g. "Batch A1"
    student_rolls: List[str] = field(default_factory=list)


@dataclass
class ClassCohort:
    class_id: str                      # e.g. "Div-A"
    class_name: str                    # e.g. "Division A (AIML)"
    semester: int
    track_tag: Optional[str] = None    # the track elective tag (e.g. "PE"), if the semester has one
    track: Optional[str] = None        # the division's track (e.g. "AIML"), derived from its members
    student_rolls: List[str] = field(default_factory=list)
    lab_batch_count: int = 3
    batches: List[LabBatch] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "semester": self.semester,
            "track_tag": self.track_tag,
            "track": self.track,
            "student_rolls": list(self.student_rolls),
            "lab_batch_count": self.lab_batch_count,
            "batches": [
                {
                    "batch_id": b.batch_id,
                    "batch_name": b.batch_name,
                    "student_rolls": list(b.student_rolls),
                }
                for b in self.batches
            ],
        }


@dataclass
class SemesterCohortConfig:
    semester: int
    classes: List[ClassCohort] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "semester": self.semester,
            "classes": [c.to_dict() for c in self.classes],
        }


# ── Catalog helpers ────────────────────────────────────────────────────────


def is_lab(subject: Any) -> bool:
    return str(getattr(subject.type, "value", subject.type)).strip().lower() == "lab"


def subject_type_value(subject: Any) -> str:
    return str(getattr(subject.type, "value", subject.type)).strip().lower()


@dataclass
class SemesterStructure:
    """How a semester's subjects split into the traditional categories."""
    semester: int
    track_tag: Optional[str] = None
    track_subtags: List[str] = field(default_factory=list)
    track_subjects: List[Any] = field(default_factory=list)
    dispersal_groups: List[Tuple[str, List[Any]]] = field(default_factory=list)
    in_class_electives: List[Any] = field(default_factory=list)
    core_subjects: List[Any] = field(default_factory=list)
    unsupported_track_tags: List[str] = field(default_factory=list)

    @property
    def dispersal_codes(self) -> Set[str]:
        return {s.subject_code for _, subjects in self.dispersal_groups for s in subjects}


def classify_semester(store: Any, semester: int) -> SemesterStructure:
    """Classify a semester's subjects by tag / subtag / type shape."""
    structure = SemesterStructure(semester=semester)
    subjects = store.list_subjects(semester=semester)
    choice_tags = store.get_choice_based_tags_for_semester(semester)

    by_tag: Dict[str, List[Any]] = {}
    for subject in subjects:
        by_tag.setdefault(subject.subject_tag, []).append(subject)

    for tag in sorted(by_tag):
        group = by_tag[tag]
        if tag not in choice_tags:
            structure.core_subjects.extend(group)
            continue
        subtags = sorted({st for s in group for st in s.supported_subtags})
        if len(subtags) < 2:
            structure.in_class_electives.extend(group)
        elif any(is_lab(s) for s in group):
            if structure.track_tag is None:
                structure.track_tag = tag
                structure.track_subtags = subtags
                structure.track_subjects = list(group)
            else:
                structure.unsupported_track_tags.append(tag)
        else:
            structure.dispersal_groups.append((tag, list(group)))
    return structure


def enrolled_codes(store: Any, roll_number: str) -> Set[str]:
    return {s.subject_code for s in store.get_enrolled_subjects_for_student(roll_number)}


def student_track(store: Any, structure: SemesterStructure, roll_number: str) -> str:
    """The student's locked-in track, or UNASSIGNED when absent / not a known track."""
    if not structure.track_tag:
        return ""
    chosen = str(store.get_lock_in_for_student(roll_number).get(structure.track_tag, "")).strip()
    return chosen if chosen in structure.track_subtags else UNASSIGNED_TRACK


def semester_students(store: Any, semester: int) -> List[Any]:
    return sorted(store.list_students(semester=semester), key=lambda s: s.roll_number)


def _min_capacity(subjects: List[Any], default: int) -> int:
    caps = [int(s.capacity) for s in subjects if getattr(s, "capacity", 0)]
    return min(caps) if caps else default


def division_capacity(structure: SemesterStructure) -> int:
    theory = [s for s in structure.core_subjects + structure.track_subjects + structure.in_class_electives
              if not is_lab(s)]
    return _min_capacity(theory, DEFAULT_DIVISION_SIZE)


def lab_batch_capacity(structure: SemesterStructure) -> int:
    labs = [s for s in structure.core_subjects + structure.track_subjects + structure.in_class_electives
            if is_lab(s)]
    return _min_capacity(labs, DEFAULT_LAB_BATCH_SIZE)


# ── Splitting helpers ──────────────────────────────────────────────────────


def balanced_chunks(items: List[Any], parts: int) -> List[List[Any]]:
    """Split into `parts` contiguous chunks whose sizes differ by at most one."""
    parts = max(1, parts)
    base, extra = divmod(len(items), parts)
    chunks: List[List[Any]] = []
    start = 0
    for i in range(parts):
        size = base + (1 if i < extra else 0)
        chunks.append(items[start:start + size])
        start += size
    return chunks


def division_letter(index: int) -> str:
    """0 -> A ... 25 -> Z, then AA, AB, ..."""
    letters = ""
    n = index
    while True:
        letters = chr(ord("A") + n % 26) + letters
        n = n // 26 - 1
        if n < 0:
            return letters


def class_letter(class_id: str, fallback: str) -> str:
    stripped = class_id.strip()
    for prefix in ("DIV-", "DIV ", "DIV_"):
        if stripped.upper().startswith(prefix):
            stripped = stripped[len(prefix):]
            break
    return stripped.strip() or fallback


# ── Detection ──────────────────────────────────────────────────────────────


def detect_clusters(store: Any, semester: int) -> dict:
    """Describe a semester for the admin: tracks, dispersal and in-class electives."""
    structure = classify_semester(store, semester)
    students = semester_students(store, semester)
    size = division_capacity(structure)
    warnings: List[str] = []

    clusters: List[dict] = []
    if structure.track_tag:
        by_track: Dict[str, List[Any]] = {}
        for st in students:
            by_track.setdefault(student_track(store, structure, st.roll_number), []).append(st)
        for track_id in sorted(by_track, key=lambda t: (t == UNASSIGNED_TRACK, t)):
            members = by_track[track_id]
            clusters.append({
                "track_id": track_id,
                "track_name": track_id if track_id != UNASSIGNED_TRACK else "No track chosen",
                "student_count": len(members),
                "students": [{"roll_number": s.roll_number, "name": s.name} for s in members],
                "suggested_divisions": max(1, round(len(members) / size)),
            })
        if UNASSIGNED_TRACK in by_track:
            warnings.append(
                f"{len(by_track[UNASSIGNED_TRACK])} student(s) have not chosen a {structure.track_tag} track. "
                "They must lock in a choice before divisions can be saved."
            )
    else:
        clusters.append({
            "track_id": "ALL",
            "track_name": f"Semester {semester} cohort",
            "student_count": len(students),
            "students": [{"roll_number": s.roll_number, "name": s.name} for s in students],
            "suggested_divisions": max(1, round(len(students) / size)),
        })

    for tag in structure.unsupported_track_tags:
        warnings.append(
            f"Tag '{tag}' also looks like a track elective. Only one track tag per semester is supported."
        )

    dispersal = []
    for tag, subjects in structure.dispersal_groups:
        codes = []
        for s in subjects:
            count = sum(1 for st in students if s.subject_code in enrolled_codes(store, st.roll_number))
            codes.append({
                "subject_code": s.subject_code,
                "subject_name": s.subject_name,
                "type": subject_type_value(s),
                "subtag": s.subtag,
                "weekly_hours": s.weekly_hours,
                "student_count": count,
            })
        no_choice = sum(
            1 for st in students
            if not any(c["subject_code"] in enrolled_codes(store, st.roll_number) for c in codes)
        )
        if no_choice:
            warnings.append(f"{no_choice} student(s) have not chosen a {tag} elective and will get none.")
        dispersal.append({
            "tag": tag,
            "is_dispersal": True,
            "subjects": codes,
            "note": (
                f"{len(subjects)} theory subjects offered. One section each, all at the same time in every "
                "division, so students can split between them. They never clash with core classes."
            ),
        })

    in_class = [
        {
            "tag": s.subject_tag,
            "subject_code": s.subject_code,
            "subject_name": s.subject_name,
            "type": subject_type_value(s),
            "weekly_hours": s.weekly_hours,
            "is_dispersal": False,
            "note": "Only one offering for this elective tag: taught in-class inside each division, no dispersal.",
        }
        for s in structure.in_class_electives
    ]
    core = [
        {
            "subject_code": s.subject_code,
            "subject_name": s.subject_name,
            "subject_tag": s.subject_tag,
            "type": subject_type_value(s),
            "weekly_hours": s.weekly_hours,
        }
        for s in structure.core_subjects
    ]
    track_subjects: Dict[str, List[str]] = {}
    for s in structure.track_subjects:
        for st in s.supported_subtags:
            track_subjects.setdefault(st, []).append(s.subject_code)

    return {
        "semester": semester,
        "total_students": len(students),
        "track_tag": structure.track_tag,
        "has_tracks": structure.track_tag is not None,
        "track_subjects": track_subjects,
        "clusters": clusters,
        "dispersal_electives": dispersal,
        "in_class_electives": in_class,
        "core_subjects": core,
        "max_division_size": size,
        "max_batch_size": lab_batch_capacity(structure),
        "warnings": warnings,
    }


# ── Suggestion ─────────────────────────────────────────────────────────────


def default_batch_count(division_size: int, batch_capacity: int) -> int:
    needed = -(-division_size // max(1, batch_capacity))
    return max(MIN_BATCHES, min(MAX_BATCHES, needed))


def suggest_classes(
    store: Any,
    semester: int,
    max_division_size: Optional[int] = None,
) -> List[dict]:
    """Suggest divisions: balanced, contiguous by roll number, inside each track."""
    structure = classify_semester(store, semester)
    target = max_division_size or division_capacity(structure)
    batch_cap = lab_batch_capacity(structure)
    students = semester_students(store, semester)

    groups: List[Tuple[Optional[str], List[Any]]] = []
    if structure.track_tag:
        by_track: Dict[str, List[Any]] = {}
        for st in students:
            by_track.setdefault(student_track(store, structure, st.roll_number), []).append(st)
        for track_id in sorted(by_track):
            if track_id != UNASSIGNED_TRACK:
                groups.append((track_id, by_track[track_id]))
    else:
        groups.append((None, students))

    classes: List[dict] = []
    counter = 0
    for track_id, members in groups:
        if not members:
            continue
        parts = max(1, round(len(members) / target))
        for chunk in balanced_chunks(members, parts):
            letter = division_letter(counter)
            counter += 1
            classes.append({
                "class_id": f"Div-{letter}",
                "class_name": f"Division {letter}" + (f" ({track_id})" if track_id else ""),
                "track_tag": structure.track_tag,
                "track": track_id,
                "student_rolls": [s.roll_number for s in chunk],
                "lab_batch_count": default_batch_count(len(chunk), batch_cap),
            })
    return classes


# ── Validation / construction ──────────────────────────────────────────────


def build_config(
    store: Any,
    semester: int,
    classes: List[dict],
) -> Tuple[SemesterCohortConfig, List[str]]:
    """Validate admin input and build the saved configuration (divisions + batches).

    Raises CohortConfigError listing every problem. Returns (config, warnings).
    """
    structure = classify_semester(store, semester)
    errors: List[str] = []
    warnings: List[str] = []

    if structure.unsupported_track_tags:
        errors.append(
            f"Semester {semester} has more than one track elective tag "
            f"({structure.track_tag}, {', '.join(structure.unsupported_track_tags)}); only one is supported."
        )
    if not classes:
        errors.append("At least one division is required.")

    roster = {s.roll_number for s in store.list_students(semester=semester)}
    seen_classes: Set[str] = set()
    seen_rolls: Dict[str, str] = {}
    prepared: List[Tuple[dict, List[str]]] = []

    for position, raw in enumerate(classes):
        class_id = str(raw.get("class_id", "")).strip()
        if not class_id:
            errors.append(f"Division #{position + 1} has no id.")
            continue
        if class_id.lower() in seen_classes:
            errors.append(f"Division id '{class_id}' is used more than once.")
            continue
        seen_classes.add(class_id.lower())

        rolls = []
        for roll in raw.get("student_rolls", []):
            roll = str(roll).strip()
            if roll not in roster:
                errors.append(f"Student {roll} in {class_id} does not belong to semester {semester}.")
            elif roll in seen_rolls:
                errors.append(f"Student {roll} is placed in both {seen_rolls[roll]} and {class_id}.")
            else:
                seen_rolls[roll] = class_id
                rolls.append(roll)
        if not rolls:
            errors.append(f"Division {class_id} has no students.")
        prepared.append((raw, sorted(rolls)))

    missing = sorted(roster - set(seen_rolls))
    if missing:
        sample = ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else "")
        errors.append(f"{len(missing)} student(s) are not placed in any division: {sample}.")

    div_cap = division_capacity(structure)
    batch_cap = lab_batch_capacity(structure)
    built: List[ClassCohort] = []

    for position, (raw, rolls) in enumerate(prepared):
        class_id = str(raw["class_id"]).strip()
        if not rolls:
            continue

        track: Optional[str] = None
        if structure.track_tag:
            member_tracks = {student_track(store, structure, r) for r in rolls}
            if UNASSIGNED_TRACK in member_tracks:
                errors.append(
                    f"Division {class_id} has students without a {structure.track_tag} choice."
                )
            elif len(member_tracks) > 1:
                errors.append(
                    f"Division {class_id} mixes {structure.track_tag} tracks "
                    f"({', '.join(sorted(member_tracks))}). Each division must stay inside one track."
                )
            else:
                track = next(iter(member_tracks))

        try:
            num_batches = int(raw.get("lab_batch_count", 3))
        except (TypeError, ValueError):
            num_batches = 0
        if not MIN_BATCHES <= num_batches <= MAX_BATCHES:
            errors.append(
                f"Division {class_id}: lab batch count must be between {MIN_BATCHES} and {MAX_BATCHES}."
            )
            continue
        if num_batches > len(rolls):
            errors.append(f"Division {class_id} has {len(rolls)} student(s), fewer than {num_batches} batches.")
            continue

        letter = class_letter(class_id, division_letter(position))
        batches = [
            LabBatch(
                batch_id=f"{letter}{i + 1}",
                batch_name=f"Batch {letter}{i + 1}",
                student_rolls=chunk,
            )
            for i, chunk in enumerate(balanced_chunks(rolls, num_batches))
        ]
        if len(rolls) > div_cap:
            warnings.append(f"Division {class_id} has {len(rolls)} students; theory capacity is {div_cap}.")
        biggest = max(len(b.student_rolls) for b in batches)
        if biggest > batch_cap:
            warnings.append(
                f"Division {class_id}: largest lab batch has {biggest} students; lab capacity is {batch_cap}."
            )

        name = str(raw.get("class_name") or "").strip() or class_id
        built.append(ClassCohort(
            class_id=class_id,
            class_name=name,
            semester=semester,
            track_tag=structure.track_tag,
            track=track,
            student_rolls=rolls,
            lab_batch_count=num_batches,
            batches=batches,
        ))

    batch_ids = [b.batch_id for c in built for b in c.batches]
    duplicated = sorted({b for b in batch_ids if batch_ids.count(b) > 1})
    if duplicated:
        errors.append(f"Batch ids would collide ({', '.join(duplicated)}); rename the divisions.")

    if errors:
        raise CohortConfigError(errors)
    return SemesterCohortConfig(semester=semester, classes=built), warnings


def roster_mismatch(store: Any, config: SemesterCohortConfig) -> List[str]:
    """Problems if the saved config no longer matches the live student roster."""
    roster = {s.roll_number for s in store.list_students(semester=config.semester)}
    placed = {r for c in config.classes for r in c.student_rolls}
    problems = []
    if roster - placed:
        problems.append(f"{len(roster - placed)} student(s) added since the setup was saved")
    if placed - roster:
        problems.append(f"{len(placed - roster)} saved student(s) no longer exist")
    return problems
