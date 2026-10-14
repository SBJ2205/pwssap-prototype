"""CP-SAT solver engine for department timetable generation (Phase 9).

Objective priority (product decisions #11, #12):
  1. PRIMARY   -- Maximise student time-slot satisfaction.
                  A student is "satisfied" at a slot to the degree their
                  rating is close to PREFERRED (1). BLOCKED (4) slots are
                  hard-forbidden: the student MUST NOT be in a section
                  whose meeting falls in a slot they blocked.
  2. SECONDARY -- Maximise faculty preference satisfaction (weighted
                  lower than time-slot satisfaction).
  3. TERTIARY  -- Balance teacher teaching loads: minimise the range
                  (max_sections_taught - min_sections_taught) across all
                  teachers.

Hard constraints:
  a. Teacher availability -- if admin blocked teacher T for slot S,
     T cannot be assigned to any section meeting in S (for either 1h interval).
  b. Slot-type rules -- theory never in slot 4, nothing in Mon-1.
  c. Teacher no-clash -- a teacher cannot be double-booked at the same time.
     For 1-hour remainders, checked for the actual 1-hour interval.
  d. Student no-clash -- an enrolled student cannot be scheduled in two
     meetings at the same time.
     For 1-hour remainders, checked for the actual 1-hour interval.
  e. Meeting non-repetition -- multiple meetings of the same section
     cannot be placed in the same physical slot.
  f. Section capacity -- total students assigned to a section <= capacity.
  g. Student BLOCKED slots -- student cannot be enrolled in a section
     meeting in a blocked slot.

3-hour subjects:
  Represented as one 2-hour meeting + one 1-hour remainder.
  The 1-hour remainder occupies part 1 (first hour) or part 2 (second hour)
  of a physical 2-hour slot. Two 1-hour remainders can share the same physical
  slot if one occupies part 1 and the other occupies part 2, provided they do
  not clash on teacher or students.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from domain.enums import PreferenceRating, SubjectType
from domain.models import Meeting, Section
from domain.timeslots import TimeSlot


_TIME_PREF_PENALTY: Dict[int, int] = {
    PreferenceRating.PREFERRED.value: 0,
    PreferenceRating.TOLERABLE.value: 1,
    PreferenceRating.DISLIKED.value:  3,
    PreferenceRating.BLOCKED.value:   9999,
}
_DEFAULT_TIME_PENALTY = 2

_FACULTY_PREF_PENALTY: Dict[int, int] = {
    PreferenceRating.PREFERRED.value: 0,
    PreferenceRating.TOLERABLE.value: 1,
    PreferenceRating.DISLIKED.value:  2,
}
_DEFAULT_FACULTY_PENALTY = 1

_TIME_WEIGHT = 5
_FACULTY_WEIGHT = 1
_LOAD_BALANCE_WEIGHT = 10


@dataclass
class SolverInput:
    sections: List[Section]
    candidate_slots: Dict[int, List[TimeSlot]]
    candidate_teachers: Dict[int, List[str]]
    time_preferences: Dict[str, Dict[str, int]]
    faculty_preferences: Dict[str, Dict[str, Dict[str, int]]]
    teacher_availability: Dict[str, Dict[str, bool]]
    subject_students: Dict[str, List[str]]
    teacher_subject_loads: Dict[Tuple[str, str], Optional[int]] = field(default_factory=dict)
    subject_semesters: Dict[str, int] = field(default_factory=dict)
    subject_tags: Dict[str, str] = field(default_factory=dict)
    subject_types: Dict[str, str] = field(default_factory=dict)
    subject_subtags: Dict[str, List[str]] = field(default_factory=dict)
    feasibility_only: bool = False
    time_limit_seconds: float = 30.0


@dataclass
class SolverResult:
    status: str  # "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "UNKNOWN"
    section_slot_assignments: Dict[int, List[str]] = field(default_factory=dict)
    section_meetings: Dict[int, List[Meeting]] = field(default_factory=dict)
    section_teacher_assignments: Dict[int, Optional[str]] = field(default_factory=dict)
    student_section_assignments: Dict[str, Dict[str, int]] = field(default_factory=dict)
    wall_time_seconds: float = 0.0
    num_conflicts: int = 0
    objective_value: int = 0
    warnings: List[str] = field(default_factory=list)


def solve(inp: SolverInput) -> SolverResult:
    sections = inp.sections
    section_by_id: Dict[int, Section] = {s.id: s for s in sections if s.id is not None}

    all_teacher_ids: List[str] = sorted({
        tid
        for tids in inp.candidate_teachers.values()
        for tid in tids
    })

    subject_sections: Dict[str, List[int]] = {}
    for section in sections:
        subject_sections.setdefault(section.subject_code, []).append(section.id)

    total_t0 = time.monotonic()

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 1: Automated Master Timetable Generation (Sections + Slots + Faculty)
    # ══════════════════════════════════════════════════════════════════════════

    m1 = cp_model.CpModel()

    # Decision variables for meeting slots:
    # 2h meetings: slot_vars_2h[sid][mi][ci]
    # 1h meetings: slot_vars_p1[sid][mi][ci] and slot_vars_p2[sid][mi][ci]
    slot_vars_2h: Dict[int, Dict[int, List[cp_model.IntVar]]] = {}
    slot_vars_p1: Dict[int, Dict[int, List[cp_model.IntVar]]] = {}
    slot_vars_p2: Dict[int, Dict[int, List[cp_model.IntVar]]] = {}
    slot_active_in: Dict[int, Dict[int, List[cp_model.IntVar]]] = {}
    period_active: Dict[Tuple[int, int, int, int], cp_model.IntVar] = {}

    for section in sections:
        sid = section.id
        cand_s = inp.candidate_slots.get(sid, [])
        slot_active_in[sid] = {}

        for mi, m in enumerate(section.meetings):
            slot_active_in[sid][mi] = []
            dur = getattr(m, "duration_hours", 2) or 2

            if dur == 1:
                p1_vars = [m1.new_bool_var(f"s{sid}_m{mi}_c{ci}_p1") for ci in range(len(cand_s))]
                p2_vars = [m1.new_bool_var(f"s{sid}_m{mi}_c{ci}_p2") for ci in range(len(cand_s))]
                slot_vars_p1.setdefault(sid, {})[mi] = p1_vars
                slot_vars_p2.setdefault(sid, {})[mi] = p2_vars

                m1.add_exactly_one(p1_vars + p2_vars)

                for ci in range(len(cand_s)):
                    period_active[(sid, mi, ci, 1)] = p1_vars[ci]
                    period_active[(sid, mi, ci, 2)] = p2_vars[ci]
                    s_act = m1.new_bool_var(f"s_act_s{sid}_m{mi}_c{ci}")
                    m1.add(s_act == p1_vars[ci] + p2_vars[ci])
                    slot_active_in[sid][mi].append(s_act)
            else:
                vars_2h = [m1.new_bool_var(f"s{sid}_m{mi}_c{ci}_2h") for ci in range(len(cand_s))]
                slot_vars_2h.setdefault(sid, {})[mi] = vars_2h
                m1.add_exactly_one(vars_2h)

                for ci in range(len(cand_s)):
                    period_active[(sid, mi, ci, 1)] = vars_2h[ci]
                    period_active[(sid, mi, ci, 2)] = vars_2h[ci]
                    slot_active_in[sid][mi].append(vars_2h[ci])

    # Teacher assignment variables
    teacher_vars: Dict[int, List[cp_model.IntVar]] = {}
    for section in sections:
        sid = section.id
        cand_t = inp.candidate_teachers.get(sid, [])
        if cand_t:
            tvars = [m1.new_bool_var(f"teacher_s{sid}_t{ti}") for ti in range(len(cand_t))]
            m1.add_exactly_one(tvars)
        else:
            tvars = []
        teacher_vars[sid] = tvars

    # 1.a Teacher availability
    for section in sections:
        sid = section.id
        cand_t = inp.candidate_teachers.get(sid, [])
        cand_s = inp.candidate_slots.get(sid, [])
        for ti, teacher_id in enumerate(cand_t):
            avail_map = inp.teacher_availability.get(teacher_id, {})
            if not teacher_vars[sid]:
                continue
            tv = teacher_vars[sid][ti]
            for mi in range(len(section.meetings)):
                for ci, slot in enumerate(cand_s):
                    if not avail_map.get(slot.key, True):
                        s_act = slot_active_in[sid][mi][ci]
                        m1.add(tv + s_act <= 1)

    # 1.b Teacher no-clash (checked per actual interval: slot_key, part)
    teacher_period_terms: Dict[str, Dict[Tuple[str, int], List[cp_model.IntVar]]] = {
        tid: {} for tid in all_teacher_ids
    }
    for section in sections:
        sid = section.id
        cand_t = inp.candidate_teachers.get(sid, [])
        cand_s = inp.candidate_slots.get(sid, [])
        for ti, teacher_id in enumerate(cand_t):
            if not teacher_vars[sid]:
                continue
            tv = teacher_vars[sid][ti]
            for mi in range(len(section.meetings)):
                for ci, slot in enumerate(cand_s):
                    for part in (1, 2):
                        act = period_active[(sid, mi, ci, part)]
                        t_act = m1.new_bool_var(f"t_act_s{sid}_m{mi}_c{ci}_p{part}_t{ti}")
                        m1.add_bool_and([tv, act]).only_enforce_if(t_act)
                        m1.add_bool_or([tv.Not(), act.Not()]).only_enforce_if(t_act.Not())
                        teacher_period_terms[teacher_id].setdefault((slot.key, part), []).append(t_act)

    for tid, period_dict in teacher_period_terms.items():
        for (sk, part), term_list in period_dict.items():
            if len(term_list) > 1:
                m1.add(sum(term_list) <= 1)

    # 1.c Meeting Non-repetition (same section cannot share same physical slot)
    for section in sections:
        sid = section.id
        n_meetings = len(section.meetings)
        if n_meetings > 1:
            cand_s = inp.candidate_slots.get(sid, [])
            for ci in range(len(cand_s)):
                same_slot_vars = [slot_active_in[sid][mi][ci] for mi in range(n_meetings)]
                m1.add(sum(same_slot_vars) <= 1)

    # 1.d Hard teacher-subject weekly load limits
    for teacher_id in all_teacher_ids:
        for subject_code in subject_sections:
            maximum = inp.teacher_subject_loads.get((teacher_id, subject_code))
            if maximum is None:
                continue
            terms = []
            for section in sections:
                if section.subject_code != subject_code:
                    continue
                subject_hours = sum(
                    getattr(meeting, "duration_hours", 2) or 2
                    for meeting in section.meetings
                )
                for ti, candidate_teacher in enumerate(inp.candidate_teachers.get(section.id, [])):
                    if candidate_teacher == teacher_id and teacher_vars[section.id]:
                        terms.append(subject_hours * teacher_vars[section.id][ti])
            if terms:
                m1.add(sum(terms) <= maximum)

    # 1.e Single-section student clash prevention in Stage 1:
    blocked_value = PreferenceRating.BLOCKED.value
    enrolled_set = {
        sc: set(students)
        for sc, students in inp.subject_students.items()
    }

    # Avoid placing a single section in a slot blocked by any of its students
    for subject_code, sids in subject_sections.items():
        if len(sids) == 1:
            sid = sids[0]
            sec = section_by_id.get(sid)
            if sec:
                cand_s = inp.candidate_slots.get(sid, [])
                for roll in enrolled_set.get(subject_code, set()):
                    st_prefs = inp.time_preferences.get(roll, {})
                    for ci, slot in enumerate(cand_s):
                        if st_prefs.get(slot.key) == blocked_value:
                            for mi in range(len(sec.meetings)):
                                m1.add(slot_active_in[sid][mi][ci] == 0)

    # For any two single-section subjects sharing enrolled students:
    all_single_sec_codes = [sc for sc, sids in subject_sections.items() if len(sids) == 1]
    for i in range(len(all_single_sec_codes)):
        for j in range(i + 1, len(all_single_sec_codes)):
            sc1 = all_single_sec_codes[i]
            sc2 = all_single_sec_codes[j]
            if enrolled_set.get(sc1, set()) & enrolled_set.get(sc2, set()):
                sid1 = subject_sections[sc1][0]
                sid2 = subject_sections[sc2][0]
                sec1 = section_by_id[sid1]
                sec2 = section_by_id[sid2]
                cand_s1 = {s.key: ci for ci, s in enumerate(inp.candidate_slots.get(sid1, []))}
                cand_s2 = {s.key: ci for ci, s in enumerate(inp.candidate_slots.get(sid2, []))}
                common_keys = set(cand_s1.keys()) & set(cand_s2.keys())
                for sk in common_keys:
                    ci1 = cand_s1[sk]
                    ci2 = cand_s2[sk]
                    for mi1 in range(len(sec1.meetings)):
                        for mi2 in range(len(sec2.meetings)):
                            for part in (1, 2):
                                act1 = period_active.get((sid1, mi1, ci1, part))
                                act2 = period_active.get((sid2, mi2, ci2, part))
                                if act1 is not None and act2 is not None:
                                    m1.add(act1 + act2 <= 1)

    # 1.f Division & Batch Cohort Non-Overlap Constraints
    slot_indices: Dict[int, Dict[str, int]] = {}
    for s in sections:
        cand_s = inp.candidate_slots.get(s.id, [])
        slot_indices[s.id] = {slot.key: ci for ci, slot in enumerate(cand_s)}

    all_slot_keys = sorted({slot.key for cand_s in inp.candidate_slots.values() for slot in cand_s})

    lab_batches: Dict[Tuple[int, int], List[Tuple[int, int]]] = defaultdict(list)
    core_theory_tracks: Dict[Tuple[int, int], List[Tuple[int, int]]] = defaultdict(list)
    elective_track_meets: Dict[Tuple[int, str, int], List[Tuple[int, int]]] = defaultdict(list)
    all_semesters = set(inp.subject_semesters.values()) if inp.subject_semesters else {0}

    for s in sections:
        sem = inp.subject_semesters.get(s.subject_code, 0)
        tag = inp.subject_tags.get(s.subject_code, "")
        stype = inp.subject_types.get(s.subject_code, "")
        subtags = inp.subject_subtags.get(s.subject_code, [])

        m_lab = re.search(r"-L(\d+)$", s.label)
        m_theo = re.search(r"-T(\d+)$", s.label)

        if m_lab:
            b_idx = int(m_lab.group(1))
            for mi in range(len(s.meetings)):
                lab_batches[(sem, b_idx)].append((s.id, mi))
                for stag in subtags:
                    elective_track_meets[(sem, stag, b_idx)].append((s.id, mi))
        elif m_theo:
            div_idx = int(m_theo.group(1))
            if not tag or tag in ("BSC", "PCC", "CORE") or (not subtags and stype == "theory"):
                for mi in range(len(s.meetings)):
                    core_theory_tracks[(sem, div_idx)].append((s.id, mi))
            for stag in subtags:
                for mi in range(len(s.meetings)):
                    elective_track_meets[(sem, stag, div_idx)].append((s.id, mi))

    # Constraint 1: Labs within the same batch b cannot overlap
    for (sem, b_idx), meets in lab_batches.items():
        for sk in all_slot_keys:
            for part in (1, 2):
                terms = [
                    period_active[(sid, mi, slot_indices[sid][sk], part)]
                    for sid, mi in meets
                    if sk in slot_indices[sid]
                ]
                if len(terms) > 1:
                    m1.add(sum(terms) <= 1)

    # Constraint 2: Core theories within the same division k cannot overlap
    for (sem, div_idx), meets in core_theory_tracks.items():
        for sk in all_slot_keys:
            for part in (1, 2):
                terms = [
                    period_active[(sid, mi, slot_indices[sid][sk], part)]
                    for sid, mi in meets
                    if sk in slot_indices[sid]
                ]
                if len(terms) > 1:
                    m1.add(sum(terms) <= 1)

    # Constraint 3: Lab batch b and its division k cannot overlap
    for sem in all_semesters:
        sem_divs = [div for (s_sem, div) in core_theory_tracks.keys() if s_sem == sem]
        sem_batches = [b for (s_sem, b) in lab_batches.keys() if s_sem == sem]
        if sem_divs and sem_batches:
            num_divs = max(sem_divs)
            num_batches = max(sem_batches)
            for b in sem_batches:
                div_k = min(num_divs, max(1, 1 + (b - 1) * num_divs // num_batches))
                t_meets = core_theory_tracks.get((sem, div_k), [])
                l_meets = lab_batches.get((sem, b), [])
                if t_meets and l_meets:
                    for sk in all_slot_keys:
                        for part in (1, 2):
                            t_terms = [
                                period_active[(sid, mi, slot_indices[sid][sk], part)]
                                for sid, mi in t_meets
                                if sk in slot_indices[sid]
                            ]
                            l_terms = [
                                period_active[(sid, mi, slot_indices[sid][sk], part)]
                                for sid, mi in l_meets
                                if sk in slot_indices[sid]
                            ]
                            if t_terms and l_terms:
                                m1.add(sum(t_terms) + sum(l_terms) <= 1)

    # Constraint 4: Electives sharing the same track (subtag) cannot clash within their division/batch
    elective_theory_by_subtag: Dict[Tuple[int, str, int], List[Tuple[int, int]]] = defaultdict(list)
    elective_lab_by_subtag: Dict[Tuple[int, str, int], List[Tuple[int, int]]] = defaultdict(list)

    for s in sections:
        sem = inp.subject_semesters.get(s.subject_code, 0)
        subtags = inp.subject_subtags.get(s.subject_code, [])
        if not subtags:
            continue
        m_lab = re.search(r"-L(\d+)$", s.label)
        m_theo = re.search(r"-T(\d+)$", s.label)
        for stag in subtags:
            if m_theo:
                div_idx = int(m_theo.group(1))
                for mi in range(len(s.meetings)):
                    elective_theory_by_subtag[(sem, stag, div_idx)].append((s.id, mi))
            elif m_lab:
                b_idx = int(m_lab.group(1))
                for mi in range(len(s.meetings)):
                    elective_lab_by_subtag[(sem, stag, b_idx)].append((s.id, mi))

    for (sem, stag, div_k), meets in elective_theory_by_subtag.items():
        if len(meets) > 1:
            for sk in all_slot_keys:
                for part in (1, 2):
                    terms = [
                        period_active[(sid, mi, slot_indices[sid][sk], part)]
                        for sid, mi in meets
                        if sk in slot_indices[sid]
                    ]
                    if len(terms) > 1:
                        m1.add(sum(terms) <= 1)

    for (sem, stag, b_idx), meets in elective_lab_by_subtag.items():
        if len(meets) > 1:
            for sk in all_slot_keys:
                for part in (1, 2):
                    terms = [
                        period_active[(sid, mi, slot_indices[sid][sk], part)]
                        for sid, mi in meets
                        if sk in slot_indices[sid]
                    ]
                    if len(terms) > 1:
                        m1.add(sum(terms) <= 1)

    # Constraint 4b: Core theory and elective theory in the same division k cannot overlap
    for (sem, stag, div_k), e_meets in elective_theory_by_subtag.items():
        c_meets = core_theory_tracks.get((sem, div_k), [])
        if c_meets and e_meets:
            for sk in all_slot_keys:
                for part in (1, 2):
                    c_terms = [period_active[(sid, mi, slot_indices[sid][sk], part)] for sid, mi in c_meets if sk in slot_indices[sid]]
                    e_terms = [period_active[(sid, mi, slot_indices[sid][sk], part)] for sid, mi in e_meets if sk in slot_indices[sid]]
                    if c_terms and e_terms:
                        m1.add(sum(c_terms) + sum(e_terms) <= 1)

    # Constraint 5: Cross-Division Shared Electives (e.g. MDM in Sem 4)
    # A subject is a cross-division shared elective if it is a pure theory elective with no corresponding lab
    # and has fewer sections than the semester's core theory divisions.
    # Because students across all divisions must choose one of these electives,
    # they cannot overlap with ANY core theory division or ANY common lab batch of that semester.
    for sem in all_semesters:
        sem_divs = [div for (s_sem, div) in core_theory_tracks.keys() if s_sem == sem]
        num_divs = max(sem_divs) if sem_divs else 0
        if num_divs == 0:
            continue

        sem_subject_codes = {s.subject_code for s in sections if inp.subject_semesters.get(s.subject_code) == sem}
        sub_sections: Dict[str, List[Section]] = defaultdict(list)
        for s in sections:
            if s.subject_code in sem_subject_codes:
                sub_sections[s.subject_code].append(s)

        # Find pure theory cross-division electives
        cross_div_meets: List[Tuple[int, int]] = []
        for code, secs in sub_sections.items():
            subtags = inp.subject_subtags.get(code, [])
            tag = inp.subject_tags.get(code, "")
            stype = inp.subject_types.get(code, "")
            if not subtags and tag.upper() in ("BSC", "PCC", "CORE", ""):
                continue
            # If there are labs associated with this tag or subtag, it is division/batch tracked
            has_associated_labs = any(
                inp.subject_types.get(other_code) == "lab"
                and (
                    inp.subject_tags.get(other_code) == tag
                    or any(st in subtags for st in inp.subject_subtags.get(other_code, []))
                )
                for other_code in sem_subject_codes
            )
            if not has_associated_labs and len(secs) < num_divs and stype == "theory":
                for s in secs:
                    for mi in range(len(s.meetings)):
                        cross_div_meets.append((s.id, mi))

        if cross_div_meets:
            sem_core_theories = [
                m for (s_sem, div_k), meets in core_theory_tracks.items()
                if s_sem == sem for m in meets
            ]
            sem_common_labs = [
                m for (s_sem, b_idx), meets in lab_batches.items()
                if s_sem == sem for m in meets
                if not inp.subject_subtags.get(section_by_id[m[0]].subject_code)
            ]
            for sk in all_slot_keys:
                for part in (1, 2):
                    cd_terms = [
                        period_active[(sid, mi, slot_indices[sid][sk], part)]
                        for sid, mi in cross_div_meets
                        if sk in slot_indices[sid]
                    ]
                    if cd_terms:
                        other_terms = [
                            period_active[(sid, mi, slot_indices[sid][sk], part)]
                            for sid, mi in (sem_core_theories + sem_common_labs)
                            if sk in slot_indices[sid]
                        ]
                        if other_terms:
                            cd_act = m1.new_bool_var(f"cd_act_{sem}_{sk}_{part}")
                            for cdt in cd_terms:
                                m1.add(cdt <= cd_act)
                            for ot in other_terms:
                                m1.add(ot + cd_act <= 1)




    # Stage 1 Objective: Faculty teaching load balance
    if len(all_teacher_ids) >= 2:
        teacher_load: Dict[str, List[cp_model.IntVar]] = {t: [] for t in all_teacher_ids}
        for section in sections:
            sid = section.id
            cand_t = inp.candidate_teachers.get(sid, [])
            for ti, teacher_id in enumerate(cand_t):
                if teacher_vars[sid]:
                    teacher_load[teacher_id].append(teacher_vars[sid][ti])

        load_vars: Dict[str, cp_model.IntVar] = {}
        for teacher_id, assignment_vars in teacher_load.items():
            if assignment_vars:
                lv = m1.new_int_var(0, len(sections), f"load_{teacher_id}")
                m1.add(lv == sum(assignment_vars))
                load_vars[teacher_id] = lv

        if len(load_vars) >= 2:
            max_load = m1.new_int_var(0, len(sections), "max_load")
            min_load = m1.new_int_var(0, len(sections), "min_load")
            load_list = list(load_vars.values())
            m1.add_max_equality(max_load, load_list)
            m1.add_min_equality(min_load, load_list)
            load_range = m1.new_int_var(0, len(sections), "load_range")
            m1.add(load_range == max_load - min_load)
            m1.minimize(load_range)

    # Solve Stage 1
    solver1 = cp_model.CpSolver()
    solver1.parameters.max_time_in_seconds = max(1.0, min(inp.time_limit_seconds * 0.5, 30.0))
    solver1.parameters.num_workers = 0

    t0_stage1 = time.monotonic()
    status1 = solver1.solve(m1)
    stage1_elapsed = time.monotonic() - t0_stage1

    status_map = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN: "UNKNOWN",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
    }
    status1_str = status_map.get(status1, "UNKNOWN")

    if status1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        elapsed = time.monotonic() - total_t0
        res = SolverResult(
            status=status1_str,
            wall_time_seconds=round(elapsed, 3),
            num_conflicts=int(solver1.num_conflicts),
        )
        if status1 == cp_model.UNKNOWN:
            res.warnings.append(
                f"Master timetable solver timed out after {stage1_elapsed:.1f}s before finding a valid schedule. "
                "Check teacher availability or load limits."
            )
        else:
            res.warnings.append(
                "Master timetable solver proved that no schedule satisfies teacher availability, no-clash, or load limits."
            )
        return res

    # Extract Stage 1 results (section meetings & teacher assignments)
    assigned_slot_keys: Dict[int, List[str]] = {}
    assigned_meetings: Dict[int, List[Meeting]] = {}
    assigned_teachers: Dict[int, Optional[str]] = {}

    for section in sections:
        sid = section.id
        cand_s = inp.candidate_slots.get(sid, [])
        sec_slots: List[str] = []
        sec_meets: List[Meeting] = []

        for mi, m in enumerate(section.meetings):
            dur = getattr(m, "duration_hours", 2) or 2
            picked_key = ""
            picked_part = None

            if dur == 1:
                p1_vars = slot_vars_p1[sid][mi]
                p2_vars = slot_vars_p2[sid][mi]
                for ci, slot in enumerate(cand_s):
                    if solver1.boolean_value(p1_vars[ci]):
                        picked_key = slot.key
                        picked_part = 1
                        break
                    elif solver1.boolean_value(p2_vars[ci]):
                        picked_key = slot.key
                        picked_part = 2
                        break
            else:
                vars_2h = slot_vars_2h[sid][mi]
                for ci, slot in enumerate(cand_s):
                    if solver1.boolean_value(vars_2h[ci]):
                        picked_key = slot.key
                        picked_part = None
                        break

            sec_slots.append(picked_key)
            sec_meets.append(
                Meeting(slot_key=picked_key, duration_hours=dur, slot_part=picked_part)
            )

        assigned_slot_keys[sid] = sec_slots
        assigned_meetings[sid] = sec_meets

        # Teacher extraction
        cand_t = inp.candidate_teachers.get(sid, [])
        picked_teacher = None
        for ti, teacher_id in enumerate(cand_t):
            if teacher_vars[sid] and solver1.boolean_value(teacher_vars[sid][ti]):
                picked_teacher = teacher_id
                break
        assigned_teachers[sid] = picked_teacher

    # If no students enrolled in the input, Stage 1 is the complete answer
    has_students = any(bool(studs) for studs in inp.subject_students.values())
    if not has_students:
        elapsed = time.monotonic() - total_t0
        return SolverResult(
            status=status1_str,
            section_slot_assignments=assigned_slot_keys,
            section_meetings=assigned_meetings,
            section_teacher_assignments=assigned_teachers,
            wall_time_seconds=round(elapsed, 3),
            num_conflicts=int(solver1.num_conflicts),
        )

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 2: Automated Student Section Allocation
    # ══════════════════════════════════════════════════════════════════════════

    m2 = cp_model.CpModel()

    # Precompute periods occupied by each section: sid -> Set[(slot_key, part)]
    section_periods: Dict[int, Set[Tuple[str, int]]] = {}
    for sid, mlist in assigned_meetings.items():
        pers = set()
        for m in mlist:
            if m.duration_hours == 1:
                pers.add((m.slot_key, m.slot_part or 1))
            else:
                pers.add((m.slot_key, 1))
                pers.add((m.slot_key, 2))
        section_periods[sid] = pers

    # Decision variables: enroll_vars[(roll, subject_code, sid)]
    enroll_vars: Dict[Tuple[str, str, int], cp_model.IntVar] = {}
    student_subject_vars: Dict[str, Dict[str, Dict[int, cp_model.IntVar]]] = {}
    student_active_sections: Dict[str, List[Tuple[str, int, cp_model.IntVar]]] = {}

    for subject_code, sids in subject_sections.items():
        for roll in inp.subject_students.get(subject_code, []):
            student_subject_vars.setdefault(roll, {}).setdefault(subject_code, {})
            sec_vars = []
            for sid in sids:
                v = m2.new_bool_var(f"enroll_r{roll}_sub{subject_code}_s{sid}")
                enroll_vars[(roll, subject_code, sid)] = v
                student_subject_vars[roll][subject_code][sid] = v
                sec_vars.append(v)
                student_active_sections.setdefault(roll, []).append((subject_code, sid, v))
            if sec_vars:
                m2.add_exactly_one(sec_vars)

    # 2.a Section capacities
    for section in sections:
        sid = section.id
        sub = section.subject_code
        enrolled = [
            enroll_vars[(roll, sub, sid)]
            for roll in inp.subject_students.get(sub, [])
            if (roll, sub, sid) in enroll_vars
        ]
        if enrolled:
            m2.add(sum(enrolled) <= section.capacity)

    # 2.b Student BLOCKED slots
    for roll, sub_prefs in inp.time_preferences.items():
        blocked_slots = {sk for sk, rating in sub_prefs.items() if rating == blocked_value}
        if not blocked_slots:
            continue
        for (r, sub, sid), v in enroll_vars.items():
            if r == roll:
                if any(sk in blocked_slots for sk, _ in section_periods.get(sid, set())):
                    m2.add(v == 0)

    # 2.c Student no-clash (linear period sum constraint)
    for roll, sec_tuples in student_active_sections.items():
        slot_terms: Dict[Tuple[str, int], List[cp_model.IntVar]] = {}
        for sc, sid, v in sec_tuples:
            for p in section_periods.get(sid, set()):
                slot_terms.setdefault(p, []).append(v)
        for p, vlist in slot_terms.items():
            if len(vlist) > 1:
                m2.add(sum(vlist) <= 1)

    # 2.d Stage 2 Objectives (Preferences & Section Size Balancing)
    obj_terms: List[cp_model.LinearExpr] = []
    if not inp.feasibility_only:
        # Time-slot satisfaction
        for (roll, sub, sid), v in enroll_vars.items():
            time_pref = inp.time_preferences.get(roll, {})
            for m in assigned_meetings.get(sid, []):
                rating = time_pref.get(m.slot_key)
                if rating is not None and rating != _DEFAULT_TIME_PENALTY:
                    penalty = _TIME_PREF_PENALTY.get(rating, _DEFAULT_TIME_PENALTY)
                    if penalty > 0:
                        obj_terms.append(cp_model.LinearExpr.term(v, _TIME_WEIGHT * penalty))

        # Faculty preference
        for (roll, sub, sid), v in enroll_vars.items():
            teacher_id = assigned_teachers.get(sid)
            if teacher_id:
                fac_pref = inp.faculty_preferences.get(roll, {})
                teacher_ratings = fac_pref.get(sub, {})
                rating = teacher_ratings.get(teacher_id)
                if rating is not None and rating != _DEFAULT_FACULTY_PENALTY:
                    penalty = _FACULTY_PREF_PENALTY.get(rating, _DEFAULT_FACULTY_PENALTY)
                    if penalty > 0:
                        obj_terms.append(cp_model.LinearExpr.term(v, _FACULTY_WEIGHT * penalty))

        # Parallel section size load balancing (linear absolute deviation)
        for sc, sids in subject_sections.items():
            tot = len(inp.subject_students.get(sc, []))
            if len(sids) >= 2 and tot > 0:
                ideal = tot // len(sids)
                for sid in sids:
                    enrolled = [
                        enroll_vars[(roll, sc, sid)]
                        for roll in inp.subject_students.get(sc, [])
                        if (roll, sc, sid) in enroll_vars
                    ]
                    sec_count = sum(enrolled)
                    dev = m2.new_int_var(0, tot, f"dev_{sid}")
                    m2.add(dev >= sec_count - ideal)
                    m2.add(dev >= ideal - sec_count)
                    obj_terms.append(cp_model.LinearExpr.term(dev, 2))

    # Solve Stage 2
    rem_time = max(1.0, inp.time_limit_seconds - stage1_elapsed)
    solver2 = cp_model.CpSolver()
    solver2.parameters.num_workers = 0

    if inp.feasibility_only or not obj_terms:
        solver2.parameters.max_time_in_seconds = rem_time
        solver2.parameters.stop_after_first_solution = True
        status2 = solver2.solve(m2)
    else:
        # Two-phase solve: first obtain a guaranteed valid assignment via feasibility pass (<5s)
        solver2_feas = cp_model.CpSolver()
        solver2_feas.parameters.max_time_in_seconds = min(10.0, max(2.0, rem_time * 0.4))
        solver2_feas.parameters.num_workers = 0
        solver2_feas.parameters.stop_after_first_solution = True
        status_feas = solver2_feas.solve(m2)

        if status_feas in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # Warm-start optimization using the valid feasible assignment
            for k, v in enroll_vars.items():
                m2.add_hint(v, 1 if solver2_feas.boolean_value(v) else 0)
            m2.minimize(sum(obj_terms))
            rem_time_opt = max(1.0, inp.time_limit_seconds - (time.monotonic() - total_t0))
            solver2.parameters.max_time_in_seconds = rem_time_opt
            status2 = solver2.solve(m2)
            if status2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                solver2 = solver2_feas
                status2 = status_feas
        else:
            solver2 = solver2_feas
            status2 = status_feas
    status2_str = status_map.get(status2, "UNKNOWN")
    elapsed = time.monotonic() - total_t0

    res = SolverResult(
        status=status2_str,
        section_slot_assignments=assigned_slot_keys,
        section_meetings=assigned_meetings,
        section_teacher_assignments=assigned_teachers,
        wall_time_seconds=round(elapsed, 3),
        num_conflicts=int(solver1.num_conflicts + solver2.num_conflicts),
    )

    if status2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if status2 == cp_model.UNKNOWN:
            res.warnings.append(
                f"Student allocation solver timed out after {rem_time:.1f}s before finding a valid assignment."
            )
        else:
            res.warnings.append(
                "Student allocation proved infeasible. Section capacities or student clash constraints could not be satisfied."
            )
        return res

    res.objective_value = int(solver2.objective_value) if not inp.feasibility_only else 0

    # Extract student-section assignments
    for (roll, sub, sid), v in enroll_vars.items():
        if solver2.boolean_value(v):
            res.student_section_assignments.setdefault(roll, {})[sub] = sid

    return res
