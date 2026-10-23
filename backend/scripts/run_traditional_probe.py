"""Replay the Traditional (division/batch) flow on the real demo_run data.

Same code path as the app: suggested divisions -> save -> generate sections in a
run -> solver.service.run_solver_for_run (what POST /admin/runs/{id}/solve calls)
-> traditional validation report.

Usage (from backend/, venv active):
    python scripts/run_traditional_probe.py [--semesters 4,6] [--time-limit 120]
                                            [--max-division-size 60] [--no-prefs]
"""
import argparse
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, SCRIPT_DIR)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import run_stress_test as rst
from data.store import get_store, reset_store
from domain.cohorts import build_config, suggest_classes
from domain.traditional_section_generation import generate_traditional_sections
from domain.traditional_plan import get_live_plan
from domain.traditional_validation import validate_traditional_run
from solver.service import run_solver_for_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Traditional mode probe on demo_run")
    parser.add_argument("--semesters", default="4,6")
    parser.add_argument("--time-limit", type=float, default=120.0)
    parser.add_argument("--max-division-size", type=int, default=None)
    parser.add_argument("--no-prefs", action="store_true", help="skip seeding student time preferences")
    args = parser.parse_args()
    semesters = [int(s) for s in args.semesters.split(",")]

    reset_store()
    store = get_store()
    rst.setup_department_data(store)
    rst.seed_teacher_availability(store)
    if not args.no_prefs:
        rst.seed_student_preferences(store)

    for sem in semesters:
        classes = suggest_classes(store, sem, args.max_division_size)
        config, warnings = build_config(store, sem, classes)
        store.cohort_configs[sem] = config
        print(f"Semester {sem}: " + ", ".join(
            f"{c.class_id}[{c.track or '-'}]={len(c.student_rolls)}st/{len(c.batches)}b" for c in config.classes
        ))
        for w in warnings:
            print("   warning:", w)

    run = store.create_run(semesters=semesters)
    gen = generate_traditional_sections(store, run.id)
    print(f"Generated {gen['generated_count']} sections, {gen['students_pinned']} students pinned, "
          f"{gen['synchronised_groups']} sync group(s)")
    for w in gen["warnings"][:10]:
        print("   warning:", w)

    t0 = time.monotonic()
    result = run_solver_for_run(run.id, store, time_limit_seconds=args.time_limit)
    print(f"Solve: status={result.status} stage1={result.stage1_status} stage2={result.stage2_status} "
          f"wall={time.monotonic() - t0:.1f}s run_status={run.status.value}")
    for w in result.warnings[:8]:
        print("   ", w)

    plan = get_live_plan(store, run.id)
    report = validate_traditional_run(store, run, plan)
    print(f"Validation: ok={report['ok']} violations={report['violation_count']} {report['counts']}")
    for v in report["violations"][:15]:
        print("   ", v["kind"], "-", v["message"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
