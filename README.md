# PWSSAP — Department Timetable Generation & Student Sectioning

**P**reference-**W**eighted **S**tudent-**S**ection **A**llocation **P**rototype

PWSSAP generates a whole department's **semester master timetable** (the recurring weekly schedule across all departmental semesters for the entire academic term) **and** assigns every student to a section in one optimisation, using Google OR-Tools **CP-SAT**. Teacher availability, clash-freedom, capacity and teacher load caps are **hard** rules; students' time-slot and faculty preferences are optimised as far as is mathematically possible, and the system tells you honestly how far that is.

| | |
|---|---|
| **Backend** | Python · FastAPI · OR-Tools CP-SAT · in-memory store |
| **Frontend** | React 19 · Vite 8 · Axios (no UI library) |
| **Demo scale** | 466 students · 29 subjects · 21 teachers · 5,144 course enrolments · 199 sections |
| **Best measured result** | 12 of 6,094 student meetings (0.20 %) in a student-blocked slot — *proven minimum* for the chosen timetable |
| **Tests** | 191 passing (+2 opt-in slow full-department tests) |

> Full technical and project context for reports, posters and presentations lives in **[`context.md`](context.md)**.

---

## Table of contents
1. [What it does](#what-it-does)
2. [How the solver works](#how-the-solver-works)
3. [Two scheduling modes](#two-scheduling-modes)
4. [Quick start](#quick-start)
5. [Authentication](#authentication)
6. [Using the app](#using-the-app)
7. [Data files (CSV)](#data-files-csv)
8. [Timetable rules](#timetable-rules)
9. [Results](#results)
10. [Testing](#testing)
11. [Project structure](#project-structure)
12. [API](#api)
13. [Known limitations](#known-limitations)

---

## What it does

- **Data in:** subjects, teachers (with the subjects they can teach and weekly-hour caps), students and
  elective allocations, all from CSV with row-level validation (all-or-nothing imports). Supports multi-semester
  department scopes simultaneously (e.g. Even Semesters 4 & 6).
- **Students:** lock in electives, rate the 19 usable timetable slots (Preferred / Tolerable / Disliked / Blocked)
  within a **course-load-based blocked quota**, and optionally rank faculty.
- **Admins:** mark teacher unavailability, generate sections (preference-weighted or division/batch), run the solver
  (with feasibility check, multi-candidate search, stop button), review the published semester timetable, make
  post-publication touch-ups/overrides, and save/compare solved runs.
- **Output:** a clash-free semester master timetable and a section for every student, with:
  - a student view showing a **satisfaction score**, cohort average, preference breakdown, and a clear notice if a
    blocked slot was unavoidable;
  - a teacher view with their semester schedule and printable/exportable **class rosters**;
  - an admin view with the department master schedule matrix, section list, and teacher workload.
- **Honest diagnostics:** per-stage solver status, blocked-slot count with *proven-minimum* flag, candidate leaderboard,
  gap-reduction statistics, and readable warnings.

## How the solver works

```
CSV + preferences ──► Stage 1: master timetable (slots + teachers, CP-SAT)
                  ──► Stage 2: student sectioning (CP-SAT)
                         Phase 0  find any valid assignment
                         Pass A   minimise students placed in blocked slots (only this)
                         Pass B   optimise everything else, blocked count capped at Pass A's optimum
                  ──► Stage 3: gap-reduction heuristic (never moves a student into a blocked/disliked slot)
                  ──► score the delivered assignment ──► publish
```

**Hard constraints:** teacher availability · teacher and student no-clash (per half-slot) · section capacity ·
teacher-per-subject weekly load caps · slot legality (no theory in slot 4, nothing in Mon-1) · meeting spacing rules ·
division/batch non-overlap.
**Soft objectives:** student time preferences (lexicographically prioritizing blocked-slot minimization in Pass A before
optimizing tolerable/preferred in Pass B) · faculty preferences (lower weight) · section-size balance · teacher load balance.

**Why "blocked" is minimised rather than absolute.** Making every student's blocked slot a hard rule is infeasible on real
data (one 56-student elective's blocks covered all 14 theory-legal slots). PWSSAP therefore uses three layers: a
**dynamic quota** (`max(1, ⌊(19 − N)/4⌋)` blocks for N enrolled subjects), **steering** in Stage 1, and **lexicographic
minimisation** in Stage 2 so blocked placements are never traded away for other preferences.

**Multi-candidate search.** With several candidates the solver builds and *scores* many master timetables (about 60 % of the
time budget), then fully optimises only the best one. The time limit is a **shared total**, not per candidate.

**Status meaning.** Overall `OPTIMAL` requires *both* stages proven optimal. On the full demo data Stage 1 is
`FEASIBLE`, so a normal result is `FEASIBLE`. If nothing valid is found, nothing is published.

## Two scheduling modes

| | **Preference-Weighted** (core) | **Traditional Division & Batch** (optional) |
|---|---|---|
| Idea | Students float between parallel sections to match preferences | Fixed divisions (Div-A…) for theory, fixed lab batches (A1…) for labs |
| Students | Placed by the optimiser | **Pinned** to their saved division/batch |
| Electives | Section per demand, solver-placed | Track electives (e.g. Sem 6 PE) form divisions *inside* each track; dispersal electives (e.g. Sem 4 MDM) run at identical times |
| Safety net | Hard constraints in the model | Independent **validator** re-checks the final timetable; failures leave the run *Solved*, not *Published* |
| Generation Route | `POST /admin/runs/{id}/generate-sections` | `POST /admin/cohorts/generate-sections` |
| Where | Admin → Solver | Admin → Classes & Batches, then Solver |

Traditional mode is **per run**: a run is either traditional or standard, and generating sections either way replaces the
previous ones (last generation wins). Student time preferences are used only as the existing soft signal when building the
master timetable. Electives are classified by catalog *shape* (tag/subtag/type), not by name.
Details: [`context.md` §8](context.md).

---

## Quick start

**Prerequisites:** Python 3.11+ (3.12 tested), Node.js 18+, npm.

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Generate secrets
# Required
$env:JWT_SECRET = (python -c "import secrets; print(secrets.token_urlsafe(48))")
# Opitonal
$env:ADMIN_SETUP_TOKEN = (python -c "import secrets; print(secrets.token_urlsafe(32))")

# View tokens
echo $env:JWT_SECRET
echo $env:ADMIN_SETUP_TOKEN

# Start backend
uvicorn main:app --port 8000
# API docs: http://localhost:8000/docs

# Remove tokens from current terminal
Remove-Item Env:JWT_SECRET
Remove-Item Env:ADMIN_SETUP_TOKEN
``` 

**Note:** Keep `JWT_SECRET` unchanged across restarts, or existing JWTs may become invalid. Store it securely rather than generating a new one each time.
> Do **not** add `--reload` while working with loaded data: the store is in memory, and a reload wipes it.

```bash
# 2) Frontend (second terminal)
cd frontend
npm install
npm run dev                      # http://localhost:5173
```

```bash
# 3) Load the demo dataset through the real API (third terminal, from the repo root)
backend\venv\Scripts\python.exe backend\scripts\seed_via_api.py
```
`demo_run/` (the sample CSVs) contains subjects, teachers, students, and elective allocations across Semesters 4 and 6. The seeder
imports the catalog, sets teacher availability, and generates synthetic student time/faculty preferences (about 20–35 s; re-runnable).

Open <http://localhost:5173> and sign in with the role, account ID, and password. The initial Admin login is
**`admin` / `admin`** unless configured otherwise; Student and Teacher credentials are set by roster imports.

**Frontend config:** the API base URL defaults to `http://localhost:8000`; override with `VITE_API_URL` (see
`frontend/.env.example`). The Vite dev server also proxies API paths to port 8000.

**Troubleshooting:** from Python clients use `127.0.0.1` (not `localhost`); a backend restart empties the store, so re-run the
seeder; on the full dataset use a time limit of **≥ 180 s** (1 candidate) or **≥ 240–300 s** (3 candidates).

---

## Authentication

Admin, Student, and Teacher sign-in uses the account role, account ID, and password. The initial Admin account is
`admin` / `admin`, unless `ADMIN_DEFAULT_PASSWORD` is set before the Admin credential is first created. Student and
Teacher accounts are created when their rosters are imported; include a non-empty `password` column in each CSV.
Passwords may be any non-empty value up to 1024 characters for roster accounts.
The bundled demo rosters do not include passwords; set `$env:DEMO_ROSTER_PASSWORD` to a non-empty value before
running the demo seeder to add credentials to those imported accounts.

Passwords are stored as salted scrypt hashes in the SQLite credentials database at
`backend/data/auth.sqlite3` by default (override with `AUTH_DB_PATH`). The credential table is initialized
automatically, with a safe migration for the `active` column. Credentials are separate from the in-memory timetable
data. Passwords and hashes are not returned by the API. Re-importing an existing account reactivates it without
changing its password; clearing a Student or Teacher roster deactivates those accounts.

After successful sign-in, the API returns a signed JWT bearer token that expires after one hour. The frontend sends
it with authenticated API requests, and the backend enforces role and identity permissions. Students and Teachers
cannot change or reset passwords. Only an authenticated Admin can change the Admin password; the sign-in page shows
that option only while the Admin role is selected. The new Admin password must be at least 8 characters.

`JWT_SECRET` is required to start the backend and must be at least 32 bytes. Keep its value private and stable across
restarts; changing it invalidates existing tokens. PowerShell environment variables last only for the current terminal,
so save the generated JWT secret privately and set the same value again in each new backend terminal.
`ADMIN_SETUP_TOKEN` is optional for normal backend use and sign-in, but must be configured with at least 32 bytes to
enable Admin password changes. Generate the values in the backend PowerShell terminal using the commands above.
To display the current setup token in that terminal, run
`$env:ADMIN_SETUP_TOKEN`; to copy it without displaying it, run
`Set-Clipboard -Value $env:ADMIN_SETUP_TOKEN`. Keep it private and enter it in the Admin password-change form.
The setup token is accepted only for the Admin password operation and does not grant general administrative access.
`Remove-Item Env:ADMIN_SETUP_TOKEN` removes the value from that terminal session, but does not remove it from an
already-running backend process. Configure a token before starting the backend if you need to enable password changes.

---

## Using the app

### Admin (sidebar)
1. **Dashboard** — 6-step setup checklist with live progress.
2. **Students** — upload roster CSV (preview + error report), inspect lock-ins, override a student's electives.
3. **Subjects** — upload catalog, configure choice-based tags, bulk-upload elective allocations.
4. **Teachers** — upload teachers with capabilities and weekly-hour caps.
5. **Availability** — click cells to block teacher slots (hard constraint).
6. **Classes & Batches** — Traditional mode setup, move students between divisions, 2–6 lab batches, generate sections.
7. **Solver** — generate sections, set time limit and candidates, *Check Feasibility*, *Run*, *Stop*; read the result card,
   candidate leaderboard and warnings; save, activate and **compare** solved runs side by side.
8. **Published Timetable** — master schedule matrix, section list, teacher workload.
9. **Touch-ups (Overrides)** — enrol/unenrol a student, reassign a teacher, override a section's capacity (with live clash/capacity checks and session audit log).

### Student
**Elective Lock-in → Time Preferences** (click cycles Indifferent → Preferred → Tolerable → Disliked → Blocked; a live quota counter
stops over-blocking) **→ Faculty Preferences → My Timetable** (satisfaction score, notices, **Download Timetable (PDF)** via the
browser's print dialog, CSV export).

### Teacher
**My Timetable & Rosters** — semester schedule grid, per-section rosters with search, printable roster (optional attendance columns), CSV exports.

---

## Data files (CSV)

| File | Columns | Notes |
|---|---|---|
| `subjects.csv` | `subject_code, subject_name, subject_tag, [subtag], semester, type(theory\|lab), weekly_hours, capacity, [slot_structure]` | Subtags may be shared as `AIML\|DS`; `slot_structure` examples: `2+1`, `2+2`. Accepts aliases: `name`, `tag`, `hours`, `linked_pattern`. |
| `teachers.csv` | `teacher_id, teacher_name, subject_1, [subject_1_load], subject_2, [subject_2_load], …` | Supports paired load caps (`subject_1_load`) or variable-width ragged subject lists without loads. |
| `students.csv` | `roll_number, name, semester` | Standard student roster. |
| `semN_electives.csv` | `roll_number, [student_name], <one column per choice tag, e.g. MDM or PE>` | Lines starting with `#` are ignored; accepts aliases for roll number (`roll_no`, `rollno`, `roll`). |

Import order: **subjects → teachers → students → elective allocations**. Imports are all-or-nothing and report row-level errors.

## Timetable rules

1. **Grid:** Monday–Friday × 4 two-hour slots (09:00–11:00, 11:15–13:15, 13:45–15:45, 15:45–17:45) = 20 slots.
2. **`Mon-1` is reserved** (no theory, no lab) → 19 usable slots.
3. **Slot 4 is lab-only** → 14 theory-legal slots.
4. **3-hour subjects** are split into a 2-hour meeting plus a 1-hour remainder (first or second hour of a slot); two remainders may share a slot without overlapping.
5. **Multi-meeting theory** sections meet at most once per day; multi-meeting labs are never back-to-back on a day.
6. **Sections (Preference-Weighted mode):** `ceil(enrolled / capacity)` per subject (seats ≥ enrolled students). Traditional mode instead creates one theory section per division and one lab section per batch.
7. **Teacher availability** and weekly load caps are never violated.

## Results

Measured 2026-10-18 on one Windows machine (Python 3.12, OR-Tools 9.15), full demo dataset (Semesters 4 & 6), synthetic adversarial student
preferences; CP-SAT under a time limit varies slightly between runs. Reproduce with the commands shown.

| Run | Command | Outcome |
|---|---|---|
| Preference-Weighted, 3 candidates, 300 s | `python scripts/run_stress_test.py --candidates 3 --time-limit 300` | **12 / 6,094** meetings in blocked slots (0.20 %, proven minimum); penalty 63,489; candidate quick-scores 210 / 12 / 151 |
| Traditional, 120 s | `python scripts/run_traditional_probe.py --time-limit 120` | **0 validation violations**; 215 blocked placements (preferences are not used for allocation); 208 sections, 466 students pinned |

Earlier in development, before blocked slots were minimised first, the same kind of run left roughly 250–300 students in blocked
slots. API responsiveness during a solve was verified (0 errors over 180 polls); student/teacher timetable lookups take ~0–16 ms.
Details and caveats: [`context.md` §14](context.md).

## Testing

```bash
cd backend
venv\Scripts\activate
pytest tests -q                       # 191 passed, 2 skipped (~14 s)

# opt-in, ~2 minutes each: full 466-student department solves
set RUN_SLOW=1                        # macOS/Linux: export RUN_SLOW=1
pytest tests/test_full_department_regression.py tests/test_traditional_full_department.py -q

# headless probes
python scripts/ui_flow_probe.py       # replays the admin flow against a running, seeded backend
```

```bash
cd frontend
npm run build                         # production build
npm run lint                          # note: currently reports 14 pre-existing style problems in 2 files
node src/pages/admin/cohortsLogic.check.mjs
```

Coverage areas: CSV parsers, validation and quota rules, grid and section generation (incl. 3-hour subjects), solver engine and
**regression tests** (infeasible cohort blocks, honest objective, Pass A/B, portfolio, cancellation), gap reduction, HTTP-level API
tests, run-lifecycle safety (single-solve lock, hidden placeholders, cleanup), saved runs, and Traditional mode. There are **no
automated browser tests**.

## Project structure

```
pwssap-prototype/
├── backend/
│   ├── main.py                  FastAPI app, CORS, router wiring
│   ├── api/                     HTTP routers (availability, cohorts, cycle, faculty_preferences, meta, overrides,
│   │                            preferences, runs, sections, solver, students, subjects, teachers; deps.py = admin guard)
│   ├── domain/                  Rules and models: enums, models, timeslots, validation, section_generation,
│   │                            cohorts, traditional_plan / _section_generation / _validation, saved_runs
│   ├── ingestion/               CSV parsers: subjects, teachers, students
│   ├── solver/                  engine.py (CP-SAT), service.py (orchestration), gap_reduction.py
│   ├── data/                    store.py (in-memory store); saved_runs/ (JSON snapshots, git-ignored)
│   ├── scripts/                 seed_via_api, ui_flow_probe, run_stress_test, run_traditional_probe
│   └── tests/                   pytest suite
├── frontend/
│   └── src/                     App.jsx, constants.js, api/ (Axios clients), components/, pages/{admin,student,teacher}
├── demo_run/                    sample CSVs across active semesters (Sem 4 & Sem 6)
├── context.md                   full project context for documentation
└── README.md
```

## API

68 application endpoints (49 admin-only, 19 public; 72 total HTTP routes including Swagger UI / OpenAPI docs) — browse them
interactively at **<http://localhost:8000/docs>**. Admin routes require the header `X-Role: admin`.

**Key solver workflows:**
- **Preference-Weighted Mode:** `POST /admin/cycle/initialize` → `POST /admin/runs/{id}/generate-sections` → `POST /admin/runs/{id}/solve?time_limit=&candidates=` → `GET /admin/runs/{id}/summary`
- **Traditional Division & Batch Mode:** `POST /admin/cohorts/save` → `POST /admin/cohorts/generate-sections` → `POST /admin/runs/{id}/solve` → `GET /admin/cohorts/validation`
Full table: [`context.md` §10](context.md).

## Known limitations

- **In-memory data:** a backend restart wipes everything except saved-run JSON snapshots; re-import data afterwards.
- **CORS is open** (`allow_origins=["*"]`), consistent with the local prototype setup.
- **Solves take minutes** on the full department; short time limits give worse results or no result. The progress bar is a timer.
- **Blocked slots are minimised, not guaranteed zero** (the UI reports the count and whether it is the proven minimum).
- **Traditional mode** ignores student preferences during allocation, and a few divisions/electives exceed nominal capacity (generation warnings).
- No room/venue modelling, no exam scheduling, semesters 1–2 unsupported; UI performance has not been measured in a browser.

## License

Internal Department Prototype — Academic Year 2026–27.
