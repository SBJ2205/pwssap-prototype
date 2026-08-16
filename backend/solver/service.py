"""Top-level solve orchestration.

Runs the CP-SAT engine, then the gap-reduction heuristic pass, then computes
baseline comparisons, and shapes everything into the response dict the
/solve API route returns. This is the only function api/solver_routes.py
calls into — engine.py and heuristics.py are implementation details of it.
"""
from data.store import InMemoryStore
from solver.engine import solve_cp_sat
from solver.heuristics import apply_gap_reduction, run_baseline, score_schedule


def run_solve(store: InMemoryStore, fairness_index: int, faculty_weight: int, enable_gap_reduction: bool) -> dict:
    outcome = solve_cp_sat(store, fairness_index, faculty_weight)
    if outcome.status != "OPTIMAL" or outcome.assignments is None:
        return {"status": "INFEASIBLE", "message": outcome.message}

    assignments = outcome.assignments

    gap_reduction = None
    if enable_gap_reduction:
        gap_reduction = apply_gap_reduction(store, assignments, faculty_weight)

    total_penalty = sum(a["penalty"] for a in assignments)

    fcfs_schedules, fcfs_unassigned = run_baseline(store, "fcfs")
    random_schedules, random_unassigned = run_baseline(store, "random")
    baselines = {
        "fcfs": {
            "total_penalty": score_schedule(store, fcfs_schedules, faculty_weight),
            "unassigned_count": len(fcfs_unassigned),
            "feasible": len(fcfs_unassigned) == 0,
        },
        "random": {
            "total_penalty": score_schedule(store, random_schedules, faculty_weight),
            "unassigned_count": len(random_unassigned),
            "feasible": len(random_unassigned) == 0,
        },
    }

    result = {
        "status": "OPTIMAL",
        "total_penalty": total_penalty,
        "objective_total_penalty": outcome.objective_total_penalty,
        "assignments": assignments,
        "solver_time_ms": outcome.wall_time_ms,
        "gap_reduction": gap_reduction,
        "baselines": baselines,
    }
    store.set_last_result(result)
    return result
