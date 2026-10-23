"""Traditional Division & Batch mode: configuration, detection, generation, hooks.

All fixtures come from the real demo_run CSVs (via the stress-test loader), never
from invented subjects, because invented fixtures hid every defect of the first
implementation. Nothing here runs the solver; see
test_traditional_full_department.py for the real end-to-end solves.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from data.store import get_store, reset_store
from domain.cohorts import UNASSIGNED_TRACK, build_config, suggest_classes
from domain.enums import RunStatus
from domain.traditional_plan import (
    BATCH_LAB,
    DISPERSAL,
    DIVISION_THEORY,
    get_live_plan,
    solver_overrides_for_run,
)
from main import app

ADMIN = {"X-Role": "admin"}

PE_THEORY = {"AIML": ["PEIT25T", "PEIT29T"], "CSEC": ["PEIT28T", "PEIT32T"]}
PE_LABS = {"AIML": ["PEIT25P", "PEIT29P"], "CSEC": ["PEIT28P", "PEIT32P"]}
MDM_SUBJECTS = ["MDMBI02", "MDMIE02", "MDMBD02", "MDMRB02"]


@pytest.fixture
def store():
    import run_stress_test as rst

    reset_store()
    store = get_store()
    rst.setup_department_data(store)
    rst.seed_teacher_availability(store)
    return store


@pytest.fixture
def client(store):
    return TestClient(app)


def save_suggested(client, store, semesters=(4, 6), **suggest_kwargs):
    for sem in semesters:
        classes = suggest_classes(store, sem, **suggest_kwargs)
        res = client.post("/admin/cohorts/save", headers=ADMIN, json={"semester": sem, "classes": classes})
        assert res.status_code == 200, res.text


def new_run(store, semesters=(4, 6)):
    return store.create_run(semesters=list(semesters))


def generate(client, run_id):
    res = client.post("/admin/cohorts/generate-sections", headers=ADMIN, json={"run_id": run_id})
    assert res.status_code == 200, res.text
    return res.json()


# ── Access control ────────────────────────────────────────────────────────


def test_every_cohort_route_requires_admin(client):
    calls = [
        ("get", "/admin/cohorts/detect-clusters?semester=6", None),
        ("get", "/admin/cohorts/suggest?semester=6", None),
        ("get", "/admin/cohorts?semester=6", None),
        ("post", "/admin/cohorts/save", {"semester": 6, "classes": []}),
        ("delete", "/admin/cohorts?semester=6", None),
        ("post", "/admin/cohorts/generate-sections", {"run_id": 1}),
        ("get", "/admin/cohorts/status?run_id=1", None),
        ("get", "/admin/cohorts/validation?run_id=1", None),
    ]
    for method, url, body in calls:
        for headers in ({}, {"X-Role": "student"}):
            res = getattr(client, method)(url, headers=headers, **({"json": body} if body is not None else {}))
            assert res.status_code == 403, (method, url, headers, res.status_code)


# ── Detection on the real data shape ──────────────────────────────────────


def test_semester6_clusters_by_pe_track_and_mdm03_is_just_a_lab(client):
    data = client.get("/admin/cohorts/detect-clusters?semester=6", headers=ADMIN).json()
    assert data["track_tag"] == "PE" and data["has_tracks"]
    counts = {c["track_id"]: c["student_count"] for c in data["clusters"]}
    assert counts == {"AIML": 124, "CSEC": 100}
    assert data["dispersal_electives"] == []
    # MDM03 is a lab tagged MDC_OE with no subtag: ordinary in-class lab, not a flagged elective.
    assert data["in_class_electives"] == []
    assert "MDM03" in {s["subject_code"] for s in data["core_subjects"]}
    assert data["track_subjects"]["AIML"] and data["track_subjects"]["CSEC"]


def test_semester4_has_mdm_dispersal_and_no_oec14_flag(client):
    data = client.get("/admin/cohorts/detect-clusters?semester=4", headers=ADMIN).json()
    assert data["track_tag"] is None and [c["track_id"] for c in data["clusters"]] == ["ALL"]
    assert data["clusters"][0]["student_count"] == 242
    assert len(data["dispersal_electives"]) == 1
    group = data["dispersal_electives"][0]
    assert group["tag"] == "MDM"
    assert {s["subject_code"] for s in group["subjects"]} == set(MDM_SUBJECTS)
    assert sum(s["student_count"] for s in group["subjects"]) == 242
    # OEC14 is a lab with tag OE (not a choice tag): must not be reported as an in-class elective.
    assert data["in_class_electives"] == []
    assert "OEC14" in {s["subject_code"] for s in data["core_subjects"]}


def test_single_offering_choice_tag_is_in_class(store, client):
    """A choice tag with only one subtag in a semester is taught in-class (shape-based, not name-based)."""
    store.set_cycle_choice_configs({"MDM": True, "PE": True, "OE": True})
    data = client.get("/admin/cohorts/detect-clusters?semester=4", headers=ADMIN).json()
    assert [e["subject_code"] for e in data["in_class_electives"]] == []  # OEC14 has no subtag: not an offering group
    oec = store.get_subject("OEC14")
    oec.subtag = "GEN"
    data = client.get("/admin/cohorts/detect-clusters?semester=4", headers=ADMIN).json()
    assert [e["subject_code"] for e in data["in_class_electives"]] == ["OEC14"]
    assert data["in_class_electives"][0]["is_dispersal"] is False


# ── Saving divisions ──────────────────────────────────────────────────────


def test_suggested_divisions_are_valid_balanced_and_inside_one_track(client, store):
    save_suggested(client, store)
    for sem in (4, 6):
        cfg = client.get(f"/admin/cohorts?semester={sem}", headers=ADMIN).json()
        roster = {s.roll_number for s in store.list_students(semester=sem)}
        placed = [r for c in cfg["classes"] for r in c["student_rolls"]]
        assert sorted(placed) == sorted(roster) and len(placed) == len(set(placed))
        for cls in cfg["classes"]:
            sizes = [len(b["student_rolls"]) for b in cls["batches"]]
            assert min(sizes) >= 1 and max(sizes) - min(sizes) <= 1
            assert sum(sizes) == len(cls["student_rolls"])
            assert 2 <= cls["lab_batch_count"] <= 6
    sem6 = client.get("/admin/cohorts?semester=6", headers=ADMIN).json()["classes"]
    assert {c["track"] for c in sem6} == {"AIML", "CSEC"}
    for cls in sem6:
        tracks = {store.get_lock_in_for_student(r)["PE"] for r in cls["student_rolls"]}
        assert tracks == {cls["track"]}


def _classes(store, sem, parts):
    rolls = sorted(s.roll_number for s in store.list_students(semester=sem))
    out, start = [], 0
    for i, size in enumerate(parts):
        chunk = rolls[start:start + size] if size is not None else rolls[start:]
        start += len(chunk)
        out.append({"class_id": f"Div-{chr(65 + i)}", "student_rolls": chunk, "lab_batch_count": 3})
    return out


def test_save_rejects_bad_input(client, store):
    def post(classes, sem=4):
        return client.post("/admin/cohorts/save", headers=ADMIN, json={"semester": sem, "classes": classes})

    ok = _classes(store, 4, [100, None])
    assert post(ok).status_code == 200

    missing = _classes(store, 4, [100, 100])  # leaves 42 students unplaced
    res = post(missing)
    assert res.status_code == 400 and "not placed" in res.json()["detail"]["message"]

    dup = _classes(store, 4, [100, None])
    dup[1]["student_rolls"].append(dup[0]["student_rolls"][0])
    assert "both" in post(dup).json()["detail"]["message"]

    empty = _classes(store, 4, [None])
    empty.append({"class_id": "Div-B", "student_rolls": [], "lab_batch_count": 3})
    assert "no students" in post(empty).json()["detail"]["message"]

    for bad in (1, 7, 0):
        batches = _classes(store, 4, [100, None])
        batches[0]["lab_batch_count"] = bad
        assert "batch count" in post(batches).json()["detail"]["message"]

    foreign = _classes(store, 4, [100, None])
    foreign[0]["student_rolls"].append(store.list_students(semester=6)[0].roll_number)
    assert "does not belong" in post(foreign).json()["detail"]["message"]

    assert post([]).status_code == 400
    # Failed saves never overwrite the last good setup.
    assert len(client.get("/admin/cohorts?semester=4", headers=ADMIN).json()["classes"]) == 2


def test_sem6_division_mixing_tracks_is_rejected(client, store):
    rolls = sorted(s.roll_number for s in store.list_students(semester=6))
    res = client.post(
        "/admin/cohorts/save", headers=ADMIN,
        json={"semester": 6, "classes": [{"class_id": "Div-A", "student_rolls": rolls, "lab_batch_count": 3}]},
    )
    assert res.status_code == 400
    assert "mixes PE tracks" in res.json()["detail"]["message"]


def test_student_without_track_choice_blocks_saving(client, store):
    roll = store.list_students(semester=6)[0].roll_number
    store.set_student_choice_selections(roll, [])
    detect = client.get("/admin/cohorts/detect-clusters?semester=6", headers=ADMIN).json()
    assert UNASSIGNED_TRACK in {c["track_id"] for c in detect["clusters"]}
    classes = suggest_classes(store, 6)
    placed = {r for c in classes for r in c["student_rolls"]}
    assert roll not in placed
    classes[0]["student_rolls"].append(roll)
    res = client.post("/admin/cohorts/save", headers=ADMIN, json={"semester": 6, "classes": classes})
    assert res.status_code == 400


# ── Generation ────────────────────────────────────────────────────────────


def test_generation_requires_setup_for_every_run_semester(client, store):
    save_suggested(client, store, semesters=(6,))
    run = new_run(store)
    res = client.post("/admin/cohorts/generate-sections", headers=ADMIN, json={"run_id": run.id})
    assert res.status_code == 400 and "semester(s) 4" in res.json()["detail"]["message"]
    assert store.list_sections() == []

    missing = client.post("/admin/cohorts/generate-sections", headers=ADMIN, json={"run_id": 999})
    assert missing.status_code == 404


def test_generation_makes_every_section_inside_the_run_and_pins_every_student(client, store):
    save_suggested(client, store)
    run = new_run(store)
    out = generate(client, run.id)

    sections = store.list_sections()
    assert sections and {s.run_id for s in sections} == {run.id}  # never run_id=None
    assert out["generated_count"] == len(sections)
    plan = get_live_plan(store, run.id)

    labels = {s.label for s in sections}
    # Every PE theory section per division of the right track, every PE lab per batch.
    for cfg_class in client.get("/admin/cohorts?semester=6", headers=ADMIN).json()["classes"]:
        k = [c["class_id"] for c in client.get("/admin/cohorts?semester=6", headers=ADMIN).json()["classes"]].index(
            cfg_class["class_id"]) + 1
        for code in PE_THEORY[cfg_class["track"]]:
            assert f"{code}-T{k}" in labels
        other = "CSEC" if cfg_class["track"] == "AIML" else "AIML"
        for code in PE_THEORY[other]:
            assert f"{code}-T{k}" not in labels
    for track, codes in PE_LABS.items():
        for code in codes:
            assert any(l.startswith(f"{code}-L") for l in labels)
    for code in PE_THEORY["AIML"] + PE_THEORY["CSEC"]:
        assert any(l.startswith(f"{code}-T") for l in labels)

    # Every enrolled subject of every student has exactly their pinned section.
    for student in store.list_students():
        expected = {s.subject_code for s in store.get_enrolled_subjects_for_student(student.roll_number)}
        assert set(plan.pins[student.roll_number]) == expected, student.roll_number
    assert len(plan.pins) == 466

    # Pins are applied only after a solve: an unsolved run leaks nothing.
    assert store.student_section_assignments == {}
    assert run.status == RunStatus.DRAFT


def test_members_of_a_division_share_theory_and_batch_members_share_labs(client, store):
    save_suggested(client, store)
    run = new_run(store)
    generate(client, run.id)
    plan = get_live_plan(store, run.id)
    by_unit = {}
    for roll, mapping in plan.pins.items():
        unit = plan.student_units[roll]
        for code, sid in mapping.items():
            kind = plan.sections[sid].kind
            if kind == DIVISION_THEORY:
                by_unit.setdefault(("div", unit.semester, unit.class_id, code), set()).add(sid)
            elif kind == BATCH_LAB:
                by_unit.setdefault(("batch", unit.semester, unit.batch_id, code), set()).add(sid)
    assert by_unit and all(len(v) == 1 for v in by_unit.values())


def test_dispersal_sections_are_one_per_subject_and_synchronised(client, store):
    save_suggested(client, store)
    run = new_run(store)
    generate(client, run.id)
    plan = get_live_plan(store, run.id)

    dispersal = [i for i in plan.sections.values() if i.kind == DISPERSAL]
    assert sorted(i.subject_code for i in dispersal) == sorted(MDM_SUBJECTS)
    assert all(i.label.endswith("-T1") for i in dispersal)
    assert plan.sync_groups == [sorted(i.section_id for i in dispersal)] or \
        [sorted(g) for g in plan.sync_groups] == [sorted(i.section_id for i in dispersal)]
    # The four elective sections hold all 242 students exactly once.
    sem4 = [s for s in store.list_students(semester=4)]
    for student in sem4:
        chosen = [c for c in MDM_SUBJECTS if c in plan.pins[student.roll_number]]
        assert len(chosen) == 1
    assert solver_overrides_for_run(store, run.id)["sync_section_groups"]


def test_batch_to_division_mapping_is_explicit_for_unequal_batch_counts(client, store):
    classes = _classes(store, 4, [120, None])
    classes[0]["lab_batch_count"] = 4
    classes[1]["lab_batch_count"] = 2
    assert client.post("/admin/cohorts/save", headers=ADMIN, json={"semester": 4, "classes": classes}).status_code == 200
    run = new_run(store, semesters=(4,))
    generate(client, run.id)
    plan = get_live_plan(store, run.id)
    assert plan.batch_division_map == {(4, 1): 1, (4, 2): 1, (4, 3): 1, (4, 4): 1, (4, 5): 2, (4, 6): 2}
    # The engine's own heuristic would have put batch 4 under division 2.
    assert min(2, max(1, 1 + (4 - 1) * 2 // 6)) == 2
    assert solver_overrides_for_run(store, run.id)["batch_division_map"][(4, 4)] == 1


def test_generation_is_idempotent_and_leaves_nothing_behind(client, store):
    save_suggested(client, store)
    run = new_run(store)
    first = generate(client, run.id)
    ids_first = {s.id for s in store.list_sections()}
    second = generate(client, run.id)
    assert second["generated_count"] == first["generated_count"] == len(store.list_sections())
    assert second["cleared_count"] == first["generated_count"]
    assert not (ids_first & {s.id for s in store.list_sections()})  # ids are never reused
    assert {s.run_id for s in store.list_sections()} == {run.id}
    labels = [s.label for s in store.list_sections()]
    assert len(labels) == len(set(labels))


def test_standard_generation_retires_the_traditional_plan(client, store):
    save_suggested(client, store)
    run = new_run(store)
    generate(client, run.id)
    assert client.get(f"/admin/cohorts/status?run_id={run.id}", headers=ADMIN).json()["mode"] == "traditional"

    std = client.post(f"/admin/runs/{run.id}/generate-sections", headers=ADMIN)
    assert std.status_code == 200
    status = client.get(f"/admin/cohorts/status?run_id={run.id}", headers=ADMIN).json()
    assert status["mode"] == "standard" and status["stale_reason"]
    assert solver_overrides_for_run(store, run.id) == {}
    assert get_live_plan(store, run.id) is None

    # ...and traditional generation takes the run back, clearing the standard sections.
    out = generate(client, run.id)
    assert out["cleared_count"] > 0
    assert client.get(f"/admin/cohorts/status?run_id={run.id}", headers=ADMIN).json()["mode"] == "traditional"


def test_generating_for_one_run_clears_other_runs_like_standard_generation(client, store):
    save_suggested(client, store)
    first = new_run(store)
    client.post(f"/admin/runs/{first.id}/generate-sections", headers=ADMIN)
    second = new_run(store)
    generate(client, second.id)
    assert {s.run_id for s in store.list_sections()} == {second.id}
    assert first.status == RunStatus.DRAFT


def test_config_change_after_generation_is_flagged(client, store):
    save_suggested(client, store)
    run = new_run(store)
    generate(client, run.id)
    assert client.get(f"/admin/cohorts/status?run_id={run.id}", headers=ADMIN).json()["config_changed"] is False
    classes = suggest_classes(store, 4)
    classes[0]["lab_batch_count"] = 4 if classes[0]["lab_batch_count"] != 4 else 5
    assert client.post("/admin/cohorts/save", headers=ADMIN, json={"semester": 4, "classes": classes}).status_code == 200
    assert client.get(f"/admin/cohorts/status?run_id={run.id}", headers=ADMIN).json()["config_changed"] is True


def test_changes_are_refused_while_a_solve_is_running(client, store):
    save_suggested(client, store)
    run = new_run(store)
    assert store.try_begin_solve(run.id, "solve")
    try:
        classes = suggest_classes(store, 4)
        assert client.post("/admin/cohorts/save", headers=ADMIN,
                           json={"semester": 4, "classes": classes}).status_code == 409
        assert client.post("/admin/cohorts/generate-sections", headers=ADMIN,
                           json={"run_id": run.id}).status_code == 409
        assert client.delete("/admin/cohorts?semester=4", headers=ADMIN).status_code == 409
    finally:
        store.end_solve(run.id)


def test_validation_endpoint_before_and_without_a_solve(client, store):
    save_suggested(client, store)
    run = new_run(store)
    assert client.get(f"/admin/cohorts/validation?run_id={run.id}", headers=ADMIN).status_code == 409
    generate(client, run.id)
    body = client.get(f"/admin/cohorts/validation?run_id={run.id}", headers=ADMIN).json()
    assert body == {"run_id": run.id, "solved": False, "report": None}


def test_store_no_longer_hosts_cohort_logic():
    from data.store import InMemoryStore

    for name in ("detect_pe_clusters", "get_semester_cohorts", "set_semester_cohorts", "clear_semester_cohorts"):
        assert not hasattr(InMemoryStore, name)


def test_build_config_balances_batches_without_empty_batch(store):
    classes = _classes(store, 4, [5, None])
    for c in classes:
        c["lab_batch_count"] = 4
    config, _ = build_config(store, 4, classes)
    assert [len(b.student_rolls) for b in config.classes[0].batches] == [2, 1, 1, 1]
