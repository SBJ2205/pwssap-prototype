import { useEffect, useState } from "react";
import { getTeacherTimetable } from "../../api/runs";
import { apiErrorMessage } from "../../api/client";
import { downloadCsv } from "../../utils/csv";
import { DAYS, SLOT_NUMBERS, SLOT_LABELS, SLOT_SHORT, slotKey } from "../../constants";
import { Card, EmptyState, PageHeader } from "../../components/ui";
import PrintableRosterModal from "../../components/PrintableRosterModal";

export default function TeacherTimetable({ session, activeRunId, runs = [] }) {
  const { identity: teacherId } = session;

  const [selectedRunId, setSelectedRunId] = useState(activeRunId ?? null);
  const [timetable, setTimetable] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Roster inspection and printing modal state
  const [printModalSection, setPrintModalSection] = useState(null);
  const [rosterSearch, setRosterSearch] = useState("");
  const [rosterViewMode, setRosterViewMode] = useState("table"); // "table" | "compact"

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getTeacherTimetable(teacherId, selectedRunId)
      .then(data => {
        if (!cancelled) setTimetable(data);
      })
      .catch(e => {
        if (!cancelled) setError(apiErrorMessage(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [teacherId, selectedRunId]);

  const schedule = timetable?.schedule || [];

  const totalAssignedHours = schedule.reduce(
    (sum, sec) =>
      sum +
      (sec.meetings || []).reduce((mSum, m) => mSum + (m.duration_hours || 2), 0),
    0
  );

  // Build a slot_key -> [section_entry] map
  const grid = {};
  for (const sec of schedule) {
    for (const m of sec.meetings) {
      if (m.slot_key) {
        if (!grid[m.slot_key]) grid[m.slot_key] = [];
        grid[m.slot_key].push({ ...sec, activeMeeting: m });
      }
    }
  }

  // ── CSV Handlers ──────────────────────────────────────────────────────────
  const downloadSectionCsv = (sec) => {
    const roster =
      sec.enrolled_roster ||
      (sec.enrolled_students || []).map(r => ({ roll_number: r, name: "–", semester: "" }));
    const rows = [
      ["roll_number", "student_name", "semester", "subject_code", "section_label"],
      ...roster.map(s => [
        s.roll_number,
        s.name || "",
        s.semester || "",
        sec.subject_code,
        sec.section_label,
      ]),
    ];
    const csvContent = rows
      .map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    downloadCsv(`${sec.section_label}_roster.csv`, csvContent);
  };

  const downloadAllRostersCsv = () => {
    const rows = [
      ["section_label", "subject_code", "subject_name", "roll_number", "student_name", "semester"],
    ];
    for (const sec of schedule) {
      const roster =
        sec.enrolled_roster ||
        (sec.enrolled_students || []).map(r => ({ roll_number: r, name: "–", semester: "" }));
      for (const s of roster) {
        rows.push([
          sec.section_label,
          sec.subject_code,
          sec.subject_name || "",
          s.roll_number,
          s.name || "",
          s.semester || "",
        ]);
      }
    }
    const csvContent = rows
      .map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    downloadCsv(`${teacherId}_all_class_rosters.csv`, csvContent);
  };

  const downloadTimetableCsv = () => {
    const rows = [
      ["Day", "Start Time", "End Time", "Duration (h)", "Subject Code", "Subject Name", "Type", "Section Label", "Enrolled Students"],
    ];
    const dayOrder = { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5 };
    const allMeetings = [];
    for (const sec of schedule) {
      for (const m of sec.meetings || []) {
        if (m.slot_key) {
          allMeetings.push({ ...m, sec });
        }
      }
    }
    allMeetings.sort(
      (a, b) =>
        (dayOrder[a.day] || 99) - (dayOrder[b.day] || 99) ||
        (a.start_time || "").localeCompare(b.start_time || "")
    );
    for (const m of allMeetings) {
      rows.push([
        m.day || "",
        m.start_time || "",
        m.end_time || "",
        m.duration_hours || 2,
        m.sec.subject_code || "",
        m.sec.subject_name || "",
        m.sec.subject_type || "",
        m.sec.section_label || "",
        m.sec.enrolled_count || 0,
      ]);
    }
    const csvContent = rows
      .map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    downloadCsv(`${teacherId}_timetable.csv`, csvContent);
  };

  const handlePrintTimetable = () => {
    window.print();
  };

  if (loading) {
    return (
      <div>
        <PageHeader title="My Timetable" />
        <Card>
          <div style={{ color: "#888", fontSize: 13, padding: "24px 0", textAlign: "center" }}>
            ⏳ Loading your timetable and rosters…
          </div>
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <PageHeader title="My Timetable" />
        <div
          style={{
            background: "#FCEBEB",
            border: "1px solid #F7C1C1",
            borderRadius: 8,
            padding: "12px 16px",
            fontSize: 13,
            color: "#791F1F",
          }}
        >
          ✕ {error}
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Timetable Print Styles */}
      <style>{`
        @media print {
          .no-print, header, nav, .sidebar {
            display: none !important;
          }
          body {
            background: #fff !important;
            color: #000 !important;
          }
          .printable-timetable-area {
            display: block !important;
          }
        }
      `}</style>

      {/* Header & Controls */}
      <div
        className="no-print"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          marginBottom: 16,
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <PageHeader
          title="My Timetable & Rosters"
          sub={`${timetable?.teacher_name || teacherId} · ${schedule.length} section(s) assigned · ${totalAssignedHours} teaching hrs/week`}
        />

        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          {schedule.length > 0 && (
            <>
              <button
                type="button"
                onClick={downloadTimetableCsv}
                style={{
                  background: "#fff",
                  color: "#185FA5",
                  border: "1px solid #185FA5",
                  borderRadius: 6,
                  padding: "6px 12px",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                📥 Timetable (CSV)
              </button>

              <button
                type="button"
                onClick={handlePrintTimetable}
                style={{
                  background: "#185FA5",
                  color: "#fff",
                  border: "none",
                  borderRadius: 6,
                  padding: "6px 14px",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                🖨️ Print Timetable
              </button>
            </>
          )}

          {/* Run Scope Selector */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "#fff",
              padding: "6px 12px",
              borderRadius: 8,
              border: "1px solid #e0ddd8",
            }}
          >
            <span style={{ fontSize: 12, fontWeight: 600, color: "#555" }}>Run:</span>
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
                <option value={activeRunId}>Active Run #{activeRunId}</option>
              )}
            </select>
          </div>
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
          {/* Section summary cards */}
          <div
            className="no-print"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
              gap: 12,
              marginBottom: 20,
            }}
          >
            {schedule.map(sec => (
              <div
                key={sec.section_id}
                style={{
                  background: "#fff",
                  border: "1px solid #e2e8f0",
                  borderRadius: 10,
                  padding: "14px 16px",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: "#0f172a", marginBottom: 2 }}>
                      {sec.subject_name || sec.subject_code}
                    </div>
                    <span
                      style={{
                        background: sec.subject_type === "lab" ? "#EEEDFB" : "#E6F1FB",
                        color: sec.subject_type === "lab" ? "#5a54c0" : "#0C447C",
                        padding: "2px 8px",
                        borderRadius: 10,
                        fontSize: 10,
                        fontWeight: 700,
                        textTransform: "uppercase",
                      }}
                    >
                      {sec.subject_type === "lab" ? "Lab" : "Theory"}
                    </span>
                  </div>

                  <div style={{ fontSize: 11, color: "#64748b", marginBottom: 8 }}>
                    <code style={{ background: "#f1f5f9", padding: "1px 5px", borderRadius: 4, fontWeight: 600 }}>
                      {sec.subject_code}
                    </code>
                    {" · "}
                    <strong style={{ color: "#1e293b" }}>{sec.section_label}</strong>
                    {" · "}
                    <span style={{ color: "#166534", fontWeight: 600 }}>{sec.enrolled_count}</span>
                    /{sec.capacity} enrolled
                  </div>

                  {/* Meeting chips */}
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 12 }}>
                    {sec.meetings.map((m, i) => (
                      <span
                        key={i}
                        style={{
                          background: m.duration_hours === 1 ? "#E1F5EE" : "#E5F5EF",
                          border: m.duration_hours === 1 ? "1px solid #7AD1B5" : "1px solid #C0DD97",
                          borderRadius: 4,
                          padding: "2px 6px",
                          fontSize: 10,
                          color: "#1D9E75",
                          fontWeight: 600,
                        }}
                      >
                        {m.day} {m.start_time}–{m.end_time} ({m.duration_hours || 2}h)
                      </span>
                    ))}
                  </div>
                </div>

                {/* Section Action Buttons */}
                <div style={{ display: "flex", gap: 8, paddingTop: 10, borderTop: "1px solid #f1f5f9" }}>
                  <button
                    type="button"
                    onClick={() => downloadSectionCsv(sec)}
                    style={{
                      flex: 1,
                      background: "#f8fafc",
                      color: "#334155",
                      border: "1px solid #cbd5e1",
                      borderRadius: 6,
                      padding: "5px 8px",
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 4,
                    }}
                  >
                    📥 Roster (CSV)
                  </button>
                  <button
                    type="button"
                    onClick={() => setPrintModalSection(sec)}
                    style={{
                      flex: 1,
                      background: "#0284c7",
                      color: "#fff",
                      border: "none",
                      borderRadius: 6,
                      padding: "5px 8px",
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 4,
                    }}
                  >
                    🖨️ Print Sheet
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Weekly timetable grid */}
          <div className="printable-timetable-area" style={{ marginBottom: 24 }}>
            <Card>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                <div style={{ fontWeight: 700, fontSize: 14, color: "#0f172a" }}>
                  Weekly Teaching Schedule
                </div>
                <div className="no-print" style={{ fontSize: 12, color: "#64748b" }}>
                  {totalAssignedHours} Teaching Hours / Week
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "110px repeat(5, 1fr)", gap: 4, marginBottom: 4 }}>
                <div />
                {DAYS.map(d => (
                  <div
                    key={d}
                    style={{
                      textAlign: "center",
                      fontSize: 12,
                      fontWeight: 700,
                      color: "#334155",
                      padding: "6px 4px",
                      background: "#f1f5f9",
                      borderRadius: 6,
                    }}
                  >
                    {d}
                  </div>
                ))}
              </div>

              {SLOT_NUMBERS.map(slotNum => (
                <div
                  key={slotNum}
                  style={{ display: "grid", gridTemplateColumns: "110px repeat(5, 1fr)", gap: 4, marginBottom: 4 }}
                >
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "center",
                      paddingRight: 6,
                    }}
                  >
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#475569" }}>
                      {SLOT_SHORT[slotNum]}
                    </div>
                    <div style={{ fontSize: 9, color: "#94a3b8" }}>{SLOT_LABELS[slotNum]}</div>
                  </div>

                  {DAYS.map(day => {
                    const key = slotKey(day, slotNum);
                    const entries = grid[key] || [];
                    return (
                      <div
                        key={day}
                        style={{
                          background: entries.length > 0 ? "#E5F5EF" : "#f8fafc",
                          borderRadius: 6,
                          padding: entries.length > 0 ? "8px 10px" : "6px",
                          minHeight: 68,
                          border: entries.length > 0 ? "1.5px solid #7AD1B5" : "1px solid #e2e8f0",
                          display: "flex",
                          flexDirection: "column",
                          gap: 4,
                        }}
                      >
                        {entries.map((sec, i) => (
                          <div
                            key={i}
                            style={{
                              background: "#fff",
                              border: "1px solid #7AD1B5",
                              borderRadius: 4,
                              padding: "5px 6px",
                              boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
                            }}
                          >
                            <div style={{ fontSize: 10, fontWeight: 700, color: "#1D9E75", lineHeight: 1.3 }}>
                              {sec.subject_name || sec.subject_code} ({sec.section_label})
                            </div>
                            <div style={{ fontSize: 9, color: "#0F5132", marginTop: 2, fontWeight: 600 }}>
                              ⏰ {sec.activeMeeting?.start_time}–{sec.activeMeeting?.end_time}{" "}
                              {sec.activeMeeting?.duration_hours === 1 && "(1h)"}
                            </div>
                            <div style={{ fontSize: 9, color: "#64748b", marginTop: 2 }}>
                              👥 {sec.enrolled_count} students
                            </div>
                          </div>
                        ))}
                      </div>
                    );
                  })}
                </div>
              ))}
            </Card>
          </div>

          {/* Student Rosters by Section */}
          {schedule.some(sec => sec.enrolled_students?.length > 0) && (
            <div className="no-print" style={{ marginTop: 24 }}>
              <Card>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 16,
                    flexWrap: "wrap",
                    gap: 12,
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 15, color: "#0f172a" }}>
                      Class Rosters & Enrolled Students
                    </div>
                    <div style={{ fontSize: 12, color: "#64748b" }}>
                      Download class rosters as CSV or print full official attendance record sheets.
                    </div>
                  </div>

                  <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                    <input
                      type="text"
                      placeholder="Search student or roll #..."
                      value={rosterSearch}
                      onChange={e => setRosterSearch(e.target.value)}
                      style={{
                        fontSize: 12,
                        padding: "5px 10px",
                        borderRadius: 6,
                        border: "1px solid #cbd5e1",
                        width: 200,
                      }}
                    />

                    <div style={{ display: "flex", background: "#f1f5f9", padding: 2, borderRadius: 6 }}>
                      <button
                        type="button"
                        onClick={() => setRosterViewMode("table")}
                        style={{
                          padding: "3px 8px",
                          border: "none",
                          borderRadius: 4,
                          background: rosterViewMode === "table" ? "#fff" : "transparent",
                          color: rosterViewMode === "table" ? "#0f172a" : "#64748b",
                          fontWeight: rosterViewMode === "table" ? 700 : 500,
                          fontSize: 11,
                          cursor: "pointer",
                        }}
                      >
                        Table
                      </button>
                      <button
                        type="button"
                        onClick={() => setRosterViewMode("compact")}
                        style={{
                          padding: "3px 8px",
                          border: "none",
                          borderRadius: 4,
                          background: rosterViewMode === "compact" ? "#fff" : "transparent",
                          color: rosterViewMode === "compact" ? "#0f172a" : "#64748b",
                          fontWeight: rosterViewMode === "compact" ? 700 : 500,
                          fontSize: 11,
                          cursor: "pointer",
                        }}
                      >
                        Tags
                      </button>
                    </div>

                    <button
                      type="button"
                      onClick={downloadAllRostersCsv}
                      style={{
                        background: "#f1f5f9",
                        color: "#1e293b",
                        border: "1px solid #cbd5e1",
                        borderRadius: 6,
                        padding: "6px 12px",
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: "pointer",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      📥 Download All Rosters (CSV)
                    </button>
                  </div>
                </div>

                {/* Section roster blocks */}
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  {schedule.map(sec => {
                    const rawRoster =
                      sec.enrolled_roster ||
                      (sec.enrolled_students || []).map(r => ({ roll_number: r, name: "–", semester: "" }));

                    const filtered = rawRoster.filter(s => {
                      if (!rosterSearch.trim()) return true;
                      const q = rosterSearch.toLowerCase();
                      return (
                        (s.roll_number || "").toLowerCase().includes(q) ||
                        (s.name || "").toLowerCase().includes(q)
                      );
                    });

                    return (
                      <div
                        key={sec.section_id}
                        style={{
                          border: "1px solid #e2e8f0",
                          borderRadius: 8,
                          padding: "14px 16px",
                          background: "#fff",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            marginBottom: 10,
                            flexWrap: "wrap",
                            gap: 8,
                          }}
                        >
                          <div>
                            <span style={{ fontWeight: 700, fontSize: 13, color: "#0f172a" }}>
                              {sec.section_label}
                            </span>
                            <span style={{ color: "#64748b", fontSize: 12, marginLeft: 8 }}>
                              {sec.subject_name || sec.subject_code} ({sec.enrolled_count} students)
                            </span>
                          </div>

                          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            <button
                              type="button"
                              onClick={() => downloadSectionCsv(sec)}
                              style={{
                                background: "#f8fafc",
                                border: "1px solid #cbd5e1",
                                borderRadius: 6,
                                padding: "4px 10px",
                                fontSize: 11,
                                fontWeight: 600,
                                color: "#334155",
                                cursor: "pointer",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 4,
                              }}
                            >
                              📥 Download CSV
                            </button>
                            <button
                              type="button"
                              onClick={() => setPrintModalSection(sec)}
                              style={{
                                background: "#0284c7",
                                border: "none",
                                borderRadius: 6,
                                padding: "4px 12px",
                                fontSize: 11,
                                fontWeight: 600,
                                color: "#fff",
                                cursor: "pointer",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 4,
                              }}
                            >
                              🖨️ Print Attendance Sheet
                            </button>
                          </div>
                        </div>

                        {/* Roster display */}
                        {filtered.length === 0 ? (
                          <div style={{ fontSize: 12, color: "#94a3b8", fontStyle: "italic", padding: "8px 0" }}>
                            {rosterSearch ? "No students matching search filter." : "No students assigned to this section."}
                          </div>
                        ) : rosterViewMode === "table" ? (
                          <div style={{ maxHeight: 240, overflowY: "auto", border: "1px solid #f1f5f9", borderRadius: 6 }}>
                            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                              <thead>
                                <tr style={{ background: "#f8fafc", textAlign: "left", borderBottom: "1px solid #e2e8f0" }}>
                                  <th style={{ padding: "6px 10px", width: 40, color: "#64748b" }}>#</th>
                                  <th style={{ padding: "6px 10px", width: 140, color: "#64748b" }}>Roll Number</th>
                                  <th style={{ padding: "6px 10px", color: "#64748b" }}>Student Name</th>
                                  <th style={{ padding: "6px 10px", width: 60, textAlign: "center", color: "#64748b" }}>Sem</th>
                                </tr>
                              </thead>
                              <tbody>
                                {filtered.map((s, idx) => (
                                  <tr key={s.roll_number} style={{ borderBottom: "1px solid #f8fafc" }}>
                                    <td style={{ padding: "6px 10px", color: "#94a3b8" }}>{idx + 1}</td>
                                    <td style={{ padding: "6px 10px", fontWeight: 700, fontFamily: "monospace", color: "#1e293b" }}>
                                      {s.roll_number}
                                    </td>
                                    <td style={{ padding: "6px 10px", color: "#334155" }}>{s.name || "–"}</td>
                                    <td style={{ padding: "6px 10px", textAlign: "center", color: "#64748b" }}>{s.semester || "–"}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                            {filtered.map(s => (
                              <span
                                key={s.roll_number}
                                style={{
                                  background: "#f1f5f9",
                                  border: "1px solid #e2e8f0",
                                  borderRadius: 6,
                                  padding: "3px 8px",
                                  fontSize: 11,
                                  color: "#334155",
                                }}
                              >
                                <strong style={{ fontFamily: "monospace" }}>{s.roll_number}</strong>
                                {s.name && s.name !== "–" && ` · ${s.name}`}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Card>
            </div>
          )}
        </>
      )}

      {/* Printable Roster / Attendance Sheet Modal */}
      <PrintableRosterModal
        isOpen={Boolean(printModalSection)}
        onClose={() => setPrintModalSection(null)}
        section={printModalSection}
        teacherName={timetable?.teacher_name || teacherId}
      />
    </div>
  );
}
