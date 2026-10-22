"""Credential storage and signed-token helpers for the API."""
import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional

from fastapi import HTTPException, Request

_configured_jwt_secret = os.environ.get("JWT_SECRET")
if not _configured_jwt_secret:
    raise RuntimeError("JWT_SECRET must be configured before starting the backend.")
if len(_configured_jwt_secret.encode("utf-8")) < 32:
    raise RuntimeError("JWT_SECRET must contain at least 32 bytes.")
_JWT_SECRET = _configured_jwt_secret
_JWT_ALGORITHM = "HS256"
_TOKEN_LIFETIME_SECONDS = 60 * 60
_DEFAULT_DATABASE = Path(__file__).resolve().parent / "data" / "auth.sqlite3"


def _database_path() -> str:
    return os.environ.get("AUTH_DB_PATH", str(_DEFAULT_DATABASE))


def _connect() -> sqlite3.Connection:
    path = Path(_database_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute(
        """CREATE TABLE IF NOT EXISTS auth_users (
            role TEXT NOT NULL,
            identity TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (role, identity)
        )"""
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(auth_users)")}
    if "active" not in columns:
        connection.execute(
            "ALTER TABLE auth_users ADD COLUMN active INTEGER NOT NULL DEFAULT 1"
        )
    return connection


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt${}${}${}".format(
        2**14,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, cost, salt_value, digest_value = encoded.split("$", 3)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_value.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(cost), r=8, p=1
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        return False


def _ensure_admin(connection: sqlite3.Connection) -> None:
    exists = connection.execute(
        "SELECT 1 FROM auth_users WHERE role = 'admin' AND identity = 'admin'"
    ).fetchone()
    if not exists:
        password = os.environ.get("ADMIN_DEFAULT_PASSWORD", "admin")
        connection.execute(
            "INSERT INTO auth_users (role, identity, password_hash) VALUES (?, ?, ?)",
            ("admin", "admin", hash_password(password)),
        )


def authenticate(role: str, identity: str, password: str) -> Optional[Dict[str, str]]:
    if role not in {"admin", "student", "teacher"}:
        return None
    with _connect() as connection:
        _ensure_admin(connection)
        row = connection.execute(
            """SELECT identity, password_hash FROM auth_users
               WHERE role = ? AND lower(identity) = lower(?) AND active = 1""",
            (role, identity),
        ).fetchone()
    if row is None or not verify_password(password, row[1]):
        return None
    return {"role": role, "identity": row[0]}


def create_credentials(role: str, credentials: Dict[str, str]) -> None:
    if role not in {"student", "teacher"}:
        raise ValueError("Only student and teacher credentials can be imported.")
    with _connect() as connection:
        for identity, password in credentials.items():
            existing = connection.execute(
                """SELECT identity FROM auth_users
                   WHERE role = ? AND lower(identity) = lower(?)""",
                (role, identity),
            ).fetchone()
            if existing:
                connection.execute(
                    "UPDATE auth_users SET active = 1 WHERE role = ? AND identity = ?",
                    (role, existing[0]),
                )
            else:
                connection.execute(
                    "INSERT INTO auth_users (role, identity, password_hash) VALUES (?, ?, ?)",
                    (role, identity, hash_password(password)),
                )


def deactivate_credentials(role: str) -> None:
    if role not in {"student", "teacher"}:
        raise ValueError("Only student and teacher credentials can be deleted.")
    with _connect() as connection:
        connection.execute("UPDATE auth_users SET active = 0 WHERE role = ?", (role,))


def change_admin_password(password: str) -> None:
    with _connect() as connection:
        _ensure_admin(connection)
        connection.execute(
            "UPDATE auth_users SET password_hash = ? WHERE role = 'admin' AND identity = 'admin'",
            (hash_password(password),),
        )


def create_access_token(user: Dict[str, str]) -> Dict[str, object]:
    issued_at = int(time.time())
    claims = {
        "sub": user["identity"],
        "role": user["role"],
        "iat": issued_at,
        "exp": issued_at + _TOKEN_LIFETIME_SECONDS,
    }
    header = {"alg": _JWT_ALGORITHM, "typ": "JWT"}
    signing_input = ".".join(
        _base64url_encode(json.dumps(part, separators=(",", ":")).encode("utf-8"))
        for part in (header, claims)
    )
    signature = hmac.new(
        _JWT_SECRET.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    return {
        "access_token": signing_input + "." + _base64url_encode(signature),
        "token_type": "bearer",
        "expires_in": _TOKEN_LIFETIME_SECONDS,
        **user,
    }


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def decode_access_token(token: str) -> Dict[str, str]:
    try:
        header_part, claims_part, signature_part = token.split(".")
        signing_input = header_part + "." + claims_part
        expected = hmac.new(
            _JWT_SECRET.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _base64url_decode(signature_part)):
            raise ValueError("Invalid signature")
        header = json.loads(_base64url_decode(header_part))
        claims = json.loads(_base64url_decode(claims_part))
        if header.get("alg") != _JWT_ALGORITHM or header.get("typ") != "JWT":
            raise ValueError("Invalid token header")
        if not isinstance(claims.get("exp"), int) or claims["exp"] <= int(time.time()):
            raise ValueError("Expired token")
        if claims.get("role") not in {"admin", "student", "teacher"}:
            raise ValueError("Invalid role")
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise ValueError("Invalid subject")
        return {"role": claims["role"], "identity": claims["sub"]}
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeError, binascii.Error):
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token")


def authorize_request(request: Request, user: Dict[str, str]) -> None:
    role, identity = user["role"], user["identity"]
    path = request.url.path
    method = request.method.upper()

    if role == "admin":
        return

    if path.startswith("/admin/"):
        raise HTTPException(status_code=403, detail="Admin role required for this action")

    if path == "/students" or path == "/teachers":
        raise HTTPException(status_code=403, detail="Roster access is restricted to admins")

    if path.startswith("/students/"):
        segments = path.strip("/").split("/")
        target = segments[1]
        suffix = "/" + "/".join(segments[2:])
        student_routes = {
            ("GET", "/available-choices"),
            ("GET", "/lock-in"),
            ("PUT", "/lock-in"),
            ("GET", "/enrolled-subjects"),
            ("GET", "/sections"),
            ("GET", "/time-preferences"),
            ("PUT", "/time-preferences"),
            ("GET", "/rankable-subjects"),
            ("GET", "/faculty-preferences"),
            ("PUT", "/faculty-preferences"),
        }
        if (
            role != "student"
            or target.casefold() != identity.casefold()
            or (method, suffix) not in student_routes
        ):
            raise HTTPException(status_code=403, detail="Access is limited to your own student data")
        return

    if path.startswith("/teachers/"):
        segments = path.strip("/").split("/")
        target = segments[1]
        suffix = "/" + "/".join(segments[2:])
        teacher_route = (
            method == "GET"
            and (
                suffix in {"/timetable", "/timetable.csv"}
                or (
                    len(segments) == 5
                    and segments[2] == "sections"
                    and segments[4] == "roster.csv"
                )
            )
        )
        if role != "teacher" or target.casefold() != identity.casefold() or not teacher_route:
            raise HTTPException(status_code=403, detail="Access is limited to your own teacher data")
        return

    if method == "GET" and path in {"/subjects", "/timeslots", "/semesters", "/health"}:
        return

    raise HTTPException(status_code=403, detail="This action is restricted to admins")


async def authenticate_request(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path in {"/health", "/auth/login"}:
        return await call_next(request)
    auth_header = request.headers.get("authorization", "")
    scheme, separator, token = auth_header.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        return _unauthorized_response()
    try:
        user = decode_access_token(token)
        authorize_request(request, user)
    except HTTPException as error:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=error.status_code,
            content={"detail": error.detail},
        )
    request.state.auth_user = user
    return await call_next(request)


def _unauthorized_response():
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=401, content={"detail": "Authentication required"})


def require_admin(request: Request) -> None:
    user = getattr(request.state, "auth_user", None)
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin role required for this action")
