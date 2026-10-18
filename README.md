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

## 🏫 Traditional Division & Batch Mode (optional)

An alternative to the preference-weighted flow: fixed **divisions** (Div A, B, ...) for theory and fixed
**lab batches** (A1..A3, ...) for labs. The preference-weighted solver stays the core product; traditional
mode only layers on top of it and does nothing for runs that were not generated in it.

**Flow** (admin, *Classes & Batches* page): set divisions and batches for each semester of the run, move
students between divisions, *Save & generate sections*, then use the normal **Solver** page and press Run.

**How it relates to runs and preference mode**

- It is **per run**. A run is either traditional or standard; generating sections either way replaces the
  run's previous sections (and, as in standard generation, every other run's), so the last generation wins.
  If standard generation replaces a traditional run's sections, the traditional plan retires itself and the
  run behaves as a normal preference-weighted run. Do not press the Solver page's own *Generate Sections*
  on a traditional run unless you want that.
- Every semester of the run needs a saved setup before generating.
- Student time preferences are used only as the existing soft signal when building the master timetable.
  Student allocation ignores them: students are **pinned** to the sections of their saved division/batch.
- Pins are applied only after a successful solve (an unsolved run shows no student timetables). The solver
  hook then re-validates the result; on any violation the run is left *Solved*, not *Published*, and the
  violations are returned in the solve warnings and `GET /admin/cohorts/validation`.
- Electives are classified by catalog *shape*, not name. A choice-based tag with >= 2 subtags and at least
  one lab is a **track** (e.g. Sem 6 PE: divisions form inside each track). A choice-based tag with >= 2
  subtags whose subjects are all theory is a **dispersal** elective (e.g. Sem 4 MDM): one section per
  subject, all at identical times, clear of core classes. A choice tag with a single offering, and any
  non-choice subject (including labs such as `MDM03` and `OEC14`), is taught in-class.
- Section labels follow the engine's conventions: `{code}-T{k}` per division, `{code}-L{b}` per batch.

**Engine/solver touch points** (all additive, inert for other runs and covered by
`tests/test_engine_traditional_hooks.py`): `SolverInput.batch_division_map` (explicit batch -> division),
`SolverInput.sync_section_groups` (dispersal synchronisation), and two hook calls in `solver/service.py`.

**Try it on the real data:** `python scripts/run_traditional_probe.py --time-limit 120`. Opt-in end-to-end
test: `set RUN_SLOW=1` then `pytest tests/test_traditional_full_department.py -q`.

## 📄 License

Internal Department Prototype — Academic Year 2026–27.
