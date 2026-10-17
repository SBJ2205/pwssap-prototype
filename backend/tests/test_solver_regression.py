"""Regression tests for solver honesty and blocked-slot handling.

Each test pins a failure that actually happened on the full department
dataset but was invisible to the earlier small-instance tests:

  * A hard per-student block on single-section subjects made Stage 1
    INFEASIBLE once a cohort's blocked slots covered every legal slot.
  * When the Stage 2 optimiser timed out, the objective-free fallback was
    reported as OPTIMAL with objective 0.
  * Tolerable ratings were silently dropped from the objective.
  * Blocked placements are minimised first (Pass A), then capped.

Run with:  venv\\Scripts\\python.exe -m pytest tests/test_solver_regression.py -q
"""
import sys

sys.path.insert(0, ".")

from domain.enums import PreferenceRating, SubjectType
from domain.models import Meeting, Section
from domain.timeslots import build_canonical_grid
from solver.engine import SolverInput, SolverResult, solve

BLOCKED = PreferenceRating.BLOCKED.value
TOLERABLE = PreferenceRating.TOLERABLE.value
THEORY_SLOTS = [s for s in build_canonical_grid() if SubjectType.THEORY in s.allowed_types]

BLOCKED_POINTS = 5 * 400  # _TIME_WEIGHT * penalty(BLOCKED)


def _section(sid, code, label_n, meetings=2, capacity=30):
    return Section(
        id=sid,
        subject_code=code,
        label=f"{code}-T{label_n}",
        teacher_id=None,
        capacity=capacity,
        meetings=[Meeting(slot_key="") for _ in range(meetings)],
        run_id=1,
    )


def _input(sections, students, time_prefs, teachers=None, avail=None, **kw):
    return SolverInput(
        sections=sections,
        candidate_slots={s.id: THEORY_SLOTS for s in sections},
        candidate_teachers=teachers or {s.id: ["T1"] for s in sections},
        time_preferences=time_prefs,
        faculty_preferences={},
        teacher_availability=avail or {},
        subject_students=students,
        time_limit_seconds=20.0,
        **kw,
    )


def test_cohort_blocks_covering_every_slot_do_not_make_stage1_infeasible():
    # One single-section subject; each of 14 students blocks a different slot,
    # so the union of blocks == every legal slot. This used to be INFEASIBLE.
    rolls = [f"S{i:02d}" for i in range(len(THEORY_SLOTS))]
    prefs = {r: {slot.key: BLOCKED} for r, slot in zip(rolls, THEORY_SLOTS)}
    res = solve(_input([_section(0, "IT1", 1)], {"IT1": rolls}, prefs))

    assert res.status in ("OPTIMAL", "FEASIBLE"), res.warnings
    # 2 meetings, each in a slot blocked by exactly one student.
    assert res.blocked_placements == 2
    assert res.blocked_minimum_proven is True
    assert any("Blocked slots" in w for w in res.warnings)


def test_objective_reflects_blocked_placements_never_zero():
    rolls = [f"S{i:02d}" for i in range(len(THEORY_SLOTS))]
    prefs = {r: {slot.key: BLOCKED} for r, slot in zip(rolls, THEORY_SLOTS)}
    res = solve(_input([_section(0, "IT1", 1)], {"IT1": rolls}, prefs))

    assert res.blocked_placements == 2
    assert res.objective_value == 2 * BLOCKED_POINTS
    assert res.candidates[0]["blocked_placements"] == 2
    assert res.candidates[0]["objective_value"] == res.objective_value


def test_tolerable_ratings_count_towards_the_objective():
    prefs = {"S1": {slot.key: TOLERABLE for slot in THEORY_SLOTS}}
    res = solve(_input([_section(0, "IT1", 1, meetings=1)], {"IT1": ["S1"]}, prefs))

    assert res.status in ("OPTIMAL", "FEASIBLE")
    # one meeting x weight 5 x penalty 1
    assert res.objective_value == 5
    assert res.blocked_placements == 0


