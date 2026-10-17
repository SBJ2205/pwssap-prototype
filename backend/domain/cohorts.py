"""Domain models for Traditional Cohort & Batch Scheduling Mode.

In this mode, students are structured into:
- Classes / Divisions (e.g. Div A, Div B, Div C).
  - If the semester has a Professional Elective (PE), classes are aligned with PE tracks (e.g. AIML, CyberSec).
  - If there is no PE (e.g. Sem 4 with MDM only), classes are drawn by admin cuts, and non-PE electives disperse during a synchronized common slot.
  - Edge case: If an elective tag in that semester has only 1 subject (e.g. Sem 6 MDM03), it is NOT a dispersal elective; all students take it in-class.
- Lab Batches (e.g. A1, A2, A3 or A1..A4):
  - Each class is subdivided into configurable number of lab batches (e.g. 2, 3, 4, etc.).
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class LabBatch:
    batch_id: str                      # e.g. "A1", "A2", "B1"
    batch_name: str                    # e.g. "Batch A1"
    student_rolls: List[str] = field(default_factory=list)


@dataclass
class ClassCohort:
    class_id: str                      # e.g. "Div-A", "Div-B", "Div-C"
    class_name: str                    # e.g. "Division A"
    semester: int
    pe_tag: Optional[str] = None       # e.g. "PE" or None if no PE
    pe_subject_code: Optional[str] = None
    pe_subtag: Optional[str] = None    # e.g. "PE-AIML"
    student_rolls: List[str] = field(default_factory=list)
    lab_batch_count: int = 3           # 2, 3, 4, etc.
    batches: List[LabBatch] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "semester": self.semester,
            "pe_tag": self.pe_tag,
            "pe_subject_code": self.pe_subject_code,
            "pe_subtag": self.pe_subtag,
            "student_rolls": list(self.student_rolls),
            "lab_batch_count": self.lab_batch_count,
            "batches": [
                {
                    "batch_id": b.batch_id,
                    "batch_name": b.batch_name,
                    "student_rolls": list(b.student_rolls),
                }
                for b in self.batches
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClassCohort":
        batches = [
            LabBatch(
                batch_id=b["batch_id"],
                batch_name=b.get("batch_name", f"Batch {b['batch_id']}"),
                student_rolls=list(b.get("student_rolls", [])),
            )
            for b in data.get("batches", [])
        ]
        return cls(
            class_id=data["class_id"],
            class_name=data.get("class_name", data["class_id"]),
            semester=int(data["semester"]),
            pe_tag=data.get("pe_tag"),
            pe_subject_code=data.get("pe_subject_code"),
            pe_subtag=data.get("pe_subtag"),
            student_rolls=list(data.get("student_rolls", [])),
            lab_batch_count=int(data.get("lab_batch_count", 3)),
            batches=batches,
        )


@dataclass
class SemesterCohortConfig:
    semester: int
    classes: List[ClassCohort] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "semester": self.semester,
            "classes": [c.to_dict() for c in self.classes],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SemesterCohortConfig":
        return cls(
            semester=int(data["semester"]),
            classes=[ClassCohort.from_dict(c) for c in data.get("classes", [])],
        )
