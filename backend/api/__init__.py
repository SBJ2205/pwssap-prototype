"""Combines all resource routers into a single api_router that main.py mounts."""
from fastapi import APIRouter

from api import (
    auth,
    availability,
    cohorts,
    cycle,
    faculty_preferences,
    meta,
    overrides,
    preferences,
    runs,
    sections,
    solver,
    students,
    subjects,
    teachers,
)

ALL_ROUTERS = [
    auth.router,
    meta.router,
    cycle.router,
    cohorts.router,
    subjects.router,
    students.router,
    teachers.router,
    availability.router,
    preferences.router,
    faculty_preferences.router,
    runs.router,
    sections.router,
    solver.router,
    overrides.admin_router,
    overrides.student_router,
]

api_router = APIRouter()
for r in ALL_ROUTERS:
    api_router.include_router(r)
    for route in r.routes:
        if route not in api_router.routes:
            api_router.routes.append(route)
