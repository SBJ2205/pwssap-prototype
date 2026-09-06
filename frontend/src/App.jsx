import "./App.css";
import { useCallback, useEffect, useState } from "react";


import { getStudents, getTeachers, getStudentLockIn } from "./api/catalog";
import { listRuns } from "./api/runs";
import { getCycleStatus } from "./api/cycle";
import { setRole as setApiRole } from "./api/client";
import Sidebar from "./components/Sidebar";
import { ErrorState, LoadingState } from "./components/ui";
import EntryScreen from "./pages/EntryScreen";

// Admin pages
import AdminDashboard from "./pages/admin/AdminDashboard";
import AdminRuns from "./pages/admin/AdminRuns";
import AdminSubjects from "./pages/admin/AdminSubjects";
import AdminStudents from "./pages/admin/AdminStudents";
import AdminTeachers from "./pages/admin/AdminTeachers";
import AdminAvailability from "./pages/admin/AdminAvailability";
import AdminSolver from "./pages/admin/AdminSolver";
import AdminTimetable from "./pages/admin/AdminTimetable";
import AdminOverrides from "./pages/admin/AdminOverrides";

// Student pages
import StudentLockIn from "./pages/student/StudentLockIn";
import StudentPrefs from "./pages/student/StudentPrefs";
import StudentFacultyPrefs from "./pages/student/StudentFacultyPrefs";
import StudentTimetable from "./pages/student/StudentTimetable";

// Teacher pages
import TeacherTimetable from "./pages/teacher/TeacherTimetable";

const PAGE_COMPONENTS = {
  "admin-dashboard":    AdminDashboard,
  "admin-runs":         AdminRuns,
  "admin-subjects":     AdminSubjects,
  "admin-students":     AdminStudents,
  "admin-teachers":     AdminTeachers,
  "admin-availability": AdminAvailability,
  "admin-solver":       AdminSolver,
  "admin-timetable":    AdminTimetable,
  "admin-overrides":    AdminOverrides,
  "student-lockin":     StudentLockIn,
  "student-prefs":         StudentPrefs,
  "student-facultyprefs":  StudentFacultyPrefs,
  "student-timetable":     StudentTimetable,
  "teacher-timetable": TeacherTimetable,
};

// Derive initial page from role.
function defaultPage(role) {
  if (role === "admin") return "admin-dashboard";
  if (role === "student") return "student-lockin";
  if (role === "teacher") return "teacher-timetable";
  return null;
}

// Persist session to localStorage so refresh doesn't log you out.
const SESSION_KEY = "pwssap_session";

function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveSession(session) {
  if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  else localStorage.removeItem(SESSION_KEY);
}

