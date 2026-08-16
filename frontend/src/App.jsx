import { useEffect, useState } from "react";

import {
  createSection, createStudent, createSubject, createTeacher,
  deleteSection, deleteStudent, deleteSubject, deleteTeacher,
  listTeachers, updateSection,
} from "./api/admin";
import { getFacultyBySubject, getSections, getStudents, getSubjects } from "./api/catalog";
import { setRole as setApiRole } from "./api/client";
import { getFacultyPrefs, getPrefs, saveFacultyPrefs as apiSaveFacultyPrefs, savePrefs as apiSavePrefs } from "./api/preferences";
import { getResults, runSolve } from "./api/solver";
import Sidebar from "./components/Sidebar";
import { Card, ErrorState, LoadingState } from "./components/ui";
import { NAV } from "./constants";
import CatalogPage from "./pages/CatalogPage";
import DashboardPage from "./pages/DashboardPage";
import FacultyPrefsPage from "./pages/FacultyPrefsPage";
import LoginPage from "./pages/LoginPage";
import PrefsPage from "./pages/PrefsPage";
import SlotsPage from "./pages/SlotsPage";
import SolverPage from "./pages/SolverPage";
import TimetablePage from "./pages/TimetablePage";

export default function App() {
  // Minimal local-prototype identity concept (see backend/api/deps.py). No
  // real password auth on the backend — logging in just asserts a role (and,
  // for a student, which student), which the backend enforces on admin-only
  // routes (e.g. GET /sections, all /admin/* CRUD) and which the frontend
  // uses to lock a student to their own data (see lockedStudentId below).
  const [session, setSession] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("pwssap_session"));
    } catch {
      return null;
    }
  });
  const role = session?.role ?? null;
  const [page, setPage] = useState(() => (role === "student" ? "prefs" : "slots"));

  const [slots, setSlots] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [students, setStudents] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [selStudent, setSelStudent] = useState(() => (session?.role === "student" ? session.studentId : 0));
  const [prefs, setPrefs] = useState({});
  const [warnings, setWarnings] = useState([]);
  const [solving, setSolving] = useState(false);
  const [solveProgress, setSolveProgress] = useState(0);
  const [results, setResults] = useState(null);
  const [fairness, setFairness] = useState(12);
  const [facultyBySubject, setFacultyBySubject] = useState({});
  const [facultyPrefs, setFacultyPrefs] = useState({});
  const [facultyWeight, setFacultyWeight] = useState(1);
  const [enableGapReduction, setEnableGapReduction] = useState(true);

  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState(null);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    if (!session) return;
    localStorage.setItem("pwssap_session", JSON.stringify(session));
    // Every request carries the current role; the backend rejects
    // admin-only routes for anything other than role=admin.
    setApiRole(session.role);
  }, [session]);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;

    // Reset loading/error before kicking off the fetch for the new role or
    // reload tick. This runs synchronously at the top of the effect (an
    // intentional, standard "reset before fetch" pattern), not in response
    // to an external event, so it's exempted from set-state-in-effect below.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCatalogLoading(true);
    setCatalogError(null);

    // /sections and /admin/teachers are admin-only — a student caller
    // would get a 403, so don't even ask for them.
    const sectionsPromise = role === "admin" ? getSections().catch(() => []) : Promise.resolve([]);
    const teachersPromise = role === "admin" ? listTeachers().catch(() => []) : Promise.resolve([]);

    Promise.all([
      sectionsPromise,
      teachersPromise,
      getSubjects(),
      getStudents(),
      getFacultyBySubject(),
      // Pick up the last solver run (if any) so results survive a page
      // reload and are visible to students who weren't present when
      // admin ran it.
      getResults().catch(() => ({ status: "NOT_RUN" })),
    ])
      .then(([sectionsData, teachersData, subjectsData, studentsData, facultyData, resultsData]) => {
        if (cancelled) return;
        setSlots(sectionsData);
        setTeachers(teachersData);
        setSubjects(subjectsData);
        setStudents(studentsData);
        setFacultyBySubject(facultyData);
        if (resultsData?.status === "OPTIMAL") setResults(resultsData);
      })
      .catch(e => {
        if (!cancelled) setCatalogError(e.message || "Failed to load data from the server.");
      })
      .finally(() => {
        if (!cancelled) setCatalogLoading(false);
      });

    return () => { cancelled = true; };
  }, [role, reloadTick, session]);

  useEffect(() => {
    if (!session || students.length === 0) return;
    getPrefs(selStudent).then(setPrefs);
    getFacultyPrefs(selStudent).then(setFacultyPrefs);
    // Clear stale warnings from the previously selected student immediately
    // (before their prefs resolve), not in reaction to an external event.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setWarnings([]);
  }, [selStudent, students, session]);

  // tsKey = "Mon|9:00" string
  function cycleRating(tsKey) {
    const cur = prefs[tsKey] ?? 0;
    const next = cur >= 4 ? 0 : cur + 1;
    const updated = { ...prefs };
    if (next === 0) delete updated[tsKey];
    else updated[tsKey] = next;
    setPrefs(updated);
  }

  async function savePrefs() {
    const data = await apiSavePrefs(selStudent, prefs);
    setWarnings(data.warnings || []);
    alert(data.warnings.length === 0
      ? "Preferences saved! No feasibility issues."
      : "Saved with warnings:\n" + data.warnings.join("\n"));
  }

  // Faculty ratings are PER SUBJECT (a professor's ranking under one subject
  // is independent of the same professor under another), and keyed by
  // teacher_id (not name) to match the backend's normalized domain model.
  // Cycle 0 (Indifferent) → 3 (Disliked) — no "Blocked" option, faculty
  // mismatch is always a soft secondary penalty, never a hard block.
  function cycleFacultyRating(subjCode, teacherId) {
    const subjPrefs = facultyPrefs[subjCode] ?? {};
    const cur = subjPrefs[teacherId] ?? 0;
    const next = cur >= 3 ? 0 : cur + 1;
    const updatedSubj = { ...subjPrefs };
    if (next === 0) delete updatedSubj[teacherId];
    else updatedSubj[teacherId] = next;
    setFacultyPrefs({ ...facultyPrefs, [subjCode]: updatedSubj });
  }

  async function saveFacultyPrefs() {
    await apiSaveFacultyPrefs(selStudent, facultyPrefs);
    alert("Faculty preferences saved!");
  }

  function handleLogin(newSession) {
    setSession(newSession);
    if (newSession.role === "student") setSelStudent(newSession.studentId);
    setPage(newSession.role === "student" ? "prefs" : "slots");
  }

  function handleLogout() {
    localStorage.removeItem("pwssap_session");
    setSession(null);
  }

  async function runSolver() {
    setSolving(true);
    setSolveProgress(0);
    setResults(null);
    // Animate progress bar
    let prog = 0;
    const interval = setInterval(() => {
      prog = Math.min(prog + Math.random() * 15 + 5, 92);
      setSolveProgress(Math.round(prog));
    }, 150);
    try {
      const data = await runSolve({
        fairness_index: fairness,
        faculty_weight: facultyWeight,
        enable_gap_reduction: enableGapReduction,
      });
      clearInterval(interval);
      setSolveProgress(100);
      setResults(data);
    } catch (e) {
      clearInterval(interval);
      if (e.response?.status === 403) {
        alert("Only admin can run the solver. Switch to \"Admin\" in the sidebar first.");
      } else {
        alert("Solver error: " + e.message);
      }
    }
    setSolving(false);
  }

  const isAdminPage = NAV.find(n => n.key === page)?.group === "Admin";

  if (!session) {
    return <LoginPage onLogin={handleLogin} />;
  }

  const lockedStudentId = session.role === "student" ? session.studentId : null;

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "system-ui, sans-serif", fontSize: 14, background: "var(--bg-page)", color: "var(--text-primary)" }}>
      <Sidebar role={role} name={session.name} onLogout={handleLogout} page={page} setPage={setPage} />

      {/* Main */}
      <div style={{ flex: 1, overflowY: "auto", padding: "28px 32px" }}>
        {catalogLoading && <LoadingState label="Loading PWSSAP data…" />}

        {!catalogLoading && catalogError && (
          <ErrorState message={catalogError} onRetry={() => setReloadTick(t => t + 1)} />
        )}

        {!catalogLoading && !catalogError && <>
          {role !== "admin" && isAdminPage && (
            <Card><div style={{ color: "var(--rating-red-fg)", fontSize: 13 }}>This section is admin-only. Switch to "Admin" in the sidebar to view it.</div></Card>
          )}
          {(role === "admin" || !isAdminPage) && <>
            {page === "catalog" && <CatalogPage
              teachers={teachers} subjects={subjects} students={students}
              onCreateTeacher={createTeacher} onDeleteTeacher={deleteTeacher}
              onCreateSubject={createSubject} onDeleteSubject={deleteSubject}
              onCreateStudent={createStudent} onDeleteStudent={deleteStudent}
              reload={() => setReloadTick(t => t + 1)} />}
            {page === "slots" && <SlotsPage slots={slots} subjects={subjects} teachers={teachers}
              onCreate={createSection} onUpdate={updateSection} onDelete={deleteSection}
              reload={() => setReloadTick(t => t + 1)} />}
            {page === "solver" && <SolverPage solving={solving} progress={solveProgress} results={results} fairness={fairness} setFairness={setFairness}
              facultyWeight={facultyWeight} setFacultyWeight={setFacultyWeight}
              enableGapReduction={enableGapReduction} setEnableGapReduction={setEnableGapReduction}
              runSolver={runSolver} setPage={setPage} />}
            {page === "dashboard" && <DashboardPage results={results} />}
            {page === "prefs" && <PrefsPage students={students} selStudent={selStudent} setSelStudent={setSelStudent} prefs={prefs} cycleRating={cycleRating} savePrefs={savePrefs} warnings={warnings} lockedStudentId={lockedStudentId} />}
            {page === "facultyprefs" && <FacultyPrefsPage students={students} subjects={subjects} facultyBySubject={facultyBySubject} selStudent={selStudent} setSelStudent={setSelStudent} facultyPrefs={facultyPrefs} cycleFacultyRating={cycleFacultyRating} saveFacultyPrefs={saveFacultyPrefs} lockedStudentId={lockedStudentId} />}
            {page === "timetable" && <TimetablePage students={students} results={results} selStudent={selStudent} setSelStudent={setSelStudent} lockedStudentId={lockedStudentId} />}
          </>}
        </>}
      </div>
    </div>
  );
}
