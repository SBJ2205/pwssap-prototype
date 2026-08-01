"""Combines all resource routers into a single api_router that main.py mounts."""
from fastapi import APIRouter

from api import catalog, preferences, solver_routes

api_router = APIRouter()
api_router.include_router(catalog.router)
api_router.include_router(preferences.router)
api_router.include_router(solver_routes.router)
