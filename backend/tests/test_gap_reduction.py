"""Unit tests for the schedule gap reduction post-processing pass."""
import unittest
from types import SimpleNamespace

from domain.enums import PreferenceRating
from domain.models import Meeting, Section
from solver.gap_reduction import compute_student_gaps, reduce_schedule_gaps


class TestGapReduction(unittest.TestCase):
    def test_compute_student_gaps(self):
        # Mon-1 and Mon-2 -> 0 gaps
        meetings = {
            1: [Meeting(slot_key="Mon-1", duration_hours=2)],
            2: [Meeting(slot_key="Mon-2", duration_hours=2)],
        }
        self.assertEqual(compute_student_gaps([1, 2], meetings), 0)

        # Mon-1 and Mon-3 -> 1 gap (Mon-2 is idle)
        meetings = {
            1: [Meeting(slot_key="Mon-1", duration_hours=2)],
            2: [Meeting(slot_key="Mon-3", duration_hours=2)],
        }
        self.assertEqual(compute_student_gaps([1, 2], meetings), 1)

        # Mon-1 and Mon-4 -> 2 gaps (Mon-2 and Mon-3 idle)
        meetings = {
            1: [Meeting(slot_key="Mon-1", duration_hours=2)],
            2: [Meeting(slot_key="Mon-4", duration_hours=2)],
        }
        self.assertEqual(compute_student_gaps([1, 2], meetings), 2)

        # Multi-day: Mon has 1 gap, Tue has 0 gaps
        meetings = {
            1: [Meeting(slot_key="Mon-1", duration_hours=2)],
            2: [Meeting(slot_key="Mon-3", duration_hours=2)],
            3: [Meeting(slot_key="Tue-2", duration_hours=2)],
            4: [Meeting(slot_key="Tue-3", duration_hours=2)],
        }
        self.assertEqual(compute_student_gaps([1, 2, 3, 4], meetings), 1)

    def test_gap_reduction_does_not_force_disliked_or_blocked_slots(self):
        """CRITICAL: User requirement:

        Do not move student into a gap-reducing section if the student marked
        the slot as DISLIKED or BLOCKED.
        """
        # Section 10 (Theory): Mon-1
        # Section 21 (Lab Batch 1): Mon-3 (Creates gap in Mon-2 for student in Sec 10)
        # Section 22 (Lab Batch 2): Mon-2 (Would close gap, but is DISLIKED by student S1)
        sec10 = Section(id=10, subject_code="CS101", label="T1", teacher_id="T1", capacity=30, meetings=[Meeting(slot_key="Mon-1", duration_hours=2)])
        sec21 = Section(id=21, subject_code="CS101P", label="L1", teacher_id="T2", capacity=15, meetings=[Meeting(slot_key="Mon-3", duration_hours=2)])
        sec22 = Section(id=22, subject_code="CS101P", label="L2", teacher_id="T3", capacity=15, meetings=[Meeting(slot_key="Mon-2", duration_hours=2)])

        assigned_meetings = {
            10: [Meeting(slot_key="Mon-1", duration_hours=2)],
            21: [Meeting(slot_key="Mon-3", duration_hours=2)],
            22: [Meeting(slot_key="Mon-2", duration_hours=2)],
        }
        assigned_teachers = {10: "T1", 21: "T2", 22: "T3"}

        # Student S1 has Sec 10 and Sec 21 -> Gap in Mon-2!
        student_assignments = {
            "S1": {"CS101": 10, "CS101P": 21},
        }

        # Student S1 explicitly marked Mon-2 as DISLIKED (rating=3)
        time_preferences = {
            "S1": {"Mon-1": 1, "Mon-2": PreferenceRating.DISLIKED.value, "Mon-3": 1},
        }

        inp = SimpleNamespace(
            sections=[sec10, sec21, sec22],
            time_preferences=time_preferences,
            faculty_preferences={},
        )

        updated_assignments, stats = reduce_schedule_gaps(
            inp=inp,
            assigned_meetings=assigned_meetings,
            assigned_teachers=assigned_teachers,
            student_assignments=student_assignments,
        )

        # S1 MUST remain in Section 21 because Mon-2 was marked DISLIKED!
        self.assertEqual(updated_assignments["S1"]["CS101P"], 21)
        self.assertEqual(stats["gaps_reduced"], 0)

    def test_gap_reduction_swaps_when_preferred(self):
        """When the slot is preferred, the pass successfully moves the student

        to eliminate the idle gap.
        """
        sec10 = Section(id=10, subject_code="CS101", label="T1", teacher_id="T1", capacity=30, meetings=[Meeting(slot_key="Mon-1", duration_hours=2)])
        sec21 = Section(id=21, subject_code="CS101P", label="L1", teacher_id="T2", capacity=15, meetings=[Meeting(slot_key="Mon-3", duration_hours=2)])
        sec22 = Section(id=22, subject_code="CS101P", label="L2", teacher_id="T3", capacity=15, meetings=[Meeting(slot_key="Mon-2", duration_hours=2)])

        assigned_meetings = {
            10: [Meeting(slot_key="Mon-1", duration_hours=2)],
            21: [Meeting(slot_key="Mon-3", duration_hours=2)],
            22: [Meeting(slot_key="Mon-2", duration_hours=2)],
        }
        assigned_teachers = {10: "T1", 21: "T2", 22: "T3"}

        student_assignments = {
            "S1": {"CS101": 10, "CS101P": 21},
        }

        # Student S1 likes Mon-2 (rating=1 Preferred)
        time_preferences = {
            "S1": {"Mon-1": 1, "Mon-2": PreferenceRating.PREFERRED.value, "Mon-3": 1},
        }

        inp = SimpleNamespace(
            sections=[sec10, sec21, sec22],
            time_preferences=time_preferences,
            faculty_preferences={},
        )

        updated_assignments, stats = reduce_schedule_gaps(
            inp=inp,
            assigned_meetings=assigned_meetings,
            assigned_teachers=assigned_teachers,
            student_assignments=student_assignments,
        )

        # S1 should be moved to Section 22 (Mon-2), eliminating the gap between Mon-1 and Mon-3!
        self.assertEqual(updated_assignments["S1"]["CS101P"], 22)
        self.assertEqual(stats["gaps_reduced"], 1)
        self.assertEqual(stats["improved_students"], 1)

    def test_gap_reduction_pairwise_swap(self):
        """Two students in parallel sections swap to reduce total gaps."""
        assigned_meetings = {
            10: [Meeting(slot_key="Mon-1", duration_hours=2)],
            20: [Meeting(slot_key="Mon-3", duration_hours=2)],
            31: [Meeting(slot_key="Mon-2", duration_hours=2)],
            32: [Meeting(slot_key="Mon-3", duration_hours=2)],
        }
        assigned_teachers = {10: "T1", 20: "T2", 31: "T3", 32: "T4"}
        sec10 = Section(id=10, subject_code="CS101", label="T1", teacher_id="T1", capacity=30, meetings=assigned_meetings[10])
        sec20 = Section(id=20, subject_code="CS102", label="T2", teacher_id="T2", capacity=30, meetings=assigned_meetings[20])
        sec31 = Section(id=31, subject_code="CS103P", label="L1", teacher_id="T3", capacity=1, meetings=assigned_meetings[31])
        sec32 = Section(id=32, subject_code="CS103P", label="L2", teacher_id="T4", capacity=1, meetings=assigned_meetings[32])

        # S1 has Sec 10 (Mon-1) and Sec 32 (Mon-3) -> Gap in Mon-2!
        # S2 has Sec 20 (Mon-3) and Sec 31 (Mon-2) -> Mon-2 and Mon-3 back-to-back -> 0 gaps
        student_assignments = {
            "S1": {"CS101": 10, "CS103P": 32},
            "S2": {"CS102": 20, "CS103P": 31},
        }

        # Both like all slots
        time_preferences = {
            "S1": {"Mon-1": 1, "Mon-2": 1, "Mon-3": 1},
            "S2": {"Mon-1": 1, "Mon-2": 1, "Mon-3": 1},
        }

        inp = SimpleNamespace(
            sections=[sec10, sec20, sec31, sec32],
            time_preferences=time_preferences,
            faculty_preferences={},
        )

        updated_assignments, stats = reduce_schedule_gaps(
            inp=inp,
            assigned_meetings=assigned_meetings,
            assigned_teachers=assigned_teachers,
            student_assignments=student_assignments,
        )

        # S2 has CS102 at Mon-3 and CS103P at Mon-3 if swapped to Sec 32, which would clash!
        # So clash check prevents swap.
        self.assertEqual(updated_assignments["S2"]["CS103P"], 31)


if __name__ == "__main__":
    unittest.main()
