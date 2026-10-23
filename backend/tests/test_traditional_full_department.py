"""Traditional mode end to end on the REAL demo_run department (466 students).

Drives the same HTTP flow as the UI -- divisions -> generate -> the normal solver
endpoint -- with a real CP-SAT solve, then verifies every guarantee with
independent checks (it does NOT reuse domain.traditional_validation).

Slow (~2-3 minutes), so it is opt-in:

    set RUN_SLOW=1
    venv\\Scripts\\python.exe -m pytest tests/test_traditional_full_department.py -q -s

Tunable: TRADITIONAL_TIME_LIMIT (default 120 seconds for the solve).
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, ".")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SLOW") != "1",
    reason="slow full-department solve; set RUN_SLOW=1 to run",
)

ADMIN = {"X-Role": "admin"}
MDM = {"MDMBI02", "MDMIE02", "MDMBD02", "MDMRB02"}
PE_SUBJECTS = {"PEIT25T", "PEIT25P", "PEIT29T", "PEIT29P", "PEIT28T", "PEIT28P", "PEIT32T", "PEIT32P"}


def periods(section):
    out = set()
    for m in section.meetings:
        assert m.slot_key, f"{section.label} has an unscheduled meeting"
        if m.duration_hours == 1:
            out.add((m.slot_key, m.slot_part or 1))
        else:
            out.update({(m.slot_key, 1), (m.slot_key, 2)})
    return out


def test_traditional_department_solves_with_every_guarantee():
    import run_stress_test as rst
    from fastapi.testclient import TestClient

    from data.store import get_store, reset_store
    from main import app

    reset_store()
    store = get_store()
    rst.setup_department_data(store)
    rst.seed_teacher_availability(store)
    rst.seed_student_preferences(store)
    client = TestClient(app, raise_server_exceptions=True)

    # ── Divisions -> generate (twice, to prove idempotence) ──────────────
    configs = {}
    for sem in (4, 6):
        suggested = client.get(f"/admin/cohorts/suggest?semester={sem}", headers=ADMIN).json()["classes"]
        res = client.post("/admin/cohorts/save", headers=ADMIN, json={"semester": sem, "classes": suggested})
        assert res.status_code == 200, res.text
        configs[sem] = res.json()["config"]

    run = client.post("/admin/runs", headers=ADMIN, json={"semesters": [4, 6], "choice_tags": []}).json()
    run_id = run["id"]
    first = client.post("/admin/cohorts/generate-sections", headers=ADMIN, json={"run_id": run_id}).json()
    second = client.post("/admin/cohorts/generate-sections", headers=ADMIN, json={"run_id": run_id}).json()
    assert second["generated_count"] == first["generated_count"] == len(store.list_sections())
    assert {s.run_id for s in store.list_sections()} == {run_id}

    # Before the solve nothing is visible to students.
    assert store.student_section_assignments == {}

    # ── Solve through the NORMAL solver endpoint (what the Solver page calls) ─
    limit = float(os.environ.get("TRADITIONAL_TIME_LIMIT", "120"))
    solved = client.post(f"/admin/runs/{run_id}/solve?time_limit={limit}", headers=ADMIN)
    assert solved.status_code == 200, solved.text
    body = solved.json()
    assert body["status"] in ("OPTIMAL", "FEASIBLE"), body["warnings"]
    assert body["run_status"] == "published", body["warnings"]
    print("\n".join(body["warnings"][-3:]))

    sections = {s.id: s for s in store.list_sections_for_run(run_id)}
    assignments = store.student_section_assignments
    slots = {s.key: s for s in store.list_time_slots()}

    # ── Every student has a section for every enrolled subject (incl. all PE) ─
    pe_seen = set()
    for student in store.list_students():
        roll = student.roll_number
        expected = {s.subject_code for s in store.get_enrolled_subjects_for_student(roll)}
        assert set(assignments[roll]) == expected, roll
        pe_seen |= set(assignments[roll]) & PE_SUBJECTS
    assert pe_seen == PE_SUBJECTS

    # ── Zero student clashes ─────────────────────────────────────────────
    for roll, mapping in assignments.items():
        seen = defaultdict(list)
        for code, sid in mapping.items():
            for p in periods(sections[sid]):
                seen[p].append(code)
        clashes = {p: c for p, c in seen.items() if len(c) > 1}
        assert not clashes, (roll, clashes)

    # ── Zero teacher clashes; availability respected; legal slots ────────
    teacher_seen = defaultdict(list)
    for section in sections.values():
        assert section.teacher_id, section.label
        availability = store.get_teacher_availability(section.teacher_id)
        for m in section.meetings:
            assert availability.get(m.slot_key, True), (section.label, section.teacher_id, m.slot_key)
            assert store.get_subject(section.subject_code).type in slots[m.slot_key].allowed_types
        for p in periods(section):
            teacher_seen[(section.teacher_id, p)].append(section.label)
    assert all(len(v) == 1 for v in teacher_seen.values()), [v for v in teacher_seen.values() if len(v) > 1]

    # ── Division / batch members share their sections (the saved setup, exactly) ─
    for sem, cfg in configs.items():
        sem_subjects = {s.subject_code: s for s in store.list_subjects(semester=sem)}
        for cls in cfg["classes"]:
            for code, subject in sem_subjects.items():
                is_lab = subject.type.value == "lab"
                if code in MDM:
                    continue
                units = [b["student_rolls"] for b in cls["batches"]] if is_lab else [cls["student_rolls"]]
                for unit in units:
                    taking = [r for r in unit if code in assignments[r]]
                    if taking:
                        assert len({assignments[r][code] for r in taking}) == 1, (sem, cls["class_id"], code)

    # Same-division PE labs/theory only exist for the matching track.
    for sem, cfg in configs.items():
        for cls in cfg["classes"]:
            if cls["track"]:
                for roll in cls["student_rolls"]:
                    mine = {c for c in assignments[roll] if c in PE_SUBJECTS}
                    assert all(store.get_subject(c).supports_subtag(cls["track"]) for c in mine)

    # ── Sem 4 MDM electives run in identical slots and hold every Sem 4 student once ─
    mdm_sections = [s for s in sections.values() if s.subject_code in MDM]
    assert len(mdm_sections) == 4
    signatures = {tuple(sorted((m.slot_key, m.duration_hours) for m in s.meetings)) for s in mdm_sections}
    assert len(signatures) == 1, signatures
    for student in store.list_students(semester=4):
        assert len(set(assignments[student.roll_number]) & MDM) == 1

    # ── Views: student, teacher, admin summary, validation ───────────────
    sample = store.list_students(semester=6)[0].roll_number
    tt = client.get(f"/students/{sample}/sections").json()["timetable"]
    assert tt and all(m["slot_key"] for e in tt for m in e["meetings"])
    teacher_id = next(iter({s.teacher_id for s in sections.values()}))
    assert client.get(f"/teachers/{teacher_id}/timetable", headers=ADMIN).status_code == 200
    summary = client.get(f"/admin/runs/{run_id}/summary", headers=ADMIN).json()
    assert summary["solved"] and summary["section_count"] == len(sections)

    status = client.get(f"/admin/cohorts/status?run_id={run_id}", headers=ADMIN).json()
    assert status["mode"] == "traditional" and status["published"]
    assert status["validation"]["ok"], status["validation"]["violations"][:5]
    assert client.get(f"/admin/cohorts/validation?run_id={run_id}", headers=ADMIN).json()["report"]["ok"]

    # ── Regenerating after a solve really resets everything ───────────────
    again = client.post("/admin/cohorts/generate-sections", headers=ADMIN, json={"run_id": run_id}).json()
    assert again["generated_count"] == first["generated_count"] == len(store.list_sections())
    assert store.get_run(run_id).status.value == "draft"
    assert not any(store.student_section_assignments.get(r) for r in store.students)