def test_solver_prefers_unrated_slot_over_tolerable_slot():
    # Two parallel sections forced into slots X (student: Tolerable) and Y
    # (unrated). Before the fix Tolerable cost 0, so X and Y tied.
    x, y = THEORY_SLOTS[0].key, THEORY_SLOTS[1].key
    avail = {"T1": {s.key: False for s in THEORY_SLOTS if s.key not in (x, y)}}
    sections = [_section(0, "IT1", 1, meetings=1), _section(1, "IT1", 2, meetings=1)]
    res = solve(_input(sections, {"IT1": ["S1"]}, {"S1": {x: TOLERABLE}}, avail=avail))

    chosen_sid = res.student_section_assignments["S1"]["IT1"]
    assert res.section_slot_assignments[chosen_sid] == [y]
    # Only the section-balance term remains (1 student over 2 parallel sections
    # => ideal 0, deviation 1, weight 2); no time-preference penalty is paid.
    assert res.objective_value == 2


def test_blocked_slot_avoided_when_an_alternative_section_exists():
    # One teacher, two sections => they must sit in different slots. The
    # teacher is only free in X and Y, and the student blocks X.
    x, y = THEORY_SLOTS[0].key, THEORY_SLOTS[1].key
    avail = {"T1": {s.key: False for s in THEORY_SLOTS if s.key not in (x, y)}}
    sections = [_section(0, "IT1", 1, meetings=1), _section(1, "IT1", 2, meetings=1)]
    res = solve(_input(sections, {"IT1": ["S1"]}, {"S1": {x: BLOCKED}}, avail=avail))

    assert res.status in ("OPTIMAL", "FEASIBLE"), res.warnings
    chosen_sid = res.student_section_assignments["S1"]["IT1"]
    assert res.section_slot_assignments[chosen_sid] == [y]
    assert res.blocked_placements == 0
    assert res.blocked_minimum_proven is True
    assert not any("Blocked slots" in w for w in res.warnings)


def test_status_is_optimal_only_when_both_stages_are_optimal():
    prefs = {"S1": {THEORY_SLOTS[0].key: TOLERABLE}}
    res = solve(_input([_section(0, "IT1", 1)], {"IT1": ["S1"]}, prefs))

    assert res.stage1_status in ("OPTIMAL", "FEASIBLE")
    assert res.stage2_status in ("OPTIMAL", "FEASIBLE")
    if res.status == "OPTIMAL":
        assert res.stage1_status == "OPTIMAL" and res.stage2_status == "OPTIMAL"
    else:
        assert "OPTIMAL" not in (res.stage1_status + res.stage2_status) or res.status == "FEASIBLE"


# ── multi-candidate portfolio (build -> score -> optimise only the winner) ──

def _cohort_blocks_input(candidates, time_limit=60.0):
    rolls = [f"S{i:02d}" for i in range(len(THEORY_SLOTS))]
    prefs = {r: {slot.key: BLOCKED} for r, slot in zip(rolls, THEORY_SLOTS)}
    inp = _input([_section(0, "IT1", 1)], {"IT1": rolls}, prefs)
    inp.candidate_count = candidates
    inp.time_limit_seconds = time_limit
    return inp


def test_portfolio_scores_all_candidates_and_fully_optimises_only_the_winner():
    # Blocks make a 0-blocked layout impossible, so no early stop: all 3 are built.
    res = solve(_cohort_blocks_input(candidates=3))

    assert res.status in ("OPTIMAL", "FEASIBLE")
    assert [c["candidate_id"] for c in res.candidates] == [1, 2, 3]
    best = [c for c in res.candidates if c["is_best"]]
    assert len(best) == 1
    assert best[0]["status"] in ("OPTIMAL", "FEASIBLE")
    assert best[0]["objective_value"] == res.objective_value == 2 * BLOCKED_POINTS
    for c in res.candidates:
        if not c["is_best"]:
            assert c["status"] == "SCORED"
            assert c["objective_value"] is None  # never a fake 0
            assert c["blocked_placements"] == 2
    assert any("Multi-candidate search" in w for w in res.warnings)


