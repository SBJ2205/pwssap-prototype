import random as pyrandom
from collections import defaultdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
from ortools.sat.python import cp_model

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Dummy Data ────────────────────────────────────────────────────────────────
# Each section instance now carries a `meetings` LIST rather than a single
# day/time pair, so a section can span multiple non-severable time blocks
# across the week (e.g. a lecture meeting Mon + Wed). IT301-A and IT303-A
# below meet twice a week to demonstrate this.

SLOT_INSTANCES = [
    {"id": 0, "subject": "Data Structures", "code": "IT301", "section": "A", "faculty": "Dr. Sharma",
     "room": "L101", "capacity": 3,
     "meetings": [{"day": "Mon", "time": "9:00"}, {"day": "Wed", "time": "9:00"}]},
    {"id": 1, "subject": "Data Structures", "code": "IT301", "section": "B", "faculty": "Prof. Mehta",
     "room": "L102", "capacity": 3,
     "meetings": [{"day": "Tue", "time": "11:00"}]},
    {"id": 2, "subject": "Data Structures", "code": "IT301", "section": "C", "faculty": "Dr. Sharma",
     "room": "L103", "capacity": 3,
     "meetings": [{"day": "Wed", "time": "14:00"}]},
    {"id": 3, "subject": "OS Concepts", "code": "IT302", "section": "A", "faculty": "Prof. Joshi",
     "room": "L201", "capacity": 3,
     "meetings": [{"day": "Mon", "time": "11:00"}]},
    {"id": 4, "subject": "OS Concepts", "code": "IT302", "section": "B", "faculty": "Dr. Nair",
     "room": "L202", "capacity": 3,
     "meetings": [{"day": "Thu", "time": "9:00"}]},
    {"id": 5, "subject": "OS Concepts", "code": "IT302", "section": "C", "faculty": "Prof. Joshi",
     "room": "L203", "capacity": 3,
     "meetings": [{"day": "Fri", "time": "10:00"}]},
    {"id": 6, "subject": "DBMS", "code": "IT303", "section": "A", "faculty": "Dr. Verma",
     "room": "L301", "capacity": 3,
     "meetings": [{"day": "Tue", "time": "9:00"}, {"day": "Thu", "time": "11:00"}]},
    {"id": 7, "subject": "DBMS", "code": "IT303", "section": "B", "faculty": "Prof. Kulkarni",
     "room": "L302", "capacity": 3,
     "meetings": [{"day": "Wed", "time": "11:00"}]},
    {"id": 8, "subject": "CN Lab", "code": "IT304", "section": "A", "faculty": "Prof. Rao",
     "room": "Lab1", "capacity": 3,
     "meetings": [{"day": "Thu", "time": "14:00"}]},
    {"id": 9, "subject": "CN Lab", "code": "IT304", "section": "B", "faculty": "Prof. Rao",
     "room": "Lab1", "capacity": 3,
     "meetings": [{"day": "Fri", "time": "14:00"}]},
]

STUDENTS = [
    {"id": 0, "name": "Pranav Waghmare",  "roll": "23101C0006"},
    {"id": 1, "name": "Vedant Ghodekar",  "roll": "23101C0007"},
    {"id": 2, "name": "Sujal Jakakure",   "roll": "23101A0018"},
    {"id": 3, "name": "Parth Mokashi",    "roll": "23101B0062"},
]

SUBJECTS = ["IT301", "IT302", "IT303", "IT304"]

# slot_id grouped by subject code
SUBJECT_SLOTS = {
    "IT301": [0, 1, 2],
    "IT302": [3, 4, 5],
    "IT303": [6, 7],
    "IT304": [8, 9],
}

SLOT_SUBJECT = {slot["id"]: slot["code"] for slot in SLOT_INSTANCES}

FACULTY_LIST = sorted({slot["faculty"] for slot in SLOT_INSTANCES})

# ── Abstract time-slot grid: 6 days × 4 periods ───────────────────────────────
# These are the canonical periods students rate — they do NOT know what subject
# falls there. The solver maps each SLOT_INSTANCE meeting's (day, time) to this
# grid.

DAYS   = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
PERIODS = ["9:00", "11:00", "14:00", "16:00"]  # 4 canonical periods

TIME_SLOTS = [
    {"key": f"{d}|{t}", "day": d, "time": t, "label": f"{d} {t}"}
    for d in DAYS for t in PERIODS
]

