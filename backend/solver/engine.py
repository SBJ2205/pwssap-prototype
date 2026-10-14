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

import time
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
    model = cp_model.CpModel()
    sections = inp.sections
    section_by_id: Dict[int, Section] = {s.id: s for s in sections if s.id is not None}

    all_teacher_ids: List[str] = sorted({
        tid
        for tids in inp.candidate_teachers.values()
        for tid in tids
    })

    # ── Decision variables ────────────────────────────────────────────────

    # slot_vars:
    # For 2-hour meetings: slot_vars[sid][mi][ci] = 1 if placed in candidate slot ci (full 2h)
    # For 1-hour meetings:
    #   slot_vars_p1[sid][mi][ci] = 1 if placed in candidate slot ci, Part 1 (first hour)
    #   slot_vars_p2[sid][mi][ci] = 1 if placed in candidate slot ci, Part 2 (second hour)
    slot_vars_2h: Dict[int, Dict[int, List[cp_model.IntVar]]] = {}
    slot_vars_p1: Dict[int, Dict[int, List[cp_model.IntVar]]] = {}
    slot_vars_p2: Dict[int, Dict[int, List[cp_model.IntVar]]] = {}

    # slot_active_in[sid][mi][ci] = bool var representing meeting mi is in physical slot ci
    slot_active_in: Dict[int, Dict[int, List[cp_model.IntVar]]] = {}

    # period_active: (sid, mi, ci, part) -> bool var where part in (1, 2)
    period_active: Dict[Tuple[int, int, int, int], cp_model.IntVar] = {}

    for section in sections:
        sid = section.id
        cand_s = inp.candidate_slots.get(sid, [])
        slot_active_in[sid] = {}

        for mi, m in enumerate(section.meetings):
            slot_active_in[sid][mi] = []
            dur = getattr(m, "duration_hours", 2) or 2

            if dur == 1:
                # 1-hour remainder: choice between Part 1 or Part 2 across candidate slots
                slot_vars_p1.setdefault(sid, {})[mi] = [
                    model.new_bool_var(f"s{sid}_m{mi}_c{ci}_p1")
                    for ci in range(len(cand_s))
                ]
                slot_vars_p2.setdefault(sid, {})[mi] = [
                    model.new_bool_var(f"s{sid}_m{mi}_c{ci}_p2")
                    for ci in range(len(cand_s))
                ]
                p1_vars = slot_vars_p1[sid][mi]
                p2_vars = slot_vars_p2[sid][mi]

                # Exactly one (slot, part) selection
                model.add_exactly_one(p1_vars + p2_vars)

                for ci in range(len(cand_s)):
                    period_active[(sid, mi, ci, 1)] = p1_vars[ci]
                    period_active[(sid, mi, ci, 2)] = p2_vars[ci]

                    # slot_active is p1 OR p2
                    s_act = model.new_bool_var(f"s_act_s{sid}_m{mi}_c{ci}")
                    model.add(s_act == p1_vars[ci] + p2_vars[ci])
                    slot_active_in[sid][mi].append(s_act)
            else:
                # 2-hour meeting: placed in candidate slot ci, spans both Part 1 and Part 2
                vars_2h = [
                    model.new_bool_var(f"s{sid}_m{mi}_c{ci}_2h")
                    for ci in range(len(cand_s))
                ]
                slot_vars_2h.setdefault(sid, {})[mi] = vars_2h
                model.add_exactly_one(vars_2h)

                for ci in range(len(cand_s)):
                    period_active[(sid, mi, ci, 1)] = vars_2h[ci]
                    period_active[(sid, mi, ci, 2)] = vars_2h[ci]
                    slot_active_in[sid][mi].append(vars_2h[ci])

    # teacher_vars[sid][ti] = 1 if teacher ti assigned to section sid
    teacher_vars: Dict[int, List[cp_model.IntVar]] = {}
    for section in sections:
        sid = section.id
        cand_t = inp.candidate_teachers.get(sid, [])
        if cand_t:
            tvars = [
                model.new_bool_var(f"teacher_s{sid}_t{ti}")
                for ti in range(len(cand_t))
            ]
            model.add_exactly_one(tvars)
        else:
            tvars = []
        teacher_vars[sid] = tvars

    # student_vars[roll][subject_code][sid] = 1 if student enrolled in section sid
    student_vars: Dict[str, Dict[str, Dict[int, cp_model.IntVar]]] = {}
    subject_sections: Dict[str, List[int]] = {}
    for section in sections:
        subject_sections.setdefault(section.subject_code, []).append(section.id)

    for subject_code, sids in subject_sections.items():
        for roll in inp.subject_students.get(subject_code, []):
            student_vars.setdefault(roll, {}).setdefault(subject_code, {})
            sec_avars = [
                model.new_bool_var(f"enroll_r{roll}_sub{subject_code}_s{sid}")
                for sid in sids
            ]
            model.add_exactly_one(sec_avars)
            for sid, avar in zip(sids, sec_avars):
                student_vars[roll][subject_code][sid] = avar

    # ── Hard Constraints ──────────────────────────────────────────────────

    # (a) Teacher availability
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
                        # Teacher T and slot ci cannot both be selected
                        s_act = slot_active_in[sid][mi][ci]
                        model.add(tv + s_act <= 1)

    # (b) Teacher no-clash (checked per actual interval: slot_key, part)
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
                        t_act = model.new_bool_var(f"t_act_s{sid}_m{mi}_c{ci}_p{part}_t{ti}")
                        model.add_bool_and([tv, act]).only_enforce_if(t_act)
                        model.add_bool_or([tv.Not(), act.Not()]).only_enforce_if(t_act.Not())
                        teacher_period_terms[teacher_id].setdefault((slot.key, part), []).append(t_act)

    for tid, period_dict in teacher_period_terms.items():
        for (sk, part), term_list in period_dict.items():
            if len(term_list) > 1:
                model.add(sum(term_list) <= 1)

    # (c) Student no-clash (checked per actual interval: slot_key, part)
    student_period_terms: Dict[str, Dict[Tuple[str, int], List[cp_model.IntVar]]] = {}
    for roll, sub_map in student_vars.items():
        for subject_code, sid_map in sub_map.items():
            for sid, avar in sid_map.items():
                section = section_by_id.get(sid)
                if section is None:
                    continue
                cand_s = inp.candidate_slots.get(sid, [])
                for mi in range(len(section.meetings)):
                    for ci, slot in enumerate(cand_s):
                        for part in (1, 2):
                            act = period_active[(sid, mi, ci, part)]
                            s_act = model.new_bool_var(f"s_act_r{roll}_s{sid}_m{mi}_c{ci}_p{part}")
                            model.add_bool_and([avar, act]).only_enforce_if(s_act)
                            model.add_bool_or([avar.Not(), act.Not()]).only_enforce_if(s_act.Not())
                            student_period_terms.setdefault(roll, {}).setdefault((slot.key, part), []).append(s_act)

    for roll, period_dict in student_period_terms.items():
        for (sk, part), term_list in period_dict.items():
            if len(term_list) > 1:
                model.add(sum(term_list) <= 1)

    # (d) Non-repetition: multiple meetings of the same section cannot share the same physical slot
    for section in sections:
        sid = section.id
        n_meetings = len(section.meetings)
        if n_meetings > 1:
            cand_s = inp.candidate_slots.get(sid, [])
            for ci in range(len(cand_s)):
                same_slot_vars = [slot_active_in[sid][mi][ci] for mi in range(n_meetings)]
                model.add(sum(same_slot_vars) <= 1)

    # (e) Section capacity
    for section in sections:
        sid = section.id
        sub = section.subject_code
        enrolled_rvars = []
        for roll in inp.subject_students.get(sub, []):
            avar = student_vars.get(roll, {}).get(sub, {}).get(sid)
            if avar is not None:
                enrolled_rvars.append(avar)
        if enrolled_rvars:
            model.add(sum(enrolled_rvars) <= section.capacity)

    # (f) Hard teacher-subject weekly load limits from the teacher CSV.
    # A missing limit is legacy/unlimited; imported subject-load pairs are
    # enforced against the real weekly hours of each assigned section.
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
                model.add(sum(terms) <= maximum)

    # (f) Student BLOCKED slots
    blocked_value = PreferenceRating.BLOCKED.value
    for roll, sub_prefs in inp.time_preferences.items():
        blocked_slots: Set[str] = {
            sk for sk, rating in sub_prefs.items() if rating == blocked_value
        }
        if not blocked_slots:
            continue
        for subject_code, sids in subject_sections.items():
            for sid in sids:
                section = section_by_id.get(sid)
                if section is None:
                    continue
                cand_s = inp.candidate_slots.get(sid, [])
                avar = student_vars.get(roll, {}).get(subject_code, {}).get(sid)
                if avar is None:
                    continue
                for mi in range(len(section.meetings)):
                    for ci, slot in enumerate(cand_s):
                        if slot.key in blocked_slots:
                            s_act = slot_active_in[sid][mi][ci]
                            model.add_bool_or([avar.Not(), s_act.Not()])

    # ── Objective ─────────────────────────────────────────────────────────

    objective_terms: List[cp_model.LinearExpr] = []

    # 1. Time-slot satisfaction penalty (primary, weight=TIME_WEIGHT)
    for roll, sub_map in student_vars.items():
        time_pref = inp.time_preferences.get(roll, {})
        for subject_code, sid_map in sub_map.items():
            for sid, avar in sid_map.items():
                section = section_by_id.get(sid)
                if section is None:
                    continue
                cand_s = inp.candidate_slots.get(sid, [])
                for mi in range(len(section.meetings)):
                    for ci, slot in enumerate(cand_s):
                        rating = time_pref.get(slot.key)
                        penalty = (
                            _TIME_PREF_PENALTY.get(rating, _DEFAULT_TIME_PENALTY)
                            if rating is not None
                            else _DEFAULT_TIME_PENALTY
                        )
                        s_act = slot_active_in[sid][mi][ci]
                        combined = model.new_bool_var(f"obj_time_r{roll}_s{sid}_m{mi}_c{ci}")
                        model.add_bool_and([avar, s_act]).only_enforce_if(combined)
                        model.add_bool_or([avar.Not(), s_act.Not()]).only_enforce_if(combined.Not())
                        if penalty > 0:
                            objective_terms.append(
                                cp_model.LinearExpr.term(combined, _TIME_WEIGHT * penalty)
                            )

    # 2. Faculty preference penalty (secondary, weight=FACULTY_WEIGHT)
    for roll, sub_map in student_vars.items():
        fac_pref = inp.faculty_preferences.get(roll, {})
        for subject_code, sid_map in sub_map.items():
            teacher_ratings = fac_pref.get(subject_code, {})
            if not teacher_ratings:
                continue
            for sid, avar in sid_map.items():
                cand_t = inp.candidate_teachers.get(sid, [])
                for ti, teacher_id in enumerate(cand_t):
                    if not teacher_vars[sid]:
                        continue
                    tv = teacher_vars[sid][ti]
                    rating = teacher_ratings.get(teacher_id)
                    penalty = (
                        _FACULTY_PREF_PENALTY.get(rating, _DEFAULT_FACULTY_PENALTY)
                        if rating is not None
                        else _DEFAULT_FACULTY_PENALTY
                    )
                    combined = model.new_bool_var(f"obj_fac_r{roll}_s{sid}_t{ti}")
                    model.add_bool_and([avar, tv]).only_enforce_if(combined)
                    model.add_bool_or([avar.Not(), tv.Not()]).only_enforce_if(combined.Not())
                    if penalty > 0:
                        objective_terms.append(
                            cp_model.LinearExpr.term(combined, _FACULTY_WEIGHT * penalty)
                        )

    # 3. Teacher load balance (tertiary, weight=LOAD_BALANCE_WEIGHT)
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
                lv = model.new_int_var(0, len(sections), f"load_{teacher_id}")
                model.add(lv == sum(assignment_vars))
                load_vars[teacher_id] = lv

        if len(load_vars) >= 2:
            max_load = model.new_int_var(0, len(sections), "max_load")
            min_load = model.new_int_var(0, len(sections), "min_load")
            load_list = list(load_vars.values())
            model.add_max_equality(max_load, load_list)
            model.add_min_equality(min_load, load_list)
            load_range = model.new_int_var(0, len(sections), "load_range")
            model.add(load_range == max_load - min_load)
            objective_terms.append(
                cp_model.LinearExpr.term(load_range, _LOAD_BALANCE_WEIGHT)
            )

    if objective_terms:
        model.minimize(sum(objective_terms))

    # ── Solve ─────────────────────────────────────────────────────────────

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = inp.time_limit_seconds
    solver.parameters.num_workers = 4

    t0 = time.monotonic()
    status_code = solver.solve(model)
    elapsed = time.monotonic() - t0

    status_map = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN: "UNKNOWN",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
    }
    status_str = status_map.get(status_code, "UNKNOWN")

    result = SolverResult(
        status=status_str,
        wall_time_seconds=round(elapsed, 3),
        num_conflicts=int(solver.num_conflicts),
    )

    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        result.warnings.append(
            f"Solver returned status={status_str}. No assignments produced."
        )
        return result

    result.objective_value = int(solver.objective_value)

    # ── Extract slot and meeting assignments ───────────────────────────────
    for section in sections:
        sid = section.id
        cand_s = inp.candidate_slots.get(sid, [])
        assigned_slots: List[str] = []
        assigned_meetings: List[Meeting] = []

        for mi, m in enumerate(section.meetings):
            dur = getattr(m, "duration_hours", 2) or 2
            picked_key = ""
            picked_part = None

            if dur == 1:
                p1_vars = slot_vars_p1[sid][mi]
                p2_vars = slot_vars_p2[sid][mi]
                for ci, slot in enumerate(cand_s):
                    if solver.boolean_value(p1_vars[ci]):
                        picked_key = slot.key
                        picked_part = 1
                        break
                    elif solver.boolean_value(p2_vars[ci]):
                        picked_key = slot.key
                        picked_part = 2
                        break
            else:
                vars_2h = slot_vars_2h[sid][mi]
                for ci, slot in enumerate(cand_s):
                    if solver.boolean_value(vars_2h[ci]):
                        picked_key = slot.key
                        picked_part = None
                        break

            assigned_slots.append(picked_key)
            assigned_meetings.append(
                Meeting(slot_key=picked_key, duration_hours=dur, slot_part=picked_part)
            )

        result.section_slot_assignments[sid] = assigned_slots
        result.section_meetings[sid] = assigned_meetings

    # ── Extract teacher assignments ────────────────────────────────────────
    for section in sections:
        sid = section.id
        cand_t = inp.candidate_teachers.get(sid, [])
        assigned_teacher = None
        for ti, teacher_id in enumerate(cand_t):
            if teacher_vars[sid] and solver.boolean_value(teacher_vars[sid][ti]):
                assigned_teacher = teacher_id
                break
        result.section_teacher_assignments[sid] = assigned_teacher

    # ── Extract student-section assignments ───────────────────────────────
    for roll, sub_map in student_vars.items():
        result.student_section_assignments.setdefault(roll, {})
        for subject_code, sid_map in sub_map.items():
            for sid, avar in sid_map.items():
                if solver.boolean_value(avar):
                    result.student_section_assignments[roll][subject_code] = sid
                    break

    return result
