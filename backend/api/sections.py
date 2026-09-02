"""Admin API for section generation and timetable preparation (Phase 8).

Routes:
  POST /admin/runs/{run_id}/generate-sections
      Trigger section generation for the run's semester.  Clears any
      sections previously generated for this run first (idempotent), then
      calls domain.section_generation.generate_sections_for_run() and
      persists the results.  Returns the generated section list plus a
      warnings list for any unassigned teachers or unresolvable slots.

  GET /admin/runs/{run_id}/sections
      List all sections for a run, with optional ?subject_code= filter.

  GET /admin/runs/{run_id}/sections/{section_id}
      Fetch a single section by ID (must belong to the specified run).

All endpoints are admin-only (product decision #14 role model).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from api.deps import require_admin
from data.store import InMemoryStore, get_store
from domain.models import Section
from domain.section_generation import generate_sections_for_run

router = APIRouter(
    prefix="/admin/runs",
    dependencies=[Depends(require_admin)],
)


# ── Serialisation helper ──────────────────────────────────────────────────

def _section_to_dict(section: Section) -> dict:
    return {
        "id": section.id,
        "run_id": section.run_id,
        "subject_code": section.subject_code,
        "label": section.label,
        "teacher_id": section.teacher_id,
        "capacity": section.capacity,
        "meetings": [
            {"slot_key": m.slot_key or None}
            for m in section.meetings
        ],
    }


# ── Routes ────────────────────────────────────────────────────────────────

@router.post("/{run_id}/generate-sections")
def generate_sections(run_id: int, store: InMemoryStore = Depends(get_store)):
    """Trigger section generation for a run.

    Idempotent: any sections previously generated for this run are cleared
    first.  The caller (admin) can safely re-run this endpoint to regenerate
    after changing teacher availability or the subject catalog, without
    creating duplicate sections.
    """
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # Clear previous sections for this run.
    cleared_count = store.clear_sections_for_run(run_id)

    # Collect all subjects for the run's semester.
    subjects = store.list_subjects(semester=run.semester)

    # Build per-subject capable-teacher lists and teacher availability maps.
    capable_teacher_ids_for = {
        subj.subject_code: store.teachers_for_subject(subj.subject_code)
        for subj in subjects
    }

    all_teacher_ids: List[str] = list({
        tid
        for tids in capable_teacher_ids_for.values()
        for tid in tids
    })
    teacher_availability_map = {
        tid: store.get_teacher_availability(tid)
        for tid in all_teacher_ids
    }

    # Enrolled counts for lab parallelism.
    enrolled_counts = {
        subj.subject_code: store.enrolled_count_for_subject(subj.subject_code, run_id)
        for subj in subjects
    }

    # Determine the next section ID to avoid collisions with existing sections.
    all_existing_ids = list(store.sections.keys())
    section_id_start = (max(all_existing_ids) + 1) if all_existing_ids else 0

    result = generate_sections_for_run(
        run=run,
        subjects=subjects,
        all_slots=store.list_time_slots(),
        capable_teacher_ids_for=capable_teacher_ids_for,
        teacher_availability_map=teacher_availability_map,
        enrolled_counts=enrolled_counts,
        section_id_start=section_id_start,
    )

    # Persist sections.
    for section in result.sections:
        store.add_section(section)

    return {
        "run_id": run_id,
        "cleared_count": cleared_count,
        "generated_count": len(result.sections),
        "sections": [_section_to_dict(s) for s in result.sections],
        "warnings": [
            {"subject_code": w.subject_code, "message": w.message}
            for w in result.warnings
        ],
    }


@router.get("/{run_id}/sections")
def list_sections(
    run_id: int,
    subject_code: Optional[str] = None,
    store: InMemoryStore = Depends(get_store),
):
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    sections = store.list_sections_for_run(run_id)
    if subject_code is not None:
        sections = [s for s in sections if s.subject_code == subject_code]

    return {
        "run_id": run_id,
        "count": len(sections),
        "sections": [_section_to_dict(s) for s in sections],
    }


@router.get("/{run_id}/sections/{section_id}")
def get_section(run_id: int, section_id: int, store: InMemoryStore = Depends(get_store)):
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    section = store.get_section(section_id)
    if section is None or section.run_id != run_id:
        raise HTTPException(status_code=404, detail="Section not found in this run")

    return _section_to_dict(section)
