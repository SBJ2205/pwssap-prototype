"""Snapshot, persistence, and comparison for solved timetable generation runs.

Allows storing completed runs on disk (both Traditional Cohorts and PWSSAP Elective
modes across any semester cycle: [4, 6, 8] or [3, 5, 7]), switching between them
as the live published timetable, and generating side-by-side comparison metrics
for faculty reviews.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from domain.enums import RunStatus
from domain.models import Meeting, Section
from domain.traditional_plan import (
    BATCH_LAB,
    DISPERSAL,
    DIVISION_THEORY,
    SectionInfo,
    StudentUnit,
    TraditionalPlan,
    get_live_plan,
)

logger = logging.getLogger("pwssap.saved_runs")

SAVED_RUNS_DIR = Path(__file__).resolve().parent.parent / "data" / "saved_runs"


def _ensure_dir() -> Path:
    SAVED_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    return SAVED_RUNS_DIR


def _sanitize_name(val: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", val)


def _section_to_dict(section: Section) -> dict:
    return {
        "id": section.id,
        "run_id": section.run_id,
        "subject_code": section.subject_code,
        "label": section.label,
        "teacher_id": section.teacher_id,
        "capacity": section.capacity,
        "meetings": [
            {
                "slot_key": m.slot_key or None,
                "duration_hours": m.duration_hours,
                "slot_part": m.slot_part,
            }
            for m in section.meetings
        ],
    }


def _dict_to_section(data: dict) -> Section:
    meetings = [
        Meeting(
            slot_key=m.get("slot_key") or "",
            duration_hours=int(m.get("duration_hours", 2) or 2),
            slot_part=m.get("slot_part"),
        )
        for m in data.get("meetings", [])
    ]
    return Section(
        id=data.get("id"),
        run_id=data.get("run_id"),
        subject_code=data.get("subject_code", ""),
        label=data.get("label", ""),
        teacher_id=data.get("teacher_id"),
        capacity=int(data.get("capacity", 30) or 30),
        meetings=meetings,
    )


def save_run_snapshot(store: Any, run_id: int, label: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Serialize a completed run to disk in backend/data/saved_runs/."""
    try:
        run = store.get_run(run_id)
        if run is None:
            return None

        plan = store.traditional_plans.get(run_id)
        mode = "traditional" if plan is not None else "elective"
        semesters = list(run.semesters) if getattr(run, "semesters", None) else [run.semester]
        sem_str = "-".join(str(s) for s in sorted(semesters))

        solve_diag = store.latest_solve_results.get(run_id, {})
        sections = store.list_sections_for_run(run_id)

        # Filter student assignments relevant to this run's semesters
        relevant_rolls = {
            s.roll_number for s in store.list_students()
            if s.semester in semesters
        }
        filtered_assignments = {
            roll: dict(m)
            for roll, m in store.student_section_assignments.items()
            if roll in relevant_rolls or not relevant_rolls
        }

        # Format snapshot ID and metadata
        snapshot_id = f"run_{run_id}_{mode}_sem{sem_str}"
        default_label = f"Sem {', '.join(str(s) for s in semesters)} ({mode.capitalize()})"

        created_at = datetime.now(timezone.utc).isoformat()

        # Traditional plan details if present
        plan_dict = None
        if plan is not None:
            plan_dict = {
                "pins": {roll: dict(m) for roll, m in plan.pins.items()},
                "sync_groups": [list(g) for g in plan.sync_groups],
                "batch_division_map": {
                    f"{sem}_{b}": div for (sem, b), div in plan.batch_division_map.items()
                },
                "warnings": list(plan.warnings),
            }

        snapshot_payload = {
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "label": label or default_label,
            "mode": mode,
            "semesters": semesters,
            "created_at": created_at,
            "metrics": {
                "status": solve_diag.get("status", run.status.value if hasattr(run.status, "value") else str(run.status)),
                "objective_value": solve_diag.get("objective_value"),
                "blocked_placements": solve_diag.get("blocked_placements"),
                "blocked_minimum_proven": solve_diag.get("blocked_minimum_proven"),
                "wall_time_seconds": solve_diag.get("wall_time_seconds"),
                "num_conflicts": solve_diag.get("num_conflicts", 0),
                "candidates": solve_diag.get("candidates", []),
                "warnings": solve_diag.get("warnings", []),
                "total_students": len(filtered_assignments),
                "assigned_sections": len(sections),
            },
            "sections": [_section_to_dict(s) for s in sections],
            "student_assignments": filtered_assignments,
            "traditional_plan": plan_dict,
        }

        folder = _ensure_dir()
        file_path = folder / f"{snapshot_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_payload, f, indent=2)

        logger.info("Saved timetable run snapshot to %s", file_path)
        return snapshot_payload

    except Exception as exc:
        logger.warning("Failed to save run snapshot for run %d: %s", run_id, exc)
        return None


