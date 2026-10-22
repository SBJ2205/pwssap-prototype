"""Replay the Admin UI network flow against a running, already-seeded backend
and measure what the browser would experience.

Steps (mirrors AdminSolver.jsx / AdminTimetable.jsx / viewers):
  1. POST /admin/cycle/initialize, POST /admin/runs/{id}/generate-sections
  2. POST /admin/runs/{id}/solve?time_limit=..&candidates=..  (blocking, as in UI)
     - while it runs, hammer light GET endpoints to measure API responsiveness
  3. GET /admin/runs/{id}/summary (payload size / latency)
  4. GET all teacher timetables -> overlap detection per teacher
  5. GET all student timetables -> latency percentiles, per-student clash
     detection, blocked-slot violations vs. saved time preferences
  6. Print solver warnings exactly as the UI receives them.

Usage:
    python backend/scripts/ui_flow_probe.py [--candidates 3] [--time-limit 60]
"""
import argparse
import json
import os
import statistics
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def mk(base, timeout=600):
    api_client = httpx.Client(base_url=base, timeout=timeout)
    login = api_client.post(
        "/auth/login",
        json={
            "role": "admin",
            "identity": "admin",
            "password": os.environ.get(
                "ADMIN_PASSWORD", os.environ.get("ADMIN_DEFAULT_PASSWORD", "admin")
            ),
        },
    )
    login.raise_for_status()
    api_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    return api_client


def pct(vals, p):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(len(vals) * p))]


def hhmm(t):
    h, m = t.split(":")[:2]
    return int(h) * 60 + int(m)


