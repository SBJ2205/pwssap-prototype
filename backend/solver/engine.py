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
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from domain.enums import PreferenceRating
from domain.models import Meeting, Section
from domain.timeslots import TimeSlot
from solver.gap_reduction import reduce_schedule_gaps


_TIME_PREF_PENALTY: Dict[int, int] = {
    PreferenceRating.PREFERRED.value: 0,
    PreferenceRating.TOLERABLE.value: 1,
    PreferenceRating.DISLIKED.value:  3,
    PreferenceRating.BLOCKED.value:   400,  # 400 * _TIME_WEIGHT (5) = 2,000 priority penalty
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
    candidate_count: int = 1
    random_seed: int = 42
    cancel_check: Optional[Callable[[], bool]] = None


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
    candidates: List[Dict] = field(default_factory=list)
    # Per-stage proof status. `status` is OPTIMAL only if BOTH are OPTIMAL.
    stage1_status: str = ""
    stage2_status: str = ""
    # Student placements in a slot the student blocked, in the delivered
    # timetable; and whether that count is the proven minimum for it.
    blocked_placements: Optional[int] = None
    blocked_minimum_proven: Optional[bool] = None


def _solve_cancellable(solver: cp_model.CpSolver, model: cp_model.CpModel, cancel_check) -> int:
    """solver.solve(), but a watcher thread stops the search soon after
    cancel_check() turns True (CP-SAT otherwise cannot be interrupted)."""
    if cancel_check is None:
        return solver.solve(model)
    done = threading.Event()

    def _watch() -> None:
        while not done.wait(0.5):
            if cancel_check():
                solver.stop_search()
                return

    watcher = threading.Thread(target=_watch, daemon=True)
    watcher.start()
    try:
        return solver.solve(model)
    finally:
        done.set()
        watcher.join(timeout=2.0)


def _solve_single_pass(
    inp: SolverInput,
    seed: int = 42,
    time_limit: Optional[float] = None,
) -> SolverResult:
    res = _solve_single_pass_impl(inp, seed=seed, time_limit=time_limit)
    if inp.cancel_check and inp.cancel_check():
        # A cancelled pass is never a valid candidate / never gets published.
        return SolverResult(
            status="UNKNOWN",
            wall_time_seconds=res.wall_time_seconds,
            warnings=["Solve cancelled by user; no timetable was published."],
        )
    return res


_STATUS_MAP = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.UNKNOWN: "UNKNOWN",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
}


@dataclass
class _Stage1:
    """Outcome of Stage 1: one concrete master timetable (slots + teachers)."""
    status: str
    slot_keys: Dict[int, List[str]]
    meetings: Dict[int, List[Meeting]]
    teachers: Dict[int, Optional[str]]
    subject_sections: Dict[str, List[int]]
    num_conflicts: int
    elapsed: float


