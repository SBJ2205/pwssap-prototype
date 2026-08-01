# PWSSAP — Preference-Weighted Section & Slot Assignment Prototype

A full-stack prototype for automated student section assignment based on **time-slot preferences**.  
Students rate abstract time periods (not specific subjects), and the **OR-Tools CP-SAT solver** finds the globally optimal assignment that minimises total dissatisfaction while keeping outcomes fair.

---

## ✨ Features

- **Blind time-slot preference** — students rate 6 days × 4 periods without knowing which subject falls where
- **CP-SAT solver** — Google OR-Tools constraint solver with fairness index cap
- **Penalty scoring** — Preferred = 0 pts · Tolerable = +1 pt · Disliked = +3 pts · Blocked = never assigned
- **Multi-meeting sections** — a section can meet more than once a week (e.g. Mon + Wed); all meetings are
  checked for clashes, capacity, and blocking
- **Faculty preference (secondary term)** — optional per-faculty ranking that only breaks ties between
  otherwise time-equivalent sections
- **Gap-reduction post-processing** — a second heuristic pass after the solver shifts students into
  alternative sections to remove idle schedule gaps, without ever increasing total penalty
- **Dashboard** — penalty breakdown, per-student results, comparison against genuinely-simulated FCFS &
  random baselines (not fabricated multipliers)
- **Personal timetable** — colour-coded by preference satisfaction

---

## 🗂 Project Structure

```
pwssap-prototype/
├── backend/
│   ├── main.py            # FastAPI app entrypoint (wires the packages below)
│   ├── domain/            # Persistence-agnostic entities (Teacher, Subject, Student, Section, TimeSlot)
│   ├── data/              # InMemoryStore + seed data (structured so SQLite can later replace it)
│   ├── solver/            # CP-SAT engine, gap-reduction + baseline heuristics, orchestration
│   └── api/               # FastAPI routers (catalog, preferences, solver_routes)
└── frontend/         # React (Vite) single-page app
    └── src/
        ├── App.jsx         # Orchestrator: state, effects, page routing
        ├── constants.js    # Shared constants (nav, rating scale, grid labels)
        ├── api/            # Thin axios-based API client (client.js + one module per resource)
        ├── components/     # Reusable UI (Sidebar, Card/Tooltip/Badge/loading-error-empty states)
        └── pages/          # One component per nav page (Slots, Solver, Dashboard, Prefs, ...)
```

---

## 🚀 Running Locally

### Backend (FastAPI)

```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install fastapi uvicorn ortools
uvicorn main:app --reload --port 8000
```

API available at **http://localhost:8000**

### Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

App available at **http://localhost:5173**

The backend URL is environment-based (Vite's `import.meta.env`) instead of hardcoded —
see `frontend/.env.example`. Copy it to `frontend/.env` and adjust `VITE_API_URL` if your
backend isn't on `http://localhost:8000`.

---

## 🔌 API Endpoints

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/sections` | admin | All sections (subject × label × teacher × meetings) — concrete timetable data |
| `GET` | `/subjects` | any | Student-safe subject catalog (code/name/department/year only) |
| `GET` | `/students` | any | All students |
| `GET` | `/timeslots` | any | Canonical 6×4 abstract time-slot grid (student-facing) |
| `GET` | `/faculty-by-subject` | any | `{subject_code: [{id, name}, ...]}` — faculty teaching each subject |
| `GET` | `/prefs/{id}` | any | Get a student's time-slot preferences |
| `POST` | `/prefs/{id}` | any | Save a student's time-slot preferences |
| `GET` | `/faculty-prefs/{id}` | any | Get a student's faculty preferences |
| `POST` | `/faculty-prefs/{id}` | any | Save a student's faculty preferences |
| `POST` | `/solve` | admin | Run the CP-SAT solver (+ gap-reduction pass + baselines) |
| `GET` | `/results` | any | Last solver result — students read this for their own post-solve timetable |
| `GET/POST/PUT/DELETE` | `/admin/teachers`, `/admin/subjects`, `/admin/students`, `/admin/sections` | admin | Catalog CRUD backing the store |

### Role concept (local prototype only)

There is no real authentication. A caller asserts its role via an `X-Role: admin`
header (or a `?role=admin` query param). `api/deps.require_admin` enforces this on
admin-only routes — see `backend/api/deps.py`. The frontend's sidebar has an
"Admin / Student" toggle that sets this header for all requests.

---

## 🧠 How the Solver Works

1. **Domain pruning** — sections with any blocked meeting are removed before solving
2. **Constraint encoding** — capacity limits, no-clash (across every meeting of a section), one section per subject
3. **Objective** — minimise Σ(time-slot penalty + faculty-mismatch penalty) across all students
4. **Fairness bound** — per-student penalty cap (configurable)
5. **Gap reduction** — post-processing pass that shifts students into alternative sections to remove idle
   schedule gaps, but only when it does not increase any student's penalty
6. **Baselines** — independent FCFS and random greedy heuristics are run under the same hard constraints for
   an honest before/after comparison on the dashboard

---

## 🛠 Tech Stack

- **Backend**: Python · FastAPI · Google OR-Tools (CP-SAT)
- **Frontend**: React 18 · Vite · Axios
