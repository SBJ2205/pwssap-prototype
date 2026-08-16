import { useState } from "react";
import { Card, InfoBox, PageHeader } from "../components/ui";

const TABS = ["Teachers", "Subjects", "Students"];

export default function CatalogPage({
  teachers, subjects, students,
  onCreateTeacher, onDeleteTeacher,
  onCreateSubject, onDeleteSubject,
  onCreateStudent, onDeleteStudent,
  reload,
}) {
  const [tab, setTab] = useState("Teachers");

  return (
    <div>
      <PageHeader title="Manage catalog" sub="Teachers, subjects, and students that slot instances and preferences are built from" />
      <InfoBox title="Where does this feed in?">
        Sections (on the Slot Instances page) reference a teacher and a subject from here, and every
        student listed here gets a row on the Submit Preferences / Faculty Preferences / My Timetable pages.
        Deleting a teacher or subject that's still used by a section is blocked by the backend until you
        remove or reassign that section first.
      </InfoBox>

      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)}
            style={{
              padding: "6px 16px", borderRadius: 20, border: "1px solid var(--border-default)", cursor: "pointer",
              fontSize: 12, fontWeight: 500,
              background: tab === t ? "var(--accent-blue)" : "var(--bg-surface)",
              color: tab === t ? "var(--on-accent)" : "var(--text-secondary)",
            }}>
            {t}
          </button>
        ))}
      </div>

      {tab === "Teachers" && (
        <EntityManager
          columns={["Name", "Department"]}
          rows={teachers.map(t => ({ id: t.id, cells: [t.name, t.department || "—"] }))}
          fields={[{ key: "name", label: "Name", required: true }, { key: "department", label: "Department" }]}
          onCreate={async (v) => { await onCreateTeacher({ name: v.name, department: v.department || null }); reload(); }}
          onDelete={async (id) => { await onDeleteTeacher(id); reload(); }}
        />
      )}

      {tab === "Subjects" && (
        <EntityManager
          columns={["Code", "Name", "Department", "Year"]}
          rows={subjects.map(s => ({ id: s.code, cells: [s.code, s.name, s.department || "—", s.year ?? "—"] }))}
          fields={[
            { key: "code", label: "Code", required: true },
            { key: "name", label: "Name", required: true },
            { key: "department", label: "Department" },
            { key: "year", label: "Year", type: "number" },
          ]}
          onCreate={async (v) => {
            await onCreateSubject({ code: v.code, name: v.name, department: v.department || null, year: v.year ? Number(v.year) : null });
            reload();
          }}
          onDelete={async (code) => { await onDeleteSubject(code); reload(); }}
        />
      )}

      {tab === "Students" && (
        <EntityManager
          columns={["Name", "Roll", "Department", "Year"]}
          rows={students.map(s => ({ id: s.id, cells: [s.name, s.roll, s.department || "—", s.year ?? "—"] }))}
          fields={[
            { key: "name", label: "Name", required: true },
            { key: "roll", label: "Roll no.", required: true },
            { key: "department", label: "Department" },
            { key: "year", label: "Year", type: "number" },
          ]}
          onCreate={async (v) => {
            await onCreateStudent({ name: v.name, roll: v.roll, department: v.department || null, year: v.year ? Number(v.year) : null });
            reload();
          }}
          onDelete={async (id) => { await onDeleteStudent(id); reload(); }}
        />
      )}
    </div>
  );
}

function EntityManager({ columns, rows, fields, onCreate, onDelete }) {
  const empty = Object.fromEntries(fields.map(f => [f.key, ""]));
  const [form, setForm] = useState(empty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await onCreate(form);
      setForm(empty);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(id) {
    if (!confirm("Delete this entry?")) return;
    try {
      await onDelete(id);
    } catch (err) {
      alert(err.response?.data?.detail || err.message || "Delete failed — it may still be referenced elsewhere.");
    }
  }

  return (
    <Card>
      <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 14 }}>
        {fields.map(f => (
          <label key={f.key} style={{ fontSize: 11, color: "var(--text-muted)" }}>
            {f.label}
            <div style={{ marginTop: 3 }}>
              <input
                required={f.required}
                type={f.type || "text"}
                value={form[f.key]}
                onChange={e => setForm(v => ({ ...v, [f.key]: e.target.value }))}
                style={{ padding: "6px 8px", fontSize: 13, borderRadius: 6, border: "1px solid var(--border-default)", background: "var(--bg-surface)", color: "var(--text-primary)", width: 130 }}
              />
            </div>
          </label>
        ))}
        <button type="submit" disabled={busy}
          style={{ padding: "7px 16px", background: "var(--accent-blue)", color: "var(--on-accent)", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 12, fontWeight: 500 }}>
          {busy ? "Adding…" : "+ Add"}
        </button>
      </form>
      {error && <div style={{ fontSize: 12, color: "var(--rating-red-fg)", marginBottom: 10 }}>{error}</div>}

      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr>{[...columns, ""].map(h => (
            <th key={h} style={{ textAlign: "left", padding: "6px 10px", fontSize: 11, fontWeight: 500, color: "var(--text-muted)", borderBottom: "1px solid var(--border-subtle)" }}>{h}</th>
          ))}</tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id}>
              {r.cells.map((c, i) => <td key={i} style={{ padding: "7px 10px", borderBottom: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>{c}</td>)}
              <td style={{ padding: "7px 10px", borderBottom: "1px solid var(--border-subtle)" }}>
                <span onClick={() => handleDelete(r.id)} style={{ cursor: "pointer", color: "var(--rating-red-fg)", fontSize: 12 }}>Delete</span>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={columns.length + 1} style={{ padding: 10, color: "var(--text-muted)", fontSize: 12 }}>Nothing here yet.</td></tr>
          )}
        </tbody>
      </table>
    </Card>
  );
}
