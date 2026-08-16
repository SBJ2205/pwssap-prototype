"""Post-processing heuristics that run AFTER the CP-SAT optimum is found:

- apply_gap_reduction: a second pass that shifts students into alternative
  sections of the same subject to remove idle schedule gaps, but only when
  doing so never increases that student's (and therefore the global) penalty.
- run_baseline / score_schedule: independent, non-optimizing FCFS and random
  heuristics used purely for the dashboard's "how much better is the solver"
  comparison. They still respect the same hard constraints (capacity, block,
  no-clash) — an infeasible baseline wouldn't be a meaningful comparison.
"""
import random as pyrandom
from collections import defaultdict
from typing import Dict, List, Tuple

from data.store import InMemoryStore
from domain.models import Section
from solver.helpers import gap_count, slot_blocked, slot_faculty_penalty, slot_time_keys, slot_time_penalty


def apply_gap_reduction(store: InMemoryStore, assignments: List[dict], faculty_weight: int, passes: int = 2) -> dict:
    sections = store.list_sections()
    section_by_id: Dict[int, Section] = {sec.id: sec for sec in sections}
    subject_sections: Dict[str, List[int]] = defaultdict(list)
    for sec in sections:
        subject_sections[sec.subject_code].append(sec.id)

    occ: Dict[int, int] = defaultdict(int)
    for a in assignments:
        for asn in a["assignments"]:
            occ[asn["slot_id"]] += 1

    def student_daytimes(a):
        dts = set()
        for asn in a["assignments"]:
            for m in asn["meetings"]:
                dts.add((m["day"], m["time"]))
        return dts

    total_gaps_before = sum(gap_count(student_daytimes(a)) for a in assignments)
    changes = []

    for _ in range(passes):
        for a in assignments:
            s = a["student_id"]
            ts_prefs = store.get_ts_prefs(s)
            fac_prefs = store.get_faculty_prefs(s)
            for asn in a["assignments"]:
                code = asn["code"]
                cur_sid = asn["slot_id"]
                cur_penalty = asn["penalty"]

                other_daytimes = set()
                for other in a["assignments"]:
                    if other is asn:
                        continue
                    for m in other["meetings"]:
                        other_daytimes.add((m["day"], m["time"]))
                cur_meeting_dts = {(m["day"], m["time"]) for m in asn["meetings"]}
                cur_gap = gap_count(other_daytimes | cur_meeting_dts)

                best = None
                for alt_sid in subject_sections[code]:
                    if alt_sid == cur_sid:
                        continue
                    alt_section = section_by_id[alt_sid]
                    if slot_blocked(alt_section, ts_prefs):
                        continue
                    if occ[alt_sid] >= alt_section.capacity:
                        continue
                    alt_daytimes = [(m.day, m.time) for m in alt_section.meetings]
                    if any(dt in other_daytimes for dt in alt_daytimes):
                        continue  # would clash with this student's other subjects

                    alt_time_pen = slot_time_penalty(alt_section, ts_prefs)
                    alt_frating, alt_fac_pen = slot_faculty_penalty(alt_section, fac_prefs, faculty_weight)
                    alt_penalty = alt_time_pen + alt_fac_pen
                    if alt_penalty > cur_penalty:
                        continue  # never degrade this student's (=> the global) penalty

                    new_gap = gap_count(other_daytimes | set(alt_daytimes))
                    if new_gap < cur_gap:
                        key = (new_gap, alt_penalty)
                        if best is None or key < (best[0], best[1]):
                            best = (new_gap, alt_penalty, alt_sid, alt_section, alt_time_pen, alt_fac_pen, alt_frating)

                if best:
                    new_gap, alt_penalty, alt_sid, alt_section, alt_time_pen, alt_fac_pen, alt_frating = best
                    occ[cur_sid] -= 1
                    occ[alt_sid] += 1
                    worst_rating = max((ts_prefs.get(k, 1) for k in slot_time_keys(alt_section)), default=1)
                    changes.append({
                        "student_id": s, "name": a["name"], "subject_code": code,
                        "from_section": asn["section"], "to_section": alt_section.label,
                        "gap_before": cur_gap, "gap_after": new_gap,
                    })
                    asn.update({
                        "section": alt_section.label,
                        "faculty": store.get_teacher(alt_section.teacher_id).name,
                        "room": alt_section.room,
                        "slot_id": alt_sid,
                        "meetings": [{"day": m.day, "time": m.time} for m in alt_section.meetings],
                        "time_penalty": alt_time_pen,
                        "faculty_rating": alt_frating,
                        "faculty_penalty": alt_fac_pen,
                        "penalty": alt_penalty,
                        "rating": worst_rating,
                    })
                    a["penalty"] += (alt_penalty - cur_penalty)

    total_gaps_after = sum(gap_count(student_daytimes(a)) for a in assignments)
    return {
        "swaps_applied": len(changes),
        "total_gaps_before": total_gaps_before,
        "total_gaps_after": total_gaps_after,
        "changes": changes,
    }


def _feasible_domain(store: InMemoryStore, student_id: int, section_ids: List[int]) -> List[int]:
    ts_prefs = store.get_ts_prefs(student_id)
    return [sid for sid in section_ids if not slot_blocked(store.get_section(sid), ts_prefs)]


def run_baseline(store: InMemoryStore, mode: str) -> Tuple[Dict[int, Dict[str, int]], List[Tuple[int, str]]]:
    """mode='fcfs': registration-order, first-fit-by-id, no preference awareness.
    mode='random': random student/subject/section order. Both are subject to
    the SAME hard constraints (capacity, block, no-clash) as the CP-SAT model."""
    students = store.list_students()
    sections = store.list_sections()
    section_by_id: Dict[int, Section] = {sec.id: sec for sec in sections}
    subject_sections: Dict[str, List[int]] = defaultdict(list)
    for sec in sections:
        subject_sections[sec.subject_code].append(sec.id)

    occ: Dict[int, int] = defaultdict(int)
    schedules: Dict[int, Dict[str, int]] = {stu.id: {} for stu in students}
    booked: Dict[int, set] = {stu.id: set() for stu in students}
    unassigned: List[Tuple[int, str]] = []

    student_order = [stu.id for stu in students]
    if mode == "random":
        pyrandom.shuffle(student_order)

    for s in student_order:
        subj_order = list(subject_sections.keys())
        if mode == "random":
            pyrandom.shuffle(subj_order)
        for subj in subj_order:
            candidates = _feasible_domain(store, s, subject_sections[subj])
            if mode == "random":
                pyrandom.shuffle(candidates)
            chosen = None
            for sid in candidates:
                sec = section_by_id[sid]
                if occ[sid] >= sec.capacity:
                    continue
                meet_dts = [(m.day, m.time) for m in sec.meetings]
                if any(dt in booked[s] for dt in meet_dts):
                    continue
                chosen = sid
                break
            if chosen is None:
                unassigned.append((s, subj))
                continue
            occ[chosen] += 1
            schedules[s][subj] = chosen
            for m in section_by_id[chosen].meetings:
                booked[s].add((m.day, m.time))

    return schedules, unassigned


def score_schedule(store: InMemoryStore, schedules: Dict[int, Dict[str, int]], faculty_weight: int) -> int:
    total = 0
    for s, subj_map in schedules.items():
        ts_prefs = store.get_ts_prefs(s)
        fac_prefs = store.get_faculty_prefs(s)
        for _subj, sid in subj_map.items():
            sec = store.get_section(sid)
            total += slot_time_penalty(sec, ts_prefs)
            _, fac_pen = slot_faculty_penalty(sec, fac_prefs, faculty_weight)
            total += fac_pen
    return total