# Build a lookup: (day, time) -> time-slot key
DAY_TIME_TO_KEY = {(ts["day"], ts["time"]): ts["key"] for ts in TIME_SLOTS}

# For times that don't exactly match a canonical period (e.g. "10:00"),
# map them to the nearest canonical period bucket.
TIME_REMAP = {
    "10:00": "9:00",   # late-morning → morning slot
    "12:00": "11:00",  # noon → late-morning slot
    "15:00": "14:00",  # mid-afternoon → afternoon slot
}

def ts_key_for(day: str, time: str) -> str:
    """Return the canonical time-slot key for a raw (day, time) pair."""
    t = TIME_REMAP.get(time, time)
    return DAY_TIME_TO_KEY.get((day, t), f"{day}|{t}")

def slot_time_keys(slot: dict) -> List[str]:
    """Return the canonical time-slot key for EVERY meeting of a section.
    A multi-meeting section (e.g. Mon + Wed lecture) yields one key per
    meeting, so blocking/penalty logic accounts for all of its occurrences."""
    return [ts_key_for(m["day"], m["time"]) for m in slot["meetings"]]

def slot_blocked(slot: dict, ts_prefs: Dict[str, int]) -> bool:
    """A section is blocked for a student if ANY of its meetings falls in a
    time period the student rated 4 (cannot attend) — they can't take a
    section they'd have to skip part of."""
    return any(ts_prefs.get(k, 1) == 4 for k in slot_time_keys(slot))

def slot_time_penalty(slot: dict, ts_prefs: Dict[str, int]) -> int:
    """Sum of time-preference penalty across every meeting of a section —
    a twice-weekly lecture in a disliked period costs the student twice."""
    return sum(PENALTY.get(ts_prefs.get(k, 1), 0) for k in slot_time_keys(slot))

def slot_faculty_penalty(slot: dict, faculty_prefs: Dict[str, int], faculty_weight: int) -> (int, int):
    """Returns (faculty_rating, weighted_penalty) for a section."""
    rating = faculty_prefs.get(slot["faculty"], 1)
    return rating, faculty_weight * PENALTY.get(rating, 0)

# Default time-slot preferences for each student
# key = "Day|Time" (e.g. "Mon|9:00"), value = 1-4
DEFAULT_TS_PREFS: Dict[int, Dict[str, int]] = {
    0: {"Mon|9:00": 1, "Mon|11:00": 2, "Tue|9:00": 1, "Tue|11:00": 2,
        "Wed|11:00": 2, "Wed|14:00": 3, "Thu|9:00": 1, "Thu|14:00": 2,
        "Fri|10:00": 2, "Fri|14:00": 1},
    1: {"Mon|9:00": 3, "Mon|11:00": 1, "Tue|9:00": 2, "Tue|11:00": 1,
        "Wed|11:00": 1, "Wed|14:00": 2, "Thu|9:00": 2, "Thu|14:00": 1,
        "Fri|10:00": 3, "Fri|14:00": 2},
    2: {"Mon|9:00": 2, "Mon|11:00": 2, "Tue|9:00": 3, "Tue|11:00": 4,
        "Wed|11:00": 1, "Wed|14:00": 1, "Thu|9:00": 1, "Thu|14:00": 3,
        "Fri|10:00": 2, "Fri|14:00": 1},
    3: {"Mon|9:00": 1, "Mon|11:00": 2, "Tue|9:00": 1, "Tue|11:00": 2,
        "Wed|11:00": 3, "Wed|14:00": 2, "Thu|9:00": 3, "Thu|14:00": 2,
        "Fri|10:00": 1, "Fri|14:00": 1},
}

# Default faculty preferences for each student: {faculty_name: rating 1-3}.
# Unlike time slots, faculty ratings have no "blocked" option (4) — the
# spec treats faculty mismatch as a soft secondary penalty term only.
DEFAULT_FACULTY_PREFS: Dict[int, Dict[str, int]] = {
    0: {"Dr. Sharma": 1, "Prof. Rao": 2},
    1: {"Prof. Mehta": 1, "Dr. Nair": 3},
    2: {"Dr. Verma": 2, "Prof. Joshi": 1},
    3: {"Prof. Kulkarni": 3, "Prof. Rao": 1},
}

