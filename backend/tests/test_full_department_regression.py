"""Full-department regression (466 students, 217 sections) through the SAME
code path the API uses (generate_sections -> run_solver_for_run).

This is the test that the small-instance suite could not replace: both the
"INFEASIBLE once a cohort blocks every slot" bug and the "OPTIMAL with
penalty 0" bug only appeared at this scale.

Slow (~2-3 minutes), so it is opt-in:

    set RUN_SLOW=1
    venv\\Scripts\\python.exe -m pytest tests/test_full_department_regression.py -q -s

Tunables: SLOW_TIME_LIMIT (default 120 seconds total).
"""
import os
import sys

sys.path.insert(0, ".")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SLOW") != "1",
    reason="slow full-department solve; set RUN_SLOW=1 to run",
)

BLOCKED_POINTS = 5 * 400


def test_full_department_solves_honestly():
    import run_stress_test as rst
    from data.store import get_store, reset_store
    from domain.enums import PreferenceRating
    from solver.service import run_solver_for_run

    reset_store()
    store = get_store()
    rst.setup_department_data(store)
    rst.seed_teacher_availability(store)
    rst.seed_student_preferences(store)
    run_id = rst.generate_sections_and_run(store, semesters=[4, 6])

    result = run_solver_for_run(
        run_id=run_id,
        store=store,
        time_limit_seconds=float(os.environ.get("SLOW_TIME_LIMIT", "120")),
        candidate_count=1,
    )

    # 1. A timetable must be produced (regression: Stage 1 INFEASIBLE).
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.warnings
    assert result.stage1_status and result.stage2_status

    # 2. Everyone with courses got sections, with no student clashes.
    assert len(result.student_section_assignments) == 466
    for roll, subs in result.student_section_assignments.items():
        seen = set()
        for sid in subs.values():
            for m in result.section_meetings[sid]:
                key = (m.slot_key, m.slot_part or 0)
                assert key not in seen or m.duration_hours == 1 and key[1] == 0, (roll, key)
                seen.add(key)

    # 3. The reported blocked count matches an independent recount.
    blocked = sum(
        1
        for roll, subs in result.student_section_assignments.items()
        for sid in subs.values()
        for m in result.section_meetings[sid]
        if store.get_time_preferences(roll).get(m.slot_key) == PreferenceRating.BLOCKED.value
    )
    assert result.blocked_placements == blocked

    # 4. Honest objective (regression: OPTIMAL / penalty 0 with violations).
    if blocked:
        assert result.objective_value >= blocked * BLOCKED_POINTS
    # 5. Blocked slots are actually minimised (was ~250-300 before Pass A/B).
    assert blocked < 80, f"{blocked} blocked placements; warnings={result.warnings}"
    # 6. Teacher hard constraints (admin blocks) are never violated.
    for sec in store.list_sections_for_run(run_id):
        avail = store.get_teacher_availability(sec.teacher_id)
        for m in sec.meetings:
            assert avail.get(m.slot_key, True), (sec.label, sec.teacher_id, m.slot_key)
