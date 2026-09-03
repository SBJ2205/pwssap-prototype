import { useState } from "react";
import { getStudents, getTeachers } from "../api/catalog";
import { setRole as setApiRole } from "../api/client";
import { apiErrorMessage } from "../api/client";

const INPUT_STYLE = {
  width: "100%",
  padding: "12px 16px",
  border: "1.5px solid #d1cfc7",
  borderRadius: 10,
  fontSize: 15,
  fontFamily: "inherit",
  outline: "none",
  background: "#fff",
  color: "#222",
  boxSizing: "border-box",
  transition: "border-color 0.15s",
};

export default function EntryScreen({ onLogin }) {
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    const input = value.trim();
    if (!input) return;

    setLoading(true);
    setError(null);

    try {
      // Admin special keyword.
      if (input.toLowerCase() === "admin") {
        setApiRole("admin");
        onLogin("admin", "admin");
        return;
      }

      // Try to match a student roll number.
      setApiRole("student");
      let students;
      try {
        students = await getStudents();
      } catch {
        students = [];
      }
      const student = students.find(
        s => s.roll_number.toLowerCase() === input.toLowerCase()
      );
      if (student) {
        onLogin("student", student.roll_number);
        return;
      }

      // Try to match a teacher ID.
      setApiRole("admin"); // teachers endpoint doesn't need admin but we need X-Role set
      let teachers;
      try {
        teachers = await getTeachers();
      } catch {
        teachers = [];
      }
      const teacher = teachers.find(
        t => t.teacher_id.toLowerCase() === input.toLowerCase()
      );
      if (teacher) {
        setApiRole("teacher");
        onLogin("teacher", teacher.teacher_id);
        return;
      }

      setError(
        `"${input}" was not recognised. Enter "admin", a student roll number (e.g. 23101C0006), or a teacher ID (e.g. T001).`
      );
    } catch (err) {
      setError(apiErrorMessage(err) || "Could not connect to the server.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "linear-gradient(135deg, #f5f4f0 0%, #eceae2 100%)",
      fontFamily: "'Inter', system-ui, sans-serif",
      padding: 24,
    }}>
      <div style={{
        width: "100%",
        maxWidth: 420,
        background: "#fff",
        borderRadius: 16,
        boxShadow: "0 4px 32px rgba(0,0,0,0.10)",
        border: "1px solid #e5e3dc",
        overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{
          padding: "28px 32px 20px",
          borderBottom: "1px solid #f0efeb",
          background: "#f9f8f5",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 8,
              background: "#185FA5", display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: 18,
            }}>📅</div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 17, color: "#111", letterSpacing: "-0.02em" }}>
                PWSSAP
              </div>
              <div style={{ fontSize: 11, color: "#888" }}>
                Department Timetable System
              </div>
            </div>
          </div>
          <p style={{ fontSize: 12, color: "#999", margin: "8px 0 0", lineHeight: 1.5 }}>
            IT Department · VIT Mumbai · AY 2025–26
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ padding: "28px 32px" }}>
          <label style={{ display: "block", fontWeight: 600, fontSize: 14, color: "#333", marginBottom: 8 }}>
            Who are you?
          </label>
          <input
            autoFocus
            type="text"
            value={value}
            onChange={e => { setValue(e.target.value); setError(null); }}
            placeholder="admin · roll number · teacher ID"
            style={INPUT_STYLE}
            disabled={loading}
          />
          <div style={{ fontSize: 11, color: "#aaa", marginTop: 7, lineHeight: 1.6 }}>
            Enter <code style={{ background: "#f1efe8", padding: "1px 5px", borderRadius: 3 }}>admin</code> for the admin panel,
            your roll number (e.g.{" "}
            <code style={{ background: "#f1efe8", padding: "1px 5px", borderRadius: 3 }}>23101C0006</code>) for the student view,
            or a teacher ID (e.g.{" "}
            <code style={{ background: "#f1efe8", padding: "1px 5px", borderRadius: 3 }}>T001</code>) for the teacher view.
          </div>

          {error && (
            <div style={{
              marginTop: 14,
              background: "#FCEBEB",
              border: "1px solid #F7C1C1",
              borderRadius: 8,
              padding: "10px 14px",
              fontSize: 12,
              color: "#791F1F",
              lineHeight: 1.5,
            }}>
              ✕ {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !value.trim()}
            style={{
              marginTop: 20,
              width: "100%",
              padding: "12px 0",
              background: loading || !value.trim() ? "#c5c3bb" : "#185FA5",
              color: "#fff",
              border: "none",
              borderRadius: 10,
              fontSize: 14,
              fontWeight: 600,
              cursor: loading || !value.trim() ? "not-allowed" : "pointer",
              fontFamily: "inherit",
              transition: "background 0.15s",
            }}
          >
            {loading ? "Checking…" : "Continue →"}
          </button>
        </form>

        {/* Role hints */}
        <div style={{
          padding: "0 32px 24px",
          display: "flex",
          gap: 8,
        }}>
          {[
            { label: "Admin",   hint: "admin",        color: "#185FA5", bg: "#E6F1FB" },
            { label: "Student", hint: "roll number",  color: "#7F77DD", bg: "#EEEDFB" },
            { label: "Teacher", hint: "teacher ID",   color: "#1D9E75", bg: "#E5F5EF" },
          ].map(({ label, hint, color, bg }) => (
            <div key={label} style={{
              flex: 1, textAlign: "center",
              background: bg, borderRadius: 8,
              padding: "8px 6px",
              border: `1px solid ${color}22`,
            }}>
              <div style={{ fontWeight: 600, fontSize: 11, color }}>{label}</div>
              <div style={{ fontSize: 10, color: "#888", marginTop: 2 }}>{hint}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
