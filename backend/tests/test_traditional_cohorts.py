import unittest
from fastapi.testclient import TestClient

from main import app
from data.store import get_store, reset_store
from domain.models import Student, StudentChoiceSelection, Subject, Teacher, TeacherSubjectCapability


class TestTraditionalCohorts(unittest.TestCase):
    def setUp(self):
        reset_store()
        self.store = get_store()
        self.client = TestClient(app)

        # Teachers
        for t_idx in range(1, 6):
            tid = f"T{t_idx}"
            self.store.upsert_teacher(Teacher(teacher_id=tid, teacher_name=f"Teacher {tid}"))

        # Capabilities
        caps = [
            ("T1", "CS601"), ("T2", "CS601"),
            ("T1", "CS601P"), ("T2", "CS601P"),
            ("T3", "MDM03"), ("T4", "MDM03"),
            ("T4", "PE_AIML"), ("T5", "PE_CSEC"),
            ("T1", "CS401"), ("T2", "MDM_A"), ("T3", "MDM_B"),
        ]
        for tid, code in caps:
            self.store.teacher_capabilities.append(
                TeacherSubjectCapability(teacher_id=tid, subject_code=code)
            )

        # Sem 6 Subjects:
        # - Core Theory CS601
        # - Core Lab CS601P
        # - MDM03 (Only 1 subject in Sem 6 -> In-class elective edge case!)
        # - PE_AIML and PE_CSEC (2 subjects under PE -> PE tracks!)
        self.store.upsert_subject(Subject(
            subject_code="CS601", subject_name="Distributed Systems", weekly_hours=3,
            capacity=60, type="theory", semester=6, subject_tag="CORE"
        ))
        self.store.upsert_subject(Subject(
            subject_code="CS601P", subject_name="DS Lab", weekly_hours=2,
            capacity=20, type="lab", semester=6, subject_tag="CORE"
        ))
        # Sem 6 MDM single subject
        self.store.upsert_subject(Subject(
            subject_code="MDM03", subject_name="Management & Data Mining", weekly_hours=2,
            capacity=60, type="theory", semester=6, subject_tag="MDM", subtag="MDM03"
        ))
        # Sem 6 PE tracks
        self.store.upsert_subject(Subject(
            subject_code="PE_AIML", subject_name="Deep Learning", weekly_hours=3,
            capacity=60, type="theory", semester=6, subject_tag="PE", subtag="AIML"
        ))
        self.store.upsert_subject(Subject(
            subject_code="PE_CSEC", subject_name="Cyber Forensics", weekly_hours=3,
            capacity=60, type="theory", semester=6, subject_tag="PE", subtag="CSEC"
        ))

        # Sem 4 Subjects:
        # - Core CS401
        # - Dispersal MDM with 2 subjects (MDM_A, MDM_B)
        self.store.upsert_subject(Subject(
            subject_code="CS401", subject_name="Data Structures", weekly_hours=3,
            capacity=60, type="theory", semester=4, subject_tag="CORE"
        ))
        self.store.upsert_subject(Subject(
            subject_code="MDM_A", subject_name="Bioinformatics", weekly_hours=2,
            capacity=60, type="theory", semester=4, subject_tag="MDM", subtag="BIO"
        ))
        self.store.upsert_subject(Subject(
            subject_code="MDM_B", subject_name="Industrial IoT", weekly_hours=2,
            capacity=60, type="theory", semester=4, subject_tag="MDM", subtag="IIOT"
        ))

        # Sem 6 Students: 6 students (4 AIML, 2 CSEC)
        for i in range(1, 5):
            roll = f"24101A010{i}"
            self.store.upsert_student(Student(roll_number=roll, name=f"Student {i}", semester=6))
            self.store.set_student_choice_selections(roll, [
                StudentChoiceSelection(roll_number=roll, tag="PE", subtag="AIML"),
                StudentChoiceSelection(roll_number=roll, tag="MDM", subtag="MDM03"),
            ])
        for i in range(5, 7):
            roll = f"24101A010{i}"
            self.store.upsert_student(Student(roll_number=roll, name=f"Student {i}", semester=6))
            self.store.set_student_choice_selections(roll, [
                StudentChoiceSelection(roll_number=roll, tag="PE", subtag="CSEC"),
                StudentChoiceSelection(roll_number=roll, tag="MDM", subtag="MDM03"),
            ])

        # Sem 4 Students: 4 students
        for i in range(1, 5):
            roll = f"25101A010{i}"
            self.store.upsert_student(Student(roll_number=roll, name=f"S4 Student {i}", semester=4))
            subtag = "BIO" if i <= 2 else "IIOT"
            self.store.set_student_choice_selections(roll, [
                StudentChoiceSelection(roll_number=roll, tag="MDM", subtag=subtag),
            ])

    def test_detect_pe_clusters_sem6_and_single_subject_mdm_edge_case(self):
        """Verify Sem 6 clusters by PE, and MDM with 1 subject is NOT marked for dispersal."""
        res = self.client.get("/admin/cohorts/detect-clusters?semester=6")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertTrue(data["has_pe"])
        self.assertEqual(data["pe_tag"], "PE")
        self.assertEqual(len(data["clusters"]), 2)

        # Tracks: AIML (4 students) and CSEC (2 students)
        tracks = {c["track_id"]: c["student_count"] for c in data["clusters"]}
        self.assertEqual(tracks.get("AIML"), 4)
        self.assertEqual(tracks.get("CSEC"), 2)

        # Crucial Edge Case: Sem 6 MDM has only 1 subject -> In-Class Elective (0 dispersal)
        in_class = data["in_class_electives"]
        self.assertEqual(len(in_class), 1)
        self.assertEqual(in_class[0]["subject_code"], "MDM03")
        self.assertFalse(in_class[0]["is_dispersal"])
        self.assertEqual(len(data["dispersal_electives"]), 0)

    def test_detect_dispersal_electives_sem4_without_pe(self):
        """Verify Sem 4 has no PE, single pool, and MDM with 2 subjects IS marked for dispersal."""
        res = self.client.get("/admin/cohorts/detect-clusters?semester=4")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertFalse(data["has_pe"])
        self.assertEqual(len(data["clusters"]), 1)
        self.assertEqual(data["clusters"][0]["track_id"], "ALL")
        self.assertEqual(data["clusters"][0]["student_count"], 4)

        # Sem 4 MDM has 2 subjects -> Dispersal Elective
        dispersal = data["dispersal_electives"]
        self.assertEqual(len(dispersal), 1)
        self.assertTrue(dispersal[0]["is_dispersal"])
        subj_codes = {s["subject_code"] for s in dispersal[0]["subjects"]}
        self.assertEqual(subj_codes, {"MDM_A", "MDM_B"})

    def test_save_cohorts_and_batch_partitioning(self):
        """Admin defines Div A (AIML) with 4 lab batches, Div B (CSEC) with 2 lab batches."""
        payload = {
            "semester": 6,
            "classes": [
                {
                    "class_id": "Div-A",
                    "class_name": "Division A (AIML)",
                    "pe_tag": "PE",
                    "pe_subject_code": "PE_AIML",
                    "pe_subtag": "AIML",
                    "student_rolls": ["24101A0101", "24101A0102", "24101A0103", "24101A0104"],
                    "lab_batch_count": 4,
                },
                {
                    "class_id": "Div-B",
                    "class_name": "Division B (CSEC)",
                    "pe_tag": "PE",
                    "pe_subject_code": "PE_CSEC",
                    "pe_subtag": "CSEC",
                    "student_rolls": ["24101A0105", "24101A0106"],
                    "lab_batch_count": 2,
                },
            ],
        }
        res = self.client.post("/admin/cohorts/save", json=payload)
        self.assertEqual(res.status_code, 200)
        saved = res.json()["config"]

        # Check Div A has 4 batches: A1..A4
        div_a = saved["classes"][0]
        self.assertEqual(len(div_a["batches"]), 4)
        self.assertEqual([b["batch_id"] for b in div_a["batches"]], ["A1", "A2", "A3", "A4"])

        # Check Div B has 2 batches: B1..B2
        div_b = saved["classes"][1]
        self.assertEqual(len(div_b["batches"]), 2)
        self.assertEqual([b["batch_id"] for b in div_b["batches"]], ["B1", "B2"])

    def test_generate_traditional_sections(self):
        """Test section generation: ensures -T{k} for theory, -L{b} for labs, in-class MDM, and student pre-assignments."""
        # 1. Save cohorts
        self.test_save_cohorts_and_batch_partitioning()

        # 2. Generate sections
        res = self.client.post("/admin/cohorts/generate-sections", json={"semester": 6})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertGreater(data["sections_created"], 0)

        # 3. Verify sections created
        sections = self.store.list_sections()
        labels = [s.label for s in sections]

        # Division 1 (Div A) has CS601-T1, MDM03-T1, PE_AIML-T1
        self.assertIn("CS601-T1", labels)
        self.assertIn("MDM03-T1", labels)
        self.assertIn("PE_AIML-T1", labels)

        # Division 2 (Div B) has CS601-T2, MDM03-T2, PE_CSEC-T2
        self.assertIn("CS601-T2", labels)
        self.assertIn("MDM03-T2", labels)
        self.assertIn("PE_CSEC-T2", labels)

        # Batches for labs: Div A had 4 batches (L1..L4), Div B had 2 batches (L5..L6)
        self.assertIn("CS601P-L1", labels)
        self.assertIn("CS601P-L2", labels)
        self.assertIn("CS601P-L3", labels)
        self.assertIn("CS601P-L4", labels)
        self.assertIn("CS601P-L5", labels)
        self.assertIn("CS601P-L6", labels)

        # 4. Verify student assignments
        assignments = self.store.student_section_assignments
        # Student 1 is in Div A -> should have CS601-T1, MDM03-T1, PE_AIML-T1, CS601P-L1
        s1_map = assignments.get("24101A0101", {})
        self.assertIn("CS601", s1_map)
        self.assertIn("MDM03", s1_map)
        self.assertIn("PE_AIML", s1_map)
        self.assertIn("CS601P", s1_map)
        s1_cs601_sec = self.store.get_section(s1_map["CS601"])
        self.assertEqual(s1_cs601_sec.label, "CS601-T1")
