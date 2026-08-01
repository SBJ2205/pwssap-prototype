// Shared constants used across pages/components.

export const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export const PERIODS = ["9:00", "11:00", "14:00", "16:00"];
export const PERIOD_LABELS = { "9:00": "9:00 AM", "11:00": "11:00 AM", "14:00": "2:00 PM", "16:00": "4:00 PM" };

export const RATING_META = {
  0: { label: "–",    bg: "#f1efe8", color: "#aaa",    title: "Indifferent",  pill: "Indifferent" },
  1: { label: "★",    bg: "#EAF3DE", color: "#27500A", title: "Preferred",    pill: "Preferred"    },
  2: { label: "✓",    bg: "#E6F1FB", color: "#0C447C", title: "Tolerable",   pill: "Tolerable"    },
  3: { label: "↓",    bg: "#FAEEDA", color: "#633806", title: "Disliked",    pill: "Disliked"     },
  4: { label: "✕",    bg: "#FCEBEB", color: "#791F1F", title: "Blocked",     pill: "Blocked"      },
};

export const PENALTY_BG = { 0: "#EAF3DE", 1: "#E6F1FB", 2: "#FAEEDA", 3: "#FCEBEB" };

// Shared table cell style used by SlotsPage and DashboardPage.
export const td = { padding: "7px 10px", borderBottom: "1px solid #f0efeb", color: "#333" };

// Sidebar navigation, grouped by which role a page belongs to.
export const NAV = [
  { key: "slots", label: "Slot Instances", color: "#185FA5", group: "Admin" },
  { key: "solver", label: "Run Solver", color: "#1D9E75", group: "Admin" },
  { key: "dashboard", label: "Dashboard", color: "#D85A30", group: "Admin" },
  { key: "prefs", label: "Submit Preferences", color: "#7F77DD", group: "Student" },
  { key: "facultyprefs", label: "Faculty Preferences", color: "#C2478D", group: "Student" },
  { key: "timetable", label: "My Timetable", color: "#BA7517", group: "Student" },
];
