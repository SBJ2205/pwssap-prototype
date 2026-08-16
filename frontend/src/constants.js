// Shared constants used across pages/components.

export const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export const PERIODS = ["9:00", "11:00", "14:00", "16:00"];
export const PERIOD_LABELS = { "9:00": "9:00 AM", "11:00": "11:00 AM", "14:00": "2:00 PM", "16:00": "4:00 PM" };

export const RATING_META = {
  0: { label: "–",    bg: "var(--bg-surface-alt)", color: "var(--text-muted)",    title: "Indifferent",  pill: "Indifferent" },
  1: { label: "★",    bg: "var(--rating-green-bg)", color: "var(--rating-green-fg)", title: "Preferred",    pill: "Preferred"    },
  2: { label: "✓",    bg: "var(--rating-blue-bg)", color: "var(--rating-blue-fg)", title: "Tolerable",   pill: "Tolerable"    },
  3: { label: "↓",    bg: "var(--rating-amber-bg)", color: "var(--rating-amber-fg)", title: "Disliked",    pill: "Disliked"     },
  4: { label: "✕",    bg: "var(--rating-red-bg)", color: "var(--rating-red-fg)", title: "Blocked",     pill: "Blocked"      },
};

export const PENALTY_BG = { 0: "var(--rating-green-bg)", 1: "var(--rating-blue-bg)", 2: "var(--rating-amber-bg)", 3: "var(--rating-red-bg)" };

// Shared table cell style used by SlotsPage and DashboardPage.
export const td = { padding: "7px 10px", borderBottom: "1px solid var(--border-subtle)", color: "var(--text-primary)" };

// Sidebar navigation, grouped by which role a page belongs to.
export const NAV = [
  { key: "catalog", label: "Manage Catalog", color: "var(--accent-amber)", group: "Admin" },
  { key: "slots", label: "Slot Instances", color: "var(--accent-blue)", group: "Admin" },
  { key: "solver", label: "Run Solver", color: "var(--accent-green)", group: "Admin" },
  { key: "dashboard", label: "Dashboard", color: "var(--accent-orange)", group: "Admin" },
  { key: "prefs", label: "Submit Preferences", color: "var(--accent-purple)", group: "Student" },
  { key: "facultyprefs", label: "Faculty Preferences", color: "var(--accent-pink)", group: "Student" },
  { key: "timetable", label: "My Timetable", color: "var(--accent-amber)", group: "Student" },
];