export default function App() {
  // session: { role: "admin"|"student"|"teacher", identity: string }
  // identity = "admin", roll_number, or teacher_id
  const [session, setSession] = useState(() => loadSession());
  const [page, setPage] = useState(() => {
    const s = loadSession();
    return s ? defaultPage(s.role) : null;
  });

  // Catalog that the entire app may need across multiple pages.
  // Loaded lazily on first login; refreshed on explicit reload.
  const [students, setStudents] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState(null);
  const [reloadTick, setReloadTick] = useState(0);

  // Sync the X-Role header whenever the session changes.
  useEffect(() => {
    if (session) setApiRole(session.role);
    else setApiRole("student"); // safe default
  }, [session]);

  // Runs & Cycle state for admin context.
  const [runs, setRuns] = useState([]);
  const [cycleStatus, setCycleStatus] = useState(null);
  const [activeRunIdState, setActiveRunIdState] = useState(() => {
    const saved = localStorage.getItem("pwssap_active_run_id");
    if (!saved || saved === "undefined" || saved === "null") return null;
    const parsed = parseInt(saved, 10);
    return isNaN(parsed) ? null : parsed;
  });

  const setActiveRunId = useCallback((id) => {
    if (id != null && !isNaN(Number(id))) {
      const num = Number(id);
      setActiveRunIdState(num);
      localStorage.setItem("pwssap_active_run_id", String(num));
    } else {
      setActiveRunIdState(null);
      localStorage.removeItem("pwssap_active_run_id");
    }
  }, []);

  const refreshRuns = useCallback(async () => {
    if (session?.role !== "admin") return [];
    try {
      const data = await listRuns();
      setRuns(data || []);
      return data || [];
    } catch {
      return [];
    }
  }, [session]);

  const refreshCycle = useCallback(async () => {
    if (session?.role !== "admin") return null;
    try {
      const data = await getCycleStatus();
      setCycleStatus(data);
      return data;
    } catch {
      return null;
    }
  }, [session]);

  // Load global catalog (students + teachers), cycle status and runs once logged in.
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCatalogLoading(true);
    setCatalogError(null);

    const promises = [
      getStudents().catch(() => []),
      getTeachers().catch(() => []),
    ];
    if (session.role === "admin") {
      promises.push(listRuns().catch(() => []));
      promises.push(getCycleStatus().catch(() => null));
    }

    Promise.all(promises)
      .then(([s, t, r, cyc]) => {
        if (cancelled) return;
        setStudents(s);
        setTeachers(t);
        if (r) setRuns(r);
        if (cyc) setCycleStatus(cyc);
      })
      .catch(e => {
        if (!cancelled) setCatalogError(e.message || "Failed to load catalog.");
      })
      .finally(() => {
        if (!cancelled) setCatalogLoading(false);
      });

    return () => { cancelled = true; };
  }, [session, reloadTick]);

  const reload = useCallback(() => {
    setReloadTick(t => t + 1);
    if (session?.role === "admin") {
      refreshCycle();
    }
  }, [session, refreshCycle]);

  async function login(role, identity) {
    const s = { role, identity };
    saveSession(s);
    setSession(s);
    if (role === "student") {
      try {
        const lockRes = await getStudentLockIn(identity);
        if (lockRes && lockRes.complete) {
          setPage("student-prefs");
        } else {
          setPage("student-lockin");
        }
      } catch {
        setPage("student-lockin");
      }
    } else {
      setPage(defaultPage(role));
    }
  }

  function logout() {
    saveSession(null);
    setSession(null);
    setPage(null);
    setStudents([]);
    setTeachers([]);
    setRuns([]);
    setCycleStatus(null);
    setActiveRunId(null);
  }

  // Not logged in → show entry screen.
  if (!session) {
    return (
      <EntryScreen
        students={students}
        teachers={teachers}
        onLogin={login}
      />
    );
  }

  const activeRun = runs.find(r => r.id === activeRunIdState) || (runs.length > 0 ? runs[runs.length - 1] : null);

  const PageComponent = PAGE_COMPONENTS[page] || null;

  // Shared props passed to every page.
  const sharedProps = {
    session,
    students,
    teachers,
    reload,
    setPage,
    runs,
    activeRun,
    activeRunId: activeRun?.id || null,
    setActiveRunId,
    refreshRuns,
    cycleStatus,
    refreshCycle,
    studentRoll: session.role === "student" ? session.identity : null,
    onNavigate: setPage,
  };

  return (
    <div className="app-container" style={{
      display: "flex", height: "100vh",
      fontFamily: "'Inter', system-ui, sans-serif",
      fontSize: 14, background: "#f5f4f0"
    }}>
      <Sidebar session={session} page={page} setPage={setPage} onLogout={logout} />

      {/* Main content */}
      <div className="app-main" style={{ flex: 1, overflowY: "auto", padding: "28px 32px", minWidth: 0 }}>
        {catalogLoading && <LoadingState label="Loading catalog…" />}

        {!catalogLoading && catalogError && (
          <ErrorState message={catalogError} onRetry={reload} />
        )}

        {!catalogLoading && PageComponent && (
          <PageComponent {...sharedProps} />
        )}
      </div>
    </div>
  );
}