def test_portfolio_stops_early_when_a_candidate_has_zero_proven_blocks():
    inp = _input([_section(0, "IT1", 1)], {"IT1": ["S1"]}, {"S1": {THEORY_SLOTS[0].key: BLOCKED}})
    inp.candidate_count = 4
    inp.time_limit_seconds = 60.0
    res = solve(inp)

    assert res.status in ("OPTIMAL", "FEASIBLE")
    assert len(res.candidates) == 1 and res.candidates[0]["is_best"]
    assert res.blocked_placements == 0
    assert any("no further candidates" in w for w in res.warnings)


def test_portfolio_picks_fewest_blocked_and_gives_winner_the_remaining_time(monkeypatch):
    import solver.engine as eng

    blocked_by_seed = {42: 5, 101: 2, 202: 9}
    calls = []

    def fake_stage1(inp, seed, solve_seconds):
        calls.append(("s1", seed, solve_seconds))
        return eng._Stage1("FEASIBLE", {}, {}, {}, {}, num_conflicts=seed, elapsed=0.0), None

    def fake_stage2(inp, seed, s1, budget, score_only=False):
        assert s1.num_conflicts == seed, "Stage 2 must receive that candidate's own Stage 1"
        calls.append(("s2-score" if score_only else "s2-final", seed, budget))
        if score_only:
            return SolverResult(status="SCORED", stage1_status="FEASIBLE", stage2_status="SCORED",
                                blocked_placements=blocked_by_seed[seed], blocked_minimum_proven=False)
        return SolverResult(status="FEASIBLE", stage1_status="FEASIBLE", stage2_status="FEASIBLE",
                            objective_value=123, blocked_placements=blocked_by_seed[seed],
                            blocked_minimum_proven=True)

    monkeypatch.setattr(eng, "_stage1", fake_stage1)
    monkeypatch.setattr(eng, "_stage2", fake_stage2)
    res = solve(_cohort_blocks_input(candidates=3, time_limit=300.0))

    finals = [c for c in calls if c[0] == "s2-final"]
    assert len(finals) == 1 and finals[0][1] == 101, "only the fewest-blocked candidate is finalised"
    assert finals[0][2] >= 0.35 * 300, "the winner gets the large remaining share, not 1/N"
    assert all(c[2] <= 45.0 for c in calls if c[0] == "s1")
    assert [c["candidate_id"] for c in res.candidates if c["is_best"]] == [2]
    by_id = {c["candidate_id"]: c for c in res.candidates}
    assert by_id[2]["objective_value"] == 123 and by_id[1]["objective_value"] is None
    assert by_id[3]["blocked_placements"] == 9
    # Per-candidate times must be sane parts of the whole, never exceed the solve itself.
    assert all(c["wall_time_seconds"] <= res.wall_time_seconds + 0.5 for c in res.candidates)


def test_portfolio_with_no_buildable_candidate_reports_unknown(monkeypatch):
    import solver.engine as eng

    monkeypatch.setattr(
        eng, "_stage1",
        lambda inp, seed, solve_seconds: (None, SolverResult(status="UNKNOWN", stage1_status="UNKNOWN")),
    )
    res = solve(_cohort_blocks_input(candidates=2))

    assert res.status == "UNKNOWN" and not res.student_section_assignments
    assert len(res.candidates) == 2
    assert all(c["objective_value"] is None for c in res.candidates)
    assert any("increase the Solver Time Limit" in w for w in res.warnings)


def test_portfolio_cancel_publishes_nothing():
    inp = _cohort_blocks_input(candidates=3)
    inp.cancel_check = lambda: True
    res = solve(inp)
    assert res.status == "UNKNOWN" and not res.student_section_assignments
    assert any("cancelled" in w.lower() for w in res.warnings)


def test_cancelled_solve_publishes_nothing():
    prefs = {"S1": {THEORY_SLOTS[0].key: TOLERABLE}}
    inp = _input([_section(0, "IT1", 1)], {"IT1": ["S1"]}, prefs, cancel_check=lambda: True)
    res = solve(inp)

    assert res.status == "UNKNOWN"
    assert not res.student_section_assignments
    assert any("cancelled" in w.lower() for w in res.warnings)
