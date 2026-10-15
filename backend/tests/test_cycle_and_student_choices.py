"""Tests for cycle elective choice configuration, section generation, and student elective lock-in."""

import io
from fastapi.testclient import TestClient
from main import app
from data.store import reset_store, get_store
from domain.models import RunStatus

client = TestClient(app)
ADMIN = {"X-Role": "admin"}
STUDENT = {"X-Role": "student"}

def test_cycle_and_student_flow():
    reset_store()

    # 1. Upload subjects with tags and subtags (similar to the user's screenshot)
    subject_csv = (
        "subject_code,subject_name,subject_tag,subtag,semester,type,weekly_hours,capacity\n"
        "IT301,Data Structures,CORE,,3,Theory,3,60\n"
        "IT302,DBMS,CORE,,3,Theory,3,60\n"
        "IT303,DS Lab,CORE,,3,Lab,2,20\n"
        "IT304,DBMS Lab,CORE,,3,Lab,2,20\n"
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
    assert res_sub.json()["count"] == 8

    # 2. Upload student in Sem 3
    student_csv = "roll_number,name,email,semester\nS101,Alice,alice@example.com,3\n"
    res_stu = client.post(
        "/admin/students/import",
        files={"file": ("students.csv", io.BytesIO(student_csv.encode("utf-8")), "text/csv")},
        headers=ADMIN,
    )
    assert res_stu.status_code == 200, res_stu.text

    # 3. GET /admin/cycle
    cyc = client.get("/admin/cycle", headers=ADMIN)
    assert cyc.status_code == 200, cyc.text
    cyc_data = cyc.json()

    # Both choice_tags and tags_detail must exist
    assert "choice_tags" in cyc_data
    assert "tags_detail" in cyc_data
    tags_detail = cyc_data["tags_detail"]
    tag_names = {t["tag"] for t in tags_detail}
    assert tag_names == {"CORE", "PE1", "MDM"}

    # PE1 and MDM define subtags and are not CORE, so by default is_choice_based is True
    pe1_info = next(t for t in tags_detail if t["tag"] == "PE1")
    mdm_info = next(t for t in tags_detail if t["tag"] == "MDM")
    core_info = next(t for t in tags_detail if t["tag"] == "CORE")
    assert pe1_info["is_choice_based"] is True
    assert mdm_info["is_choice_based"] is True
    assert core_info["is_choice_based"] is False

    # 4. PUT /admin/cycle/choice-tags
    res_put = client.put(
        "/admin/cycle/choice-tags",
        json=[{"tag": "PE1", "is_choice_based": True}, {"tag": "MDM", "is_choice_based": True}],
        headers=ADMIN,
    )
    assert res_put.status_code == 200, res_put.text

    # 5. Check student available choices
    res_avail = client.get("/students/S101/available-choices", headers=STUDENT)
    assert res_avail.status_code == 200, res_avail.text
    avail = res_avail.json()
    assert "available_choices" in avail
    choices = avail["available_choices"]
    assert "PE1" in choices
    assert "MDM" in choices
    assert sorted(choices["PE1"]) == ["IT307_WT", "IT308_MC"]
    assert sorted(choices["MDM"]) == ["IT309_CF", "IT310_CS"]

    # Student lock in
    res_lock = client.put(
        "/students/S101/lock-in",
        json={"choices": {"PE1": "IT307_WT", "MDM": "IT309_CF"}},
        headers=STUDENT,
    )
    assert res_lock.status_code == 200, res_lock.text
    assert res_lock.json()["complete"] is True

    # 6. POST /admin/cycle/initialize
    res_init = client.post("/admin/cycle/initialize", headers=ADMIN)
    assert res_init.status_code == 200, res_init.text
    init_data = res_init.json()
    assert "run_id" in init_data and isinstance(init_data["run_id"], int)
    assert "current_run" in init_data and isinstance(init_data["current_run"]["id"], int)
    run_id = init_data["run_id"]

    # 7. POST /admin/runs/{run_id}/generate-sections
    res_gen = client.post(f"/admin/runs/{run_id}/generate-sections", headers=ADMIN)
    assert res_gen.status_code == 200, res_gen.text
    gen_data = res_gen.json()
    assert gen_data["run_id"] == run_id
    assert gen_data["generated_count"] > 0
    print(f"PASS: Cycle flow and section generation successful! Generated {gen_data['generated_count']} sections.")

if __name__ == "__main__":
    test_cycle_and_student_flow()
