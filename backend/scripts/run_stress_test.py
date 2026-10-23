"""PWSSAP Department-Wide Full-Saturation Stress Test Script.

Simulates 100% saturation across all ~466 students and 21 faculty members:
1. Loads full official curriculum dataset from demo_run/ (subjects, teachers, students, electives).
2. Seeds real-world teacher availability constraints (including HOD Dr. Vidya Chitre's non-academic Thursday + Tue 4-6).
3. Seeds 100% student preferences for all 466 students:
   - Dynamic time slot quotas (max 2 for Sem 6, 1 for Sem 4)
   - Realistic behavioral archetypes (Night Owls, Early Birds, Balanced)
   - Faculty preference rankings including dislikes
4. Generates sections and solves via solver.service.run_solver_for_run (the exact path the API uses).
5. Emits an executive performance, scalability, and satisfaction benchmark report.

Usage:
    py -3.14 backend/scripts/run_stress_test.py [--candidates 1] [--time-limit 240] [--semesters 4,6]
"""

import argparse
import csv
import io
import os
import random
import sys
import time
from collections import defaultdict
from typing import Dict, List

# Ensure backend root is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, BACKEND_DIR)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from data.store import get_store, reset_store
from domain.enums import PreferenceRating
from domain.models import StudentChoiceSelection
from domain.timeslots import build_canonical_grid, is_slot_usable
from ingestion.students_csv import parse_students_csv
from ingestion.subjects_csv import parse_subjects_csv
from ingestion.teachers_csv import parse_teachers_csv


def load_demo_csv(relative_path: str) -> str:
    full_path = os.path.join(BACKEND_DIR, "..", relative_path)
    if not os.path.exists(full_path):
        # Fallback to local repo root
        full_path = os.path.join(os.getcwd(), relative_path)
    with open(full_path, "r", encoding="utf-8-sig") as f:
        return f.read()


def setup_department_data(store):
    print(" [1/5] Loading official demo CSVs into memory store...")
    
    # 1. Subjects
    subj_csv = load_demo_csv("demo_run/subjects.csv")
    parsed_subj = parse_subjects_csv(subj_csv)
    for s in parsed_subj.subjects:
        store.upsert_subject(s)
    print(f"       -> Loaded {len(parsed_subj.subjects)} subjects across semesters 4 and 6")

    # 2. Teachers
    teacher_csv = load_demo_csv("demo_run/teachers.csv")
    known_codes = {s.subject_code for s in store.list_subjects()}
    parsed_teachers = parse_teachers_csv(teacher_csv, known_codes)
    for t in parsed_teachers.teachers:
        store.upsert_teacher(t)
    for teacher_id, subject_codes in parsed_teachers.capabilities.items():
        subject_loads = {
            code: parsed_teachers.loads.get(teacher_id, {}).get(code)
            for code in subject_codes
        }
        store.replace_teacher_capabilities(teacher_id, subject_loads)
    print(f"       -> Loaded {len(parsed_teachers.teachers)} faculty members with capability matrices")

    # 3. Students
    stu_csv = load_demo_csv("demo_run/students.csv")
    parsed_stu = parse_students_csv(stu_csv)
    for s in parsed_stu.students:
        store.upsert_student(s)
    print(f"       -> Loaded {len(parsed_stu.students)} students ({sum(1 for s in parsed_stu.students if s.semester == 4)} in Sem 4, {sum(1 for s in parsed_stu.students if s.semester == 6)} in Sem 6)")

    # 4. Elective Allocations
    store.set_cycle_choice_configs({"MDM": True, "PE": True})
    for sem in (4, 6):
        elec_csv = load_demo_csv(f"demo_run/sem{sem}_electives.csv")
        reader = csv.DictReader(io.StringIO(elec_csv))
        count = 0
        for row in reader:
            roll = row.get("roll_number", "").strip()
            if not roll:
                continue
            selections = []
            for col, val in row.items():
                if col not in ("roll_number", "student_name", "name") and val:
                    selections.append(StudentChoiceSelection(roll_number=roll, tag=col.strip(), subtag=val.strip()))
            if selections:
                store.set_student_choice_selections(roll, selections)
                count += 1
        print(f"       -> Imported {count} elective choices for Semester {sem}")


