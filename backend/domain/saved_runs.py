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

        plan = get_live_plan(store, run_id)
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
        default_label = f"Sem {', '.join(str(s) for s in semesters)} ({mode.capitalize()})"
        if label:
            clean_lbl = _sanitize_name(label).lower().replace(" ", "_")
            base_id = f"run_{run_id}_{clean_lbl}"
        else:
            base_id = f"run_{run_id}_{mode}_sem{sem_str}"

        # Avoid overwriting an existing snapshot — append a counter if the file exists
        folder = _ensure_dir()
        snapshot_id = base_id
        counter = 2
        while (folder / f"{snapshot_id}.json").exists():
            snapshot_id = f"{base_id}_v{counter}"
            counter += 1

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
                "sections": {
                    str(sid): {
                        "section_id": info.section_id,
                        "semester": info.semester,
                        "subject_code": info.subject_code,
                        "label": info.label,
                        "kind": info.kind,
                        "division": info.division,
                        "batch": info.batch,
                        "class_id": info.class_id,
                        "batch_id": info.batch_id,
                    }
                    for sid, info in plan.sections.items()
                },
                "division_names": {
                    f"{sem}_{k}": name for (sem, k), name in getattr(plan, "division_names", {}).items()
                },
                "batch_names": {
                    f"{sem}_{b}": name for (sem, b), name in getattr(plan, "batch_names", {}).items()
                },
                "config_snapshot": getattr(plan, "config_snapshot", {}),
            }

        display_label = label or default_label
        if counter > 2:
            display_label = f"{display_label} #{counter - 1}"

        snapshot_payload = {
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "label": display_label,
            "mode": mode,
            "semesters": semesters,
            "created_at": created_at,
            "metrics": {
                "status": solve_diag.get("status", run.status.value if hasattr(run.status, "value") else str(run.status)),
                "objective_value": solve_diag.get("objective_value"),
                "penalty_breakdown": solve_diag.get("penalty_breakdown", {}),
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

        file_path = folder / f"{snapshot_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_payload, f, indent=2)

        logger.info("Saved timetable run snapshot to %s", file_path)
        return snapshot_payload

    except Exception as exc:
        logger.warning("Failed to save run snapshot for run %d: %s", run_id, exc)
        return None


def get_active_snapshot_id(store: Optional[Any] = None) -> Optional[str]:
    """Get the currently active snapshot ID from store or pointer file."""
    if store is not None and getattr(store, "active_snapshot_id", None):
        return store.active_snapshot_id
    pointer = SAVED_RUNS_DIR / "active_run.json"
    if pointer.exists():
        try:
            with open(pointer, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("snapshot_id")
        except Exception:
            pass
    return None


def list_saved_snapshots(store: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Return summary metadata for all saved runs on disk."""
    folder = _ensure_dir()
    active_snap = get_active_snapshot_id(store)
    snapshots = []
    for file_path in folder.glob("*.json"):
        if file_path.name == "active_run.json":
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            snap_id = data.get("snapshot_id", file_path.stem)
            snapshots.append({
                "snapshot_id": snap_id,
                "run_id": data.get("run_id"),
                "label": data.get("label", file_path.stem),
                "mode": data.get("mode", "unknown"),
                "semesters": data.get("semesters", []),
                "created_at": data.get("created_at"),
                "metrics": data.get("metrics", {}),
                "section_count": len(data.get("sections", [])),
                "student_count": len(data.get("student_assignments", {})),
                "is_active": (snap_id == active_snap) if active_snap else False,
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

    # 3. Clean and restore student-section assignments for relevant semesters
    relevant_rolls = {
        s.roll_number for s in store.list_students()
        if s.semester in semesters
    }
    for roll in relevant_rolls:
        store.student_section_assignments.pop(roll, None)

    for roll, mapping in snapshot.get("student_assignments", {}).items():
        store.student_section_assignments[roll] = {
            subj_code: int(sid) for subj_code, sid in mapping.items()
        }

    # 4. Restore solver diagnostics cache
    if "metrics" in snapshot:
        store.latest_solve_results[run_id] = dict(snapshot["metrics"])
        store.latest_solve_results[run_id]["run_id"] = run_id
        store.latest_solve_results[run_id]["sections"] = snapshot.get("sections", [])

    # 5. Restore TraditionalPlan if present or if mode is traditional
    plan_dict = snapshot.get("traditional_plan")
    is_traditional = (snapshot.get("mode") == "traditional") or (plan_dict is not None)
    if is_traditional:
        b_map = {}
        div_names = {}
        batch_names = {}
        sec_map = {}
        pins = {}
        sync_groups = []
        warnings = []
        config_snapshot = {}

        if plan_dict:
            for k_str, div in plan_dict.get("batch_division_map", {}).items():
                parts = k_str.split("_")
                if len(parts) == 2:
                    b_map[(int(parts[0]), int(parts[1]))] = div

            for k_str, name in plan_dict.get("division_names", {}).items():
                parts = k_str.split("_")
                if len(parts) == 2:
                    div_names[(int(parts[0]), int(parts[1]))] = name

            for k_str, name in plan_dict.get("batch_names", {}).items():
                parts = k_str.split("_")
                if len(parts) == 2:
                    batch_names[(int(parts[0]), int(parts[1]))] = name

            pins = plan_dict.get("pins", {})
            sync_groups = plan_dict.get("sync_groups", [])
            warnings = plan_dict.get("warnings", [])
            config_snapshot = plan_dict.get("config_snapshot", {})

            if "sections" in plan_dict and plan_dict["sections"]:
                for sid_str, s_info in plan_dict["sections"].items():
                    sec_map[int(sid_str)] = SectionInfo(
                        section_id=int(s_info["section_id"]),
                        semester=int(s_info["semester"]),
                        subject_code=s_info["subject_code"],
                        label=s_info["label"],
                        kind=s_info["kind"],
                        division=s_info.get("division"),
                        batch=s_info.get("batch"),
                        class_id=s_info.get("class_id"),
                        batch_id=s_info.get("batch_id"),
                    )

        # Fallback / ensure sec_map covers all restored sections
        for s_dict in snapshot.get("sections", []):
            sid = int(s_dict["id"])
            if sid not in sec_map:
                lbl = s_dict.get("label", "")
                sub_code = s_dict.get("subject_code", "")
                kind = "dispersal"
                if "-T" in lbl:
                    kind = "division_theory"
                elif "-L" in lbl:
                    kind = "batch_lab"
                subj = store.get_subject(sub_code)
                sem = subj.semester if subj else (semesters[0] if semesters else 0)
                sec_map[sid] = SectionInfo(
                    section_id=sid,
                    semester=sem,
                    subject_code=sub_code,
                    label=lbl,
                    kind=kind,
                )

        # If pins were empty in plan_dict, use student_assignments as pins
        if not pins and snapshot.get("student_assignments"):
            pins = {roll: dict(m) for roll, m in snapshot.get("student_assignments", {}).items()}

        plan = TraditionalPlan(
            run_id=run_id,
            semesters=semesters,
            sections=sec_map,
            pins=pins,
            sync_groups=sync_groups,
            batch_division_map=b_map,
            warnings=warnings,
            division_names=div_names,
            batch_names=batch_names,
            config_snapshot=config_snapshot,
        )
        store.traditional_plans[run_id] = plan
    else:
        store.traditional_plans.pop(run_id, None)

    # 6. Set store active run tracker
    store.active_run_id = run_id
    store.active_snapshot_id = snapshot_id

    # 7. Persist active run pointer to disk so it survives server reloads and role changes
    try:
        folder = _ensure_dir()
        with open(folder / "active_run.json", "w", encoding="utf-8") as f:
            json.dump({"active_run_id": run_id, "snapshot_id": snapshot_id}, f, indent=2)
    except Exception as exc:
        logger.warning("Failed saving active run pointer: %s", exc)

    return {
        "ok": True,
        "active_run_id": run_id,
        "active_snapshot_id": snapshot_id,
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


def ensure_active_run_loaded(store: Any) -> Optional[int]:
    """If store has no active_run_id, try to load it from the active_run.json pointer file."""
    if getattr(store, "active_run_id", None) is not None:
        return store.active_run_id
    if getattr(store, "runs", None) or getattr(store, "student_section_assignments", None) or getattr(store, "sections", None):
        return getattr(store, "active_run_id", None)
    pointer = SAVED_RUNS_DIR / "active_run.json"
    if pointer.exists():
        try:
            with open(pointer, "r", encoding="utf-8") as f:
                data = json.load(f)
            snap_id = data.get("snapshot_id")
            if snap_id and (SAVED_RUNS_DIR / f"{snap_id}.json").exists():
                res = activate_saved_run(store, snap_id)
                return res.get("active_run_id")
        except Exception as exc:
            logger.warning("Failed restoring active run from pointer: %s", exc)
    return getattr(store, "active_run_id", None)


def delete_saved_snapshot(snapshot_id: str) -> bool:
    """Delete a saved run snapshot file."""
    folder = _ensure_dir()
    file_path = folder / f"{_sanitize_name(snapshot_id)}.json"
    pointer = folder / "active_run.json"
    if pointer.exists():
        try:
            with open(pointer, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("snapshot_id") == snapshot_id:
                pointer.unlink(missing_ok=True)
        except Exception:
            pass
    if file_path.exists():
        file_path.unlink()
        return True
    return False
