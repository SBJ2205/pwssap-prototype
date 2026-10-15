import io
import unittest
from fastapi.testclient import TestClient

from main import app
from data.store import reset_store, get_store
from domain.models import Student, Subject


class TestElectiveCSVImport(unittest.TestCase):
    def setUp(self):
        reset_store()
        self.store = get_store()
        self.client = TestClient(app)
        self.admin_headers = {"X-Role": "admin"}

        # Register students
        self.store.upsert_student(Student(roll_number="25101A0101", name="Alice", semester=4))
        self.store.upsert_student(Student(roll_number="25101A0102", name="Bob", semester=4))
        self.store.upsert_student(Student(roll_number="24101A0101", name="Charlie", semester=6))

        # Register subjects
        self.store.upsert_subject(Subject(
            subject_code="MDM401",
            subject_name="Intro to AI",
            weekly_hours=3,
            capacity=60,
            type="theory",
            semester=4,
            subject_tag="MDM",
            subtag="MDM-AI",
        ))
        self.store.upsert_subject(Subject(
            subject_code="MDM402",
            subject_name="Web Dev Basics",
            weekly_hours=3,
            capacity=60,
            type="theory",
            semester=4,
            subject_tag="MDM",
            subtag="MDM-WD",
        ))
        self.store.upsert_subject(Subject(
            subject_code="PE601",
            subject_name="Cloud Computing",
            weekly_hours=3,
            capacity=60,
            type="theory",
            semester=6,
            subject_tag="PE",
            subtag="PE-Cloud",
        ))

        # Configure MDM and PE as choice tags
        self.client.put(
            "/admin/cycle/choice-tags",
            json=[{"tag": "MDM", "is_choice_based": True}, {"tag": "PE", "is_choice_based": True}],
            headers=self.admin_headers,
        )

    def test_elective_template_generation(self):
        res = self.client.get("/admin/cycle/elective-template/4", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res.headers["content-type"])
        content = res.text
        self.assertIn("roll_number,student_name,MDM", content)
        self.assertIn("25101A0101,Alice,", content)
        self.assertIn("25101A0102,Bob,", content)
        self.assertNotIn("Charlie", content)  # Charlie is sem 6

    def test_elective_template_for_semester_without_electives(self):
        res = self.client.get("/admin/cycle/elective-template/8", headers=self.admin_headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn("No choice-based elective tags", res.json()["detail"])

    def test_import_elective_allocations_success(self):
        csv_data = (
            "roll_number,student_name,MDM\n"
            "25101A0101,Alice,MDM-AI\n"
            "25101A0102,Bob,MDM-WD\n"
        )
        files = {"file": ("sem4_allocations.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
        res = self.client.post(
            "/admin/cycle/import-elective-allocations?semester=4",
            headers=self.admin_headers,
            files=files,
        )
        self.assertEqual(res.status_code, 200)
        json_data = res.json()
        self.assertEqual(json_data["updated_count"], 2)

        # Check lock-in in store
        self.assertTrue(self.store.has_complete_lock_in("25101A0101"))
        lock_alice = self.store.get_lock_in_for_student("25101A0101")
        self.assertEqual(lock_alice.get("MDM"), "MDM-AI")

        self.assertTrue(self.store.has_complete_lock_in("25101A0102"))
        lock_bob = self.store.get_lock_in_for_student("25101A0102")
        self.assertEqual(lock_bob.get("MDM"), "MDM-WD")

    def test_import_elective_allocations_invalid_subtag(self):
        csv_data = (
            "roll_number,student_name,MDM\n"
            "25101A0101,Alice,MDM-INVALID\n"
        )
        files = {"file": ("sem4_allocations.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
        res = self.client.post(
            "/admin/cycle/import-elective-allocations?semester=4",
            headers=self.admin_headers,
            files=files,
        )
        self.assertEqual(res.status_code, 400)
        detail = res.json()["detail"]
        self.assertIn("errors", detail)
        self.assertTrue(any("MDM-INVALID" in e["error"] for e in detail["errors"]))

    def test_import_elective_allocations_wrong_semester_student(self):
        # Charlie is sem 6, but uploaded in sem 4 file
        csv_data = (
            "roll_number,student_name,MDM\n"
            "24101A0101,Charlie,MDM-AI\n"
        )
        files = {"file": ("sem4_allocations.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
        res = self.client.post(
            "/admin/cycle/import-elective-allocations?semester=4",
            headers=self.admin_headers,
            files=files,
        )
        self.assertEqual(res.status_code, 400)
        detail = res.json()["detail"]
        self.assertIn("errors", detail)
        self.assertTrue(any("Semester 6" in e["error"] for e in detail["errors"]))


if __name__ == "__main__":
    unittest.main()