# In-memory stores
student_ts_prefs: Dict[int, Dict[str, int]] = {k: dict(v) for k, v in DEFAULT_TS_PREFS.items()}
student_faculty_prefs: Dict[int, Dict[str, int]] = {k: dict(v) for k, v in DEFAULT_FACULTY_PREFS.items()}
last_result = {}

# ── Penalty mapping ───────────────────────────────────────────────────────────
# Shared by both the time-slot dimension and the faculty dimension —
# both use the same 1=Preferred / 2=Tolerable / 3=Disliked rating scale.

PENALTY = {1: 0, 2: 1, 3: 3}   # rating 4 (time only) → domain pruned, never assigned

# ── Routes: read-only data ────────────────────────────────────────────────────

@app.get("/slots")
def get_slots():
    return SLOT_INSTANCES

@app.get("/students")
def get_students():
    return STUDENTS

@app.get("/timeslots")
def get_timeslots():
    """Return the canonical time-slot grid (6 days × 4 periods)."""
    return TIME_SLOTS

@app.get("/faculty")
def get_faculty():
    return FACULTY_LIST

# ── Routes: time-slot preferences ─────────────────────────────────────────────

@app.get("/prefs/{student_id}")
def get_prefs(student_id: int):
    """Return the student's time-slot preferences as {day|time: rating}."""
    return student_ts_prefs.get(student_id, {})

class PrefsPayload(BaseModel):
    prefs: Dict[str, int]   # "Day|Time" → rating

@app.post("/prefs/{student_id}")
def save_prefs(student_id: int, payload: PrefsPayload):
    student_ts_prefs[student_id] = payload.prefs
    # Quick feasibility check: for each subject, at least one section
    # must survive block-pruning (no meeting rated 4).
    ts_prefs = payload.prefs
    warnings = []
    for subj, slot_ids in SUBJECT_SLOTS.items():
        available = [sid for sid in slot_ids if not slot_blocked(SLOT_INSTANCES[sid], ts_prefs)]
        if len(available) == 0:
            warnings.append(f"All slots for {subj} are blocked — assignment will be INFEASIBLE.")
    return {"status": "saved", "warnings": warnings}

# ── Routes: faculty preferences ───────────────────────────────────────────────

@app.get("/faculty-prefs/{student_id}")
def get_faculty_prefs(student_id: int):
    """Return the student's faculty preferences as {faculty_name: rating}."""
    return student_faculty_prefs.get(student_id, {})

class FacultyPrefsPayload(BaseModel):
    prefs: Dict[str, int]   # faculty name → rating (1-3)

@app.post("/faculty-prefs/{student_id}")
def save_faculty_prefs(student_id: int, payload: FacultyPrefsPayload):
    student_faculty_prefs[student_id] = payload.prefs
    return {"status": "saved"}

# ── Gap-count helper (shared by gap-reduction pass & reporting) ──────────────

def gap_count(daytimes) -> int:
    """Count idle canonical periods strictly between a student's first and
    last class on each day, summed across the week."""
    by_day = defaultdict(set)
    for day, time in daytimes:
        t = TIME_REMAP.get(time, time)
        if t in PERIODS:
            by_day[day].add(PERIODS.index(t))
    total = 0
    for idxs in by_day.values():
        if len(idxs) > 1:
            total += (max(idxs) - min(idxs) + 1) - len(idxs)
    return total

# ── Gap-reduction post-processing pass ────────────────────────────────────────