def list_saved_snapshots() -> List[Dict[str, Any]]:
    """Return summary metadata for all saved runs on disk."""
    folder = _ensure_dir()
    snapshots = []
    for file_path in folder.glob("*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            snapshots.append({
                "snapshot_id": data.get("snapshot_id", file_path.stem),
                "run_id": data.get("run_id"),
                "label": data.get("label", file_path.stem),
                "mode": data.get("mode", "unknown"),
                "semesters": data.get("semesters", []),
                "created_at": data.get("created_at"),
                "metrics": data.get("metrics", {}),
                "section_count": len(data.get("sections", [])),
                "student_count": len(data.get("student_assignments", {})),
            })
        except Exception as exc:
            logger.warning("Error reading snapshot %s: %s", file_path, exc)

    # Sort newest first
    snapshots.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    return snapshots


def get_saved_snapshot(snapshot_id: str) -> Optional[Dict[str, Any]]:
    """Read a specific saved snapshot file."""
    folder = _ensure_dir()
    file_path = folder / f"{_sanitize_name(snapshot_id)}.json"
    if not file_path.exists():
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed reading snapshot %s: %s", snapshot_id, exc)
        return None


def activate_saved_run(store: Any, snapshot_id: str) -> Dict[str, Any]:
    """Restore a saved run snapshot as the active timetable in the live store."""
    snapshot = get_saved_snapshot(snapshot_id)
    if snapshot is None:
        raise ValueError(f"Snapshot '{snapshot_id}' does not exist.")

    run_id = snapshot["run_id"]
    semesters = snapshot.get("semesters", [])

    # 1. Ensure GenerationRun exists in store
    run = store.get_run(run_id)
    if run is None:
        run = store.create_run(semesters=semesters)
        run.id = run_id
        store.runs[run_id] = run
    run.status = RunStatus.PUBLISHED
    if hasattr(run, "semesters"):
        run.semesters = semesters

    # 2. Restore sections for this run
    store.clear_sections_for_run(run_id)
    for s_dict in snapshot.get("sections", []):
        sec = _dict_to_section(s_dict)
        sec.run_id = run_id
        store.sections[sec.id] = sec

    # 3. Restore student-section assignments
    for roll, mapping in snapshot.get("student_assignments", {}).items():
        for subj_code, sid in mapping.items():
            store.enroll_student(roll, subj_code, sid)

    # 4. Restore solver diagnostics cache
    if "metrics" in snapshot:
        store.latest_solve_results[run_id] = dict(snapshot["metrics"])
        store.latest_solve_results[run_id]["run_id"] = run_id
        store.latest_solve_results[run_id]["sections"] = snapshot.get("sections", [])

    # 5. Restore TraditionalPlan if present
    plan_dict = snapshot.get("traditional_plan")
    if plan_dict:
        b_map = {}
        for k_str, div in plan_dict.get("batch_division_map", {}).items():
            parts = k_str.split("_")
            if len(parts) == 2:
                b_map[(int(parts[0]), int(parts[1]))] = div
        plan = TraditionalPlan(
            run_id=run_id,
            semesters=semesters,
            pins=plan_dict.get("pins", {}),
            sync_groups=plan_dict.get("sync_groups", []),
            batch_division_map=b_map,
            warnings=plan_dict.get("warnings", []),
        )
        store.traditional_plans[run_id] = plan
    else:
        store.traditional_plans.pop(run_id, None)

    # 6. Set store active run tracker
    store.active_run_id = run_id

    return {
        "ok": True,
        "active_run_id": run_id,
        "label": snapshot.get("label"),
        "mode": snapshot.get("mode"),
        "semesters": semesters,
        "restored_sections": len(snapshot.get("sections", [])),
        "restored_students": len(snapshot.get("student_assignments", {})),
    }


