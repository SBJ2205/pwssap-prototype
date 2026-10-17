"""Cohort management API router for Traditional Division & Batch Scheduling mode."""
import math
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from data.store import InMemoryStore, get_store
from domain.cohorts import ClassCohort, LabBatch, SemesterCohortConfig
from domain.traditional_section_generation import generate_traditional_sections_for_semester

router = APIRouter(prefix="/admin/cohorts", tags=["Cohorts"])


class ClassCohortPayload(BaseModel):
    class_id: str = Field(..., description="e.g. Div-A, Div-B, Div-C")
    class_name: Optional[str] = None
    pe_tag: Optional[str] = None
    pe_subject_code: Optional[str] = None
    pe_subtag: Optional[str] = None
    student_rolls: List[str] = Field(default_factory=list)
    lab_batch_count: int = Field(default=3, ge=1, le=10)


class SaveCohortConfigPayload(BaseModel):
    semester: int
    classes: List[ClassCohortPayload]


@router.get("/detect-clusters")
def detect_clusters(
    semester: int = Query(..., ge=1, le=8),
    store: InMemoryStore = Depends(get_store),
):
    """Detect PE tracks, dispersal electives, and in-class electives for a semester."""
    return store.detect_pe_clusters(semester)


@router.get("")
def get_cohort_config(
    semester: int = Query(..., ge=1, le=8),
    store: InMemoryStore = Depends(get_store),
):
    """Get the saved cohort configuration for a semester."""
    config = store.get_semester_cohorts(semester)
    if not config:
        return {"semester": semester, "classes": []}
    return config.to_dict()


@router.post("/save")
def save_cohort_config(
    payload: SaveCohortConfigPayload,
    store: InMemoryStore = Depends(get_store),
):
    """Save class divisions and automatically partition each class into lab batches."""
    sem_students = {s.roll_number: s for s in store.students.values() if s.semester == payload.semester}

    assigned_rolls = set()
    classes: List[ClassCohort] = []

    for cls_p in payload.classes:
        for roll in cls_p.student_rolls:
            if roll not in sem_students:
                raise HTTPException(
                    status_code=400,
                    detail=f"Student {roll} does not belong to semester {payload.semester}.",
                )
            if roll in assigned_rolls:
                raise HTTPException(
                    status_code=400,
                    detail=f"Student {roll} is assigned to multiple classes.",
                )
            assigned_rolls.add(roll)

        rolls = list(cls_p.student_rolls)
        num_batches = max(1, cls_p.lab_batch_count)
        batch_size = math.ceil(len(rolls) / num_batches) if rolls else 0

        batches: List[LabBatch] = []
        for b_idx in range(num_batches):
            batch_slice = rolls[b_idx * batch_size : (b_idx + 1) * batch_size] if batch_size > 0 else []
            cls_letter = cls_p.class_id.replace("Div-", "").replace("DIV-", "").strip() or f"C{len(classes)+1}"
            batch_id = f"{cls_letter}{b_idx + 1}"
            batches.append(LabBatch(
                batch_id=batch_id,
                batch_name=f"Batch {batch_id}",
                student_rolls=batch_slice,
            ))

        classes.append(ClassCohort(
            class_id=cls_p.class_id,
            class_name=cls_p.class_name or cls_p.class_id,
            semester=payload.semester,
            pe_tag=cls_p.pe_tag,
            pe_subject_code=cls_p.pe_subject_code,
            pe_subtag=cls_p.pe_subtag,
            student_rolls=rolls,
            lab_batch_count=num_batches,
            batches=batches,
        ))

    config = SemesterCohortConfig(semester=payload.semester, classes=classes)
    saved = store.set_semester_cohorts(payload.semester, config)
    return {"status": "ok", "config": saved.to_dict()}


@router.delete("")
def delete_cohort_config(
    semester: int = Query(..., ge=1, le=8),
    store: InMemoryStore = Depends(get_store),
):
    """Delete cohort configuration for a semester."""
    store.clear_semester_cohorts(semester)
    return {"status": "ok", "semester": semester}


class GenerateSectionsPayload(BaseModel):
    semester: int


@router.post("/generate-sections")
def generate_sections(
    payload: GenerateSectionsPayload,
    store: InMemoryStore = Depends(get_store),
):
    """Generate traditional division & batch sections and assign students."""
    try:
        result = generate_traditional_sections_for_semester(store, payload.semester)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