def seed_teacher_availability(store):
    print(" [2/5] Seeding realistic faculty availability & administrative blocks...")
    all_slots = [s for s in build_canonical_grid() if is_slot_usable(s)]
    slot_keys = [s.key for s in all_slots]

    # HOD Dr. Vidya Chitre (T001): entire Thursday non-academic + Tuesday 4-6
    hod_blocks = {
        "Thu-1": False,
        "Thu-2": False,
        "Thu-3": False,
        "Thu-4": False,
        "Tue-4": False,
    }
    for sk, avail in hod_blocks.items():
        store.set_teacher_availability("T001", sk, avail)

    # Key senior faculty with typical committee / research half-days:
    # T002 (Dean/Committee): Wed afternoon (Wed-3, Wed-4)
    # T008 (Research/Mentorship): Fri afternoon (Fri-3, Fri-4)
    additional_blocks = {
        "T002": ["Wed-3", "Wed-4"],
        "T008": ["Fri-3", "Fri-4"],
    }
    blocked_count = len(hod_blocks)
    for tid, slots in additional_blocks.items():
        for sk in slots:
            store.set_teacher_availability(tid, sk, False)
            blocked_count += 1

    print(f"       -> Configured Dr. Vidya Chitre (HOD): Thursday full day + Tue 4-6 blocked")
    print(f"       -> Configured Senior Faculty (T002, T008) administrative & committee blocks ({blocked_count} total blocked faculty slots)")


