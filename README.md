# PWSSAP — Preference-Weighted Section & Slot Assignment Prototype

A full-stack prototype for automated student section assignment based on **time-slot preferences**.  
Students rate abstract time periods (not specific subjects), and the **OR-Tools CP-SAT solver** finds the globally optimal assignment that minimises total dissatisfaction while keeping outcomes fair.

---

## ✨ Features

- **Blind time-slot preference** — students rate 6 days × 4 periods without knowing which subject falls where
- **CP-SAT solver** — Google OR-Tools constraint solver with fairness index cap
- **Penalty scoring** — Preferred = 0 pts · Tolerable = +1 pt · Disliked = +3 pts · Blocked = never assigned
- **Dashboard** — penalty breakdown, per-student results, comparison against FCFS & random baselines
- **Personal timetable** — colour-coded by preference satisfaction

---

## 🗂 Project Structure

```
pwssap-prototype/
├── backend/          # FastAPI + OR-Tools Python server
│   └── main.py
└── frontend/         # React (Vite) single-page app
    └── src/
        └── App.jsx
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

---

## 🔌 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/slots` | All slot instances (subject × section × time) |
| `GET` | `/students` | All students |
| `GET` | `/timeslots` | Canonical 6×4 time-slot grid |
| `GET` | `/prefs/{id}` | Get a student's time-slot preferences |
| `POST` | `/prefs/{id}` | Save a student's time-slot preferences |
| `POST` | `/solve` | Run the CP-SAT solver |
| `GET` | `/results` | Last solver result |

---

## 🧠 How the Solver Works

1. **Domain pruning** — blocked slots removed before solving
2. **Constraint encoding** — capacity limits, no-clash, one section per subject
3. **Objective** — minimise Σ(penalty) across all students
4. **Fairness bound** — per-student penalty cap (configurable)
5. **Gap reduction** — post-processing to minimise idle schedule gaps

---

## 🛠 Tech Stack

- **Backend**: Python · FastAPI · Google OR-Tools (CP-SAT)
- **Frontend**: React 18 · Vite · Axios
