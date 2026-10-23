import { useState } from "react";
import { downloadCsv } from "../utils/csv";

export default function PrintableRosterModal({
  isOpen,
  onClose,
  section,
  teacherName,
}) {
  const [search, setSearch] = useState("");
  const [includeAttendanceCols, setIncludeAttendanceCols] = useState(true);

  if (!isOpen || !section) return null;

  const roster = section.enrolled_roster || (section.enrolled_students || []).map(r => ({
    roll_number: r,
    name: "–",
    semester: "",
  }));

  const filteredRoster = roster.filter(s => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      (s.roll_number || "").toLowerCase().includes(q) ||
      (s.name || "").toLowerCase().includes(q)
    );
  });

  const handleDownloadCsv = () => {
    const rows = [
      ["roll_number", "student_name", "semester", "subject_code", "section_label"],
      ...roster.map(s => [
        s.roll_number,
        s.name || "",
        s.semester || "",
        section.subject_code,
        section.section_label,
      ]),
    ];
    const csvContent = rows
      .map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    downloadCsv(`${section.section_label}_roster.csv`, csvContent);
  };

  const handlePrint = () => {
    window.print();
  };

  const meetingsText = (section.meetings || [])
    .filter(m => m.day && m.start_time)
    .map(m => `${m.day} ${m.start_time}–${m.end_time}`)
    .join(", ");

  return (
    <>
      {/* Print Stylesheet */}
      <style>{`
        @media print {
          @page {
            size: portrait;
            margin: 10mm 12mm;
          }
          .no-print, .app-sidebar, .sidebar, header, nav, button, .printable-timetable-area {
            display: none !important;
          }
          body, html, #root, .app-container, .app-main {
            background: #fff !important;
            color: #000 !important;
            height: auto !important;
            min-height: 0 !important;
            overflow: visible !important;
            padding: 0 !important;
            margin: 0 !important;
            width: 100% !important;
            display: block !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }
          .roster-modal-overlay {
            position: static !important;
            display: block !important;
            background: transparent !important;
            backdrop-filter: none !important;
            padding: 0 !important;
            margin: 0 !important;
            width: 100% !important;
            height: auto !important;
            overflow: visible !important;
            box-shadow: none !important;
            inset: auto !important;
            z-index: auto !important;
          }
          .roster-modal-dialog {
            background: transparent !important;
            box-shadow: none !important;
            border: none !important;
            border-radius: 0 !important;
            max-width: 100% !important;
            width: 100% !important;
            max-height: none !important;
            height: auto !important;
            overflow: visible !important;
            display: block !important;
            padding: 0 !important;
            margin: 0 !important;
          }
          .roster-modal-body {
            padding: 0 !important;
            overflow: visible !important;
            height: auto !important;
            max-height: none !important;
            display: block !important;
            background: #fff !important;
          }
          #printable-roster-content {
            display: block !important;
            position: static !important;
            width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            background: #fff !important;
            color: #000 !important;
            overflow: visible !important;
          }
          table {
            border-collapse: collapse !important;
            width: 100% !important;
          }
          th, td {
            border: 1px solid #333 !important;
            padding: 6px 8px !important;
            font-size: 10pt !important;
            color: #000 !important;
          }
          tr {
            page-break-inside: avoid;
            break-inside: avoid;
          }
        }
      `}</style>

      {/* Modal Overlay */}
      <div
        className="roster-modal-overlay"
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 9999,
          background: "rgba(15, 23, 42, 0.65)",
          backdropFilter: "blur(3px)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 16,
        }}
      >
        <div
          className="roster-modal-dialog"
          style={{
            background: "#fff",
            borderRadius: 12,
            maxWidth: 900,
            width: "100%",
            maxHeight: "92vh",
            display: "flex",
            flexDirection: "column",
            boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
            overflow: "hidden",
          }}
        >
          {/* Modal Header (Screen Only) */}
          <div
            className="no-print"
            style={{
              padding: "16px 24px",
              borderBottom: "1px solid #e2e8f0",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              background: "#f8fafc",
            }}
          >
            <div>
              <div style={{ fontWeight: 700, fontSize: 16, color: "#0f172a" }}>
                Class Roster & Attendance Sheet
              </div>
              <div style={{ fontSize: 12, color: "#64748b" }}>
                {section.section_label} · {section.subject_name || section.subject_code} ({roster.length} students)
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <button
                type="button"
                onClick={handleDownloadCsv}
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
                📥 Download CSV
              </button>

              <button
                type="button"
                onClick={handlePrint}
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
                🖨️ Print Sheet
              </button>

              <button
                type="button"
                onClick={onClose}
                style={{
                  background: "none",
                  border: "none",
                  fontSize: 18,
                  color: "#94a3b8",
                  cursor: "pointer",
                  padding: "4px 8px",
                  lineHeight: 1,
                }}
              >
                ✕
              </button>
            </div>
          </div>

          {/* Modal Toolbar (Screen Only) */}
          <div
            className="no-print"
            style={{
              padding: "10px 24px",
              borderBottom: "1px solid #f1f5f9",
              background: "#fff",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 12,
            }}
          >
            <input
              type="text"
              placeholder="Search by roll number or name..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{
                fontSize: 12,
                padding: "6px 10px",
                borderRadius: 6,
                border: "1px solid #cbd5e1",
                width: 250,
              }}
            />

            <label style={{ fontSize: 12, color: "#475569", display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={includeAttendanceCols}
                onChange={e => setIncludeAttendanceCols(e.target.checked)}
              />
              Include Blank Attendance Columns for Printing
            </label>
          </div>

          {/* Printable Document Body */}
          <div className="roster-modal-body" style={{ flex: 1, overflowY: "auto", padding: "24px", background: "#fff" }}>
            <div id="printable-roster-content">
              {/* Official Academic Header */}
              <div style={{ borderBottom: "2px solid #0f172a", paddingBottom: 12, marginBottom: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
                  <div>
                    <h1 style={{ margin: "0 0 4px", fontSize: 18, fontWeight: 800, color: "#0f172a", textTransform: "uppercase", letterSpacing: 0.5 }}>
                      Department of Information Technology
                    </h1>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#185FA5" }}>
                      CLASS ENROLLED ROSTER & ATTENDANCE RECORD
                    </div>
                  </div>
                  <div style={{ textAlign: "right", fontSize: 12, color: "#475569" }}>
                    <div><strong>Academic Cycle</strong>: 2026–2027</div>
                    <div><strong>Date Printed</strong>: {new Date().toLocaleDateString()}</div>
                  </div>
                </div>

                {/* Course & Section Details Grid */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                    gap: 10,
                    marginTop: 12,
                    background: "#f8fafc",
                    padding: "10px 14px",
                    borderRadius: 6,
                    border: "1px solid #e2e8f0",
                    fontSize: 12,
                  }}
                >
                  <div>
                    <span style={{ color: "#64748b" }}>Subject: </span>
                    <strong style={{ color: "#0f172a" }}>{section.subject_name || section.subject_code}</strong>{" "}
                    <code>({section.subject_code})</code>
                  </div>
                  <div>
                    <span style={{ color: "#64748b" }}>Section: </span>
                    <strong style={{ color: "#0f172a" }}>{section.section_label}</strong>{" "}
                    <span style={{ textTransform: "capitalize" }}>({section.subject_type})</span>
                  </div>
                  <div>
                    <span style={{ color: "#64748b" }}>Faculty Instructor: </span>
                    <strong style={{ color: "#0f172a" }}>{teacherName || section.teacher_id || "–"}</strong>
                  </div>
                  <div>
                    <span style={{ color: "#64748b" }}>Class Strength: </span>
                    <strong style={{ color: "#166534" }}>{roster.length}</strong> / {section.capacity} Enrolled
                  </div>
                  {meetingsText && (
                    <div style={{ gridColumn: "1 / -1" }}>
                      <span style={{ color: "#64748b" }}>Scheduled Meetings: </span>
                      <strong style={{ color: "#0f172a" }}>{meetingsText}</strong>
                    </div>
                  )}
                </div>
              </div>

              {/* Roster Table */}
              {filteredRoster.length === 0 ? (
                <div style={{ padding: "32px 0", textAlign: "center", color: "#64748b", fontSize: 13 }}>
                  No students found matching your search.
                </div>
              ) : (
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ background: "#f1f5f9", textAlign: "left" }}>
                      <th style={{ padding: "8px 10px", width: 40, border: "1px solid #cbd5e1" }}>#</th>
                      <th style={{ padding: "8px 10px", width: 140, border: "1px solid #cbd5e1" }}>Roll Number</th>
                      <th style={{ padding: "8px 10px", border: "1px solid #cbd5e1" }}>Student Name</th>
                      <th style={{ padding: "8px 10px", width: 60, textAlign: "center", border: "1px solid #cbd5e1" }}>Sem</th>
                      {includeAttendanceCols && (
                        <>
                          <th style={{ padding: "8px 10px", width: 75, textAlign: "center", border: "1px solid #cbd5e1" }}>Date: ___</th>
                          <th style={{ padding: "8px 10px", width: 75, textAlign: "center", border: "1px solid #cbd5e1" }}>Date: ___</th>
                          <th style={{ padding: "8px 10px", width: 75, textAlign: "center", border: "1px solid #cbd5e1" }}>Date: ___</th>
                          <th style={{ padding: "8px 10px", width: 90, textAlign: "center", border: "1px solid #cbd5e1" }}>Remarks</th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRoster.map((student, idx) => (
                      <tr key={student.roll_number} style={{ background: idx % 2 === 1 ? "#fafafa" : "#fff" }}>
                        <td style={{ padding: "6px 10px", border: "1px solid #cbd5e1", textAlign: "center", color: "#64748b" }}>
                          {idx + 1}
                        </td>
                        <td style={{ padding: "6px 10px", border: "1px solid #cbd5e1", fontWeight: 700, fontFamily: "monospace", color: "#0f172a" }}>
                          {student.roll_number}
                        </td>
                        <td style={{ padding: "6px 10px", border: "1px solid #cbd5e1", fontWeight: 500, color: "#1e293b" }}>
                          {student.name || "–"}
                        </td>
                        <td style={{ padding: "6px 10px", border: "1px solid #cbd5e1", textAlign: "center", color: "#64748b" }}>
                          {student.semester || "–"}
                        </td>
                        {includeAttendanceCols && (
                          <>
                            <td style={{ padding: "6px 10px", border: "1px solid #cbd5e1" }} />
                            <td style={{ padding: "6px 10px", border: "1px solid #cbd5e1" }} />
                            <td style={{ padding: "6px 10px", border: "1px solid #cbd5e1" }} />
                            <td style={{ padding: "6px 10px", border: "1px solid #cbd5e1" }} />
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {/* Signatures Footer for Official Printing */}
              <div
                style={{
                  marginTop: 36,
                  display: "flex",
                  justifyContent: "space-between",
                  paddingTop: 24,
                  fontSize: 12,
                  color: "#334155",
                }}
              >
                <div>
                  <div style={{ borderTop: "1px solid #94a3b8", width: 220, paddingTop: 4, fontWeight: 600 }}>
                    Faculty Signature
                  </div>
                  <div style={{ fontSize: 11, color: "#64748b" }}>
                    {teacherName || section.teacher_id}
                  </div>
                </div>

                <div style={{ textAlign: "right" }}>
                  <div style={{ borderTop: "1px solid #94a3b8", width: 220, paddingTop: 4, fontWeight: 600 }}>
                    HOD / Academic Coordinator
                  </div>
                  <div style={{ fontSize: 11, color: "#64748b" }}>
                    Department Stamp & Date
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
