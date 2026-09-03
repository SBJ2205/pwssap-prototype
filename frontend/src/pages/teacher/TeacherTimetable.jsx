import { useEffect, useState } from "react";
import { getTeacherTimetable } from "../../api/runs";
import { apiErrorMessage } from "../../api/client";
import { DAYS, SLOT_NUMBERS, SLOT_LABELS, SLOT_SHORT, slotKey } from "../../constants";
import { Card, EmptyState, PageHeader } from "../../components/ui";

export default function TeacherTimetable({ session, activeRunId, runs = [] }) {
  const { identity: teacherId } = session;

  const [selectedRunId, setSelectedRunId] = useState(activeRunId ?? null);
  const [timetable, setTimetable] = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    getTeacherTimetable(teacherId, selectedRunId)
      .then(data => { if (!cancelled) setTimetable(data); })
      .catch(e   => { if (!cancelled) setError(apiErrorMessage(e)); })
      .finally(()=> { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [teacherId, selectedRunId]);

  if (loading) return (
    <div>
      <PageHeader title="My Timetable" />
      <Card><div style={{ color: "#888", fontSize: 13 }}>⏳ Loading…</div></Card>
    </div>
  );

  if (error) return (
    <div>
      <PageHeader title="My Timetable" />
      <div style={{ background: "#FCEBEB", border: "1px solid #F7C1C1", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#791F1F" }}>
        ✕ {error}
      </div>
    </div>
  );

  const schedule = timetable?.schedule || [];

  // Build a slot_key -> [section_entry] map
  const grid = {};
  for (const sec of schedule) {
    for (const m of sec.meetings) {
      if (m.slot_key) {
        if (!grid[m.slot_key]) grid[m.slot_key] = [];
        grid[m.slot_key].push(sec);
      }
    }
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <PageHeader
          title="My Timetable"
          sub={`${timetable?.teacher_name || teacherId} · ${schedule.length} section(s) assigned`}
        />

        {/* Run Scope Selector */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#fff", padding: "6px 12px", borderRadius: 8, border: "1px solid #e0ddd8" }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#555" }}>Run Scope:</span>
          <select
            value={selectedRunId ?? ""}
            onChange={e => setSelectedRunId(e.target.value ? parseInt(e.target.value, 10) : null)}
            style={{ fontSize: 12, padding: "4px 8px", borderRadius: 4, border: "1px solid #ccc" }}
          >
            <option value="">All Runs (Combined)</option>
            {runs.map(r => (
              <option key={r.id} value={r.id}>
                Run #{r.id} (Sem {r.semester})
              </option>
            ))}
            {runs.length === 0 && activeRunId != null && (
              <option value={activeRunId}>
                Active Run #{activeRunId}
              </option>
            )}
          </select>
        </div>
      </div>

      {schedule.length === 0 && (
        <EmptyState
          title="No sections assigned"
          message="No timetable has been published yet, or no sections are assigned to you."
        />
      )}

      {schedule.length > 0 && (
        <>
          {/* Section cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 10, marginBottom: 20 }}>
            {schedule.map(sec => (
              <div key={sec.section_id} style={{
                background: "#fff", border: "1px solid #e5e3dc",
                borderRadius: 10, padding: "12px 16px",
              }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: "#222", marginBottom: 2 }}>
                  {sec.subject_name || sec.subject_code}
                </div>
                <div style={{ fontSize: 11, color: "#888", marginBottom: 6 }}>
                  <code style={{ background: "#f1efe8", padding: "1px 4px", borderRadius: 3 }}>{sec.subject_code}</code>
                  {" · "}
                  <span style={{
                    background: sec.subject_type === "lab" ? "#EEEDFB" : "#E6F1FB",
                    color: sec.subject_type === "lab" ? "#5a54c0" : "#0C447C",
                    padding: "1px 6px", borderRadius: 10, fontSize: 10, fontWeight: 600,
                  }}>
                    {sec.subject_type === "lab" ? "Lab" : "Theory"}
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#555" }}>
                  <div>📋 {sec.section_label} · {sec.enrolled_count}/{sec.capacity} enrolled</div>
                  <div style={{ marginTop: 4, color: "#888" }}>
                    {sec.meetings.map((m, i) => (
                      <span key={i} style={{ marginRight: 6 }}>
                        {m.day} {m.start_time}–{m.end_time}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Weekly grid */}
          <Card>
            <div style={{ fontWeight: 600, marginBottom: 14, fontSize: 13 }}>Weekly Grid</div>
            <div style={{ display: "grid", gridTemplateColumns: "110px repeat(5, 1fr)", gap: 4, marginBottom: 4 }}>
              <div />
              {DAYS.map(d => (
                <div key={d} style={{
                  textAlign: "center", fontSize: 12, fontWeight: 600,
                  color: "#444", padding: "6px 4px", background: "#f9f8f5", borderRadius: 6,
                }}>{d}</div>
              ))}
            </div>
            {SLOT_NUMBERS.map(slotNum => (
              <div key={slotNum} style={{ display: "grid", gridTemplateColumns: "110px repeat(5, 1fr)", gap: 4, marginBottom: 4 }}>
                <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", paddingRight: 6 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "#555" }}>{SLOT_SHORT[slotNum]}</div>
                  <div style={{ fontSize: 9, color: "#aaa" }}>{SLOT_LABELS[slotNum]}</div>
                </div>
                {DAYS.map(day => {
                  const key = slotKey(day, slotNum);
                  const entries = grid[key] || [];
                  return (
                    <div key={day} style={{
                      background: entries.length > 0 ? "#E5F5EF" : "#f9f8f5",
                      borderRadius: 6, padding: entries.length > 0 ? "8px 10px" : "6px",
                      minHeight: 60, border: "0.5px solid #e5e3dc",
                    }}>
                      {entries.map((sec, i) => (
                        <div key={i}>
                          <div style={{ fontSize: 10, fontWeight: 600, color: "#1D9E75", lineHeight: 1.3 }}>
                            {sec.subject_name || sec.subject_code}
                          </div>
                          <div style={{ fontSize: 9, color: "#555", marginTop: 1 }}>{sec.section_label}</div>
                          <div style={{ fontSize: 9, color: "#888" }}>{sec.enrolled_count} students</div>
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            ))}
          </Card>

          {/* Student roster per section */}
          {schedule.some(sec => sec.enrolled_students?.length > 0) && (
            <Card>
              <div style={{ fontWeight: 600, marginBottom: 12, fontSize: 13 }}>Student Roster</div>
              {schedule.map(sec => (
                <div key={sec.section_id} style={{ marginBottom: 16, paddingBottom: 16, borderBottom: "1px solid #f1efe8" }}>
                  <div style={{ fontWeight: 500, fontSize: 12, marginBottom: 6 }}>
                    {sec.section_label} — {sec.subject_name || sec.subject_code}
                    <span style={{ fontWeight: 400, color: "#888", marginLeft: 8 }}>
                      ({sec.enrolled_count} student{sec.enrolled_count !== 1 ? "s" : ""})
                    </span>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {(sec.enrolled_students || []).map(roll => (
                      <span key={roll} style={{
                        background: "#f1efe8", border: "1px solid #e5e3dc",
                        borderRadius: 6, padding: "3px 8px", fontSize: 11,
                        fontFamily: "monospace", color: "#444",
                      }}>{roll}</span>
                    ))}
                    {sec.enrolled_students?.length === 0 && (
                      <span style={{ fontSize: 11, color: "#bbb" }}>No students assigned yet.</span>
                    )}
                  </div>
                </div>
              ))}
            </Card>
          )}
        </>
      )}
    </div>
  );
}