def seed_student_preferences(store):
    print(" [3/5] Simulating 100% student preferences for all 466 students...")
    all_slots = [s for s in build_canonical_grid() if is_slot_usable(s)]
    slot_keys = [s.key for s in all_slots]
    ratable_keys = slot_keys
    morning_slots = [k for k in slot_keys if k.endswith("-1") or k.endswith("-2")]
    afternoon_slots = [k for k in slot_keys if k.endswith("-3") or k.endswith("-4")]
    friday_slots = [k for k in slot_keys if k.startswith("Fri-")]

    rng = random.Random(1337)
    students = store.list_students()
    
    total_blocked = 0
    total_disliked = 0
    total_preferred = 0

    for i, s in enumerate(students):
        roll = s.roll_number
        sem = s.semester
        
        # Max blocks dynamically based on course load:
        # Sem 6 has ~10 subjects -> (19 - 10)//4 = 2 max blocks
        # Sem 4 has ~14 subjects -> (19 - 14)//4 = 1 max block
        max_blocks = 2 if sem == 6 else 1

        # Partition slots by attributes:
        slot_1 = [k for k in ratable_keys if k.endswith("-1")]
        slot_2 = [k for k in ratable_keys if k.endswith("-2")]
        slot_3 = [k for k in ratable_keys if k.endswith("-3")]
        slot_4 = [k for k in ratable_keys if k.endswith("-4")]
        friday = [k for k in ratable_keys if k.startswith("Fri-")]
        monday = [k for k in ratable_keys if k.startswith("Mon-")]

        ratings: Dict[str, int] = {}
        blocked_chosen: List[str] = []
        arche = i % 4

        if arche == 0:  # Night Owl (hates 9 AM, loves mid-day & afternoon)
            blocked_pool = slot_1 + monday
            blocked_chosen = rng.sample(blocked_pool, min(max_blocks, len(blocked_pool)))
            for k in slot_1:
                if k not in blocked_chosen:
                    ratings[k] = PreferenceRating.DISLIKED.value
            for k in friday[-1:]:
                ratings[k] = PreferenceRating.DISLIKED.value
            mid_day = slot_2 + slot_3
            for k in rng.sample(mid_day, min(6, len(mid_day))):
                ratings[k] = PreferenceRating.PREFERRED.value
            for k in ratable_keys:
                if k not in ratings and k not in blocked_chosen:
                    ratings[k] = PreferenceRating.TOLERABLE.value if rng.random() < 0.75 else PreferenceRating.DISLIKED.value

        elif arche == 1:  # Early Bird (loves morning & mid-day, hates late afternoon)
            blocked_pool = slot_4 + slot_3
            blocked_chosen = rng.sample(blocked_pool, min(max_blocks, len(blocked_pool)))
            for k in slot_4:
                if k not in blocked_chosen:
                    ratings[k] = PreferenceRating.DISLIKED.value
            for k in slot_3[-2:]:
                if k not in blocked_chosen:
                    ratings[k] = PreferenceRating.DISLIKED.value
            mornings = slot_1 + slot_2
            for k in rng.sample(mornings, min(6, len(mornings))):
                ratings[k] = PreferenceRating.PREFERRED.value
            for k in ratable_keys:
                if k not in ratings and k not in blocked_chosen:
                    ratings[k] = PreferenceRating.TOLERABLE.value if rng.random() < 0.70 else PreferenceRating.DISLIKED.value

        elif arche == 2:  # Long Weekend Seeker (protects Friday & Monday)
            blocked_pool = friday + monday[:1]
            blocked_chosen = rng.sample(blocked_pool, min(max_blocks, len(blocked_pool)))
            for k in friday:
                if k not in blocked_chosen:
                    ratings[k] = PreferenceRating.DISLIKED.value
            for k in monday[:1]:
                if k not in blocked_chosen:
                    ratings[k] = PreferenceRating.DISLIKED.value
            core_mid = [k for k in (slot_2 + slot_3) if not k.startswith("Fri-")]
            for k in rng.sample(core_mid, min(6, len(core_mid))):
                ratings[k] = PreferenceRating.PREFERRED.value
            for k in ratable_keys:
                if k not in ratings and k not in blocked_chosen:
                    ratings[k] = PreferenceRating.TOLERABLE.value if rng.random() < 0.65 else PreferenceRating.DISLIKED.value

        else:  # Mid-Day / Anti-Extreme (hates 9 AM and late 15:45, loves 11:15 & 13:45)
            extremes = slot_1 + slot_4
            blocked_chosen = rng.sample(extremes, min(max_blocks, len(extremes)))
            for k in extremes:
                if k not in blocked_chosen:
                    ratings[k] = PreferenceRating.DISLIKED.value
            for k in slot_2:
                ratings[k] = PreferenceRating.PREFERRED.value
            for k in slot_3[:2]:
                ratings[k] = PreferenceRating.PREFERRED.value
            for k in ratable_keys:
                if k not in ratings and k not in blocked_chosen:
                    ratings[k] = PreferenceRating.TOLERABLE.value

        # Apply block tokens
        for b_slot in blocked_chosen:
            ratings[b_slot] = PreferenceRating.BLOCKED.value

        store.set_time_preferences(roll, ratings)

        # Count stats
        total_blocked += sum(1 for v in ratings.values() if v == PreferenceRating.BLOCKED.value)
        total_disliked += sum(1 for v in ratings.values() if v == PreferenceRating.DISLIKED.value)
        total_preferred += sum(1 for v in ratings.values() if v == PreferenceRating.PREFERRED.value)

        # Faculty preferences
        # For each capable subject, randomly rank teachers with some dislikes
        enrolled_subs = store.get_enrolled_subjects_for_student(roll)
        fac_prefs: Dict[str, Dict[str, int]] = {}
        for sub in enrolled_subs:
            capable_tids = store.teachers_for_subject(sub.subject_code)
            if len(capable_tids) >= 2:
                shuffled = list(capable_tids)
                rng.shuffle(shuffled)
                t_ratings = {shuffled[0]: PreferenceRating.PREFERRED.value}
                for other_tid in shuffled[1:]:
                    t_ratings[other_tid] = PreferenceRating.DISLIKED.value if rng.random() < 0.75 else PreferenceRating.TOLERABLE.value
                fac_prefs[sub.subject_code] = t_ratings
        if fac_prefs:
            store.set_faculty_preferences(roll, fac_prefs)

    print(f"       -> Seeded 100% time & faculty preferences for {len(students)} students")
    print(f"       -> Ratings distribution: {total_preferred} Preferred, {total_disliked} Disliked, {total_blocked} Blocked tokens used")


def generate_sections_and_run(store, semesters: List[int]) -> int:
    """Create a run and generate sections exactly as POST /admin/runs/{id}/generate-sections does."""
    print(f" [4/5] Generating parallel sections for Semesters {semesters}...")
    from api.sections import generate_sections

    run = store.create_run(semesters=semesters)
    gen = generate_sections(run.id, store)
    print(f"       -> Created {gen['generated_count']} parallel sections (theory & lab)")
    return run.id


