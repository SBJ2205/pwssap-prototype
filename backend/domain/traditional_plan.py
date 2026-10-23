"""The record of a run that was generated in Traditional (division/batch) mode.

A TraditionalPlan is created by domain.traditional_section_generation and kept in
``store.traditional_plans[run_id]``. It remembers things the generic section
records cannot express:

- ``pins``: each student's fixed section per subject (their division/batch).
- ``batch_division_map``: the explicit parent division of every lab batch.
- ``sync_groups``: dispersal elective sections that must run at the same time.

It also provides the two hooks used by solver.service. Both do nothing for any
run that has no live plan, so the preference-weighted flow is untouched:

- ``solver_overrides_for_run``  extra SolverInput fields for a traditional run.
- ``finalize_traditional_run``  re-applies the pinned students after the solver
  and checks the result with domain.traditional_validation.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from domain.enums import RunStatus

# Kinds of traditional section.
DIVISION_THEORY = "division_theory"   # "-T{k}": one section per division
BATCH_LAB = "batch_lab"               # "-L{b}": one section per lab batch
DISPERSAL = "dispersal"               # elective section shared across divisions


@dataclass
class SectionInfo:
    section_id: int
    semester: int
    subject_code: str
    label: str
    kind: str
    division: Optional[int] = None     # engine division index k
    batch: Optional[int] = None        # engine batch index b
    class_id: Optional[str] = None
    batch_id: Optional[str] = None


@dataclass
class StudentUnit:
    semester: int
    class_id: str
    division: int
    batch_id: str
    batch: int


@dataclass
class TraditionalPlan:
    run_id: int
    semesters: List[int]
    sections: Dict[int, SectionInfo] = field(default_factory=dict)
    pins: Dict[str, Dict[str, int]] = field(default_factory=dict)
    student_units: Dict[str, StudentUnit] = field(default_factory=dict)
    sync_groups: List[List[int]] = field(default_factory=list)
    batch_division_map: Dict[Tuple[int, int], int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    # semester -> {division index: class_id} and {batch index: batch_id}
    division_names: Dict[Tuple[int, int], str] = field(default_factory=dict)
    batch_names: Dict[Tuple[int, int], str] = field(default_factory=dict)
    config_snapshot: Dict[int, dict] = field(default_factory=dict)
    last_report: Optional[dict] = None   # validation report from the latest solve


def get_live_plan(store: Any, run_id: int) -> Optional[TraditionalPlan]:
    """The run's plan, if its sections are still exactly the ones it generated.

    Standard generation (or deleting/regenerating anything) changes the run's
    sections, which silently retires the plan: it is then ignored everywhere.
    """
    plan = getattr(store, "traditional_plans", {}).get(run_id)
    if plan is None:
        return None
    live = {s.id: s for s in store.list_sections_for_run(run_id)}
    if set(live) != set(plan.sections):
        return None
    for sid, info in plan.sections.items():
        section = live[sid]
        if section.label != info.label or section.subject_code != info.subject_code:
            return None
    return plan


def plan_staleness(store: Any, run_id: int) -> Optional[str]:
    """Why a registered plan is no longer live, or None when live / absent."""
    if run_id not in getattr(store, "traditional_plans", {}):
        return None
    if get_live_plan(store, run_id) is None:
        return "The run's sections were regenerated or changed after the traditional sections were generated."
    return None


def solver_overrides_for_run(store: Any, run_id: int) -> Dict[str, Any]:
    """Extra SolverInput fields for a traditional run; {} for every other run."""
    plan = get_live_plan(store, run_id)
    if plan is None:
        return {}
    return {
        "batch_division_map": dict(plan.batch_division_map),
        "sync_section_groups": [list(group) for group in plan.sync_groups],
        "pinned_student_sections": {roll: dict(m) for roll, m in plan.pins.items()},
    }


def apply_pins(store: Any, plan: TraditionalPlan) -> None:
    """Make the saved division/batch memberships the live student assignments."""
    for roll, mapping in plan.pins.items():
        store.student_section_assignments[roll] = dict(mapping)


def finalize_traditional_run(store: Any, run: Any, result: Any) -> None:
    """After a successful solve of a traditional run: pin students and validate.

    Replaces whatever Stage 2 assigned with the saved divisions/batches, then
    validates the final timetable. Violations are reported in ``result.warnings``
    and the run is left SOLVED (not PUBLISHED) instead of publishing silently.
    """
    plan = get_live_plan(store, run.id)
    if plan is None:
        return
    from domain.traditional_validation import summarise_report, validate_traditional_run

    apply_pins(store, plan)
    result.student_section_assignments = {roll: dict(m) for roll, m in plan.pins.items()}

    report = validate_traditional_run(store, run, plan)
    plan.last_report = report
    result.warnings.extend(summarise_report(report))
    if not report["ok"]:
        run.status = RunStatus.SOLVED
