// Shared constants used across pages/components.
// Time slot definitions match the backend canonical grid exactly.

// Monday–Friday only (Saturday removed).
export const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];

// Canonical slot periods in slot-number order (1–4).
// Backend keys are "{Day}-{slot_number}" e.g. "Mon-1".
export const SLOT_NUMBERS = [1, 2, 3, 4];

// Full time range labels for display (matches backend seed data).
export const SLOT_LABELS = {
  1: "9:00–11:00",
  2: "11:15–13:15",
  3: "13:45–15:45",
  4: "15:45–17:45",
};

// Short display labels for compact headers.
export const SLOT_SHORT = {
  1: "9:00",
  2: "11:15",
  3: "13:45",
  4: "15:45",
};

// Special slot rules (for visual annotation — backend is authoritative for enforcement).
// slot 1 on Monday: no theory, no lab.
// slot 4 on any day: labs only, no theory.
export function getSlotRestriction(day, slotNum) {
  if (day === "Mon" && slotNum === 1) return "restricted"; // no theory, no lab
  if (slotNum === 4) return "lab-only";                    // labs permitted, theory prohibited
  return null;
}

export function slotKey(day, slotNum) {
  return `${day}-${slotNum}`;
}

// Time-preference rating semantics (backend: 1=preferred, 2=tolerable, 3=disliked, 4=blocked).
// 0 = unrated = indifferent (treated same as preferred by solver).
export const RATING_META = {
  0: { label: "–",  bg: "#f1efe8", color: "#aaa",    title: "Indifferent", pill: "Indifferent" },
  1: { label: "★",  bg: "#EAF3DE", color: "#27500A", title: "Preferred",   pill: "Preferred"   },
  2: { label: "✓",  bg: "#E6F1FB", color: "#0C447C", title: "Tolerable",   pill: "Tolerable"   },
  3: { label: "↓",  bg: "#FAEEDA", color: "#633806", title: "Disliked",    pill: "Disliked"    },
  4: { label: "✕",  bg: "#FCEBEB", color: "#791F1F", title: "Blocked",     pill: "Blocked"     },
};

// Colour by rating value for timetable view (penalty colour-coding).
export const PENALTY_BG = {
  0: "#EAF3DE",  // preferred / indifferent
  1: "#EAF3DE",  // preferred
  2: "#E6F1FB",  // tolerable
  3: "#FAEEDA",  // disliked
  4: "#FCEBEB",  // blocked (shouldn't appear in result, but defensive)
};

// Shared table cell style for dense data tables.
export const td = { padding: "7px 10px", borderBottom: "1px solid #f0efeb", color: "#333" };

// Supported semesters split by odd/even.
export const ODD_SEMESTERS = [3, 5, 7];
export const EVEN_SEMESTERS = [4, 6, 8];
export const ALL_SEMESTERS = [...ODD_SEMESTERS, ...EVEN_SEMESTERS].sort((a, b) => a - b);

// Navigation items, grouped by role.
// "group" determines which role sees each item.
export const NAV = [
  // Admin pages
  { key: "admin-dashboard",    label: "Dashboard",           color: "#185FA5", group: "admin" },
  { key: "admin-runs",         label: "Runs & Semesters",    color: "#1D9E75", group: "admin" },
  { key: "admin-subjects",     label: "Subjects",            color: "#7F77DD", group: "admin" },
  { key: "admin-students",     label: "Students",            color: "#C2478D", group: "admin" },
  { key: "admin-teachers",     label: "Teachers",            color: "#D85A30", group: "admin" },
  { key: "admin-availability", label: "Availability",        color: "#BA7517", group: "admin" },
  { key: "admin-solver",       label: "Solver",              color: "#1D9E75", group: "admin" },
  { key: "admin-timetable",    label: "Published Timetable", color: "#185FA5", group: "admin" },
  { key: "admin-overrides",    label: "Touch-ups",           color: "#D85A30", group: "admin" },

  // Student pages
  { key: "student-prefs",         label: "Time Preferences",    color: "#7F77DD", group: "student" },
  { key: "student-facultyprefs",  label: "Faculty Preferences", color: "#C2478D", group: "student" },
  { key: "student-timetable",     label: "My Timetable",        color: "#BA7517", group: "student" },

  // Teacher pages
  { key: "teacher-timetable", label: "My Timetable", color: "#1D9E75", group: "teacher" },
];