def compare_saved_runs(store: Any, snapshot_id_a: str, snapshot_id_b: str) -> Dict[str, Any]:
    """Generate a side-by-side comparison between two saved run snapshots."""
    a = get_saved_snapshot(snapshot_id_a)
    b = get_saved_snapshot(snapshot_id_b)

    if a is None:
        raise ValueError(f"Snapshot A '{snapshot_id_a}' not found.")
    if b is None:
        raise ValueError(f"Snapshot B '{snapshot_id_b}' not found.")

    m_a = a.get("metrics", {})
    m_b = b.get("metrics", {})

    blocked_a = m_a.get("blocked_placements")
    blocked_b = m_b.get("blocked_placements")

    pen_a = m_a.get("objective_value")
    pen_b = m_b.get("objective_value")

    # Compute improvement deltas if applicable
    blocked_improvement_pct = None
    if blocked_a is not None and blocked_b is not None and blocked_a > 0:
        blocked_improvement_pct = round(((blocked_a - blocked_b) / blocked_a) * 100, 1)

    penalty_improvement_pct = None
    if pen_a is not None and pen_b is not None and pen_a > 0:
        penalty_improvement_pct = round(((pen_a - pen_b) / pen_a) * 100, 1)

    takeaway = (
        f"Compared {a.get('label')} vs {b.get('label')}: "
    )
    if blocked_improvement_pct is not None and blocked_improvement_pct > 0:
        takeaway += f"{b.get('label')} reduced student blocked-slot violations by {blocked_improvement_pct}%."
    elif blocked_improvement_pct is not None and blocked_improvement_pct < 0:
        takeaway += f"{a.get('label')} has {-blocked_improvement_pct}% fewer student blocked-slot violations."
    else:
        takeaway += "Both configurations achieve identical blocked slot counts."

    return {
        "run_a": {
            "snapshot_id": a.get("snapshot_id"),
            "label": a.get("label"),
            "mode": a.get("mode"),
            "semesters": a.get("semesters"),
            "status": m_a.get("status"),
            "blocked_placements": blocked_a,
            "objective_value": pen_a,
            "wall_time_seconds": m_a.get("wall_time_seconds"),
            "num_conflicts": m_a.get("num_conflicts", 0),
            "total_students": m_a.get("total_students", len(a.get("student_assignments", {}))),
            "assigned_sections": m_a.get("assigned_sections", len(a.get("sections", []))),
        },
        "run_b": {
            "snapshot_id": b.get("snapshot_id"),
            "label": b.get("label"),
            "mode": b.get("mode"),
            "semesters": b.get("semesters"),
            "status": m_b.get("status"),
            "blocked_placements": blocked_b,
            "objective_value": pen_b,
            "wall_time_seconds": m_b.get("wall_time_seconds"),
            "num_conflicts": m_b.get("num_conflicts", 0),
            "total_students": m_b.get("total_students", len(b.get("student_assignments", {}))),
            "assigned_sections": m_b.get("assigned_sections", len(b.get("sections", []))),
        },
        "deltas": {
            "blocked_improvement_pct": blocked_improvement_pct,
            "penalty_improvement_pct": penalty_improvement_pct,
        },
        "takeaway": takeaway,
    }


def delete_saved_snapshot(snapshot_id: str) -> bool:
    """Delete a saved run snapshot file."""
    folder = _ensure_dir()
    file_path = folder / f"{_sanitize_name(snapshot_id)}.json"
    if file_path.exists():
        file_path.unlink()
        return True
    return False
