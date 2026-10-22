import hashlib
import hmac
import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

import auth
from data.store import reset_store
from main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "credentials.sqlite3"))
    monkeypatch.setenv("ADMIN_DEFAULT_PASSWORD", "admin")
    monkeypatch.setenv("ADMIN_SETUP_TOKEN", "configured-admin-setup-token-for-tests")
    reset_store()
    with TestClient(app) as test_client:
        yield test_client
    reset_store()


def _login(client, role, identity, password):
    return client.post(
        "/auth/login",
        json={"role": role, "identity": identity, "password": password},
    )


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _expired_token():
    header = auth._base64url_encode(b'{"alg":"HS256","typ":"JWT"}')
    claims = auth._base64url_encode(
        json.dumps(
            {"sub": "admin", "role": "admin", "iat": int(time.time()) - 120, "exp": int(time.time()) - 60},
            separators=(",", ":"),
        ).encode()
    )
    body = f"{header}.{claims}"
    signature = hmac.new(
        auth._JWT_SECRET.encode(), body.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{body}.{auth._base64url_encode(signature)}"


def test_default_admin_hashes_password_and_protects_endpoints(client, tmp_path):
    response = _login(client, "admin", "admin", "admin")
    assert response.status_code == 200
    token = response.json()["access_token"]

    with sqlite3.connect(tmp_path / "credentials.sqlite3") as connection:
        stored_hash = connection.execute(
            "SELECT password_hash FROM auth_users WHERE role = 'admin'"
        ).fetchone()[0]
    assert stored_hash.startswith("scrypt$")
    assert stored_hash != "admin"
    assert auth.verify_password("admin", stored_hash)

    assert client.get("/admin/cycle", headers=_headers(token)).status_code == 200
    assert client.get("/admin/cycle", headers={"X-Role": "admin"}).status_code == 401
    assert client.get("/admin/cycle").status_code == 401


def test_roster_import_hashes_student_and_teacher_passwords_for_login(client, tmp_path):
    students_csv = "roll_number,name,semester,password\nS100,Student One,4,student-secret-1\n"
    student_import = client.post(
        "/admin/students/import",
        headers=_headers(_login(client, "admin", "admin", "admin").json()["access_token"]),
        files={"file": ("students.csv", students_csv, "text/csv")},
    )
    assert student_import.status_code == 200, student_import.text

    teachers_csv = (
        "teacher_id,teacher_name,subject_1,subject_1_load,subject_2,subject_2_load,"
        "subject_3,subject_3_load,subject_4,subject_4_load,subject_5,subject_5_load,password\n"
        "T100,Teacher One,,,,,,,,,,,teacher-secret-1\n"
    )
    teacher_import = client.post(
        "/admin/teachers/import",
        headers=_headers(_login(client, "admin", "admin", "admin").json()["access_token"]),
        files={"file": ("teachers.csv", teachers_csv, "text/csv")},
    )
    assert teacher_import.status_code == 200, teacher_import.text

    student_login = _login(client, "student", "S100", "student-secret-1")
    teacher_login = _login(client, "teacher", "T100", "teacher-secret-1")
    assert student_login.status_code == 200
    assert teacher_login.status_code == 200
    assert student_login.json()["name"] == "Student One"
    assert teacher_login.json()["name"] == "Teacher One"
    teacher_headers = _headers(teacher_login.json()["access_token"])
    assert client.get("/teachers/T100/timetable", headers=teacher_headers).status_code == 200
    assert client.get("/teachers/T101/timetable", headers=teacher_headers).status_code == 403
    assert client.get("/teachers", headers=teacher_headers).status_code == 403

    with sqlite3.connect(tmp_path / "credentials.sqlite3") as connection:
        credential_rows = connection.execute(
            "SELECT role, password_hash FROM auth_users WHERE identity IN ('S100', 'T100')"
        ).fetchall()
    assert len(credential_rows) == 2
    assert all(value.startswith("scrypt$") for _, value in credential_rows)
    assert all("student-secret-1" not in value and "teacher-secret-1" not in value for _, value in credential_rows)
    assert "password" not in str(student_import.json()).lower()
    assert "password" not in str(teacher_import.json()).lower()

    changed_password_csv = "roll_number,name,semester,password\nS100,Student One,4,new-password-1\n"
    reimport = client.post(
        "/admin/students/import",
        headers=_headers(_login(client, "admin", "admin", "admin").json()["access_token"]),
        files={"file": ("students.csv", changed_password_csv, "text/csv")},
    )
    assert reimport.status_code == 200
    assert _login(client, "student", "S100", "student-secret-1").status_code == 200
    assert _login(client, "student", "S100", "new-password-1").status_code == 401

def test_csv_requires_password_but_accepts_short_password(client):
    admin = _login(client, "admin", "admin", "admin").json()["access_token"]
    missing_password = client.post(
        "/admin/students/import",
        headers=_headers(admin),
        files={"file": ("students.csv", "roll_number,name,semester\nS101,Student,4\n", "text/csv")},
    )
    short_password = client.post(
        "/admin/students/import",
        headers=_headers(admin),
        files={
            "file": (
                "students.csv",
                "roll_number,name,semester,password\nS101,Student,4,short\n",
                "text/csv",
            )
        },
    )
    assert missing_password.status_code == 400
    assert short_password.status_code == 200
    assert _login(client, "student", "S101", "short").status_code == 200


def test_setup_token_only_changes_admin_password(client):
    admin = _login(client, "admin", "admin", "admin").json()["access_token"]
    too_short = client.post(
        "/auth/admin-password",
        headers={
            **_headers(admin),
            "X-Admin-Setup-Token": "configured-admin-setup-token-for-tests",
        },
        json={"new_password": "short7"},
    )
    assert too_short.status_code == 422
    assert client.post(
        "/auth/admin-password",
        headers=_headers(admin),
        json={"new_password": "newpass8"},
    ).status_code == 403

    changed = client.post(
        "/auth/admin-password",
        headers={
            **_headers(admin),
            "X-Admin-Setup-Token": "configured-admin-setup-token-for-tests",
        },
        json={"new_password": "newpass8"},
    )
    assert changed.status_code == 200
    assert _login(client, "admin", "admin", "admin").status_code == 401
    assert _login(client, "admin", "admin", "newpass8").status_code == 200
    assert client.post(
        "/admin/cycle/initialize",
        headers={"X-Admin-Setup-Token": "configured-admin-setup-token-for-tests"},
    ).status_code == 401


def test_rejects_invalid_expired_and_cross_role_tokens_and_scopes_data(client):
    admin = _login(client, "admin", "admin", "admin").json()["access_token"]
    imported = client.post(
        "/admin/students/import",
        headers=_headers(admin),
        files={
            "file": (
                "students.csv",
                "roll_number,name,semester,password\nS200,Student Two,4,student-secret-2\n",
                "text/csv",
            )
        },
    )
    assert imported.status_code == 200

    student = _login(client, "student", "S200", "student-secret-2").json()
    student_headers = _headers(student["access_token"])
    assert client.get("/students/S200/lock-in", headers=student_headers).status_code == 200
    assert client.get("/students/S201/lock-in", headers=student_headers).status_code == 403
    assert client.get("/students", headers=student_headers).status_code == 403
    assert client.get("/admin/cycle", headers=student_headers).status_code == 403
    assert client.get(
        "/students/S200/lock-in",
        headers=_headers(student["access_token"][:-1] + ("a" if student["access_token"][-1] != "a" else "b")),
    ).status_code == 401
    assert client.get("/students/S200/lock-in", headers=_headers(_expired_token())).status_code == 401
    assert _login(client, "student", "S200", "wrong-password").status_code == 401
    with pytest.raises(HTTPException) as invalid_token_error:
        auth.decode_access_token("é.é.é")
    assert invalid_token_error.value.status_code == 401

    assert client.post(
        "/auth/admin-password",
        headers={
            **student_headers,
            "X-Admin-Setup-Token": "configured-admin-setup-token-for-tests",
        },
        json={"new_password": "a-new-admin-password"},
    ).status_code == 403


def test_roster_clear_deactivates_without_resetting_existing_password(client):
    admin = _login(client, "admin", "admin", "admin").json()["access_token"]
    headers = _headers(admin)
    roster = "roll_number,name,semester,password\nS300,Student Three,4,student-secret-3\n"
    assert client.post(
        "/admin/students/import",
        headers=headers,
        files={"file": ("students.csv", roster, "text/csv")},
    ).status_code == 200
    assert _login(client, "student", "S300", "student-secret-3").status_code == 200

    assert client.delete("/admin/students", headers=headers).status_code == 200
    assert _login(client, "student", "S300", "student-secret-3").status_code == 401

    replacement = "roll_number,name,semester,password\nS300,Student Three,4,reset-attempt\n"
    assert client.post(
        "/admin/students/import",
        headers=headers,
        files={"file": ("students.csv", replacement, "text/csv")},
    ).status_code == 200
    assert _login(client, "student", "S300", "student-secret-3").status_code == 200
    assert _login(client, "student", "S300", "reset-attempt").status_code == 401
