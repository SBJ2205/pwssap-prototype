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

SLOT_INSTANCES = [
    {"id": 0, "subject": "Data Structures", "code": "IT301", "section": "A", "faculty": "Dr. Sharma",  "day": "Mon", "time": "9:00",  "room": "L101", "capacity": 3},
    {"id": 1, "subject": "Data Structures", "code": "IT301", "section": "B", "faculty": "Prof. Mehta", "day": "Tue", "time": "11:00", "room": "L102", "capacity": 3},
    {"id": 2, "subject": "Data Structures", "code": "IT301", "section": "C", "faculty": "Dr. Sharma",  "day": "Wed", "time": "14:00", "room": "L103", "capacity": 3},
    {"id": 3, "subject": "OS Concepts",     "code": "IT302", "section": "A", "faculty": "Prof. Joshi", "day": "Mon", "time": "11:00", "room": "L201", "capacity": 3},
    {"id": 4, "subject": "OS Concepts",     "code": "IT302", "section": "B", "faculty": "Dr. Nair",   "day": "Thu", "time": "9:00",  "room": "L202", "capacity": 3},
    {"id": 5, "subject": "OS Concepts",     "code": "IT302", "section": "C", "faculty": "Prof. Joshi", "day": "Fri", "time": "10:00", "room": "L203", "capacity": 3},
    {"id": 6, "subject": "DBMS",            "code": "IT303", "section": "A", "faculty": "Dr. Verma",   "day": "Tue", "time": "9:00",  "room": "L301", "capacity": 3},
    {"id": 7, "subject": "DBMS",            "code": "IT303", "section": "B", "faculty": "Prof. Kulkarni","day": "Wed","time": "11:00", "room": "L302", "capacity": 3},
    {"id": 8, "subject": "CN Lab",          "code": "IT304", "section": "A", "faculty": "Prof. Rao",   "day": "Thu", "time": "14:00", "room": "Lab1", "capacity": 3},
    {"id": 9, "subject": "CN Lab",          "code": "IT304", "section": "B", "faculty": "Prof. Rao",   "day": "Fri", "time": "14:00", "room": "Lab1", "capacity": 3},
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

# ── Abstract time-slot grid: 6 days × 4 periods ───────────────────────────────
# These are the canonical periods students rate — they do NOT know what subject
# falls there. The solver maps each SLOT_INSTANCE's (day, time) to this grid.

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

def slot_time_key(slot: dict) -> str:
    """Return the canonical time-slot key for a slot instance."""
    t = TIME_REMAP.get(slot["time"], slot["time"])
    return DAY_TIME_TO_KEY.get((slot["day"], t), f"{slot['day']}|{t}")

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

# In-memory store for time-slot preferences
# student_id -> {"Day|Time" -> rating}
student_ts_prefs: Dict[int, Dict[str, int]] = {k: dict(v) for k, v in DEFAULT_TS_PREFS.items()}
last_result = {}

# ── Penalty mapping ───────────────────────────────────────────────────────────

PENALTY = {1: 0, 2: 1, 3: 3}   # rating 4 → domain pruned, never assigned

# ── Routes ────────────────────────────────────────────────────────────────────

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

@app.get("/prefs/{student_id}")
def get_prefs(student_id: int):
    """Return the student's time-slot preferences as {day|time: rating}."""
    return student_ts_prefs.get(student_id, {})

class PrefsPayload(BaseModel):
    prefs: Dict[str, int]   # "Day|Time" → rating

@app.post("/prefs/{student_id}")
def save_prefs(student_id: int, payload: PrefsPayload):
    student_ts_prefs[student_id] = payload.prefs
    # Quick feasibility check: for each subject, at least one slot instance
    # must map to a time key the student hasn't blocked.
    ts_prefs = payload.prefs
    warnings = []
    for subj, slot_ids in SUBJECT_SLOTS.items():
        available = [
            sid for sid in slot_ids
            if ts_prefs.get(slot_time_key(SLOT_INSTANCES[sid]), 1) != 4
        ]
        if len(available) == 0:
            warnings.append(f"All slots for {subj} are blocked — assignment will be INFEASIBLE.")
    return {"status": "saved", "warnings": warnings}

class SolvePayload(BaseModel):
    fairness_index: int = 12

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
            # Domain pruning: remove slots whose time-key is blocked (rating 4)
            domain = [
                sid for sid in slot_ids
                if ts_prefs.get(slot_time_key(SLOT_INSTANCES[sid]), 1) != 4
            ]
            if not domain:
                return {"status": "INFEASIBLE",
                        "message": f"Student {STUDENTS[s]['name']} has all slots blocked for {subj}"}
            x[s][subj] = model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(domain), f"x_s{s}_{subj}"
            )

    # ── Capacity constraints ──────────────────────────────────────────────────
    for slot_id in range(n_slots):
        slot_info = SLOT_INSTANCES[slot_id]
        subj = slot_info["code"]
        cap  = slot_info["capacity"]
        count_vars = []
        for s in range(n_students):
            b = model.NewBoolVar(f"b_s{s}_slot{slot_id}")
            model.Add(x[s][subj] == slot_id).OnlyEnforceIf(b)
            model.Add(x[s][subj] != slot_id).OnlyEnforceIf(b.Not())
            count_vars.append(b)
        model.Add(sum(count_vars) <= cap)

    # ── No-clash constraints ──────────────────────────────────────────────────
    # Build a day-time → [slot_ids] map
    from collections import defaultdict
    timeslot_map = defaultdict(list)
    for slot in SLOT_INSTANCES:
        timeslot_map[(slot["day"], slot["time"])].append(slot["id"])

    for s in range(n_students):
        for (day, time), clash_slots in timeslot_map.items():
            # Find which subjects have slots at this day-time
            involved = []
            for subj, slot_ids in SUBJECT_SLOTS.items():
                overlapping = [sid for sid in slot_ids if sid in clash_slots]
                if overlapping:
                    involved.append((subj, overlapping))
            if len(involved) >= 2:
                for i in range(len(involved)):
                    for j in range(i+1, len(involved)):
                        subj_i, sids_i = involved[i]
                        subj_j, sids_j = involved[j]
                        b_i = model.NewBoolVar(f"clash_s{s}_{i}_{j}_i")
                        b_j = model.NewBoolVar(f"clash_s{s}_{i}_{j}_j")
                        model.AddLinearExpressionInDomain(x[s][subj_i], cp_model.Domain.FromValues(sids_i)).OnlyEnforceIf(b_i)
                        model.AddLinearExpressionInDomain(x[s][subj_j], cp_model.Domain.FromValues(sids_j)).OnlyEnforceIf(b_j)
                        model.AddBoolOr([b_i.Not(), b_j.Not()])

    # ── Objective: minimise total weighted penalty ────────────────────────────
    penalty_vars = []
    for s in range(n_students):
        ts_prefs = student_ts_prefs.get(s, {})
        student_penalty_terms = []
        for subj, slot_ids in SUBJECT_SLOTS.items():
            domain = [
                sid for sid in slot_ids
                if ts_prefs.get(slot_time_key(SLOT_INSTANCES[sid]), 1) != 4
            ]
            for sid in domain:
                ts_key = slot_time_key(SLOT_INSTANCES[sid])
                rating = ts_prefs.get(ts_key, 1)
                pen    = PENALTY.get(rating, 0)
                if pen > 0:
                    b = model.NewBoolVar(f"pen_s{s}_{subj}_slot{sid}")
                    model.Add(x[s][subj] == sid).OnlyEnforceIf(b)
                    model.Add(x[s][subj] != sid).OnlyEnforceIf(b.Not())
                    student_penalty_terms.append(pen * b)
        if student_penalty_terms:
            sp = model.NewIntVar(0, 100, f"sp_{s}")
            model.Add(sp == sum(student_penalty_terms))
            # Fairness Index constraint
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
    total_penalty = 0
    for s in range(n_students):
        ts_prefs = student_ts_prefs.get(s, {})
        student_assignments = []
        student_penalty = 0
        for subj in SUBJECT_SLOTS:
            sid = solver.Value(x[s][subj])
            slot = SLOT_INSTANCES[sid]
            ts_key = slot_time_key(slot)
            rating = ts_prefs.get(ts_key, 1)
            pen = PENALTY.get(rating, 0)
            student_penalty += pen
            student_assignments.append({
                "subject": slot["subject"],
                "code": subj,
                "section": slot["section"],
                "faculty": slot["faculty"],
                "day": slot["day"],
                "time": slot["time"],
                "room": slot["room"],
                "slot_id": sid,
                "ts_key": ts_key,
                "rating": rating,
                "penalty": pen,
            })
        total_penalty += student_penalty
        assignments.append({
            "student_id": s,
            "name": STUDENTS[s]["name"],
            "roll": STUDENTS[s]["roll"],
            "penalty": student_penalty,
            "assignments": student_assignments,
        })

    last_result = {
        "status": "OPTIMAL",
        "total_penalty": int(solver.ObjectiveValue()),
        "assignments": assignments,
        "solver_time_ms": round(solver.WallTime() * 1000, 1),
    }
    return last_result

@app.get("/results")
def get_results():
    return last_result if last_result else {"status": "NOT_RUN"}