# PWSSAP — Department Timetable Generation System

An end-to-end department-scoped academic timetable scheduling platform powered by Google OR-Tools CP-SAT. The system coordinates CSV data ingestion, curriculum and elective choice management, student time and faculty preference matrices, teacher availability constraints, automated constraint-satisfaction solving, post-publication administrative overrides, and role-based student/teacher timetable portals with PDF exports.

---

## 🌟 Key Highlights & Capabilities

- **Automated CP-SAT Scheduling Engine**:
  - Solves multi-section teacher assignment and time-slot scheduling simultaneously.
  - Multi-objective optimization: maximizes student time preferences, breaks ties using secondary faculty preferences, and enforces equal teacher load distribution.
  - Handles **3-hour subjects** by accurately scheduling one 2-hour meeting and one 1-hour remainder with interval-level clash detection and slot sharing.
  - Hard constraint guarantees: strictly zero student clashes, zero teacher double-booking, zero teacher availability violations, and strict elective theory/lab cohort synchronization.
- **Streamlined 6-Step Administrative Workflow**:
  1. Student Roster Ingestion & Cohort Setup
  2. Subject Catalog, Elective Groups & Choice Lock-In Configuration
  3. Faculty Capabilities & Workload Limits
  4. Teacher Availability Grid & Hard Constraints
  5. Student Elective Overrides & Choice Tracking
  6. Automated CP-SAT Solver Execution & Publication
- **Personalized Student Experience**:
  - Name and roll number persistence across the portal.
  - Elective course track lock-in with real-time cohort tracking.
  - Blind time-slot preference rating (Preferred, Tolerable, Disliked, Blocked) and secondary faculty ranking.
  - Responsive weekly schedule grid with uniform block sizing, horizontal scrolling, and one-click **PDF Download** formatted for A4 landscape with institutional header.
- **Teacher Schedule & Class Rosters**:
  - Weekly teaching grid showing assigned sections, timings, and weekly hours.
  - Enrollment view with printable student rosters and attendance sheets.
  - CSV export for personal calendar imports.
- **Administrative Overrides & Inspection**:
  - Post-solve manual reassignment of teachers, time slots, and section enrollments with instant clash checking and capacity validation.

---

## 🗂 Project Structure

```
pwssap-prototype/
├── backend/
│   ├── api/                   # FastAPI route handlers
│   │   ├── availability.py    # Teacher availability endpoints
│   │   ├── cycle.py           # Department cycle management
│   │   ├── overrides.py       # Post-solve manual override endpoints
│   │   ├── preferences.py     # Student time & timetable endpoints
│   │   ├── runs.py            # Solver generation runs & cycle scoping
│   │   ├── sections.py        # Section generation & timetable preparation
│   │   ├── solver.py          # Solver trigger & status endpoints
│   │   ├── students.py        # Student catalog & choice allocation
│   │   ├── subjects.py        # Subject catalog & choice-tag configuration
│   │   └── teachers.py        # Teacher catalog, capabilities & timetables
│   ├── data/
│   │   └── store.py           # In-memory thread-safe state store
│   ├── domain/                # Core business domain models & rules
│   │   ├── enums.py           # RunStatus, SubjectType, Weekday enums
│   │   ├── models.py          # Domain dataclasses & schemas
│   │   ├── section_generation.py # Section splitting & slot structure parsing
│   │   ├── timeslots.py       # Canonical 5×4 timetable grid
│   │   └── validation.py      # Input validation & constraint checking
│   ├── ingestion/             # CSV ingestion & validation parsers
│   │   ├── students_csv.py    # Student roster parser
│   │   ├── subjects_csv.py    # Subject catalog parser
│   │   └── teachers_csv.py    # Faculty capability parser
│   ├── solver/                # Optimization & scheduling engine
│   │   ├── engine.py          # CP-SAT constraint formulation & solve logic
│   │   └── service.py         # Solver lifecycle orchestration
│   ├── tests/                 # Comprehensive test suite (130 pytest + 79 solver tests)
│   ├── main.py                # FastAPI application entrypoint
│   └── requirements.txt       # Python dependencies
├── frontend/                  # React 19 + Vite single-page application
│   ├── src/
│   │   ├── api/               # Axios API clients
│   │   ├── components/        # Reusable UI components & dialogs
│   │   ├── pages/             # Admin, Teacher, and Student pages
│   │   ├── App.jsx            # Application orchestrator & session state
│   │   └── constants.js       # Navigation, slot definitions & color scales
│   └── package.json           # Frontend dependencies & scripts
├── demo_run/                  # Sample CSV data for end-to-end demonstrations
└── README.md
```

---

## 🚀 Getting Started

### 1. Prerequisites

- Python 3.11+
- Node.js 18+ and npm

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start backend server
uvicorn main:app --reload --port 8000
```

The backend API documentation is available at **http://localhost:8000/docs**.

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The web application is available at **http://localhost:5173**.

---

## 🧪 Testing & Validation

### Backend Tests

Run the complete backend test suite using `pytest`:

```bash
cd backend
venv\Scripts\activate
pytest tests
```

To run the solver verification scripts directly:

```bash
python -m tests.test_solver
python -m tests.test_solver_3hour
python -m tests.test_section_generation
```

### Frontend Validation

```bash
cd frontend
npm run lint
npm run build
```

---

## 📐 Canonical Timetable Rules

1. **Grid Geometry**: 5 days (Monday through Friday) × 4 time slots per day.
2. **Institute Reserved Slot**: Monday Slot 1 (09:00–11:00) is reserved for institute/department-level assemblies and meetings; no classes or labs are scheduled here.
3. **Lab Exclusivity**: Slot 4 (15:45–17:45) across all days is strictly dedicated to laboratory practicals; core theory subjects cannot be scheduled in Slot 4.
4. **3-Hour Subjects**: Configured with a `2+1` slot structure, scheduled as one full 2-hour meeting and one 1-hour remainder session. Two 1-hour remainder sessions can share a single 2-hour slot with accurate start/end intervals without overlap.
5. **Teacher Availability**: Faculty availability preferences are treated as hard constraints; instructors are never scheduled in unapproved or blocked slots.

---

## 📄 License

Internal Department Prototype — Academic Year 2025–26.
