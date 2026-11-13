"""FastAPI application entrypoint.

Wires together the modular api/, solver/, domain/, and data/ packages:
- domain/  — persistence-agnostic entities (Teacher, Subject, Student, Section, TimeSlot)
- data/    — InMemoryStore + seed data (structured so SQLite can later replace it)
- solver/  — CP-SAT engine, gap-reduction + baseline heuristics, orchestration
- api/     — FastAPI routers that translate HTTP <-> the layers above
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api import ALL_ROUTERS, api_router

app = FastAPI(title="PWSSAP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
for r in ALL_ROUTERS:
    for route in r.routes:
        if route not in app.routes:
            app.routes.append(route)

# Mount built frontend SPA when available (for standalone web/desktop application)
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.isdir(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path in ("docs", "redoc", "openapi.json"):
            return None
        target = os.path.join(frontend_dist, full_path)
        if full_path and os.path.isfile(target):
            return FileResponse(target)
        index_file = os.path.join(frontend_dist, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        return {"error": "Frontend build not found"}
