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
                  teachers. This is a real optimisation term, not a
                  cosmetic post-processing step.

Hard constraints (always take precedence):
  a. Teacher availability -- if admin blocked teacher T for slot S,
     T cannot be assigned to any section that meets in S.
  b. Slot-type rules -- theory never in slot 4, nothing in Mon-1
     (already enforced structurally by the canonical grid's allowed_types,
     so the solver only chooses from valid slots for each section type).
  c. No double-booking -- a teacher cannot be assigned to two sections
     that share any meeting slot.
  d. Student BLOCKED slots -- a student who rated slot S as BLOCKED (4)
     cannot be enrolled in a section whose meeting lands on S.

What this engine receives (SolverInput) and produces (SolverResult)
----------------------------------------------------------------------
Input:
  - sections         -- the Phase 8 scaffolding Section list (with or
                        without pre-assigned teacher / slot keys).
  - candidate_slots  -- per-section, the list of valid slots (type-legal,
                        not filtered by teacher yet -- the engine handles
                        that via hard constraints).
  - candidate_teachers -- per-section, the list of capable teacher_ids.
  - student_enrollments -- which students are enrolled in which sections
                           (section_id -> [roll_number]).  Phase 9 decides
                           *which* section each student goes to; input
                           enrollment is optional.  If provided, it is
                           taken as fixed; if absent (the common Phase 9
                           case) the engine assigns students to sections
                           subject to capacity constraints.
  - time_preferences -- roll_number -> {slot_key: rating}.
  - faculty_preferences -- roll_number -> {subject_code: {teacher_id: rating}}.
  - teacher_availability -- teacher_id -> {slot_key: available_bool}.
  - section_capacities -- section_id -> max_students (from Section.capacity).

Output:
  - section_slot_assignments  -- section_id -> [slot_key, ...] (one per meeting).
  - section_teacher_assignments -- section_id -> teacher_id.
  - student_section_assignments -- roll_number -> section_id (per subject).
  - status -- "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "UNKNOWN".
  - solver_stats -- wall_time, num_conflicts, etc.

Design note on student-section assignment
------------------------------------------
In a single CP-SAT model the number of variables would be
  |students| x |sections|  (assignment booleans)
plus  |sections| x |slots|  (slot placement booleans)
plus  |sections| x |teachers|  (teacher assignment booleans).

For realistic department sizes (e.g. 200 students, 20 sections, 19 usable
slots, 10 teachers) this is roughly 200x20 + 20x19 + 20x10 = 4000+380+200
= ~4580 binary variables -- well within CP-SAT's comfort zone.

We keep all three variable groups in one model so the solver can jointly
optimise teacher-slot placement and student-section assignment.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from domain.enums import PreferenceRating, SubjectType
from domain.models import Section
from domain.timeslots import TimeSlot


# ── Rating-to-penalty conversion ──────────────────────────────────────────
#
# CP-SAT minimises, so we convert preference ratings to *penalties*:
#   PREFERRED (1) -> 0 penalty    (ideal)
#   TOLERABLE (2) -> 1 penalty
#   DISLIKED  (3) -> 3 penalty
#   unrated        -> 2 penalty    (treated as weakly tolerable)
#
# BLOCKED (4) is a hard constraint, not a penalty term.

_TIME_PREF_PENALTY: Dict[int, int] = {
    PreferenceRating.PREFERRED.value: 0,
    PreferenceRating.TOLERABLE.value: 1,
    PreferenceRating.DISLIKED.value:  3,
    PreferenceRating.BLOCKED.value:   9999,  # sentinel -- should never reach objective
}
_DEFAULT_TIME_PENALTY = 2  # unrated slot

# Faculty preference penalty weights.  Lower than time-slot penalties so
# the solver always prioritises slot satisfaction over teacher preference.
_FACULTY_PREF_PENALTY: Dict[int, int] = {
    PreferenceRating.PREFERRED.value: 0,
    PreferenceRating.TOLERABLE.value: 1,
    PreferenceRating.DISLIKED.value:  2,
}
_DEFAULT_FACULTY_PENALTY = 1  # unranked teacher

