"""Combines all resource routers into a single api_router that main.py mounts."""
from fastapi import APIRouter

from api import meta, runs, students, subjects

api_router = APIRouter()
api_router.include_router(meta.router)
api_router.include_router(subjects.router)
api_router.include_router(students.router)
api_router.include_router(runs.router)
