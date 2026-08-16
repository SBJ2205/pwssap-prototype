"""Core CP-SAT optimization: builds and solves the assignment model.

Contains ONLY the mathematical model. Orchestration (gap-reduction pass,
baseline comparisons, final result shaping) lives in solver/service.py,
which is what api/solver_routes.py actually calls.
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

from ortools.sat.python import cp_model

from data.store import InMemoryStore
from domain.models import Section
from solver.helpers import slot_blocked, slot_faculty_penalty, slot_time_keys, slot_time_penalty


@dataclass
class SolveOutcome:
    status: str                              # "OPTIMAL" or "INFEASIBLE"
    assignments: Optional[List[dict]] = None
    objective_total_penalty: Optional[int] = None
    wall_time_ms: Optional[float] = None
    message: Optional[str] = None


def solve_cp_sat(store: InMemoryStore, fairness_index: int, faculty_weight: int) -> SolveOutcome:
    model = cp_model.CpModel()
    solver = cp_model.CpSolver()

    students = store.list_students()
    sections = store.list_sections()
    section_by_id: Dict[int, Section] = {sec.id: sec for sec in sections}
    section_subject: Dict[int, str] = {sec.id: sec.subject_code for sec in sections}

    subject_sections: Dict[str, List[int]] = defaultdict(list)
    for sec in sections:
        subject_sections[sec.subject_code].append(sec.id)

    # ── Decision variables: x[s][subj] = section_id assigned to student s ──
    x: Dict[int, Dict[str, "cp_model.IntVar"]] = {}
    for student in students:
        s = student.id
        x[s] = {}
        ts_prefs = store.get_ts_prefs(s)
        for subj, section_ids in subject_sections.items():
            # Domain pruning: remove sections with ANY meeting the student blocked.
            domain = [sid for sid in section_ids if not slot_blocked(section_by_id[sid], ts_prefs)]
            if not domain:
                return SolveOutcome(
                    status="INFEASIBLE",
                    message=f"Student {student.name} has all slots blocked for {subj}",
                )
            x[s][subj] = model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(domain), f"x_s{s}_{subj}"
            )

    # ── Reified per-(student, section) assignment booleans ─────────────────
    # assign[s][sid] is TRUE iff x[s][subj_of(sid)] == sid. Reified in BOTH
    # directions so it's a trustworthy indicator reused for capacity,
    # no-clash, and penalty scoring below.
    assign: Dict[int, Dict[int, "cp_model.IntVar"]] = {}
    for student in students:
        s = student.id
        assign[s] = {}
        for sec in sections:
            b = model.NewBoolVar(f"assign_s{s}_sec{sec.id}")
            model.Add(x[s][sec.subject_code] == sec.id).OnlyEnforceIf(b)
            model.Add(x[s][sec.subject_code] != sec.id).OnlyEnforceIf(b.Not())
            assign[s][sec.id] = b

    # ── Capacity constraints ────────────────────────────────────────────────
    for sec in sections:
        model.Add(sum(assign[student.id][sec.id] for student in students) <= sec.capacity)

    # ── No-clash constraints ────────────────────────────────────────────────
    # Build a day-time -> [section_ids] map. A multi-meeting section
    # contributes one entry PER meeting, so it's checked for clashes at
    # every time block it occupies, not just a single nominal slot.
    timeslot_map: Dict[tuple, List[int]] = defaultdict(list)
    for sec in sections:
        for m in sec.meetings:
            timeslot_map[(m.day, m.time)].append(sec.id)

    for (_day, _time), clash_sections in timeslot_map.items():
        subjects_here = {section_subject[sid] for sid in clash_sections}
        if len(subjects_here) < 2:
            continue  # only one subject meets at this time -> nothing can clash
        for student in students:
            model.Add(sum(assign[student.id][sid] for sid in clash_sections) <= 1)

    # ── Objective: minimise total weighted penalty ────────────────────────────
    # Primary term: time-slot penalty (summed across all meetings of the
    # assigned section). Secondary term: faculty-mismatch penalty.
    penalty_vars = []
    for student in students:
        s = student.id
        ts_prefs = store.get_ts_prefs(s)
        fac_prefs = store.get_faculty_prefs(s)
        student_penalty_terms = []
        for sec in sections:
            time_pen = slot_time_penalty(sec, ts_prefs)
            _, fac_pen = slot_faculty_penalty(sec, fac_prefs, faculty_weight)
            pen = time_pen + fac_pen
            if pen > 0:
                student_penalty_terms.append(pen * assign[s][sec.id])
        sp = model.NewIntVar(0, 200, f"sp_{s}")
        model.Add(sp == sum(student_penalty_terms))
        model.Add(sp <= fairness_index)  # Fairness Index: per-student penalty cap
        penalty_vars.append(sp)

    model.Minimize(sum(penalty_vars))

    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveOutcome(status="INFEASIBLE", message="No feasible assignment found.")

    # ── Extract result ────────────────────────────────────────────────────────
    assignments = []
    for student in students:
        s = student.id
        ts_prefs = store.get_ts_prefs(s)
        fac_prefs = store.get_faculty_prefs(s)
        student_assignments = []
        student_penalty = 0
        for subj in subject_sections:
            sid = solver.Value(x[s][subj])
            sec = section_by_id[sid]
            time_pen = slot_time_penalty(sec, ts_prefs)
            frating, fac_pen = slot_faculty_penalty(sec, fac_prefs, faculty_weight)
            pen = time_pen + fac_pen
            worst_rating = max((ts_prefs.get(k, 1) for k in slot_time_keys(sec)), default=1)
            student_penalty += pen
            student_assignments.append({
                "subject": store.get_subject(subj).name,
                "code": subj,
                "section": sec.label,
                "faculty": store.get_teacher(sec.teacher_id).name,
                "room": sec.room,
                "slot_id": sid,
                "meetings": [{"day": m.day, "time": m.time} for m in sec.meetings],
                "rating": worst_rating,
                "time_penalty": time_pen,
                "faculty_rating": frating,
                "faculty_penalty": fac_pen,
                "penalty": pen,
            })
        assignments.append({
            "student_id": s,
            "name": student.name,
            "roll": student.roll,
            "penalty": student_penalty,
            "assignments": student_assignments,
        })

    return SolveOutcome(
        status="OPTIMAL",
        assignments=assignments,
        objective_total_penalty=int(solver.ObjectiveValue()),
        wall_time_ms=round(solver.WallTime() * 1000, 1),
    )