# Relative weight for faculty-preference penalties vs. time-slot penalties.
# e.g. TIME_WEIGHT=5 means a single "disliked" slot (penalty 3) costs 15
# in objective units; a "disliked" teacher (penalty 2) costs 2 units.
_TIME_WEIGHT = 5
_FACULTY_WEIGHT = 1

# Load-balance weight: each unit of (max_load - min_load) above 0 costs
# this many objective units.  Kept low so load balance never overrides
# student satisfaction.
_LOAD_BALANCE_WEIGHT = 10


# ── Data transfer objects ─────────────────────────────────────────────────

@dataclass
class SolverInput:
    """Everything the engine needs; computed and passed by solver/service.py."""

    # Section list for this run (from Phase 8 store data).
    sections: List[Section]

    # section_id -> list of valid TimeSlot objects (type-legal, per section.subject type).
    candidate_slots: Dict[int, List[TimeSlot]]

    # section_id -> list of capable teacher_ids for the subject.
    candidate_teachers: Dict[int, List[str]]

    # roll_number -> slot_key -> rating int (1-4).  Missing key = unrated.
    time_preferences: Dict[str, Dict[str, int]]

    # roll_number -> subject_code -> teacher_id -> rating int (1-3).
    faculty_preferences: Dict[str, Dict[str, Dict[str, int]]]

    # teacher_id -> slot_key -> available bool.  Missing = True.
    teacher_availability: Dict[str, Dict[str, bool]]

    # subject_code -> [roll_number, ...] for students in this semester.
    # Used to decide which students can be enrolled in which sections.
    subject_students: Dict[str, List[str]]

    # Time limit for the solver in seconds.
    time_limit_seconds: float = 30.0


@dataclass
class SolverResult:
    status: str  # "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "UNKNOWN"

    # section_id -> [slot_key] (one per meeting in the linked pattern).
    section_slot_assignments: Dict[int, List[str]] = field(default_factory=dict)

    # section_id -> teacher_id (None if no teacher assigned).
    section_teacher_assignments: Dict[int, Optional[str]] = field(default_factory=dict)

    # roll_number -> {subject_code -> section_id}.
    student_section_assignments: Dict[str, Dict[str, int]] = field(default_factory=dict)

    # Diagnostic info.
    wall_time_seconds: float = 0.0
    num_conflicts: int = 0
    objective_value: int = 0
    warnings: List[str] = field(default_factory=list)


# ── Engine ────────────────────────────────────────────────────────────────

