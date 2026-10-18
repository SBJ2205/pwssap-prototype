"""The traditional-mode hooks in the solver must be inert for every other run.

The proof is at the model level: the Stage 1 CP-SAT model built for a normal
(preference-weighted) run is *identical* whether the optional traditional inputs
are absent, explicitly empty, or an explicit map that equals the old heuristic.
Then small real solves show the inputs do what they claim when supplied.
"""
import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import pytest
from ortools.sat.python import cp_model

from data.store import get_store, reset_store
from domain.enums import SubjectType
from domain.models import Meeting, Section
from domain.timeslots import build_canonical_grid, is_slot_usable
from solver import engine, service
from solver.engine import SolverInput, SolverResult, _batch_division


def legacy_division(num_divs: int, num_batches: int, b: int) -> int:
    return min(num_divs, max(1, 1 + (b - 1) * num_divs // num_batches))


def empty_input(**kwargs) -> SolverInput:
    return SolverInput(
        sections=[], candidate_slots={}, candidate_teachers={}, time_preferences={},
        faculty_preferences={}, teacher_availability={}, subject_students={}, **kwargs,
    )


def test_new_solver_input_fields_default_to_inert_values():
    inp = empty_input()
    assert inp.batch_division_map is None and inp.sync_section_groups is None and inp.pinned_student_sections is None


def test_batch_division_without_a_map_is_exactly_the_old_heuristic():
    inp = empty_input()
    for num_divs in range(1, 9):
        for num_batches in range(1, 25):
            for b in range(1, num_batches + 1):
                assert _batch_division(inp, 6, b, num_divs, num_batches) == legacy_division(num_divs, num_batches, b)


def test_explicit_map_overrides_only_the_batches_it_names():
    inp = empty_input(batch_division_map={(4, 4): 1})
    assert _batch_division(inp, 4, 4, 2, 6) == 1            # explicit
    assert _batch_division(inp, 4, 5, 2, 6) == legacy_division(2, 6, 5)  # not in the map
    assert _batch_division(inp, 6, 4, 2, 6) == legacy_division(2, 6, 4)  # other semester


# ── Stage 1 model fingerprint on the real department, preference path ─────


@pytest.fixture
def standard_run_input(monkeypatch):
    import run_stress_test as rst
    from api.sections import generate_sections

    reset_store()
    store = get_store()
    rst.setup_department_data(store)
    rst.seed_teacher_availability(store)
    rst.seed_student_preferences(store)
    run = store.create_run(semesters=[6])
    generate_sections(run.id, store)

    captured = {}

    def fake_solve(inp):
        captured["inp"] = inp
        return SolverResult(status="UNKNOWN")

    monkeypatch.setattr(service, "solve", fake_solve)
    service.run_solver_for_run(run.id, store, time_limit_seconds=5.0)
    return captured["inp"]


def stage1_model_text(inp: SolverInput, monkeypatch) -> str:
    captured = []

    def fake_solve(solver, model, cancel_check):
        captured.append(str(model.proto))
        solver.parameters.max_time_in_seconds = 0.05
        return solver.solve(model)

    monkeypatch.setattr(engine, "_solve_cancellable", fake_solve)
    engine._stage1(inp, seed=1, solve_seconds=1.0)
    return captured[0]


def test_preference_path_model_is_identical_with_or_without_traditional_inputs(standard_run_input, monkeypatch):
    base = stage1_model_text(standard_run_input, monkeypatch)
    assert standard_run_input.batch_division_map is None and standard_run_input.sync_section_groups is None

    explicit_nothing = replace(standard_run_input, batch_division_map=None, sync_section_groups=[])
    assert stage1_model_text(explicit_nothing, monkeypatch) == base
    assert stage1_model_text(replace(standard_run_input, batch_division_map={}), monkeypatch) == base


def test_the_traditional_inputs_are_actually_consumed(standard_run_input, monkeypatch):
    base = stage1_model_text(standard_run_input, monkeypatch)
    by_code = {}
    for s in standard_run_input.sections:
        by_code.setdefault(s.subject_code, []).append(s.id)
    group = next(ids for ids in by_code.values() if len(ids) >= 2)
    assert stage1_model_text(replace(standard_run_input, sync_section_groups=[group]), monkeypatch) != base
    assert stage1_model_text(replace(standard_run_input, batch_division_map={(6, 1): 4}), monkeypatch) != base


# ── Small real solves: the inputs do what they claim ─────────────────────


def mini_input(sections, subject_meta, **kwargs):
    grid = [s for s in build_canonical_grid() if is_slot_usable(s)]
    theory = [s for s in grid if SubjectType.THEORY in s.allowed_types]
    lab = [s for s in grid if SubjectType.LAB in s.allowed_types]
    candidate_slots = {
        s.id: theory if subject_meta[s.subject_code]["type"] == "theory" else lab for s in sections
    }
    defaults = {
        "time_preferences": {},
        "faculty_preferences": {},
        "teacher_availability": {},
        "subject_students": {},
        "subject_semesters": {c: 1 for c in subject_meta},
        "subject_tags": {c: m["tag"] for c, m in subject_meta.items()},
        "subject_types": {c: m["type"] for c, m in subject_meta.items()},
        "subject_subtags": {c: m.get("subtags", []) for c, m in subject_meta.items()},
        "feasibility_only": True,
        "time_limit_seconds": 20.0,
    }
    defaults.update(kwargs)
    return SolverInput(
        sections=sections,
        candidate_slots=candidate_slots,
        candidate_teachers={s.id: [f"T-{s.id}"] for s in sections},   # one private teacher each
        **defaults,
    )


def section(sid, code, label, meetings=(2,)):
    return Section(
        id=sid, subject_code=code, label=label, teacher_id=None, capacity=10,
        meetings=[Meeting(slot_key="", duration_hours=d, slot_part=1 if d == 1 else None) for d in meetings],
        run_id=1,
    )


def slots_of(result, sid):
    return sorted((m.slot_key, m.duration_hours) for m in result.section_meetings[sid])


def test_sync_groups_force_identical_slots():
    meta = {
        "CORE": {"type": "theory", "tag": "PCC"},
        "MDMA": {"type": "theory", "tag": "MDM", "subtags": ["A"]},
        "MDMB": {"type": "theory", "tag": "MDM", "subtags": ["B"]},
        "MDMC": {"type": "theory", "tag": "MDM", "subtags": ["C"]},
    }
    sections = [
        section(1, "CORE", "CORE-T1", (2, 2)),
        section(2, "MDMA", "MDMA-T1", (2, 2)),
        section(3, "MDMB", "MDMB-T1", (2, 2)),
        section(4, "MDMC", "MDMC-T1", (2, 2)),
    ]
    result = engine.solve(mini_input(sections, meta, sync_section_groups=[[2, 3, 4]]))
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert slots_of(result, 2) == slots_of(result, 3) == slots_of(result, 4)
    core = {m.slot_key for m in result.section_meetings[1]}
    assert core.isdisjoint({m.slot_key for m in result.section_meetings[2]})  # still clear of core


def test_explicit_batch_map_keeps_each_batch_clear_of_its_real_division():
    """Division 1 has 4 batches, division 2 has 2: the old heuristic maps batch 4 to division 2."""
    meta = {
        "TH": {"type": "theory", "tag": "PCC"},
        "LB": {"type": "lab", "tag": "PCC"},
    }
    sections = [section(1, "TH", "TH-T1", (2, 2)), section(2, "TH", "TH-T2", (2, 2))]
    sections += [section(10 + b, "LB", f"LB-L{b}", (2,)) for b in range(1, 7)]
    mapping = {(1, 1): 1, (1, 2): 1, (1, 3): 1, (1, 4): 1, (1, 5): 2, (1, 6): 2}
    result = engine.solve(mini_input(sections, meta, batch_division_map=mapping))
    assert result.status in ("OPTIMAL", "FEASIBLE")
    theory = {k: {m.slot_key for m in result.section_meetings[sid]} for k, sid in ((1, 1), (2, 2))}
    for b, div in mapping.items():
        lab_slot = {m.slot_key for m in result.section_meetings[10 + b[1]]}
        assert lab_slot.isdisjoint(theory[div]), (b, div)


def test_pinned_cohorts_evaluate_candidates_and_report_blocked_placements():
    meta = {"CORE": {"type": "theory", "tag": "PCC"}}
    sections = [section(1, "CORE", "CORE-T1", (2,))]
    pinned = {"R1": {"CORE": 1}}
    time_prefs = {"R1": {"Mon-1": 4, "Mon-2": 4}}
    inp = mini_input(
        sections,
        meta,
        pinned_student_sections=pinned,
        subject_students={"CORE": ["R1"]},
        time_preferences=time_prefs,
        feasibility_only=False,
        candidate_count=2,
    )
    result = engine.solve(inp)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    assert result.blocked_placements is not None
    assert isinstance(result.blocked_placements, int)
    assert len(result.candidates) >= 1
    assert result.candidates[0]["blocked_placements"] is not None