def overlaps(meetings):
    """meetings: list of (day, start, end, label). Return overlapping pairs."""
    by_day = defaultdict(list)
    for d, s, e, lbl in meetings:
        by_day[d].append((hhmm(s), hhmm(e), lbl))
    bad = []
    for d, items in by_day.items():
        items.sort()
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if items[j][0] < items[i][1]:
                    bad.append((d, items[i][2], items[j][2]))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--candidates", type=int, default=1)
    ap.add_argument("--time-limit", type=float, default=180, help="TOTAL budget shared by all candidates")
    args = ap.parse_args()
    c = mk(args.base_url)

    print("== 1. Cycle init + section generation")
    t = time.monotonic()
    init = c.post("/admin/cycle/initialize").json()
    run_id = init["run_id"]
    gen = c.post(f"/admin/runs/{run_id}/generate-sections").json()
    print(f"  run_id={run_id} sections={gen['generated_count']} warnings={len(gen.get('warnings', []))} "
          f"({time.monotonic() - t:.2f}s)")
    for w in gen.get("warnings", [])[:5]:
        print("   gen-warning:", w)

    print(f"== 2. Solve (candidates={args.candidates}, time_limit={args.time_limit}s) with concurrent API pings")
    ping_lat, ping_err = [], 0
    stop = threading.Event()

    def pinger():
        nonlocal ping_err
        pc = mk(args.base_url, 30)
        while not stop.is_set():
            s = time.monotonic()
            try:
                pc.get("/health").raise_for_status()
                pc.get(f"/admin/runs/{run_id}").raise_for_status()
                ping_lat.append(time.monotonic() - s)
            except Exception:
                ping_err += 1
            time.sleep(1)

    guard = {"status": "not tested"}

    def guard_check():
        time.sleep(5)  # let the solve start
        gc = mk(args.base_url, 30)
        st = gc.get("/admin/runs/solve/status").json()
        r2 = gc.post(f"/admin/runs/{run_id}/solve", params={"time_limit": 5})
        guard["status"] = f"status endpoint active={st.get('active')}; 2nd solve -> HTTP {r2.status_code}"

    th = threading.Thread(target=pinger, daemon=True)
    th.start()
    threading.Thread(target=guard_check, daemon=True).start()
    t = time.monotonic()
    r = c.post(f"/admin/runs/{run_id}/solve",
               params={"time_limit": args.time_limit, "candidates": args.candidates})
    solve_wall = time.monotonic() - t
    stop.set()
    th.join(timeout=5)
    if r.status_code != 200:
        print("  SOLVE FAILED", r.status_code, r.text[:500])
        sys.exit(1)
    res = r.json()
    print(f"  status={res['status']} run_status={res['run_status']} objective={res['objective_value']} "
          f"solver_wall={res['wall_time_seconds']}s http_wall={solve_wall:.1f}s "
          f"(configured limit {args.time_limit}s x {args.candidates} candidates)")
    print(f"  stage1={res.get('stage1_status')} stage2={res.get('stage2_status')} "
          f"blocked_placements={res.get('blocked_placements')} (proven min: {res.get('blocked_minimum_proven')})")
    print(f"  response payload: {len(r.content) / 1024:.0f} KB")
    for cand in res.get("candidates", []):
        print("   candidate:", {k: cand.get(k) for k in
              ("candidate_id", "status", "objective_value", "blocked_placements", "wall_time_seconds", "is_best")})

    # While a solve is running, a second one must be refused (409) - checked in the pinger below.
    print(f"  concurrent-solve guard: {guard['status']}")
    if ping_lat:
        print(f"  API responsiveness during solve: {len(ping_lat)} pings, "
              f"median={statistics.median(ping_lat)*1000:.0f}ms max={max(ping_lat)*1000:.0f}ms, errors={ping_err}")

    print("== 3. Admin summary (Timetable/Sections inspector payload)")
    t = time.monotonic()
    sm = c.get(f"/admin/runs/{run_id}/summary")
    print(f"  {sm.status_code} {len(sm.content) / 1024:.0f} KB in {time.monotonic() - t:.2f}s, "
          f"sections={sm.json().get('section_count')}")

    print("== 4. Teacher timetables")
    teachers = c.get("/teachers").json()
    tt_lat, t_over, empty = [], 0, []
    sec_meetings = {}
    for te in teachers:
        s = time.monotonic()
        d = c.get(f"/teachers/{te['teacher_id']}/timetable", params={"run_id": run_id}).json()
        tt_lat.append(time.monotonic() - s)
        ms = []
        for sec in d["schedule"]:
            for m in sec["meetings"]:
                if m["day"]:
                    ms.append((m["day"], m["start_time"], m["end_time"], sec["section_label"]))
        bad = overlaps(ms)
        if bad:
            t_over += 1
            print(f"  OVERLAP {te['teacher_id']}: {bad[:3]}")
        if d["section_count"] == 0:
            empty.append(te["teacher_id"])
    print(f"  {len(teachers)} teachers; latency median={statistics.median(tt_lat)*1000:.0f}ms "
          f"max={max(tt_lat)*1000:.0f}ms; teachers with overlaps={t_over}; with 0 sections={empty}")

    print("== 5. Student timetables (all students)")
    students = c.get("/students").json()

    def fetch(stu):
        with mk(args.base_url, 60) as sc:
            s = time.monotonic()
            d = sc.get(f"/students/{stu['roll_number']}/sections").json()
            lat = time.monotonic() - s
            prefs = {p["slot_key"]: p["rating"] for p in
                     sc.get(f"/students/{stu['roll_number']}/time-preferences").json()}
            return stu, d, lat, prefs

    # sequential latency (what a single user feels) on a sample, then full sweep in parallel
    seq = []
    for stu in students[:50]:
        s = time.monotonic()
        c.get(f"/students/{stu['roll_number']}/sections")
        seq.append(time.monotonic() - s)
    print(f"  single-user latency (50 sequential): median={statistics.median(seq)*1000:.0f}ms "
          f"p95={pct(seq, .95)*1000:.0f}ms")

    with ThreadPoolExecutor(8) as pool:
        out = list(pool.map(fetch, students))
    clashes = unassigned = blocked_hits = total_meets = 0
    clash_examples, blocked_examples = [], []
    for stu, d, lat, prefs in out:
        ms, subj_n = [], len(d["timetable"])
        if subj_n == 0:
            unassigned += 1
        for e in d["timetable"]:
            for m in e["meetings"]:
                if m["day"]:
                    ms.append((m["day"], m["start_time"], m["end_time"], e["subject_code"]))
                    total_meets += 1
                    if prefs.get(m["slot_key"]) == 4:
                        blocked_hits += 1
                        if len(blocked_examples) < 5:
                            blocked_examples.append((stu["roll_number"], e["subject_code"], m["slot_key"]))
        bad = overlaps(ms)
        if bad:
            clashes += 1
            if len(clash_examples) < 5:
                clash_examples.append((stu["roll_number"], bad[:2]))
    print(f"  students={len(students)} with-empty-timetable={unassigned} students-with-clashes={clashes} "
          f"blocked-slot meetings={blocked_hits}/{total_meets}")
    for e in clash_examples:
        print("   clash:", e)
    for e in blocked_examples:
        print("   blocked-hit:", e)

    print("== 6. Solver warnings as received by UI")
    warns = res.get("warnings", [])
    print(f"  {len(warns)} warning(s); types of value: {sorted({type(w).__name__ for w in warns})}")
    for w in warns:
        print("   -", w if isinstance(w, str) else json.dumps(w)[:400])


if __name__ == "__main__":
    main()