def apply_gap_reduction(assignments: List[dict], faculty_weight: int, passes: int = 2) -> dict:
    """Second-pass heuristic: after the CP-SAT solve, look for idle gaps in
    each student's daily schedule and try to shift them to an alternative
    section of the SAME subject that removes the gap — but only if doing so
    does not increase that student's (and therefore the global) penalty, and
    only if it stays capacity- and clash-feasible. This can only keep the
    global objective the same or lower; it never degrades it."""
    occ = defaultdict(int)
    for a in assignments:
        for asn in a["assignments"]:
            occ[asn["slot_id"]] += 1

    def student_daytimes(a):
        dts = set()
        for asn in a["assignments"]:
            for m in asn["meetings"]:
                dts.add((m["day"], m["time"]))
        return dts

    total_gaps_before = sum(gap_count(student_daytimes(a)) for a in assignments)
    changes = []

    for _ in range(passes):
        for a in assignments:
            s = a["student_id"]
            ts_prefs = student_ts_prefs.get(s, {})
            fac_prefs = student_faculty_prefs.get(s, {})
            for asn in a["assignments"]:
                code = asn["code"]
                cur_sid = asn["slot_id"]
                cur_penalty = asn["penalty"]

                other_daytimes = set()
                for other in a["assignments"]:
                    if other is asn:
                        continue
                    for m in other["meetings"]:
                        other_daytimes.add((m["day"], m["time"]))
                cur_meeting_dts = {(m["day"], m["time"]) for m in asn["meetings"]}
                cur_gap = gap_count(other_daytimes | cur_meeting_dts)

                best = None
                for alt_sid in SUBJECT_SLOTS[code]:
                    if alt_sid == cur_sid:
                        continue
                    alt_slot = SLOT_INSTANCES[alt_sid]
                    if slot_blocked(alt_slot, ts_prefs):
                        continue
                    if occ[alt_sid] >= alt_slot["capacity"]:
                        continue
                    alt_daytimes = [(m["day"], m["time"]) for m in alt_slot["meetings"]]
                    if any(dt in other_daytimes for dt in alt_daytimes):
                        continue  # would clash with this student's other subjects

                    alt_time_pen = slot_time_penalty(alt_slot, ts_prefs)
                    alt_frating, alt_fac_pen = slot_faculty_penalty(alt_slot, fac_prefs, faculty_weight)
                    alt_penalty = alt_time_pen + alt_fac_pen
                    if alt_penalty > cur_penalty:
                        continue  # never degrade this student's (=> the global) penalty

                    new_gap = gap_count(other_daytimes | set(alt_daytimes))
                    if new_gap < cur_gap:
                        key = (new_gap, alt_penalty)
                        if best is None or key < (best[0], best[1]):
                            best = (new_gap, alt_penalty, alt_sid, alt_slot, alt_time_pen, alt_fac_pen, alt_frating)

                if best:
                    new_gap, alt_penalty, alt_sid, alt_slot, alt_time_pen, alt_fac_pen, alt_frating = best
                    occ[cur_sid] -= 1
                    occ[alt_sid] += 1
                    worst_rating = max((ts_prefs.get(k, 1) for k in slot_time_keys(alt_slot)), default=1)
                    changes.append({
                        "student_id": s, "name": a["name"], "subject_code": code,
                        "from_section": asn["section"], "to_section": alt_slot["section"],
                        "gap_before": cur_gap, "gap_after": new_gap,
                    })
                    asn.update({
                        "section": alt_slot["section"],
                        "faculty": alt_slot["faculty"],
                        "room": alt_slot["room"],
                        "slot_id": alt_sid,
                        "meetings": alt_slot["meetings"],
                        "time_penalty": alt_time_pen,
                        "faculty_rating": alt_frating,
                        "faculty_penalty": alt_fac_pen,
                        "penalty": alt_penalty,
                        "rating": worst_rating,
                    })
                    a["penalty"] += (alt_penalty - cur_penalty)

    total_gaps_after = sum(gap_count(student_daytimes(a)) for a in assignments)
    return {
        "swaps_applied": len(changes),
        "total_gaps_before": total_gaps_before,
        "total_gaps_after": total_gaps_after,
        "changes": changes,
    }

# ── Naive baseline heuristics (for genuine, non-fabricated comparison) ───────

def _build_domain(student_id: int, subj: str) -> List[int]:
    ts_prefs = student_ts_prefs.get(student_id, {})
    return [sid for sid in SUBJECT_SLOTS[subj] if not slot_blocked(SLOT_INSTANCES[sid], ts_prefs)]

def run_baseline(mode: str) -> (Dict[int, Dict[str, int]], List[tuple]):
    """mode='fcfs': registration-order, first-fit-by-id, no preference awareness.
    mode='random': random student order, random subject order, random section
    choice — subject only to the SAME hard constraints (capacity, block,
    no-clash) the CP-SAT model enforces, since an infeasible baseline
    schedule wouldn't be a meaningful comparison."""
    occ = defaultdict(int)
    schedules: Dict[int, Dict[str, int]] = {s: {} for s in range(len(STUDENTS))}
    booked: Dict[int, set] = {s: set() for s in range(len(STUDENTS))}
    unassigned = []

    student_order = list(range(len(STUDENTS)))
    if mode == "random":
        pyrandom.shuffle(student_order)

    for s in student_order:
        subj_order = list(SUBJECT_SLOTS.keys())
        if mode == "random":
            pyrandom.shuffle(subj_order)
        for subj in subj_order:
            candidates = _build_domain(s, subj)
            if mode == "random":
                pyrandom.shuffle(candidates)
            chosen = None
            for sid in candidates:
                slot = SLOT_INSTANCES[sid]
                if occ[sid] >= slot["capacity"]:
                    continue
                meet_dts = [(m["day"], m["time"]) for m in slot["meetings"]]
                if any(dt in booked[s] for dt in meet_dts):
                    continue
                chosen = sid
                break
            if chosen is None:
                unassigned.append((s, subj))
                continue
            occ[chosen] += 1
            schedules[s][subj] = chosen
            for m in SLOT_INSTANCES[chosen]["meetings"]:
                booked[s].add((m["day"], m["time"]))

    return schedules, unassigned

