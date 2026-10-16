"""Post-processing heuristic pass to reduce idle schedule gaps for students (Stage 3).

Transfers or swaps students between parallel sections of the same course to
compress their daily schedules into contiguous blocks, subject to:
  1. Strict zero student clashes.
  2. Section capacity limits.
  3. No degradation of student time or faculty preferences.
  4. CRITICAL: Never moves a student into a slot they specifically marked as
     BLOCKED (4) or DISLIKED (3).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Set, Tuple

from domain.enums import PreferenceRating
from domain.models import Meeting, Section
from domain.timeslots import TimeSlot


_TIME_PENALTIES: Dict[int, int] = {
    PreferenceRating.PREFERRED.value: 0,
    PreferenceRating.TOLERABLE.value: 1,
    PreferenceRating.DISLIKED.value:  3,
    PreferenceRating.BLOCKED.value:   9999,
}
_DEFAULT_TIME_PENALTY = 2

_FACULTY_PENALTIES: Dict[int, int] = {
    PreferenceRating.PREFERRED.value: 0,
    PreferenceRating.TOLERABLE.value: 1,
    PreferenceRating.DISLIKED.value:  2,
}
_DEFAULT_FACULTY_PENALTY = 1


def compute_student_gaps(sids: Iterable[int], assigned_meetings: Dict[int, List[Meeting]]) -> int:
    """Calculate the total idle slot gaps in a student's weekly schedule.

    For each day, the span of classes is from min_slot to max_slot.
    Gaps = (max_slot - min_slot + 1) - count_of_occupied_slots.
    """
    occupied_by_day: Dict[str, Set[int]] = defaultdict(set)
    for sid in sids:
        for m in assigned_meetings.get(sid, []):
            if m.slot_key and "-" in m.slot_key:
                day, slot_num_str = m.slot_key.split("-")
                try:
                    slot_num = int(slot_num_str)
                    occupied_by_day[day].add(slot_num)
                except ValueError:
                    pass

    total_gaps = 0
    for day, slots in occupied_by_day.items():
        if len(slots) >= 2:
            min_s = min(slots)
            max_s = max(slots)
            total_gaps += (max_s - min_s + 1) - len(slots)
    return total_gaps


def reduce_schedule_gaps(
    inp,
    assigned_meetings: Dict[int, List[Meeting]],
    assigned_teachers: Dict[int, Optional[str]],
    student_assignments: Dict[str, Dict[str, int]],
    max_passes: int = 5,
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, int]]:
    """Iteratively swap and move students between parallel sections to minimize schedule gaps.

    Returns:
      (new_student_assignments, stats_dict)
    """
    # Precompute periods occupied by each section: sid -> Set[(slot_key, part)]
    section_periods: Dict[int, Set[Tuple[str, int]]] = {}
    for sid, mlist in assigned_meetings.items():
        pers: Set[Tuple[str, int]] = set()
        for m in mlist:
            if not m.slot_key:
                continue
            if getattr(m, "duration_hours", 2) == 1:
                pers.add((m.slot_key, getattr(m, "slot_part", 1) or 1))
            else:
                pers.add((m.slot_key, 1))
                pers.add((m.slot_key, 2))
        section_periods[sid] = pers

    # Map section ID -> capacity
    section_capacities: Dict[int, int] = {
        s.id: s.capacity for s in inp.sections if s.id is not None
    }

    # Parallel sections per subject
    subject_sections: Dict[str, List[int]] = {}
    for s in inp.sections:
        if s.id is not None:
            subject_sections.setdefault(s.subject_code, []).append(s.id)

    # Deep copy assignments to work with: roll -> {subject_code: sid}
    curr_assignments: Dict[str, Dict[str, int]] = {
        roll: dict(sub_map) for roll, sub_map in student_assignments.items()
    }

    # Current counts per section
    section_counts: Dict[int, int] = defaultdict(int)
    for sub_map in curr_assignments.values():
        for sid in sub_map.values():
            section_counts[sid] += 1

    # Measure initial gaps
    initial_total_gaps = sum(
        compute_student_gaps(sub_map.values(), assigned_meetings)
        for sub_map in curr_assignments.values()
    )

    improved_students: Set[str] = set()
    total_swaps = 0

    def calc_time_penalty(roll: str, sid: int) -> int:
        time_pref = inp.time_preferences.get(roll, {})
        pen = 0
        for m in assigned_meetings.get(sid, []):
            r = time_pref.get(m.slot_key)
            if r is not None:
                pen += _TIME_PENALTIES.get(r, _DEFAULT_TIME_PENALTY)
            else:
                pen += _DEFAULT_TIME_PENALTY
        return pen

    def calc_fac_penalty(roll: str, subject_code: str, sid: int) -> int:
        teacher = assigned_teachers.get(sid)
        if not teacher:
            return 0
        fac_pref = inp.faculty_preferences.get(roll, {}).get(subject_code, {})
        r = fac_pref.get(teacher)
        if r is not None:
            return _FACULTY_PENALTIES.get(r, _DEFAULT_FACULTY_PENALTY)
        return _DEFAULT_FACULTY_PENALTY

    def satisfies_preference_constraints(roll: str, subject_code: str, cand_sid: int, orig_sid: int) -> bool:
        """Ensure candidate section never places student into a BLOCKED or DISLIKED slot

        and does not increase time or faculty preference penalties.
        """
        time_pref = inp.time_preferences.get(roll, {})

        # 1. Reject if any meeting in candidate section is in a BLOCKED or DISLIKED slot
        for m in assigned_meetings.get(cand_sid, []):
            rating = time_pref.get(m.slot_key)
            if rating in (PreferenceRating.BLOCKED.value, PreferenceRating.DISLIKED.value):
                return False

        # 2. Penalty must not increase
        orig_time_pen = calc_time_penalty(roll, orig_sid)
        cand_time_pen = calc_time_penalty(roll, cand_sid)
        if cand_time_pen > orig_time_pen:
            return False

        orig_fac_pen = calc_fac_penalty(roll, subject_code, orig_sid)
        cand_fac_pen = calc_fac_penalty(roll, subject_code, cand_sid)
        if cand_fac_pen > orig_fac_pen:
            return False

        return True

    def has_no_clashes(roll: str, cand_sid: int, orig_sid: int) -> bool:
        """Check that cand_sid doesn't clash with any of roll's OTHER enrolled sections."""
        other_periods: Set[Tuple[str, int]] = set()
        for sc, sid in curr_assignments[roll].items():
            if sid != orig_sid:
                other_periods.update(section_periods.get(sid, set()))
        return other_periods.isdisjoint(section_periods.get(cand_sid, set()))

    # Iterative improvement passes
    for _pass in range(max_passes):
        improved_in_this_pass = False

        # Loop over subjects with parallel sections
        for subject_code, sids in subject_sections.items():
            if len(sids) < 2:
                continue

            # Find all students enrolled in this subject who currently have schedule gaps
            gapped_students = [
                roll for roll in curr_assignments
                if subject_code in curr_assignments[roll]
                and compute_student_gaps(curr_assignments[roll].values(), assigned_meetings) > 0
            ]

            for roll in gapped_students:
                curr_sid = curr_assignments[roll][subject_code]
                curr_student_gaps = compute_student_gaps(curr_assignments[roll].values(), assigned_meetings)
                if curr_student_gaps == 0:
                    continue

                best_swap: Optional[Tuple[str, int, int]] = None  # (other_roll, cand_sid, gap_reduction)
                best_direct: Optional[Tuple[int, int]] = None     # (cand_sid, gap_reduction)

                # Try candidate alternative sections
                for cand_sid in sids:
                    if cand_sid == curr_sid:
                        continue

                    # Check validity for this student
                    if not has_no_clashes(roll, cand_sid, curr_sid):
                        continue
                    if not satisfies_preference_constraints(roll, subject_code, cand_sid, curr_sid):
                        continue

                    # Potential new gaps for student
                    new_sids = [sid if sid != curr_sid else cand_sid for sid in curr_assignments[roll].values()]
                    new_student_gaps = compute_student_gaps(new_sids, assigned_meetings)
                    if new_student_gaps >= curr_student_gaps:
                        continue
                    reduction = curr_student_gaps - new_student_gaps

                    # Option A: Pairwise swap with a student currently in cand_sid
                    candidates_in_cand = [
                        r for r in curr_assignments
                        if curr_assignments[r].get(subject_code) == cand_sid
                    ]
                    for other_roll in candidates_in_cand:
                        if not has_no_clashes(other_roll, curr_sid, cand_sid):
                            continue
                        if not satisfies_preference_constraints(other_roll, subject_code, curr_sid, cand_sid):
                            continue

                        other_curr_gaps = compute_student_gaps(curr_assignments[other_roll].values(), assigned_meetings)
                        other_new_sids = [sid if sid != cand_sid else curr_sid for sid in curr_assignments[other_roll].values()]
                        other_new_gaps = compute_student_gaps(other_new_sids, assigned_meetings)

                        # Must not increase other student's gaps
                        if other_new_gaps > other_curr_gaps:
                            continue

                        combined_reduction = (curr_student_gaps - new_student_gaps) + (other_curr_gaps - other_new_gaps)
                        if combined_reduction > (best_swap[2] if best_swap else 0):
                            best_swap = (other_roll, cand_sid, combined_reduction)

                    # Option B: Direct move if capacity allows
                    cap = section_capacities.get(cand_sid, 999)
                    if section_counts[cand_sid] < cap:
                        if reduction > (best_direct[1] if best_direct else 0):
                            best_direct = (cand_sid, reduction)

                # Apply best move found
                if best_swap:
                    other_roll, cand_sid, _ = best_swap
                    curr_assignments[roll][subject_code] = cand_sid
                    curr_assignments[other_roll][subject_code] = curr_sid
                    improved_students.add(roll)
                    improved_students.add(other_roll)
                    total_swaps += 1
                    improved_in_this_pass = True
                    break
                elif best_direct:
                    cand_sid, _ = best_direct
                    curr_assignments[roll][subject_code] = cand_sid
                    section_counts[curr_sid] -= 1
                    section_counts[cand_sid] += 1
                    improved_students.add(roll)
                    total_swaps += 1
                    improved_in_this_pass = True
                    break

        if not improved_in_this_pass:
            break

    final_total_gaps = sum(
        compute_student_gaps(sub_map.values(), assigned_meetings)
        for sub_map in curr_assignments.values()
    )

    stats = {
        "initial_gaps": initial_total_gaps,
        "final_gaps": final_total_gaps,
        "gaps_reduced": max(0, initial_total_gaps - final_total_gaps),
        "swaps_count": total_swaps,
        "improved_students": len(improved_students),
    }

    return curr_assignments, stats
