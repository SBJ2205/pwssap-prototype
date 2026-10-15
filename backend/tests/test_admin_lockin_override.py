"""Tests for admin student elective lock-in inspection and override features."""

import io
from fastapi.testclient import TestClient
from main import app
from data.store import reset_store

client = TestClient(app)
ADMIN = {"X-Role": "admin"}
STUDENT = {"X-Role": "student"}

def test_admin_lockin_inspection_and_override():
    reset_store()

    # 1. Upload subjects with tags and subtags in semester 3
    subject_csv = (
        "subject_code,subject_name,subject_tag,subtag,semester,type,weekly_hours,capacity\n"
        "IT301,Data Structures,CORE,,3,Theory,3,60\n"
        "IT307,Web Technologies,PE1,IT307_WT,3,Theory,3,30\n"
        "IT308,Mobile Computing,PE1,IT308_MC,3,Theory,3,30\n"
        "IT309,Cloud Foundations,MDM,IT309_CF,3,Theory,3,30\n"
        "IT310,Cyber Security Intro,MDM,IT310_CS,3,Theory,3,30\n"
    )
    res_sub = client.post(
        "/admin/subjects/import",
        files={"file": ("subjects.csv", io.BytesIO(subject_csv.encode("utf-8")), "text/csv")},
        headers=ADMIN,
    )
    assert res_sub.status_code == 200, res_sub.text

    # 2. Upload 3 students in Sem 3
    student_csv = (
        "roll_number,name,email,semester\n"
        "S101,Alice,alice@example.com,3\n"
        "S102,Bob,bob@example.com,3\n"
        "S103,Charlie,charlie@example.com,3\n"
    )
    res_stu = client.post(
        "/admin/students/import",
        files={"file": ("students.csv", io.BytesIO(student_csv.encode("utf-8")), "text/csv")},
        headers=ADMIN,
    )
    assert res_stu.status_code == 200, res_stu.text

    # 3. GET /admin/cycle to verify students_lock_in structure
    cyc = client.get("/admin/cycle", headers=ADMIN)
    assert cyc.status_code == 200, cyc.text
    cyc_data = cyc.json()

    assert "students_lock_in" in cyc_data
    assert len(cyc_data["students_lock_in"]) == 3
    assert cyc_data["lock_in_total_students"] == 3
    assert cyc_data["lock_in_complete_count"] == 0

    s101_item = next(s for s in cyc_data["students_lock_in"] if s["roll_number"] == "S101")
    assert s101_item["is_complete"] is False
    assert set(s101_item["applicable_tags"]) == {"PE1", "MDM"}
    assert set(s101_item["missing_tags"]) == {"PE1", "MDM"}
    assert s101_item["locked_in"] == {}

    # 4. Admin override for S101 via PUT /students/S101/lock-in
    res_override = client.put(
        "/students/S101/lock-in",
        json={"choices": {"PE1": "IT307_WT", "MDM": "IT309_CF"}},
        headers=ADMIN,
    )
    assert res_override.status_code == 200, res_override.text
    assert res_override.json()["complete"] is True

    # Check cycle status after single override
    cyc2 = client.get("/admin/cycle", headers=ADMIN).json()
    assert cyc2["lock_in_complete_count"] == 1
    s101_after = next(s for s in cyc2["students_lock_in"] if s["roll_number"] == "S101")
    assert s101_after["is_complete"] is True
    assert s101_after["missing_tags"] == []
    assert s101_after["locked_in"] == {"PE1": "IT307_WT", "MDM": "IT309_CF"}

    # 5. POST /admin/cycle/auto-lock-in for pending students (S102, S103)
    res_auto = client.post("/admin/cycle/auto-lock-in", headers=ADMIN)
    assert res_auto.status_code == 200, res_auto.text
    auto_data = res_auto.json()
    assert auto_data["auto_locked_count"] == 2

    # Verify all students are now locked in
    cyc3 = client.get("/admin/cycle", headers=ADMIN).json()
    assert cyc3["lock_in_complete_count"] == 3
    for s in cyc3["students_lock_in"]:
        assert s["is_complete"] is True
        assert len(s["missing_tags"]) == 0
        assert "PE1" in s["locked_in"]
        assert "MDM" in s["locked_in"]

    # 6. Admin edit choice for S102 to change PE1
    res_edit = client.put(
        "/students/S102/lock-in",
        json={"choices": {"PE1": "IT308_MC", "MDM": "IT310_CS"}},
        headers=ADMIN,
    )
    assert res_edit.status_code == 200, res_edit.text
    cyc4 = client.get("/admin/cycle", headers=ADMIN).json()
    s102_after = next(s for s in cyc4["students_lock_in"] if s["roll_number"] == "S102")
    assert s102_after["locked_in"]["PE1"] == "IT308_MC"
    assert s102_after["locked_in"]["MDM"] == "IT310_CS"

if __name__ == "__main__":
    test_admin_lockin_inspection_and_override()
