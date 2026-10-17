"""Traditional Division & Batch Section Generation.

Generates Section records and deterministic student-to-section enrollments
for traditional academic cohorts.

Key rules:
- Theory subjects for Division k get label "{code}-T{k}", enforcing non-overlap
  across core theory subjects within Division k (CP-SAT Constraint 2).
- Lab subjects for Batch b get label "{code}-L{b}", enforcing non-overlap
  for that lab batch and non-overlap with its parent division (CP-SAT Constraints 1 & 3).
- In-Class Electives (e.g. Sem 6 MDM with only 1 subject) are treated as in-class
  division subjects: label "{code}-T{k}", 0 dispersal across divisions.
- Dispersal Electives (e.g. Sem 4 MDM with >= 2 subjects) get synchronized sections
  across all divisions.
"""
import math
from typing import Dict, List, Optional, Set

from data.store import InMemoryStore
from domain.models import Meeting, Section, Subject
from domain.timeslots import is_slot_usable


def _build_meetings_template(weekly_hours: int, slot_structure: Optional[str] = None) -> List[Meeting]:
    """Create meeting templates with empty slot_key, to be scheduled by Stage 1 solver."""
    if weekly_hours <= 1:
        return [Meeting(slot_key="", duration_hours=1, slot_part=1)]
    elif weekly_hours == 2:
        return [Meeting(slot_key="", duration_hours=2, slot_part=None)]
    elif weekly_hours == 3:
        # Standard Mumbai University 3-hr theory: 2hr block + 1hr block
        return [
            Meeting(slot_key="", duration_hours=2, slot_part=None),
            Meeting(slot_key="", duration_hours=1, slot_part=1),
        ]
    elif weekly_hours == 4:
        # Two 2-hr blocks
        return [
            Meeting(slot_key="", duration_hours=2, slot_part=None),
            Meeting(slot_key="", duration_hours=2, slot_part=None),
        ]
    else:
        num_2s = weekly_hours // 2
        rem = weekly_hours % 2
        meets = [Meeting(slot_key="", duration_hours=2, slot_part=None) for _ in range(num_2s)]
        if rem:
            meets.append(Meeting(slot_key="", duration_hours=1, slot_part=1))
        return meets


