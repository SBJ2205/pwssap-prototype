import { useEffect, useMemo, useState } from "react";
import { getStudents } from "../api/catalog";
import { Card } from "../components/ui";
import { useTheme } from "../context/ThemeContext";

// Simple identity-only "login" for the local prototype (see backend/api/deps.py
// — there's no real auth/password on the backend). What this DOES enforce:
// an admin can browse everything, but a student who logs in as themselves is
// locked to their own preferences/timetable (see App.jsx's lockedStudentId),
// they can't page through other students' data anymore.
export default function LoginPage({ onLogin }) {
  const { theme, toggleTheme } = useTheme();
  const [mode, setMode] = useState("student"); // "student" | "admin"
  const [students, setStudents] = useState([]);
  const [loadingStudents, setLoadingStudents] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(null);
  const [adminName, setAdminName] = useState("");

  useEffect(() => {
    getStudents()
      .then(setStudents)
      .catch(() => setStudents([]))
      .finally(() => setLoadingStudents(false));
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return students;
    return students.filter(s => s.name.toLowerCase().includes(q) || s.roll.toLowerCase().includes(q));
  }, [students, search]);

  function handleContinue() {
    if (mode === "admin") {
      onLogin({ role: "admin", name: adminName.trim() || "Admin" });
    } else if (selected) {
      onLogin({ role: "student", studentId: selected.id, name: selected.name });
    }
  }

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--bg-page)", color: "var(--text-primary)", fontFamily: "system-ui, sans-serif", padding: 20,
    }}>
      <div style={{ width: "100%", maxWidth: 420 }}>
        <div style={{ textAlign: "center", marginBottom: 20 }}>
          <div style={{ fontWeight: 700, fontSize: 22, letterSpacing: "0.02em" }}>PWSSAP</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>Section Assignment System</div>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>VIT Mumbai · IT 2025–26</div>
        </div>

        <Card>
          <div style={{ display: "flex", borderRadius: 6, overflow: "hidden", border: "1px solid var(--border-subtle)", marginBottom: 16 }}>
            {["student", "admin"].map(m => (
              <div key={m}
                onClick={() => setMode(m)}
                style={{
                  flex: 1, textAlign: "center", padding: "8px 0", cursor: "pointer", fontSize: 13,
                  fontWeight: mode === m ? 600 : 400,
                  background: mode === m ? "var(--accent-blue)" : "var(--bg-surface)",
                  color: mode === m ? "var(--on-accent)" : "var(--text-secondary)",
                }}>
                {m === "admin" ? "Admin" : "Student"}
              </div>
            ))}
          </div>

          {mode === "student" ? (
            <>
              <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>Which student are you?</div>
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search by name or roll number…"
                style={{
                  width: "100%", padding: "8px 10px", fontSize: 13, borderRadius: 6, marginBottom: 10,
                  border: "1px solid var(--border-default)", background: "var(--bg-surface)", color: "var(--text-primary)",
                }}
              />
              <div style={{ maxHeight: 220, overflowY: "auto", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: 6 }}>
                {loadingStudents && <div style={{ fontSize: 12, color: "var(--text-muted)", padding: 8 }}>Loading students…</div>}
                {!loadingStudents && filtered.length === 0 && (
                  <div style={{ fontSize: 12, color: "var(--text-muted)", padding: 8 }}>No students match "{search}".</div>
                )}
                {filtered.map(s => (
                  <div key={s.id} onClick={() => setSelected(s)}
                    style={{
                      padding: "8px 10px", borderRadius: 6, cursor: "pointer", marginBottom: 4,
                      background: selected?.id === s.id ? "var(--rating-blue-bg)" : "var(--bg-surface-hover)",
                      border: selected?.id === s.id ? "1px solid var(--select-border)" : "1px solid transparent",
                    }}>
                    <div style={{ fontWeight: 500, fontSize: 13 }}>{s.name}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{s.roll}</div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <>
              <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>Admin name (optional)</div>
              <input
                value={adminName}
                onChange={e => setAdminName(e.target.value)}
                placeholder="e.g. Prof. Rasika Ransing"
                style={{
                  width: "100%", padding: "8px 10px", fontSize: 13, borderRadius: 6,
                  border: "1px solid var(--border-default)", background: "var(--bg-surface)", color: "var(--text-primary)",
                }}
              />
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
                Admins can manage the catalog, run the solver, and view every student's data.
              </div>
            </>
          )}

          <button
            onClick={handleContinue}
            disabled={mode === "student" && !selected}
            style={{
              width: "100%", marginTop: 16, padding: "9px 0", borderRadius: 6, border: "none", cursor: "pointer",
              fontSize: 13, fontWeight: 600, background: "var(--accent-blue)", color: "var(--on-accent)",
              opacity: mode === "student" && !selected ? 0.5 : 1,
            }}>
            Continue {mode === "student" && selected ? `as ${selected.name}` : mode === "admin" ? "as Admin" : ""}
          </button>
        </Card>

        <div style={{ textAlign: "center", marginTop: 14 }}>
          <span onClick={toggleTheme} style={{ fontSize: 11, color: "var(--text-muted)", cursor: "pointer" }}>
            {theme === "dark" ? "☀ Switch to light mode" : "☾ Switch to dark mode"}
          </span>
        </div>
      </div>
    </div>
  );
}
