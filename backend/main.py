"""FastAPI application entrypoint.

Wires together the modular api/, solver/, domain/, and data/ packages:
- domain/  — persistence-agnostic entities (Teacher, Subject, Student, Section, TimeSlot)
- data/    — InMemoryStore + seed data (structured so SQLite can later replace it)
- solver/  — CP-SAT engine, gap-reduction + baseline heuristics, orchestration
- api/     — FastAPI routers that translate HTTP <-> the layers above
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import api_router

app = FastAPI(title="PWSSAP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
