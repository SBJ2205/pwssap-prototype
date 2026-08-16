import { useRef, useState } from "react";
import { td } from "../constants";
import { Badge, Card, EmptyState, InfoBox, MetricsRow, PageHeader } from "../components/ui";
import { parseCSV, toCSV, downloadCSV } from "../lib/csv";

const CSV_TEMPLATE_HEADERS = ["subject_code", "label", "teacher_name", "room", "capacity", "meetings"];
const CSV_TEMPLATE_EXAMPLE = "IT301,D,Dr. Rao,CR-4,60,Mon 9:00;Wed 11:00";

// "Mon 9:00;Wed 11:00" -> [{day:"Mon",time:"9:00"}, {day:"Wed",time:"11:00"}]
function parseMeetings(str) {
  return String(str || "")
    .split(";")
    .map(s => s.trim())
    .filter(Boolean)
    .map(s => {
      const [day, time] = s.split(/\s+/);
      return { day, time };
    })
    .filter(m => m.day && m.time);
}
function meetingsToStr(meetings) {
  return (meetings || []).map(m => `${m.day} ${m.time}`).join("; ");
}

const emptyForm = { subject_code: "", label: "", teacher_id: "", room: "", capacity: 60, meetings: "" };

export default function SlotsPage({ slots, subjects, teachers, onCreate, onUpdate, onDelete, reload }) {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [importMsg, setImportMsg] = useState(null);
  const fileRef = useRef(null);

  const uniqueSubjects = [...new Set(slots.map(s => s.code))];
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  function startEdit(s) {
    setEditingId(s.id);
    setShowForm(true);
    setForm({
      subject_code: s.code,
      label: s.section,
      teacher_id: teachers.find(t => t.name === s.faculty)?.id ?? "",
      room: s.room,
      capacity: s.capacity,
      meetings: meetingsToStr(s.meetings),
    });
  }

  function resetForm() {
    setForm(emptyForm);
    setEditingId(null);
    setShowForm(false);
    setError(null);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const payload = {
        subject_code: form.subject_code,
        label: form.label,
        teacher_id: Number(form.teacher_id),
        room: form.room,
        capacity: Number(form.capacity),
        meetings: parseMeetings(form.meetings),
      };
      if (payload.meetings.length === 0) throw new Error("Add at least one meeting, e.g. \"Mon 9:00\".");
      if (editingId) await onUpdate(editingId, payload);
      else await onCreate(payload);
      resetForm();
      reload();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(id) {
    if (!confirm("Delete this section? Students assigned to it will need to be re-solved.")) return;
    try {
      await onDelete(id);
      reload();
    } catch (err) {
      alert(err.response?.data?.detail || err.message || "Delete failed.");
    }
  }

  function downloadTemplate() {
    downloadCSV("pwssap_sections_template.csv", CSV_TEMPLATE_HEADERS.join(",") + "\n" + CSV_TEMPLATE_EXAMPLE);
  }

  async function handleFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportMsg(null);
    const text = await file.text();
    const rows = parseCSV(text);
    if (rows.length === 0) {
      setImportMsg("No rows found in that file.");
      return;
    }
    let created = 0;
    const failures = [];
    for (const row of rows) {
      const teacher = teachers.find(t => t.name === row.teacher_name);
      if (!teacher) {
        failures.push(`${row.subject_code || "?"} ${row.label || ""}: unknown teacher "${row.teacher_name}"`);
        continue;
      }
      try {
        await onCreate({
          subject_code: row.subject_code,
          label: row.label,
          teacher_id: teacher.id,
          room: row.room,
          capacity: Number(row.capacity) || 0,
          meetings: parseMeetings(row.meetings),
        });
        created += 1;
      } catch (err) {
        failures.push(`${row.subject_code || "?"} ${row.label || ""}: ${err.response?.data?.detail || err.message}`);
      }
    }
    reload();
    setImportMsg(
      `Imported ${created} of ${rows.length} row${rows.length === 1 ? "" : "s"}.` +
      (failures.length ? " Skipped: " + failures.join(" | ") : "")
    );
    if (fileRef.current) fileRef.current.value = "";
  }

  function exportSectionsCSV() {
    const rows = slots.map(s => ({
      subject_code: s.code,
      label: s.section,
      teacher_name: s.faculty,
      room: s.room,
      capacity: s.capacity,
      meetings: meetingsToStr(s.meetings),
    }));
    downloadCSV("pwssap_sections.csv", toCSV(rows, CSV_TEMPLATE_HEADERS));
  }

  return (
    <div>
      <PageHeader title="Slot instances" sub="Pre-scheduled section instances for this semester" />
      <InfoBox title="What are slot instances?">
        Each row below is one <strong>section</strong> of a subject — a specific class with a fixed teacher and room, meeting at
        one or more fixed times per week (some sections meet twice a week, e.g. a lecture on Mon + Wed).
        Each subject has multiple sections (A, B, C…). The solver will pick <strong>exactly one section per subject</strong> for
        every student, based on their time preferences — and a student is scheduled into ALL of that section's weekly meetings.
      </InfoBox>
      <MetricsRow items={[
        { val: slots.length, label: "Total instances",
          tip: "Total number of class sections across all subjects (e.g. Data Structures Sec A, Sec B, Sec C = 3 instances)." },
        { val: uniqueSubjects.length, label: "Subjects",
          tip: "Number of distinct subjects offered this semester. Every student must be assigned one section of each subject." },
        { val: slots.reduce((a, s) => a + s.capacity, 0), label: "Total seats",
          tip: "Sum of all section capacities. Each section can accommodate at most this many students." },
        { val: "CP-SAT", label: "Solver engine",
          tip: "Google OR-Tools CP-SAT — a Constraint Programming / Boolean SAT hybrid solver used to find the optimal assignment." },
      ]} />

      <Card>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button onClick={() => { resetForm(); setShowForm(v => !v); }}
              style={btnStyle("var(--accent-blue)")}>
              {showForm && !editingId ? "Cancel" : "+ New section"}
            </button>
            <button onClick={downloadTemplate} style={btnStyle("var(--bg-surface-alt)", "var(--text-primary)")}>
              ⬇ CSV template
            </button>
            <label style={{ ...btnStyle("var(--bg-surface-alt)", "var(--text-primary)"), display: "inline-block" }}>
              ⬆ Bulk import CSV
              <input ref={fileRef} type="file" accept=".csv" onChange={handleFile} style={{ display: "none" }} />
            </label>
          </div>
          <button onClick={exportSectionsCSV} style={btnStyle("var(--accent-green)")}>⬇ Export sections CSV</button>
        </div>
        {importMsg && <div style={{ marginTop: 10, fontSize: 12, color: "var(--text-secondary)" }}>{importMsg}</div>}

        {showForm && (
          <form onSubmit={handleSubmit} style={{
            marginTop: 14, padding: 14, background: "var(--bg-surface-alt)", borderRadius: 8,
            display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10,
          }}>
            <Field label="Subject code">
              <input required list="subject-codes" value={form.subject_code} onChange={e => set("subject_code", e.target.value)} style={inputStyle} placeholder="IT301" />
              <datalist id="subject-codes">
                {subjects.map(s => <option key={s.code} value={s.code}>{s.name}</option>)}
              </datalist>
            </Field>
            <Field label="Section label">
              <input required value={form.label} onChange={e => set("label", e.target.value)} style={inputStyle} placeholder="A" />
            </Field>
            <Field label="Teacher">
              <select required value={form.teacher_id} onChange={e => set("teacher_id", e.target.value)} style={inputStyle}>
                <option value="">Select…</option>
                {teachers.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </Field>
            <Field label="Room">
              <input required value={form.room} onChange={e => set("room", e.target.value)} style={inputStyle} placeholder="CR-4" />
            </Field>
            <Field label="Capacity">
              <input required type="number" min={1} value={form.capacity} onChange={e => set("capacity", e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Meetings (day time; day time)">
              <input required value={form.meetings} onChange={e => set("meetings", e.target.value)} style={inputStyle} placeholder="Mon 9:00; Wed 11:00" />
            </Field>
            {error && <div style={{ gridColumn: "1 / -1", fontSize: 12, color: "var(--rating-red-fg)" }}>{error}</div>}
            <div style={{ gridColumn: "1 / -1", display: "flex", gap: 8 }}>
              <button type="submit" disabled={busy} style={btnStyle("var(--accent-blue)")}>
                {busy ? "Saving…" : editingId ? "Save changes" : "Create section"}
              </button>
              <button type="button" onClick={resetForm} style={btnStyle("transparent", "var(--text-secondary)")}>Cancel</button>
            </div>
          </form>
        )}
      </Card>

      {slots.length === 0 ? (
        <EmptyState message="No sections have been created yet." />
      ) : (
        <Card>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>{["Subject", "Code", "Section", "Faculty", "Meetings", "Room", "Capacity", ""].map(h => (
                <th key={h} style={{ textAlign: "left", padding: "6px 10px", fontSize: 11, fontWeight: 500, color: "var(--text-muted)", borderBottom: "1px solid var(--border-subtle)" }}>{h}</th>
              ))}</tr>
            </thead>
            <tbody>
              {slots.map(s => (
                <tr key={s.id}>
                  <td style={td}>{s.subject}</td>
                  <td style={td}><code style={{ fontSize: 11, background: "var(--bg-surface-alt)", padding: "1px 5px", borderRadius: 3 }}>{s.code}</code></td>
                  <td style={td}><Badge color="blue">Sec {s.section}</Badge></td>
                  <td style={td}>{s.faculty}</td>
                  <td style={td}>
                    {s.meetings.map((m, i) => (
                      <span key={i} style={{ marginRight: 6, whiteSpace: "nowrap" }}>{m.day} {m.time}{i < s.meetings.length - 1 ? "," : ""}</span>
                    ))}
                    {s.meetings.length > 1 && <span style={{ fontSize: 10, color: "var(--text-muted)" }}> ({s.meetings.length}x/week)</span>}
                  </td>
                  <td style={td}>{s.room}</td>
                  <td style={td}>{s.capacity}</td>
                  <td style={{ ...td, whiteSpace: "nowrap" }}>
                    <span onClick={() => startEdit(s)} style={{ cursor: "pointer", color: "var(--accent-blue)", fontSize: 12, marginRight: 10 }}>Edit</span>
                    <span onClick={() => handleDelete(s.id)} style={{ cursor: "pointer", color: "var(--rating-red-fg)", fontSize: 12 }}>Delete</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label style={{ display: "block", fontSize: 11, color: "var(--text-muted)" }}>
      {label}
      <div style={{ marginTop: 3 }}>{children}</div>
    </label>
  );
}

const inputStyle = {
  width: "100%", padding: "6px 8px", fontSize: 13, borderRadius: 6,
  border: "1px solid var(--border-default)", background: "var(--bg-surface)", color: "var(--text-primary)",
};

function btnStyle(bg, fg = "var(--on-accent)") {
  return {
    padding: "6px 14px", background: bg, color: fg, border: bg === "transparent" ? "1px solid var(--border-default)" : "none",
    borderRadius: 6, cursor: "pointer", fontSize: 12, fontWeight: 500,
  };
}