def _stage1(inp: SolverInput, seed: int, solve_seconds: float) -> Tuple[Optional[_Stage1], Optional[SolverResult]]:
    """Stage 1: build a master timetable. Returns (stage1, None) or (None, failure_result)."""
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
    enrolled_set = {
        sc: set(students)
        for sc, students in inp.subject_students.items()
    }

    # NOTE: student-blocked slots are deliberately NOT hard-forbidden for
    # single-section subjects. The union of a large cohort's blocked slots can
    # cover every legal slot (e.g. 56 students of one elective), which made
    # Stage 1 INFEASIBLE. Layer 2 (+300 per blocked student, below) steers the
    # section away softly; any unavoidable case surfaces as a diagnostic warning.

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

    # Constraint 4c: Elective theory and elective labs of the same track cannot overlap for the corresponding batch
    for sem in all_semesters:
        sem_stags = {stag for (s_sem, stag, _) in list(elective_theory_by_subtag.keys()) + list(elective_lab_by_subtag.keys()) if s_sem == sem}
        for stag in sem_stags:
            stag_divs = [div for (s_sem, s_tag, div) in elective_theory_by_subtag.keys() if s_sem == sem and s_tag == stag]
            stag_batches = [b for (s_sem, s_tag, b) in elective_lab_by_subtag.keys() if s_sem == sem and s_tag == stag]
            if stag_divs and stag_batches:
                n_d = max(stag_divs)
                n_b = max(stag_batches)
                for b in stag_batches:
                    mapped_div = min(n_d, max(1, 1 + (b - 1) * n_d // n_b))
                    e_th = elective_theory_by_subtag.get((sem, stag, mapped_div), [])
                    e_lb = elective_lab_by_subtag.get((sem, stag, b), [])
                    if e_th and e_lb:
                        for sk in all_slot_keys:
                            for part in (1, 2):
                                th_terms = [period_active[(sid, mi, slot_indices[sid][sk], part)] for sid, mi in e_th if sk in slot_indices[sid]]
                                lb_terms = [period_active[(sid, mi, slot_indices[sid][sk], part)] for sid, mi in e_lb if sk in slot_indices[sid]]
                                if th_terms and lb_terms:
                                    m1.add(sum(th_terms) + sum(lb_terms) <= 1)

    # Constraint 4d: Elective theory in division k cannot overlap with common/core labs of that division
    for sem in all_semesters:
        sem_divs = [div for (s_sem, div) in core_theory_tracks.keys() if s_sem == sem]
        sem_batches = [b for (s_sem, b) in lab_batches.keys() if s_sem == sem]
        if sem_divs and sem_batches:
            num_divs = max(sem_divs)
            num_batches = max(sem_batches)
            for b in sem_batches:
                div_k = min(num_divs, max(1, 1 + (b - 1) * num_divs // num_batches))
                common_labs = [
                    m for m in lab_batches.get((sem, b), [])
                    if not inp.subject_subtags.get(section_by_id[m[0]].subject_code)
                ]
                if not common_labs:
                    continue
                # For each elective track in this semester, ensure its theory in div_k does not clash with common labs in batch b
                for (s_sem, stag, e_div), e_meets in elective_theory_by_subtag.items():
                    if s_sem == sem and e_div == div_k and e_meets:
                        for sk in all_slot_keys:
                            for part in (1, 2):
                                e_terms = [period_active[(sid, mi, slot_indices[sid][sk], part)] for sid, mi in e_meets if sk in slot_indices[sid]]
                                l_terms = [period_active[(sid, mi, slot_indices[sid][sk], part)] for sid, mi in common_labs if sk in slot_indices[sid]]
                                if e_terms and l_terms:
                                    m1.add(sum(e_terms) + sum(l_terms) <= 1)

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

    # Stage 1 Objective: Faculty teaching load balance + Cohort slot preferences (Student-aware Master TT)
    stage1_obj_terms: List[cp_model.LinearExpr] = []

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
            stage1_obj_terms.append(cp_model.LinearExpr.term(load_range, 10))

    # Cohort aggregated student slot preference + Proactive Blocked Slot Avoidance
    if inp.subject_students and inp.time_preferences:
        for section in sections:
            sid = section.id
            sub_code = section.subject_code
            studs = inp.subject_students.get(sub_code, [])
            if not studs:
                continue
            cand_s = inp.candidate_slots.get(sid, [])
            for ci, slot in enumerate(cand_s):
                sk = slot.key
                blocked_students_count = sum(
                    1 for roll in studs
                    if inp.time_preferences.get(roll, {}).get(sk) == PreferenceRating.BLOCKED.value
                )
                tot_p = sum(
                    _TIME_PREF_PENALTY.get(
                        inp.time_preferences.get(roll, {}).get(sk, _DEFAULT_TIME_PENALTY),
                        _DEFAULT_TIME_PENALTY,
                    )
                    for roll in studs
                    if inp.time_preferences.get(roll, {}).get(sk) != PreferenceRating.BLOCKED.value
                )
                avg_penalty = max(0, min(50, round(tot_p / len(studs))))
                # Heavily penalize putting cohort sections in slots that any enrolled student has blocked
                combined_penalty = (avg_penalty * 2) + (blocked_students_count * 300)
                if combined_penalty > 0:
                    for mi, m in enumerate(section.meetings):
                        dur = getattr(m, "duration_hours", 2) or 2
                        if dur == 1:
                            if sid in slot_active_in and mi in slot_active_in[sid] and ci < len(slot_active_in[sid][mi]):
                                s_act = slot_active_in[sid][mi][ci]
                                stage1_obj_terms.append(cp_model.LinearExpr.term(s_act, combined_penalty))
                        else:
                            if sid in slot_vars_2h and mi in slot_vars_2h[sid] and ci < len(slot_vars_2h[sid][mi]):
                                v_2h = slot_vars_2h[sid][mi][ci]
                                stage1_obj_terms.append(cp_model.LinearExpr.term(v_2h, combined_penalty))

    if stage1_obj_terms:
        m1.minimize(sum(stage1_obj_terms))

    # Solve Stage 1
    solver1 = cp_model.CpSolver()
    solver1.parameters.max_time_in_seconds = max(1.0, solve_seconds)
    solver1.parameters.num_workers = 0
    solver1.parameters.random_seed = seed

    t0_stage1 = time.monotonic()
    status1 = _solve_cancellable(solver1, m1, inp.cancel_check)
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
            stage1_status=status1_str,
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
        return None, res

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

    return _Stage1(
        status=status1_str,
        slot_keys=assigned_slot_keys,
        meetings=assigned_meetings,
        teachers=assigned_teachers,
        subject_sections=subject_sections,
        num_conflicts=int(solver1.num_conflicts),
        elapsed=stage1_elapsed,
    ), None


def _stage2(
    inp: SolverInput,
    seed: int,
    s1: _Stage1,
    budget: float,
    score_only: bool = False,
) -> SolverResult:
    """Stage 2: assign students to the sections of a FIXED master timetable.

    score_only=True stops after Pass A (minimum blocked placements) and returns
    status "SCORED" - a cheap way to compare candidate master timetables.
    """
    sections = inp.sections
    subject_sections = s1.subject_sections
    assigned_slot_keys = s1.slot_keys
    assigned_meetings = s1.meetings
    assigned_teachers = s1.teachers
    status1_str = s1.status
    status_map = _STATUS_MAP
    total_t0 = time.monotonic()
    effective_time_limit = float(budget)
    stage1_elapsed = 0.0

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
    # Treated as high-priority soft penalties (2,000 points per meeting) in
    # section 2.d below to steer students away while avoiding fatal INFEASIBLE bottlenecks.


    # 2.c Student no-clash (linear period sum constraint)
    for roll, sec_tuples in student_active_sections.items():
        slot_terms: Dict[Tuple[str, int], List[cp_model.IntVar]] = {}
        for sc, sid, v in sec_tuples:
            for p in section_periods.get(sid, set()):
                slot_terms.setdefault(p, []).append(v)
        for p, vlist in slot_terms.items():
            if len(vlist) > 1:
                m2.add(sum(vlist) <= 1)

    # 2.d Stage 2 objectives.
    # Student BLOCKED placements are kept apart from every other preference
    # term. They are minimised FIRST and on their own (Pass A), then capped at
    # that value while all remaining preferences are optimised (Pass B).
    # Net effect: blocked slots are treated as hard whenever the timetable
    # allows it, and otherwise limited to the minimum possible - without the
    # big blocked penalty drowning out (or being drowned by) other terms.
    blocked_value = PreferenceRating.BLOCKED.value
    blocked_terms: List[cp_model.LinearExpr] = []  # v * (#blocked meetings of that section)
    other_terms: List[cp_model.LinearExpr] = []
    if not inp.feasibility_only:
        for (roll, sub, sid), v in enroll_vars.items():
            time_pref = inp.time_preferences.get(roll, {})
            n_blocked = 0
            for m in assigned_meetings.get(sid, []):
                rating = time_pref.get(m.slot_key)
                if rating is None:
                    continue
                if rating == blocked_value:
                    n_blocked += 1
                else:
                    penalty = _TIME_PREF_PENALTY.get(rating, _DEFAULT_TIME_PENALTY)
                    if penalty > 0:
                        other_terms.append(cp_model.LinearExpr.term(v, _TIME_WEIGHT * penalty))
            if n_blocked:
                blocked_terms.append(cp_model.LinearExpr.term(v, n_blocked))

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
                        other_terms.append(cp_model.LinearExpr.term(v, _FACULTY_WEIGHT * penalty))

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
                    other_terms.append(cp_model.LinearExpr.term(dev, 2))

    # Solve Stage 2
    rem_time = max(1.0, effective_time_limit - stage1_elapsed)

    def _new_solver(limit: float, first_solution: bool = False) -> cp_model.CpSolver:
        s = cp_model.CpSolver()
        s.parameters.num_workers = 0
        s.parameters.random_seed = seed
        s.parameters.max_time_in_seconds = max(1.0, limit)
        if first_solution:
            s.parameters.stop_after_first_solution = True
        return s

    def _remaining() -> float:
        return max(1.0, effective_time_limit - (time.monotonic() - total_t0))

    def _hint_from(src: cp_model.CpSolver) -> None:
        m2.clear_hints()
        for _k, _v in enroll_vars.items():
            m2.add_hint(_v, 1 if src.boolean_value(_v) else 0)

    stage2_notes: List[str] = []

    blocked_minimum_proven: Optional[bool] = None
    solver2: cp_model.CpSolver

    if inp.feasibility_only or not (blocked_terms or other_terms):
        solver2 = _new_solver(rem_time, first_solution=True)
        status2 = _solve_cancellable(solver2, m2, inp.cancel_check)
        if status2 in (cp_model.OPTIMAL, cp_model.FEASIBLE) and not inp.feasibility_only:
            blocked_minimum_proven = True  # nothing to optimise: no blocks at all
            if score_only:
                return SolverResult(
                    status="SCORED",
                    wall_time_seconds=round(time.monotonic() - total_t0, 3),
                    num_conflicts=int(s1.num_conflicts),
                    stage1_status=status1_str,
                    stage2_status="SCORED",
                    blocked_placements=0,
                    blocked_minimum_proven=True,
                )
    else:
        # Phase 0: any valid assignment (guarantees we always have a fallback).
        solver_feas = _new_solver(min(20.0, max(5.0, rem_time * 0.75)), first_solution=True)
        status_feas = _solve_cancellable(solver_feas, m2, inp.cancel_check)
        solver2, status2 = solver_feas, status_feas

        if status_feas in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            best = solver_feas
            blocked_best = 0

            # Pass A: minimise blocked placements ONLY.
            pass_a_proven = True
            if blocked_terms:
                blocked_sum = sum(blocked_terms)
                _hint_from(best)
                m2.minimize(blocked_sum)
                # Scoring a candidate only needs Pass A, so it may use all of the budget.
                solver_a = _new_solver(_remaining() * (1.0 if score_only else 0.35))
                status_a = _solve_cancellable(solver_a, m2, inp.cancel_check)
                if status_a in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                    best = solver_a
                    blocked_best = int(round(solver_a.objective_value))
                    pass_a_proven = status_a == cp_model.OPTIMAL
                else:
                    blocked_best = int(round(solver_feas.value(blocked_sum)))
                    pass_a_proven = False
                blocked_minimum_proven = pass_a_proven
            else:
                blocked_minimum_proven = True

            if score_only:
                return SolverResult(
                    status="SCORED",
                    wall_time_seconds=round(time.monotonic() - total_t0, 3),
                    num_conflicts=int(s1.num_conflicts),
                    stage1_status=status1_str,
                    stage2_status="SCORED",
                    blocked_placements=blocked_best,
                    blocked_minimum_proven=blocked_minimum_proven,
                )

            # Pass B: optimise everything else with blocked placements capped.
            pass_b_proven = True
            if other_terms:
                if blocked_terms:
                    m2.add(sum(blocked_terms) <= blocked_best)
                _hint_from(best)
                m2.clear_objective()
                m2.minimize(sum(other_terms))
                solver_b = _new_solver(_remaining())
                status_b = _solve_cancellable(solver_b, m2, inp.cancel_check)
                if status_b in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                    best = solver_b
                    pass_b_proven = status_b == cp_model.OPTIMAL
                else:
                    pass_b_proven = False
                    stage2_notes.append(
                        "Student preference optimiser (Pass B) found no improvement within the time budget; "
                        "blocked slots were minimised but other preferences were not optimised."
                    )
            solver2 = best
            status2 = cp_model.OPTIMAL if (pass_a_proven and pass_b_proven) else cp_model.FEASIBLE

    status2_str = status_map.get(status2, "UNKNOWN")
    elapsed = time.monotonic() - total_t0

    if status2 in (cp_model.OPTIMAL, cp_model.FEASIBLE) and not inp.feasibility_only:
        # OPTIMAL means *both* stages are proven optimal; Stage 1 usually only
        # reaches FEASIBLE within its time slice, so say so honestly.
        overall_status = "OPTIMAL" if (status1_str == "OPTIMAL" and status2_str == "OPTIMAL") else "FEASIBLE"
    else:
        overall_status = status2_str

    res = SolverResult(
        status=overall_status,
        section_slot_assignments=assigned_slot_keys,
        section_meetings=assigned_meetings,
        section_teacher_assignments=assigned_teachers,
        wall_time_seconds=round(elapsed, 3),
        num_conflicts=int(s1.num_conflicts + solver2.num_conflicts),
        stage1_status=status1_str,
        stage2_status=status2_str,
        blocked_minimum_proven=blocked_minimum_proven,
    )
    res.warnings.extend(stage2_notes)

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

    # Extract student-section assignments
    for (roll, sub, sid), v in enroll_vars.items():
        if solver2.boolean_value(v):
            res.student_section_assignments.setdefault(roll, {})[sub] = sid

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 3: Post-Processing Schedule Gap Reduction Pass
    # ══════════════════════════════════════════════════════════════════════════
    if not inp.feasibility_only and res.status in ("OPTIMAL", "FEASIBLE") and res.student_section_assignments:
        updated_assignments, gap_stats = reduce_schedule_gaps(
            inp=inp,
            assigned_meetings=assigned_meetings,
            assigned_teachers=assigned_teachers,
            student_assignments=res.student_section_assignments,
        )
        res.student_section_assignments = updated_assignments
        if gap_stats.get("gaps_reduced", 0) > 0:
            res.warnings.append(
                f"Schedule gap reduction: eliminated {gap_stats['gaps_reduced']} idle slot gap(s) "
                f"across {gap_stats['improved_students']} student(s) without violating preferences."
            )

    # Score the assignment actually being delivered (after gap reduction).
    # This is computed from the assignment itself - never read back from a
    # solver whose objective may not have been the one that produced it.
    if not inp.feasibility_only and res.status in ("OPTIMAL", "FEASIBLE"):
        total_penalty = 0
        blocked_violations: List[Tuple[str, str, str]] = []
        section_load: Dict[int, int] = defaultdict(int)
        for roll, sub_assignments in res.student_section_assignments.items():
            time_pref = inp.time_preferences.get(roll, {})
            fac_pref = inp.faculty_preferences.get(roll, {})
            for sub, sid in sub_assignments.items():
                section_load[sid] += 1
                for m in assigned_meetings.get(sid, []):
                    rating = time_pref.get(m.slot_key)
                    if rating == blocked_value:
                        blocked_violations.append((roll, sub, m.slot_key))
                        total_penalty += _TIME_WEIGHT * _TIME_PREF_PENALTY[blocked_value]
                    elif rating is not None:
                        total_penalty += _TIME_WEIGHT * _TIME_PREF_PENALTY.get(rating, _DEFAULT_TIME_PENALTY)
                teacher_id = assigned_teachers.get(sid)
                if teacher_id:
                    f_rating = fac_pref.get(sub, {}).get(teacher_id)
                    if f_rating is not None and f_rating != _DEFAULT_FACULTY_PENALTY:
                        total_penalty += _FACULTY_WEIGHT * _FACULTY_PREF_PENALTY.get(f_rating, _DEFAULT_FACULTY_PENALTY)
        for sc, sids in subject_sections.items():
            tot = len(inp.subject_students.get(sc, []))
            if len(sids) >= 2 and tot > 0:
                ideal = tot // len(sids)
                total_penalty += sum(2 * abs(section_load.get(sid, 0) - ideal) for sid in sids)

        res.objective_value = total_penalty
        res.blocked_placements = len(blocked_violations)

        if blocked_violations:
            examples = ", ".join(f"{roll} ({sub} @ {sk})" for roll, sub, sk in blocked_violations[:5])
            more = f" and {len(blocked_violations) - 5} more" if len(blocked_violations) > 5 else ""
            if res.blocked_minimum_proven:
                verdict = (
                    "This is the proven minimum for this master timetable: no assignment can place fewer "
                    "students in blocked slots. Only a different master timetable (try more candidates) can lower it."
                )
            else:
                verdict = (
                    "This is the best found but NOT proven minimal; a longer Solver Time Limit may reduce it."
                )
            res.warnings.append(
                f"Blocked slots: {len(blocked_violations)} placement(s) fall in a slot the student blocked. "
                f"{verdict} Examples: {examples}{more}."
            )

    return res



def _solve_single_pass_impl(
    inp: SolverInput,
    seed: int = 42,
    time_limit: Optional[float] = None,
) -> SolverResult:
    t0 = time.monotonic()
    limit = float(time_limit) if time_limit is not None else float(inp.time_limit_seconds)

    s1, failure = _stage1(inp, seed, solve_seconds=min(limit * 0.7, 45.0))
    if failure is not None:
        return failure

    # If no students enrolled in the input, Stage 1 is the complete answer
    if not any(bool(studs) for studs in inp.subject_students.values()):
        return SolverResult(
            status=s1.status,
            section_slot_assignments=s1.slot_keys,
            section_meetings=s1.meetings,
            section_teacher_assignments=s1.teachers,
            wall_time_seconds=round(time.monotonic() - t0, 3),
            num_conflicts=s1.num_conflicts,
            stage1_status=s1.status,
        )

    res = _stage2(inp, seed, s1, budget=max(1.0, limit - s1.elapsed))
    res.wall_time_seconds = round(time.monotonic() - t0, 3)
    return res



def _candidate_summary(candidate_id: int, seed: int, res: SolverResult, is_best: bool) -> Dict:
    return {
        "candidate_id": candidate_id,
        "seed": seed,
        "status": res.status,
        "stage1_status": res.stage1_status,
        "stage2_status": res.stage2_status,
        # Only a fully optimised result has a meaningful penalty; candidates
        # that were merely scored (or failed) report None, never a fake 0.
        "objective_value": res.objective_value if res.status in ("OPTIMAL", "FEASIBLE") else None,
        "blocked_placements": res.blocked_placements,
        "blocked_minimum_proven": res.blocked_minimum_proven,
        "wall_time_seconds": res.wall_time_seconds,
        "num_conflicts": res.num_conflicts,
        "is_best": is_best,
    }


def solve(inp: SolverInput) -> SolverResult:
    """Entrypoint for CP-SAT timetable generation.

    If candidate_count > 1, builds several master timetables, scores each by
    its minimum blocked-slot placements, and fully optimises only the best
    (see _solve_portfolio).
    """
    if inp.candidate_count <= 1 or inp.feasibility_only:
        res = _solve_single_pass(inp, seed=inp.random_seed, time_limit=inp.time_limit_seconds)
        res.candidates = [_candidate_summary(1, inp.random_seed, res, is_best=True)]
        return res

    return _solve_portfolio(inp)


def _solve_portfolio(inp: SolverInput) -> SolverResult:
    """Multi-candidate search that does NOT split the full solve N ways.

    Phase 1 (about 60% of the budget): for each candidate seed, build a master
    timetable (Stage 1) and score it cheaply with Stage 2's Pass A - the minimum
    number of students it forces into a slot they blocked.
    Phase 2 (everything that is left): run the complete Stage 2 (Pass A + B)
    on the single best-scoring master timetable only.
    """
    t_start = time.monotonic()
    total = float(inp.time_limit_seconds)
    n = min(10, max(2, int(inp.candidate_count)))
    seeds = [42, 101, 202, 303, 404, 505, 606, 707, 808, 909][:n]
    cancelled = lambda: bool(inp.cancel_check and inp.cancel_check())  # noqa: E731

    # No students => nothing to score; a single Stage 1 is the whole answer.
    if not any(bool(studs) for studs in inp.subject_students.values()):
        res = _solve_single_pass(inp, seed=seeds[0], time_limit=total)
        res.candidates = [_candidate_summary(1, seeds[0], res, is_best=True)]
        return res

    per_candidate = (total * 0.6) / n
    stage1_seconds = max(5.0, min(45.0, per_candidate * 0.65))
    score_seconds = max(5.0, per_candidate * 0.35)

    built: List[Tuple[int, int, _Stage1, SolverResult]] = []  # (candidate_id, seed, stage1, score)
    summaries: List[Dict] = []
    notes: List[str] = []

    for idx, seed in enumerate(seeds):
        if cancelled():
            break
        cand_t0 = time.monotonic()
        s1, failure = _stage1(inp, seed, solve_seconds=stage1_seconds)
        if cancelled():
            break
        if failure is not None:
            failure.wall_time_seconds = round(time.monotonic() - cand_t0, 3)
            summaries.append(_candidate_summary(idx + 1, seed, failure, is_best=False))
            continue

        score = _stage2(inp, seed, s1, budget=score_seconds, score_only=True)
        if cancelled():
            break
        score.wall_time_seconds = round(time.monotonic() - cand_t0, 3)
        summaries.append(_candidate_summary(idx + 1, seed, score, is_best=False))
        if score.status == "SCORED":
            built.append((idx + 1, seed, s1, score))
            if score.blocked_placements == 0 and score.blocked_minimum_proven:
                notes.append(
                    f"Candidate #{idx + 1} places nobody in a blocked slot (proven), so no further candidates "
                    "were built; the saved time went to optimising it."
                )
                break

    if cancelled():
        return SolverResult(
            status="UNKNOWN",
            wall_time_seconds=round(time.monotonic() - t_start, 3),
            warnings=["Solve cancelled by user; no timetable was published."],
            candidates=summaries,
        )

    if not built:
        return SolverResult(
            status="UNKNOWN",
            wall_time_seconds=round(time.monotonic() - t_start, 3),
            warnings=[
                f"None of the {len(summaries)} candidate master timetables could be built and scored in "
                f"{per_candidate:.0f}s each (Stage 1 {stage1_seconds:.0f}s + scoring {score_seconds:.0f}s). "
                f"The department is large ({len(inp.sections)} sections): increase the Solver Time Limit "
                "or use fewer candidates."
            ],
            candidates=summaries,
            stage1_status=summaries[0]["stage1_status"] if summaries else "",
        )

    best_id, best_seed, best_s1, best_score = min(
        built, key=lambda b: (b[3].blocked_placements, b[0])
    )
    remaining = max(5.0, total - (time.monotonic() - t_start))
    final_t0 = time.monotonic()
    final = _stage2(inp, best_seed, best_s1, budget=remaining)
    final_seconds = time.monotonic() - final_t0
    if cancelled():
        return SolverResult(
            status="UNKNOWN",
            wall_time_seconds=round(time.monotonic() - t_start, 3),
            warnings=["Solve cancelled by user; no timetable was published."],
            candidates=summaries,
        )
    final.wall_time_seconds = round(time.monotonic() - t_start, 3)

    for row in summaries:
        if row["candidate_id"] == best_id:
            build_and_score_seconds = row["wall_time_seconds"]
            row.update(_candidate_summary(best_id, best_seed, final, is_best=True))
            # This candidate's own time: building + scoring + its full optimisation.
            row["wall_time_seconds"] = round(build_and_score_seconds + final_seconds, 3)
    final.candidates = summaries

    minima = ", ".join(f"#{cid}: {sc.blocked_placements}" for cid, _s, _t, sc in built)
    final.warnings.append(
        f"Multi-candidate search: built and scored {len(built)} master timetable(s) on blocked-slot placements "
        f"(minimum found per candidate - {minima}); selected Candidate #{best_id} and spent the remaining "
        f"{remaining:.0f}s fully optimising it. Other candidates were scored only, not fully optimised."
    )
    final.warnings.extend(notes)
    return final
