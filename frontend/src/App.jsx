import "./App.css";
import { useCallback, useEffect, useState } from "react";


import { getStudents, getTeachers } from "./api/catalog";
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
  "student-prefs":         StudentPrefs,
  "student-facultyprefs":  StudentFacultyPrefs,
  "student-timetable":     StudentTimetable,
  "teacher-timetable": TeacherTimetable,
};

// Derive initial page from role.
function defaultPage(role) {
  if (role === "admin") return "admin-dashboard";
  if (role === "student") return "student-prefs";
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

  // Load global catalog (students + teachers) once logged in.
  // Components that only need a subset can do their own fetching.
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCatalogLoading(true);
     
    setCatalogError(null);

    Promise.all([
      getStudents().catch(() => []),
      getTeachers().catch(() => []),
    ])
      .then(([s, t]) => {
        if (cancelled) return;
        setStudents(s);
        setTeachers(t);
      })
      .catch(e => {
        if (!cancelled) setCatalogError(e.message || "Failed to load catalog.");
      })
      .finally(() => {
        if (!cancelled) setCatalogLoading(false);
      });

    return () => { cancelled = true; };
  }, [session, reloadTick]);

  const reload = useCallback(() => setReloadTick(t => t + 1), []);

  function login(role, identity) {
    const s = { role, identity };
    saveSession(s);
    setSession(s);
    setPage(defaultPage(role));
  }

  function logout() {
    saveSession(null);
    setSession(null);
    setPage(null);
    setStudents([]);
    setTeachers([]);
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

  const PageComponent = PAGE_COMPONENTS[page] || null;

  // Shared props passed to every page.
  const sharedProps = {
    session,
    students,
    teachers,
    reload,
    setPage,
  };

  return (
    <div style={{
      display: "flex", height: "100vh",
      fontFamily: "'Inter', system-ui, sans-serif",
      fontSize: 14, background: "#f5f4f0"
    }}>
      <Sidebar session={session} page={page} setPage={setPage} onLogout={logout} />

      {/* Main content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "28px 32px", minWidth: 0 }}>
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
