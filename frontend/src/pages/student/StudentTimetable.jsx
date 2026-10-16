import { useEffect, useState } from "react";
import { getStudentTimetable } from "../../api/preferences";
import { apiErrorMessage } from "../../api/client";
import { DAYS, SLOT_NUMBERS, SLOT_LABELS, SLOT_SHORT, slotKey } from "../../constants";
import { Card, EmptyState, PageHeader } from "../../components/ui";

export default function StudentTimetable({ session }) {
  const { identity: rollNumber, name: sessionName } = session;

  const [timetable, setTimetable] = useState(null); // null = not loaded yet
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    getStudentTimetable(rollNumber)
      .then(data => {
        if (!cancelled) setTimetable(data);
      })
      .catch(e => {
        if (!cancelled) setError(apiErrorMessage(e));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [rollNumber]);

  const handlePrintTimetable = () => {
    window.print();
  };

  const downloadTimetableCsv = () => {
    if (!timetable || !entries.length) return;
    const dayOrder = { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5 };
    const rows = [
      ["Day", "Start Time", "End Time", "Duration (Hrs)", "Subject Code", "Subject Name", "Type", "Section", "Teacher", "Roll Number", "Student Name"]
    ];
    const allMeetings = [];
    for (const e of entries) {
      for (const m of e.meetings) {
        if (m.day && m.start_time) {
          allMeetings.push({ ...m, entry: e });
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
        m.day,
        m.start_time,
        m.end_time,
        m.duration_hours || 2,
        m.entry.subject_code,
        m.entry.subject_name || "",
        m.entry.subject_type || "",
        m.entry.section_label || "",
        m.entry.teacher_name || m.entry.teacher_id || "",
        rollNumber,
        timetable.name || sessionName || ""
      ]);
    }
    const csvContent = rows
      .map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `${rollNumber}_timetable.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (loading) return (
    <div>
      <PageHeader title="My Timetable" />
      <Card><div style={{ color: "#888", fontSize: 13, padding: "20px 0", textAlign: "center" }}>⏳ Loading timetable…</div></Card>
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

  const entries = timetable?.timetable || [];
  const studentName = timetable?.name || sessionName || "Student";

  if (entries.length === 0) {
    return (
      <div>
        <PageHeader
          title="My Timetable"
          sub={`Signed in as ${studentName} · Roll number: ${rollNumber}`}
        />
        <EmptyState
          title="No timetable yet"
          message="Results are not published yet. Check back after the admin runs the solver."
        />
      </div>
    );
  }

  // Build a grid: { "Mon-1": [ { ...entry, activeMeeting: meeting } ] }
  const grid = {};
  for (const entry of entries) {
    for (const meeting of entry.meetings) {
      if (meeting.slot_key) {
        if (!grid[meeting.slot_key]) grid[meeting.slot_key] = [];
        grid[meeting.slot_key].push({ ...entry, activeMeeting: meeting });
      }
    }
  }

  return (
    <div>
      {/* Timetable Print & Responsive Styles */}
      <style>{`
        @media print {
          @page {
            size: landscape;
            margin: 8mm 10mm;
          }
          .no-print, .app-sidebar, header, nav, button {
            display: none !important;
          }
          body, html {
            background: #fff !important;
            color: #000 !important;
            font-size: 11pt !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
          .app-container, .app-main {
            display: block !important;
            width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: visible !important;
            height: auto !important;
          }
          .print-header-banner {
            display: block !important;
          }
          .timetable-scroll-container {
            overflow: visible !important;
            box-shadow: none !important;
            border: none !important;
          }
          .timetable-grid-table {
            min-width: 100% !important;
            width: 100% !important;
          }
          .timetable-slot-row {
            break-inside: avoid;
            page-break-inside: avoid;
          }
        }
      `}</style>

      {/* Official Print Header Banner (visible only during print/PDF generation) */}
      <div className="print-header-banner" style={{ display: "none", marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", borderBottom: "2px solid #185FA5", paddingBottom: 10 }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, color: "#185FA5", letterSpacing: "-0.02em" }}>
              VIDYALANKAR INSTITUTE OF TECHNOLOGY
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#334155" }}>
              Department of Information Technology — Student Timetable
            </div>
            <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
              Academic Year 2026–27 · Semester {timetable.semester}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: "#0f172a" }}>{studentName}</div>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#185FA5" }}>Roll No: {rollNumber}</div>
            <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 2 }}>
              Generated on {new Date().toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
            </div>
          </div>
        </div>
      </div>

      {/* Screen Header & Action Buttons */}
      <div className="no-print" style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "flex-start",
        marginBottom: 16,
        flexWrap: "wrap",
        gap: 12,
      }}>
        <PageHeader
          title="My Timetable"
          sub={`Signed in as ${studentName} · Roll No: ${rollNumber} · Semester ${timetable.semester} · AY 2026–27`}
        />

        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button
            type="button"
            onClick={downloadTimetableCsv}
            style={{
              background: "#fff",
              color: "#185FA5",
              border: "1px solid #185FA5",
              borderRadius: 8,
              padding: "8px 14px",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              transition: "background 0.15s",
            }}
          >
            📋 Export CSV
          </button>

          <button
            type="button"
            onClick={handlePrintTimetable}
            style={{
              background: "#185FA5",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              padding: "8px 16px",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              boxShadow: "0 2px 8px rgba(24, 95, 165, 0.25)",
              transition: "transform 0.1s, background 0.15s",
            }}
          >
            📥 Download Timetable (PDF)
          </button>
        </div>
      </div>

      {/* Weekly Schedule Grid Card with Horizontal Scroll */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, color: "#111" }}>Weekly Schedule Grid</div>
            <div style={{ fontSize: 12, color: "#666", marginTop: 2 }}>
              Fixed uniform schedule blocks with 2-hour meetings and 1-hour remainder intervals. Scroll horizontally to browse all days.
            </div>
          </div>
          <div className="no-print" style={{ fontSize: 11, color: "#888", display: "flex", alignItems: "center", gap: 4 }}>
            <span>↔ Scroll horizontally</span>
          </div>
        </div>

        {/* Scrollable Container */}
        <div className="timetable-scroll-container" style={{
          overflowX: "auto",
          borderRadius: 8,
          paddingBottom: 8,
          marginTop: 12,
          WebkitOverflowScrolling: "touch",
        }}>
          <div className="timetable-grid-table" style={{
            minWidth: 1080,
          }}>
            {/* Table Header: Days */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "100px repeat(5, minmax(196px, 1fr))",
              gap: 8,
              marginBottom: 8,
            }}>
              <div style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 11,
                fontWeight: 700,
                color: "#64748b",
                background: "#f8fafc",
                borderRadius: 8,
                border: "1px solid #e2e8f0",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}>
                Slot / Day
              </div>
              {DAYS.map(d => (
                <div key={d} style={{
                  textAlign: "center",
                  fontSize: 13,
                  fontWeight: 700,
                  color: "#1e293b",
                  padding: "9px 6px",
                  background: "#f1f5f9",
                  borderRadius: 8,
                  border: "1px solid #e2e8f0",
                  letterSpacing: "-0.01em",
                }}>
                  {d}
                </div>
              ))}
            </div>

            {/* Slot Rows */}
            {SLOT_NUMBERS.map(slotNum => (
              <div
                key={slotNum}
                className="timetable-slot-row"
                style={{
                  display: "grid",
                  gridTemplateColumns: "100px repeat(5, minmax(196px, 1fr))",
                  gap: 8,
                  marginBottom: 8,
                  alignItems: "stretch",
                }}
              >
                {/* Time slot column label */}
                <div style={{
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  alignItems: "center",
                  background: "#f8fafc",
                  borderRadius: 8,
                  border: "1px solid #e2e8f0",
                  padding: "10px 6px",
                  textAlign: "center",
                }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>
                    {SLOT_SHORT[slotNum]}
                  </div>
                  <div style={{ fontSize: 10, color: "#64748b", marginTop: 2, fontWeight: 500 }}>
                    {SLOT_LABELS[slotNum]}
                  </div>
                  <div style={{
                    fontSize: 9,
                    fontWeight: 600,
                    color: "#94a3b8",
                    marginTop: 6,
                    background: "#e2e8f0",
                    padding: "1px 6px",
                    borderRadius: 4,
                  }}>
                    Slot {slotNum}
                  </div>
                </div>

                {/* Day Cells */}
                {DAYS.map(day => {
                  const key = slotKey(day, slotNum);
                  const cellEntries = grid[key] || [];
                  const isMon1 = day === "Mon" && slotNum === 1;
                  const hasEntries = cellEntries.length > 0;

                  return (
                    <div
                      key={day}
                      style={{
                        minHeight: 128,
                        borderRadius: 8,
                        display: "flex",
                        flexDirection: "column",
                        gap: 6,
                      }}
                    >
                      {/* Case 1: Active Meetings inside Cell */}
                      {hasEntries && cellEntries.map((item, idx) => {
                        const isOneHour = item.activeMeeting?.duration_hours === 1;
                        const isLab = item.subject_type === "lab";

                        // Single meeting takes full cell height; dual 1h meetings share evenly
                        if (cellEntries.length === 1) {
                          return (
                            <div
                              key={idx}
                              style={{
                                flex: 1,
                                height: "100%",
                                display: "flex",
                                flexDirection: "column",
                                justifyContent: "space-between",
                                padding: "9px 12px",
                                background: isLab ? "#faf5ff" : "#f0f7ff",
                                border: isLab ? "1px solid #e9d5ff" : "1px solid #bae6fd",
                                borderLeft: isLab ? "4px solid #7c3aed" : "4px solid #0284c7",
                                borderRadius: 8,
                                boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
                              }}
                            >
                              <div>
                                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 6, marginBottom: 4 }}>
                                  <span style={{
                                    fontSize: 12,
                                    fontWeight: 700,
                                    color: isLab ? "#581c87" : "#0369a1",
                                    letterSpacing: "-0.01em",
                                  }}>
                                    {item.subject_code}
                                  </span>
                                  <span style={{
                                    fontSize: 10,
                                    fontWeight: 700,
                                    background: isLab ? "#f3e8ff" : "#e0f2fe",
                                    color: isLab ? "#6b21a8" : "#0369a1",
                                    padding: "2px 6px",
                                    borderRadius: 4,
                                  }}>
                                    {item.section_label || (isLab ? "Lab" : "Theory")}
                                  </span>
                                </div>

                                <div
                                  style={{
                                    fontSize: 11,
                                    fontWeight: 600,
                                    color: "#1e293b",
                                    lineHeight: 1.35,
                                    display: "-webkit-box",
                                    WebkitLineClamp: 2,
                                    WebkitBoxOrient: "vertical",
                                    overflow: "hidden",
                                    marginBottom: 6,
                                  }}
                                  title={item.subject_name}
                                >
                                  {item.subject_name}
                                </div>
                              </div>

                              <div>
                                <div
                                  style={{
                                    fontSize: 10,
                                    color: "#475569",
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 5,
                                    whiteSpace: "nowrap",
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                    marginBottom: 4,
                                  }}
                                  title={item.teacher_name || item.teacher_id}
                                >
                                  <span style={{ fontSize: 11 }}>👤</span>
                                  <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                                    {item.teacher_name || item.teacher_id || "Unassigned"}
                                  </span>
                                </div>

                                <div style={{
                                  fontSize: 10,
                                  fontWeight: 600,
                                  color: isOneHour ? "#b45309" : (isLab ? "#6b21a8" : "#0369a1"),
                                  background: isOneHour ? "#fef3c7" : "#ffffff",
                                  border: isOneHour ? "1px solid #fde68a" : (isLab ? "1px solid #f3e8ff" : "1px solid #e0f2fe"),
                                  borderRadius: 4,
                                  padding: "2px 6px",
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: 4,
                                }}>
                                  <span>⏰</span> {item.activeMeeting?.start_time}–{item.activeMeeting?.end_time}
                                  <span style={{ opacity: 0.8, fontWeight: 500 }}>({item.activeMeeting?.duration_hours || 2}h)</span>
                                </div>
                              </div>
                            </div>
                          );
                        }

                        // Multiple 1-hour split meetings in the same cell
                        return (
                          <div
                            key={idx}
                            style={{
                              flex: 1,
                              minHeight: 58,
                              display: "flex",
                              flexDirection: "column",
                              justifyContent: "space-between",
                              padding: "6px 9px",
                              background: isLab ? "#faf5ff" : "#f0f7ff",
                              border: isLab ? "1px solid #e9d5ff" : "1px solid #bae6fd",
                              borderLeft: isLab ? "3px solid #7c3aed" : "3px solid #0284c7",
                              borderRadius: 6,
                              boxShadow: "0 1px 2px rgba(0,0,0,0.02)",
                            }}
                          >
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 4 }}>
                              <span style={{ fontSize: 11, fontWeight: 700, color: isLab ? "#581c87" : "#0369a1" }}>
                                {item.subject_code} ({item.section_label})
                              </span>
                              <span style={{
                                fontSize: 9,
                                fontWeight: 700,
                                background: "#fef3c7",
                                color: "#b45309",
                                padding: "1px 5px",
                                borderRadius: 3,
                              }}>
                                1h
                              </span>
                            </div>

                            <div
                              style={{
                                fontSize: 10,
                                fontWeight: 600,
                                color: "#334155",
                                whiteSpace: "nowrap",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                              }}
                              title={item.subject_name}
                            >
                              {item.subject_name}
                            </div>

                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 9, color: "#64748b" }}>
                              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "58%" }} title={item.teacher_name}>
                                👤 {item.teacher_name || item.teacher_id}
                              </span>
                              <span style={{ fontWeight: 600, color: "#0284c7" }}>
                                ⏰ {item.activeMeeting?.start_time}–{item.activeMeeting?.end_time}
                              </span>
                            </div>
                          </div>
                        );
                      })}

                      {/* Case 2: Monday Slot 1 Reserved Department Block */}
                      {isMon1 && !hasEntries && (
                        <div style={{
                          height: "100%",
                          minHeight: 128,
                          background: "#f8fafc",
                          border: "1px dashed #cbd5e1",
                          borderRadius: 8,
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "center",
                          justifyContent: "center",
                          color: "#94a3b8",
                          gap: 4,
                          padding: 10,
                          textAlign: "center",
                        }}>
                          <span style={{ fontSize: 16 }}>🏛️</span>
                          <span style={{ fontSize: 11, fontWeight: 600, color: "#64748b" }}>Reserved Slot</span>
                          <span style={{ fontSize: 9, color: "#94a3b8" }}>Institute / Dept Activity</span>
                        </div>
                      )}

                      {/* Case 3: Empty Free Slot */}
                      {!isMon1 && !hasEntries && (
                        <div style={{
                          height: "100%",
                          minHeight: 128,
                          background: "#fafaf9",
                          border: "1px dashed #e2e8f0",
                          borderRadius: 8,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          color: "#cbd5e1",
                        }}>
                          <span style={{ fontSize: 11, fontWeight: 500, color: "#94a3b8" }}>— Free Slot —</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* Enrolled Courses & Faculty Summary */}
      <div style={{ marginTop: 24 }}>
        <Card>
          <div style={{ fontWeight: 700, fontSize: 14, color: "#111", marginBottom: 4 }}>
            Enrolled Courses & Faculty Summary
          </div>
          <div style={{ fontSize: 12, color: "#666", marginBottom: 16 }}>
            Official course roster for Semester {timetable.semester} with assigned faculties and class meetings.
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
            {entries.map(e => (
              <div
                key={e.section_id}
                style={{
                  background: "#fff",
                  border: "1px solid #e5e3dc",
                  borderRadius: 10,
                  padding: "14px 16px",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
                }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 6, marginBottom: 4 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, color: "#111" }}>
                    {e.subject_name || e.subject_code}
                  </div>
                  <span style={{
                    background: e.subject_type === "lab" ? "#EEEDFB" : "#E6F1FB",
                    color: e.subject_type === "lab" ? "#5a54c0" : "#0C447C",
                    padding: "2px 8px",
                    borderRadius: 12,
                    fontSize: 10,
                    fontWeight: 700,
                    flexShrink: 0,
                  }}>
                    {e.subject_type === "lab" ? "Lab" : "Theory"}
                  </span>
                </div>

                <div style={{ fontSize: 11, color: "#888", marginBottom: 8 }}>
                  <code style={{ background: "#f1efe8", padding: "1px 5px", borderRadius: 4, fontWeight: 600 }}>
                    {e.subject_code}
                  </code>
                  {" · "}
                  <span style={{ fontWeight: 600, color: "#555" }}>Section: {e.section_label}</span>
                </div>

                <div style={{ fontSize: 12, color: "#444", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
                  <span>👤</span>
                  <span style={{ fontWeight: 600 }}>{e.teacher_name || e.teacher_id || "Unassigned"}</span>
                </div>

                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {e.meetings.map((m, i) => (
                    <span
                      key={i}
                      style={{
                        background: m.duration_hours === 1 ? "#FEF3C7" : "#F0F7FF",
                        border: m.duration_hours === 1 ? "1px solid #FDE68A" : "1px solid #BAE6FD",
                        borderRadius: 4,
                        padding: "2px 7px",
                        fontSize: 10,
                        color: m.duration_hours === 1 ? "#92400E" : "#0369A1",
                        fontWeight: 600,
                      }}
                    >
                      {m.day} {m.start_time}–{m.end_time} ({m.duration_hours || 2}h)
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