def solve(inp: SolverInput) -> SolverResult:
    """Build and solve the CP-SAT timetabling model, return assignments."""
    model = cp_model.CpModel()

    sections = inp.sections
    section_by_id: Dict[int, Section] = {s.id: s for s in sections if s.id is not None}

    # Index all teacher_ids that appear anywhere in this run.
    all_teacher_ids: List[str] = sorted({
        tid
        for tids in inp.candidate_teachers.values()
        for tid in tids
    })

    # ── Decision variables ────────────────────────────────────────────────

    # slot_var[section_id][meeting_idx][slot_idx] = 1 if meeting m of
    # section s is placed in slot candidate_slots[s][slot_idx].
    slot_vars: Dict[int, List[List[cp_model.IntVar]]] = {}
    for section in sections:
        sid = section.id
        n_meetings = len(section.meetings)
        cand = inp.candidate_slots.get(sid, [])
        slot_vars[sid] = []
        for _m in range(n_meetings):
            meeting_vars = [
                model.new_bool_var(f"slot_s{sid}_m{_m}_c{ci}")
                for ci in range(len(cand))
            ]
            slot_vars[sid].append(meeting_vars)
            # Exactly one slot per meeting.
            model.add_exactly_one(meeting_vars)

    # teacher_var[section_id][teacher_idx] = 1 if that teacher is assigned.
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
            tvars = []  # no capable teacher -- section floats unassigned
        teacher_vars[sid] = tvars

    # student_var[roll_number][subject_code][section_id] = 1 if enrolled.
    # We build these per-subject so each student is in exactly one section.
    student_vars: Dict[str, Dict[str, Dict[int, cp_model.IntVar]]] = {}
    subject_sections: Dict[str, List[int]] = {}  # subject_code -> [section_id]
    for section in sections:
        subject_sections.setdefault(section.subject_code, []).append(section.id)

    for subject_code, sids in subject_sections.items():
        for roll in inp.subject_students.get(subject_code, []):
            student_vars.setdefault(roll, {}).setdefault(subject_code, {})
            sec_avars = [
                model.new_bool_var(f"enroll_r{roll}_sub{subject_code}_s{sid}")
                for sid in sids
            ]
            # Exactly one section per student per subject.
            model.add_exactly_one(sec_avars)
            for sid, avar in zip(sids, sec_avars):
                student_vars[roll][subject_code][sid] = avar

    # ── Hard constraints ──────────────────────────────────────────────────

    # (a) Teacher availability: if admin blocked teacher T in slot S,
    #     T cannot be assigned to section M whose meeting is in S.
    for section in sections:
        sid = section.id
        cand_t = inp.candidate_teachers.get(sid, [])
        cand_s = inp.candidate_slots.get(sid, [])
        for ti, teacher_id in enumerate(cand_t):
            avail_map = inp.teacher_availability.get(teacher_id, {})
            for mi in range(len(section.meetings)):
                for ci, slot in enumerate(cand_s):
                    if not avail_map.get(slot.key, True):
                        # teacher_t AND slot_c cannot both be 1.
                        if teacher_vars[sid]:
                            model.add(
                                teacher_vars[sid][ti] + slot_vars[sid][mi][ci] <= 1
                            )

    # (b) No teacher double-booking: for each pair of sections, if they
    #     share the same teacher assignment and the same meeting slot,
    #     that is forbidden.
    #     We model this via a helper bool: "section X is in slot S AND
    #     teacher T" implies no other section with teacher T can be in
    #     slot S at the same time.
    #
    # For efficiency: group sections by subject, then handle cross-section
    # clashes using AddBoolAnd / implications.
    #
    # For each pair (s1, s2), each meeting of s1, each candidate slot S,
    # each teacher T: NOT (teacher(s1)=T AND slot(s1.mi)=S AND
    #                       teacher(s2)=T AND slot(s2.mj)=S)
    #
    # This is O(|sections|^2 x |meetings| x |slots| x |teachers|). For
    # small department sizes this is fine; the model stays compact.
    for i, s1 in enumerate(sections):
        for s2 in sections[i+1:]:
            sid1, sid2 = s1.id, s2.id
            cand_t1 = inp.candidate_teachers.get(sid1, [])
            cand_t2 = inp.candidate_teachers.get(sid2, [])
            shared_teachers = set(cand_t1) & set(cand_t2)
            if not shared_teachers:
                continue
            cand_s1 = inp.candidate_slots.get(sid1, [])
            cand_s2 = inp.candidate_slots.get(sid2, [])
            for teacher_id in shared_teachers:
                ti1 = cand_t1.index(teacher_id)
                ti2 = cand_t2.index(teacher_id)
                t_var1 = teacher_vars[sid1][ti1] if teacher_vars[sid1] else None
                t_var2 = teacher_vars[sid2][ti2] if teacher_vars[sid2] else None
                if t_var1 is None or t_var2 is None:
                    continue
                for mi1, meeting1 in enumerate(s1.meetings):
                    for ci1, slot1 in enumerate(cand_s1):
                        sv1 = slot_vars[sid1][mi1][ci1]
                        for mi2, meeting2 in enumerate(s2.meetings):
                            for ci2, slot2 in enumerate(cand_s2):
                                if slot1.key != slot2.key:
                                    continue
                                sv2 = slot_vars[sid2][mi2][ci2]
                                # t_var1=1, sv1=1, t_var2=1, sv2=1 is forbidden.
                                model.add_bool_or([
                                    t_var1.Not(), sv1.Not(),
                                    t_var2.Not(), sv2.Not(),
                                ])

    # (c) Section capacity: total students assigned to a section <= capacity.
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

    # (d) Student BLOCKED constraint: if a student rated a slot as BLOCKED (4),
    #     they cannot be assigned to a section whose meeting falls in that slot.
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
                            # student in section AND section in blocked slot is forbidden.
                            model.add_bool_or([
                                avar.Not(), slot_vars[sid][mi][ci].Not()
                            ])

    # ── Objective ─────────────────────────────────────────────────────────

    objective_terms: List[cp_model.LinearExpr] = []

    # 1. Time-slot satisfaction penalty (primary, weight=TIME_WEIGHT).
    #    For each student assigned to a section, penalise based on the
    #    slot(s) that section meets in relative to the student's ratings.
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
                        sv = slot_vars[sid][mi][ci]
                        # Penalty applies when BOTH avar=1 (student in section)
                        # AND sv=1 (section in that slot).
                        combined = model.new_bool_var(
                            f"obj_time_r{roll}_s{sid}_m{mi}_c{ci}"
                        )
                        model.add_bool_and([avar, sv]).only_enforce_if(combined)
                        model.add_bool_or([avar.Not(), sv.Not()]).only_enforce_if(
                            combined.Not()
                        )
                        if penalty > 0:
                            objective_terms.append(
                                cp_model.LinearExpr.term(combined, _TIME_WEIGHT * penalty)
                            )

    # 2. Faculty preference penalty (secondary, weight=FACULTY_WEIGHT).
    #    For each student assigned to a section, penalise based on the
    #    teacher assigned relative to the student's teacher rankings.
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
                    combined = model.new_bool_var(
                        f"obj_fac_r{roll}_s{sid}_t{ti}"
                    )
                    model.add_bool_and([avar, tv]).only_enforce_if(combined)
                    model.add_bool_or([avar.Not(), tv.Not()]).only_enforce_if(
                        combined.Not()
                    )
                    if penalty > 0:
                        objective_terms.append(
                            cp_model.LinearExpr.term(combined, _FACULTY_WEIGHT * penalty)
                        )

    # 3. Teacher load balance (tertiary, weight=LOAD_BALANCE_WEIGHT).
    #    Each teacher_var that is 1 for a section counts +1 for that
    #    teacher's load.  We minimise (max_load - min_load).
    if len(all_teacher_ids) >= 2:
        teacher_load: Dict[str, List[cp_model.IntVar]] = {t: [] for t in all_teacher_ids}
        for section in sections:
            sid = section.id
            cand_t = inp.candidate_teachers.get(sid, [])
            for ti, teacher_id in enumerate(cand_t):
                if teacher_vars[sid]:
                    teacher_load[teacher_id].append(teacher_vars[sid][ti])

        # Load variable per teacher.
        load_vars: Dict[str, cp_model.IntVar] = {}
        for teacher_id, assignment_vars in teacher_load.items():
            if assignment_vars:
                lv = model.new_int_var(
                    0, len(sections), f"load_{teacher_id}"
                )
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

    # Minimise total penalty.
    if objective_terms:
        model.minimize(sum(objective_terms))

    # ── Solve ─────────────────────────────────────────────────────────────

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = inp.time_limit_seconds
    solver.parameters.num_workers = 4  # use multiple threads

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

    # ── Extract slot assignments ───────────────────────────────────────────
    for section in sections:
        sid = section.id
        cand_s = inp.candidate_slots.get(sid, [])
        assigned_slots: List[str] = []
        for mi in range(len(section.meetings)):
            picked = None
            for ci, slot in enumerate(cand_s):
                if solver.boolean_value(slot_vars[sid][mi][ci]):
                    picked = slot.key
                    break
            assigned_slots.append(picked or "")
        result.section_slot_assignments[sid] = assigned_slots

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
