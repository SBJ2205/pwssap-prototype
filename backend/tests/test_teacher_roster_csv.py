import unittest
from fastapi.testclient import TestClient

from main import app
from data.store import reset_store, get_store
from domain.models import Teacher, Subject, Student, Section, Meeting, GenerationRun, RunStatus


class TestTeacherRosterCsv(unittest.TestCase):
    def setUp(self):
        reset_store()
        self.store = get_store()
        self.client = TestClient(app)

        # 1. Setup teacher
        self.teacher = Teacher(teacher_id="T101", teacher_name="Prof. Sharma")
        self.store.upsert_teacher(self.teacher)

        # 2. Setup subject
        self.subject = Subject(
            subject_code="IT301",
            subject_name="Data Structures",
            weekly_hours=4,
            capacity=60,
            type="theory",
            semester=3,
            subject_tag="CORE",
        )
        self.store.upsert_subject(self.subject)

        # 3. Setup students
        self.s1 = Student(roll_number="25101A0101", name="Aarav Sharma", semester=3)
        self.s2 = Student(roll_number="25101A0102", name="Bhavna Patel", semester=3)
        self.store.upsert_student(self.s1)
        self.store.upsert_student(self.s2)

        # 4. Setup run and section
        self.run = self.store.create_run(semesters=[3])
        self.run.status = RunStatus.PUBLISHED

        self.section = Section(
            id=10,
            run_id=1,
            subject_code="IT301",
            label="IT301-T1",
            teacher_id="T101",
            capacity=60,
            meetings=[Meeting(duration_hours=2, slot_key="Mon-2")],
        )
        self.store.add_section(self.section)

        # 5. Enroll students into section
        self.store.enroll_student("25101A0101", "IT301", 10)
        self.store.enroll_student("25101A0102", "IT301", 10)

    def test_teacher_timetable_enrolled_roster(self):
        res = self.client.get("/teachers/T101/timetable")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["teacher_id"], "T101")
        self.assertEqual(len(data["schedule"]), 1)
        sec = data["schedule"][0]
        self.assertEqual(sec["section_label"], "IT301-T1")
        self.assertEqual(sec["enrolled_count"], 2)

        # Check enriched enrolled_roster
        self.assertIn("enrolled_roster", sec)
        roster = sec["enrolled_roster"]
        self.assertEqual(len(roster), 2)
        self.assertEqual(roster[0]["roll_number"], "25101A0101")
        self.assertEqual(roster[0]["name"], "Aarav Sharma")
        self.assertEqual(roster[1]["roll_number"], "25101A0102")
        self.assertEqual(roster[1]["name"], "Bhavna Patel")

    def test_download_section_roster_csv(self):
        res = self.client.get("/teachers/T101/sections/10/roster.csv")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res.headers["content-type"])
        self.assertIn('attachment; filename="IT301-T1_roster.csv"', res.headers["content-disposition"])

        content = res.text
        lines = content.strip().split("\r\n" if "\r\n" in content else "\n")
        self.assertEqual(lines[0], "roll_number,student_name,semester")
        self.assertIn("25101A0101,Aarav Sharma,3", content)
        self.assertIn("25101A0102,Bhavna Patel,3", content)

    def test_download_section_roster_csv_wrong_teacher(self):
        # Teacher T999 does not exist
        res = self.client.get("/teachers/T999/sections/10/roster.csv")
        self.assertEqual(res.status_code, 404)

    def test_download_teacher_timetable_csv(self):
        res = self.client.get("/teachers/T101/timetable.csv")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res.headers["content-type"])
        self.assertIn('attachment; filename="T101_timetable.csv"', res.headers["content-disposition"])

        content = res.text
        self.assertIn("day,start_time,end_time,duration_hours,subject_code,subject_name,subject_type,section_label,enrolled_count", content)
        self.assertIn("IT301,Data Structures,theory,IT301-T1,2", content)


if __name__ == "__main__":
    unittest.main()
