"""Seed a RUNNING PWSSAP backend over HTTP with the full demo_run dataset.

Unlike run_stress_test.py (which writes into an in-process store), this talks
to the live REST API exactly like the browser does, so the data is visible in
the Admin / Student / Teacher UIs immediately and every server-side validation
(including the Layer-1 dynamic block quota) is exercised.

Seeds:
  1. subjects.csv, teachers.csv, students_template.csv (admin CSV imports)
  2. choice-based tags (MDM, PE) + sem4/sem6 elective allocations (lock-in)
  3. teacher availability (HOD Thu + Tue-4, plus two committee half-days)
  4. 100% student time preferences (archetypes, quota-aware) + faculty rankings

Usage (from repo root, backend venv active; only needs httpx):
    python backend/scripts/seed_via_api.py [--base-url http://127.0.0.1:8000]
                                           [--no-clear] [--seed 1337]

Re-runnable: by default it clears subjects/teachers/students first.
"""

import argparse
import os
import random
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import httpx

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEMO_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "demo_run"))

PREFERRED, TOLERABLE, DISLIKED, BLOCKED = 1, 2, 3, 4

# Teacher admin blocks: HOD (T001) all Thursday + Tue-4; committee half-days.
TEACHER_BLOCKS = {
    "T001": ["Thu-1", "Thu-2", "Thu-3", "Thu-4", "Tue-4"],
    "T002": ["Wed-3", "Wed-4"],
    "T008": ["Fri-3", "Fri-4"],
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def fail(msg: str, resp: httpx.Response | None = None):
    print(f"FATAL: {msg}")
    if resp is not None:
        print(f"  HTTP {resp.status_code}: {resp.text[:800]}")
    sys.exit(1)


def upload(client: httpx.Client, path: str, csv_name: str, extra: dict | None = None):
    with open(os.path.join(DEMO_DIR, csv_name), "rb") as f:
        r = client.post(path, files={"file": (csv_name, f, "text/csv")}, data=extra or {})
    if r.status_code != 200:
        fail(f"upload of {csv_name} to {path} failed", r)
    return r.json()


def build_preferences(rng, idx, slot_keys, max_blocks):
    morning = [k for k in slot_keys if k.endswith(("-1", "-2"))]
    afternoon = [k for k in slot_keys if k.endswith(("-3", "-4"))]
    friday = [k for k in slot_keys if k.startswith("Fri-")]
    ratings: dict[str, int] = {}
    arche = idx % 10
    if arche <= 2:  # night owl
        for k in morning[:2]:
            ratings[k] = DISLIKED
        for k in afternoon[:3]:
            ratings[k] = PREFERRED
        blocked = rng.sample(morning, min(max_blocks, len(morning)))
    elif arche <= 5:  # early bird
        for k in morning[:3]:
            ratings[k] = PREFERRED
        for k in afternoon[-2:]:
            ratings[k] = DISLIKED
        blocked = rng.sample(afternoon, min(max_blocks, len(afternoon)))
    else:  # balanced / friday blocker
        for k in friday[-2:]:
            ratings[k] = DISLIKED
        ratings[rng.choice(morning)] = PREFERRED
        ratings[rng.choice(afternoon)] = TOLERABLE
        blocked = rng.sample(friday, min(max_blocks, len(friday)))
    for k in blocked:
        ratings[k] = BLOCKED
    return ratings


def seed_student(client, student, idx, seed, ratable_keys):
    roll = student["roll_number"]
    rng = random.Random(f"{seed}-{roll}")
    out = {"roll": roll, "time_ok": False, "fac_ok": False, "warnings": 0, "err": None}

    r = client.get(f"/students/{roll}/time-preferences")
    if r.status_code != 200:
        out["err"] = f"GET time-prefs {r.status_code}"
        return out
    max_blocks = r.json()[0]["max_allowed_blocks"]

    ratings = build_preferences(rng, idx, ratable_keys, max_blocks)
    r = client.put(f"/students/{roll}/time-preferences", json={"ratings": ratings})
    if r.status_code != 200:
        out["err"] = f"PUT time-prefs {r.status_code}: {r.text[:200]}"
        return out
    out["time_ok"] = True
    out["warnings"] = len(r.json().get("warnings", []))
    out["blocked"] = sum(1 for v in ratings.values() if v == BLOCKED)
    out["max_blocks"] = max_blocks

    r = client.get(f"/students/{roll}/rankable-subjects")
    prefs: dict[str, dict[str, int]] = {}
    if r.status_code == 200:
        for item in r.json():
            tids = [t["teacher_id"] for t in item["teachers"]]
            if len(tids) < 2:
                continue
            rng.shuffle(tids)
            prefs[item["subject_code"]] = {
                tids[0]: PREFERRED,
                tids[1]: rng.choice([TOLERABLE, DISLIKED]),
            }
    if prefs:
        r = client.put(f"/students/{roll}/faculty-preferences", json={"preferences": prefs})
        if r.status_code != 200:
            out["err"] = f"PUT fac-prefs {r.status_code}: {r.text[:200]}"
            return out
    out["fac_ok"] = True
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--no-clear", action="store_true")
    ap.add_argument("--seed", default="1337")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    client = httpx.Client(base_url=args.base_url, headers={"X-Role": "admin"}, timeout=60)
    t0 = time.monotonic()
    try:
        client.get("/health").raise_for_status()
    except Exception as exc:
        fail(f"backend not reachable at {args.base_url}: {exc}")

    if not args.no_clear:
        print("[0/5] Clearing existing students / teachers / subjects ...")
        for p in ("/admin/students", "/admin/teachers", "/admin/subjects"):
            client.delete(p).raise_for_status()

    print("[1/5] Importing CSVs ...")
    r = upload(client, "/admin/subjects/import", "subjects.csv")
    print("  subjects:", {k: v for k, v in r.items() if k in ("count", "status")})
    r = upload(client, "/admin/teachers/import", "teachers.csv")
    print("  teachers:", {k: v for k, v in r.items() if k in ("count", "capabilities", "status")})
    r = upload(client, "/admin/students/import", "students_template.csv")
    print("  students:", {k: v for k, v in r.items() if k in ("count", "status")})

    print("[2/5] Configuring choice tags + elective lock-ins ...")
    r = client.put("/admin/cycle/choice-tags", json={"MDM": True, "PE": True})
    if r.status_code != 200:
        fail("choice-tags config failed", r)
    for sem in (4, 6):
        r = upload(client, "/admin/cycle/import-elective-allocations", f"sem{sem}_electives.csv", {"semester": str(sem)})
        print(f"  sem {sem} electives: status={r.get('status')} updated={r.get('updated_count')} errors={len(r.get('errors', []))}")

    print("[3/5] Seeding teacher availability ...")
    for tid, slots in TEACHER_BLOCKS.items():
        r = client.put(f"/admin/teachers/{tid}/availability", json={"slots": {s: False for s in slots}})
        if r.status_code != 200:
            fail(f"availability for {tid} failed", r)
    print(f"  blocked slots: {sum(len(v) for v in TEACHER_BLOCKS.values())} across {len(TEACHER_BLOCKS)} teachers")

    print("[4/5] Seeding 100% student preferences (time + faculty) ...")
    students = client.get("/students").json()
    students.sort(key=lambda s: s["roll_number"])
    # Ratable keys come from the per-student GET; fetch once from the first student.
    first = client.get(f"/students/{students[0]['roll_number']}/time-preferences").json()
    ratable_keys = [s["slot_key"] for s in first]

    def work(args_):
        i, s = args_
        with httpx.Client(base_url=client.base_url, headers=client.headers, timeout=60) as c:
            return seed_student(c, s, i, args.seed, ratable_keys)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(work, enumerate(students)))

    ok = [x for x in results if x["time_ok"] and x["fac_ok"]]
    bad = [x for x in results if x["err"]]
    quota = Counter(x.get("max_blocks") for x in results if x["time_ok"])
    print(f"  fully seeded: {len(ok)}/{len(students)}  | with warnings: {sum(1 for x in results if x['warnings'])}")
    print(f"  quota distribution (max_blocks -> students): {dict(quota)}")
    for x in bad[:10]:
        print(f"  ! {x['roll']}: {x['err']}")

    print("[5/5] Verifying ...")
    cyc = client.get("/admin/cycle").json()
    print("  cycle status keys:", list(cyc.keys()))
    print(f"Done in {time.monotonic() - t0:.1f}s. "
          f"Open http://localhost:5173/admin -> Solver.")
    sys.exit(0 if not bad else 2)


if __name__ == "__main__":
    main()
