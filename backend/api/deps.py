"""Minimal role concept for the local prototype.

There is no real authentication here — a caller simply asserts their role
via the `X-Role` header (or a `role` query param as a convenience for
manual testing in a browser). This is intentionally lightweight: the task
only requires that teacher-timetable data and admin-only actions are not
reachable by an ordinary student caller in the local product, not a full
auth system.
"""
from typing import Optional

from fastapi import Header, HTTPException, Query


def require_admin(
    x_role: Optional[str] = Header(default=None, alias="X-Role"),
    role: Optional[str] = Query(default=None),
) -> None:
    """Raise 403 unless the caller identifies itself as "admin"."""
    effective_role = (x_role or role or "").lower()
    if effective_role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required for this action")