def score_schedule(schedules: Dict[int, Dict[str, int]], faculty_weight: int) -> int:
    total = 0
    for s, subj_map in schedules.items():
        ts_prefs = student_ts_prefs.get(s, {})
        fac_prefs = student_faculty_prefs.get(s, {})
        for subj, sid in subj_map.items():
            slot = SLOT_INSTANCES[sid]
            total += slot_time_penalty(slot, ts_prefs)
            _, fac_pen = slot_faculty_penalty(slot, fac_prefs, faculty_weight)
            total += fac_pen
    return total

# ── Solve ──────────────────────────────────────────────────────────────────────

class SolvePayload(BaseModel):
    fairness_index: int = 12
    faculty_weight: int = 1          # weight of the secondary faculty-mismatch term
    enable_gap_reduction: bool = True

@app.post("/solve")
def solve(payload: SolvePayload):
    global last_result
    model = cp_model.CpModel()
    solver = cp_model.CpSolver()

    n_students = len(STUDENTS)
    n_slots    = len(SLOT_INSTANCES)

    # ── Decision variables ────────────────────────────────────────────────────
    # x[s][subj] = slot_id assigned to student s for subject subj
    x = {}
    for s in range(n_students):
        x[s] = {}
        ts_prefs = student_ts_prefs.get(s, {})
        for subj, slot_ids in SUBJECT_SLOTS.items():
            # Domain pruning: remove sections with ANY meeting the student blocked
            domain = [sid for sid in slot_ids if not slot_blocked(SLOT_INSTANCES[sid], ts_prefs)]
            if not domain:
                return {"status": "INFEASIBLE",
                        "message": f"Student {STUDENTS[s]['name']} has all slots blocked for {subj}"}
            x[s][subj] = model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(domain), f"x_s{s}_{subj}"
            )

    # ── Reified per-(student, slot) assignment booleans ───────────────────────
    # assign[s][slot_id] is TRUE iff x[s][subj_of(slot_id)] == slot_id.
    # Reified in BOTH directions (b ⟺ x==slot_id) so it's a trustworthy
    # indicator reused for capacity, no-clash, and penalty scoring below.
    assign = {}
    for s in range(n_students):
        assign[s] = {}
        for slot_id in range(n_slots):
            subj = SLOT_SUBJECT[slot_id]
            b = model.NewBoolVar(f"assign_s{s}_slot{slot_id}")
            model.Add(x[s][subj] == slot_id).OnlyEnforceIf(b)
            model.Add(x[s][subj] != slot_id).OnlyEnforceIf(b.Not())
            assign[s][slot_id] = b

    # ── Capacity constraints ──────────────────────────────────────────────────
    for slot_id in range(n_slots):
        cap = SLOT_INSTANCES[slot_id]["capacity"]
        model.Add(sum(assign[s][slot_id] for s in range(n_students)) <= cap)

    # ── No-clash constraints ──────────────────────────────────────────────────
    # Build a day-time → [slot_ids] map. A multi-meeting section contributes
    # one entry PER meeting, so it's correctly checked for clashes at every
    # time block it occupies, not just a single nominal slot.
    timeslot_map = defaultdict(list)
    for slot in SLOT_INSTANCES:
        for m in slot["meetings"]:
            timeslot_map[(m["day"], m["time"])].append(slot["id"])

    for (day, time), clash_slots in timeslot_map.items():
        subjects_here = {SLOT_SUBJECT[sid] for sid in clash_slots}
        if len(subjects_here) < 2:
            continue  # only one subject meets at this time — nothing can clash
        for s in range(n_students):
            # A student can hold at most one section — from ANY subject —
            # among all sections that occupy this day-time slot.
            model.Add(sum(assign[s][sid] for sid in clash_slots) <= 1)

    # ── Objective: minimise total weighted penalty ────────────────────────────
    # Primary term: time-slot preference penalty (summed across all meetings
    # of the assigned section). Secondary term: faculty-mismatch penalty,
    # scaled by faculty_weight.
    penalty_vars = []
    for s in range(n_students):
        ts_prefs = student_ts_prefs.get(s, {})
        fac_prefs = student_faculty_prefs.get(s, {})
        student_penalty_terms = []
        for slot_id in range(n_slots):
            slot = SLOT_INSTANCES[slot_id]
            time_pen = slot_time_penalty(slot, ts_prefs)
            _, fac_pen = slot_faculty_penalty(slot, fac_prefs, payload.faculty_weight)
            pen = time_pen + fac_pen
            if pen > 0:
                student_penalty_terms.append(pen * assign[s][slot_id])
        sp = model.NewIntVar(0, 200, f"sp_{s}")
        model.Add(sp == sum(student_penalty_terms))
        # Fairness Index constraint (applies to combined time+faculty penalty)
        model.Add(sp <= payload.fairness_index)
        penalty_vars.append(sp)

    model.Minimize(sum(penalty_vars))

    # ── Solve ─────────────────────────────────────────────────────────────────
    solver.parameters.max_time_in_seconds = 10.0
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {"status": "INFEASIBLE", "message": "No feasible assignment found."}

    # ── Extract result ────────────────────────────────────────────────────────
    assignments = []
    for s in range(n_students):
        ts_prefs = student_ts_prefs.get(s, {})
        fac_prefs = student_faculty_prefs.get(s, {})
        student_assignments = []
        student_penalty = 0
        for subj in SUBJECT_SLOTS:
            sid = solver.Value(x[s][subj])
            slot = SLOT_INSTANCES[sid]
            time_pen = slot_time_penalty(slot, ts_prefs)
            frating, fac_pen = slot_faculty_penalty(slot, fac_prefs, payload.faculty_weight)
            pen = time_pen + fac_pen
            worst_rating = max((ts_prefs.get(k, 1) for k in slot_time_keys(slot)), default=1)
            student_penalty += pen
            student_assignments.append({
                "subject": slot["subject"],
                "code": subj,
                "section": slot["section"],
                "faculty": slot["faculty"],
                "room": slot["room"],
                "slot_id": sid,
                "meetings": slot["meetings"],
                "rating": worst_rating,
                "time_penalty": time_pen,
                "faculty_rating": frating,
                "faculty_penalty": fac_pen,
                "penalty": pen,
            })
        assignments.append({
            "student_id": s,
            "name": STUDENTS[s]["name"],
            "roll": STUDENTS[s]["roll"],
            "penalty": student_penalty,
            "assignments": student_assignments,
        })

    objective_total_penalty = int(solver.ObjectiveValue())

    # ── Post-processing: gap-reduction heuristic ──────────────────────────────
    gap_reduction = None
    if payload.enable_gap_reduction:
        gap_reduction = apply_gap_reduction(assignments, payload.faculty_weight)

    total_penalty = sum(a["penalty"] for a in assignments)

    # ── Baselines: genuine FCFS & Random heuristics (not fabricated) ─────────
    fcfs_schedules, fcfs_unassigned = run_baseline("fcfs")
    random_schedules, random_unassigned = run_baseline("random")
    baselines = {
        "fcfs": {
            "total_penalty": score_schedule(fcfs_schedules, payload.faculty_weight),
            "unassigned_count": len(fcfs_unassigned),
            "feasible": len(fcfs_unassigned) == 0,
        },
        "random": {
            "total_penalty": score_schedule(random_schedules, payload.faculty_weight),
            "unassigned_count": len(random_unassigned),
            "feasible": len(random_unassigned) == 0,
        },
    }

    last_result = {
        "status": "OPTIMAL",
        "total_penalty": total_penalty,
        "objective_total_penalty": objective_total_penalty,
        "assignments": assignments,
        "solver_time_ms": round(solver.WallTime() * 1000, 1),
        "gap_reduction": gap_reduction,
        "baselines": baselines,
    }
    return last_result

@app.get("/results")
def get_results():
    return last_result if last_result else {"status": "NOT_RUN"}
