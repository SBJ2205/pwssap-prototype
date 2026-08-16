# Frontend changes in this build

Everything below was added on top of the existing frontend/backend without
changing the original visual design — same layout, same colors in light mode,
same components.

## 1. Dark mode
- Every color is now a CSS variable (`frontend/src/index.css`), themed via
  `data-theme="light"|"dark"` on `<html>`.
- Toggle lives at the bottom of the sidebar. Persisted in localStorage,
  defaults to your OS preference on first visit.
- Light mode is pixel-identical to before — the variables just default to the
  original hardcoded hex values.

## 2. Admin CRUD (previously read-only / missing)
- **Slot Instances page**: create / edit / delete sections, not just a table.
- **New "Manage Catalog" page**: add/delete Teachers, Subjects, Students.
- **CSV bulk import** for sections, with a downloadable template.
- **CSV export** for sections and for a student's personal timetable.
- **PDF export** for the timetable via a print-optimized view (hides sidebar
  and pickers, keeps just the grid — use the browser's "Save as PDF").

All of this calls the `/admin/*` endpoints that already existed in the
backend (`backend/api/admin.py`) but weren't wired up on the frontend yet.

## 3. Login screen
- New entry screen (`frontend/src/pages/LoginPage.jsx`) using the same design
  system as the rest of the app (same `Card`, colors, fonts).
- **Admin**: enter a name (optional) and continue — gets the full admin view.
- **Student**: search/select yourself from the actual student roster (pulled
  live from `GET /students`), then continue.
- Once logged in as a specific student, that student is **locked** to their
  own preferences/timetable — the "Students" picker on the Prefs / Faculty
  Prefs / Timetable pages only shows their own row, so they can no longer
  browse or edit anyone else's data (previously any "student" could switch to
  any student via a dropdown). Admins are unaffected and can still browse
  everyone.
- Sidebar's old "Viewing as Admin/Student" toggle is replaced with a
  "Logged in as ⟨name⟩" readout + a Log out button, in the same visual slot
  and style.
- Session (role + which student) persists in localStorage across reloads,
  same mechanism as before — log out to switch identities.


```bash
cd backend
pip install fastapi uvicorn ortools pydantic
python3 -m uvicorn main:app --reload

# separate terminal
cd frontend
npm install
npm run dev
```
Frontend defaults to `http://localhost:8000` for the API — override with a
`frontend/.env` containing `VITE_API_URL=...` if needed.
