"""Authentication endpoints for the role-based dashboard API."""
import hmac
import os
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from auth import authenticate, change_admin_password, create_access_token
from data.store import get_store

router = APIRouter(prefix="/auth")


class LoginRequest(BaseModel):
    role: Literal["admin", "student", "teacher"]
    identity: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class AdminPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=1024)


@router.post("/login")
def login(payload: LoginRequest):
    user = authenticate(payload.role, payload.identity.strip(), payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token_data = create_access_token(user)
    store = get_store()
    if user["role"] == "admin":
        name = "Administrator"
    elif user["role"] == "student":
        student = store.get_student(user["identity"])
        name = student.name if student else user["identity"]
    else:
        teacher = store.get_teacher(user["identity"])
        name = teacher.teacher_name if teacher else user["identity"]
    token_data["name"] = name
    return token_data


@router.post("/admin-password")
def update_admin_password(
    payload: AdminPasswordRequest,
    request: Request,
    setup_token: str = Header(default="", alias="X-Admin-Setup-Token"),
):
    user = getattr(request.state, "auth_user", None)
    configured_token = os.environ.get("ADMIN_SETUP_TOKEN", "")
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin authentication required")
    if len(configured_token.encode("utf-8")) < 32:
        raise HTTPException(
            status_code=503,
            detail="Admin password changes are unavailable until a secure setup token is configured",
        )
    if not hmac.compare_digest(
        setup_token.encode("utf-8"), configured_token.encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail="Valid Admin setup token required")
    change_admin_password(payload.new_password)
    return {"status": "updated"}