def execute_stress_benchmark(store, run_id: int, candidate_count: int, time_limit: float):
    """Solve through solver.service.run_solver_for_run - the SAME code path as
    POST /admin/runs/{id}/solve - so results match what the app produces."""
    from solver.service import run_solver_for_run

    print(f"\n [5/5] Launching CP-SAT Engine: {candidate_count} candidate(s), {time_limit:.0f}s TOTAL budget...")
    print("=" * 80)

    t_start = time.monotonic()
    result = run_solver_for_run(
        run_id=run_id,
        store=store,
        time_limit_seconds=time_limit,
        candidate_count=candidate_count,
    )
    total_elapsed = time.monotonic() - t_start

    print("=" * 80)
    print("                       PWSSAP STRESS TEST BENCHMARK RESULTS")
    print("=" * 80)

    print(f"\n▶ OVERALL STATUS:               {result.status}")
    print(f"▶ STAGE 1 (master timetable):   {result.stage1_status or 'n/a'}")
    print(f"▶ STAGE 2 (student sectioning): {result.stage2_status or 'n/a'}")
    print(f"▶ TOTAL SOLVE TIME:             {total_elapsed:.2f} seconds")
    print(f"▶ PENALTY (lower is better):    {result.objective_value}")
    print(f"▶ SEARCH CONFLICTS EXPLORED:    {result.num_conflicts:,}")

    if result.candidates:
        print("\n▶ CANDIDATE PORTFOLIO BREAKDOWN:")
        print(f"  {'Candidate':<12} {'Status':<10} {'Penalty':<10} {'Blocked':<9} {'Proven':<8} {'Wall (s)':<10} Best")
        print("  " + "-" * 66)
        for c in result.candidates:
            print(
                f"  #{c.get('candidate_id', 1):<11} {str(c.get('status', '')):<10} "
                f"{str(c.get('objective_value', '')):<10} {str(c.get('blocked_placements', '')):<9} "
                f"{str(c.get('blocked_minimum_proven', '')):<8} {c.get('wall_time_seconds', 0.0):<10.2f} "
                f"{'★ BEST' if c.get('is_best') else ''}"
            )

    ok = result.status in ("OPTIMAL", "FEASIBLE")
    if ok and result.student_section_assignments:
        sec_meetings = result.section_meetings
        ratings = defaultdict(int)
        for roll, subs in result.student_section_assignments.items():
            t_pref = store.get_time_preferences(roll)
            for sub_code, sid in subs.items():
                for m in sec_meetings.get(sid, []):
                    ratings[t_pref.get(m.slot_key, 0)] += 1
        tot = sum(ratings.values()) or 1
        blocked = ratings[PreferenceRating.BLOCKED.value]
        print("\n▶ STUDENT TIME-SLOT SATISFACTION METRICS:")
        print(f"  • Students Evaluated:           {len(result.student_section_assignments)}")
        print(f"  • Total Meeting Allocations:    {tot:,}")
        print(f"  • Unrated / Preferred:          {ratings[0] + ratings[1]:,} ({(ratings[0] + ratings[1]) / tot * 100:.1f}%)")
        print(f"  • Tolerable:                    {ratings[2]:,} ({ratings[2] / tot * 100:.1f}%)")
        print(f"  • Disliked:                     {ratings[3]:,} ({ratings[3] / tot * 100:.1f}%)")
        print(f"  • Blocked placements:           {blocked} ({blocked / tot * 100:.2f}%)"
              f"  [minimum proven: {result.blocked_minimum_proven}]")

    if result.warnings:
        print("\n▶ SOLVER WARNINGS & DIAGNOSTICS:")
        for w in result.warnings:
            print(f"  ⚠ {w}")

    print("\n" + "=" * 80)
    print("  ✅ Timetable produced." if ok else "  ❌ BENCHMARK FAILED: no feasible schedule produced.")
    print("=" * 80 + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description="PWSSAP Department Stress Test")
    parser.add_argument("--candidates", type=int, default=1, help="Number of multi-start candidates (default: 1)")
    parser.add_argument("--time-limit", type=float, default=240.0,
                        help="TOTAL time budget in seconds, shared by all candidates (default: 240)")
    parser.add_argument("--semesters", type=str, default="4,6", help="Comma-separated semesters (default: 4,6)")
    args = parser.parse_args()

    sems = [int(s.strip()) for s in args.semesters.split(",")]

    reset_store()
    store = get_store()

    setup_department_data(store)
    seed_teacher_availability(store)
    seed_student_preferences(store)
    run_id = generate_sections_and_run(store, semesters=sems)
    execute_stress_benchmark(store, run_id, candidate_count=args.candidates, time_limit=args.time_limit)


if __name__ == "__main__":
    main()