def generate_traditional_sections_for_semester(
    store: InMemoryStore,
    semester: int,
    run_id: Optional[int] = None,
) -> dict:
    """Generate traditional sections and assign students deterministically."""
    cohort_config = store.get_semester_cohorts(semester)
    if not cohort_config or not cohort_config.classes:
        raise ValueError(f"No cohort configuration found for semester {semester}.")

    cluster_info = store.detect_pe_clusters(semester)
    all_sem_subjects = store.list_subjects(semester=semester)

    # Differentiate subject categories
    in_class_codes = {item["subject_code"] for item in cluster_info.get("in_class_electives", [])}
    dispersal_codes = {
        s["subject_code"]
        for group in cluster_info.get("dispersal_electives", [])
        for s in group.get("subjects", [])
    }
    pe_tag = cluster_info.get("pe_tag")

    core_theories: List[Subject] = []
    core_labs: List[Subject] = []
    in_class_theories: List[Subject] = []

    for s in all_sem_subjects:
        code = s.subject_code
        tag_up = (s.subject_tag or "").strip().upper()

        if code in in_class_codes:
            if s.type == "theory":
                in_class_theories.append(s)
            else:
                core_labs.append(s)
        elif code in dispersal_codes:
            pass  # Handled in dispersal block
        elif pe_tag and tag_up == pe_tag:
            pass  # Handled per class based on PE track
        else:
            if s.type == "theory":
                core_theories.append(s)
            else:
                core_labs.append(s)

    created_sections: List[Section] = []
    global_batch_counter = 1

    # Keep track of teacher workload to distribute evenly
    teacher_loads: Dict[str, int] = {}

    def pick_teacher(subject_code: str) -> Optional[str]:
        eligible = store.teachers_for_subject(subject_code)
        if not eligible:
            return None
        # Pick teacher with minimum assigned sections
        eligible.sort(key=lambda t: (teacher_loads.get(t, 0), t))
        chosen = eligible[0]
        teacher_loads[chosen] = teacher_loads.get(chosen, 0) + 1
        return chosen

    # 1. Division & Batch Sections
    for div_idx, cls in enumerate(cohort_config.classes, start=1):
        div_rolls = cls.student_rolls
        div_capacity = max(len(div_rolls), 1)

        # 1a. Core Theories & In-Class Electives (e.g. Sem 6 MDM)
        for subj in (core_theories + in_class_theories):
            label = f"{subj.subject_code}-T{div_idx}"
            sec = Section(
                id=None,
                subject_code=subj.subject_code,
                label=label,
                teacher_id=pick_teacher(subj.subject_code),
                capacity=div_capacity,
                meetings=_build_meetings_template(subj.weekly_hours, subj.slot_structure),
                run_id=run_id,
            )
            saved_sec = store.add_section(sec)
            created_sections.append(saved_sec)
            for r in div_rolls:
                store.student_section_assignments.setdefault(r, {})[subj.subject_code] = saved_sec.id

        # 1b. PE Theory for this division (if class has PE track)
        if cls.pe_subject_code:
            pe_subj = store.get_subject(cls.pe_subject_code)
            if pe_subj and pe_subj.type == "theory":
                label = f"{pe_subj.subject_code}-T{div_idx}"
                sec = Section(
                    id=None,
                    subject_code=pe_subj.subject_code,
                    label=label,
                    teacher_id=pick_teacher(pe_subj.subject_code),
                    capacity=div_capacity,
                    meetings=_build_meetings_template(pe_subj.weekly_hours, pe_subj.slot_structure),
                    run_id=run_id,
                )
                saved_sec = store.add_section(sec)
                created_sections.append(saved_sec)
                for r in div_rolls:
                    store.student_section_assignments.setdefault(r, {})[pe_subj.subject_code] = saved_sec.id

        # 1c. Core Labs for Batches
        for batch in cls.batches:
            b_idx = global_batch_counter
            global_batch_counter += 1
            batch_rolls = batch.student_rolls
            batch_capacity = max(len(batch_rolls), 1)

            for lab_subj in core_labs:
                label = f"{lab_subj.subject_code}-L{b_idx}"
                sec = Section(
                    id=None,
                    subject_code=lab_subj.subject_code,
                    label=label,
                    teacher_id=pick_teacher(lab_subj.subject_code),
                    capacity=batch_capacity,
                    meetings=_build_meetings_template(lab_subj.weekly_hours, lab_subj.slot_structure),
                    run_id=run_id,
                )
                saved_sec = store.add_section(sec)
                created_sections.append(saved_sec)
                for r in batch_rolls:
                    store.student_section_assignments.setdefault(r, {})[lab_subj.subject_code] = saved_sec.id

    # 2. Dispersal Electives (e.g. Sem 4 MDM with multiple subjects)
    for group in cluster_info.get("dispersal_electives", []):
        tag = group.get("tag")
        for subj_info in group.get("subjects", []):
            code = subj_info["subject_code"]
            subj = store.get_subject(code)
            if not subj:
                continue

            # Find all students who locked into this elective
            enrolled_rolls = []
            for r, choices in store.student_choice_selections.items():
                st = store.get_student(r)
                if not st or st.semester != semester:
                    continue
                for c in choices:
                    if c.tag.strip().upper() == tag.strip().upper():
                        if subj.supports_subtag(c.subtag) or c.subtag == code:
                            enrolled_rolls.append(r)
                            break

            if not enrolled_rolls:
                continue

            label = f"{subj.subject_code}-E1"
            sec = Section(
                id=None,
                subject_code=subj.subject_code,
                label=label,
                teacher_id=pick_teacher(subj.subject_code),
                capacity=len(enrolled_rolls),
                meetings=_build_meetings_template(subj.weekly_hours, subj.slot_structure),
                run_id=run_id,
            )
            saved_sec = store.add_section(sec)
            created_sections.append(saved_sec)
            for r in enrolled_rolls:
                store.student_section_assignments.setdefault(r, {})[subj.subject_code] = saved_sec.id

    assigned_count = sum(
        1 for r, subjs in store.student_section_assignments.items()
        if store.get_student(r) and store.get_student(r).semester == semester
    )

    return {
        "status": "ok",
        "semester": semester,
        "sections_created": len(created_sections),
        "students_assigned": assigned_count,
        "classes_count": len(cohort_config.classes),
    }
