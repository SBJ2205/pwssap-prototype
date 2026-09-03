import { useCallback, useEffect, useState, useMemo } from "react";
import { getRunSummary } from "../../api/runs";
import { apiErrorMessage } from "../../api/client";
import { DAYS, SLOT_NUMBERS, SLOT_LABELS, SLOT_SHORT, td } from "../../constants";
import { Card, PageHeader, Badge, MetricsRow } from "../../components/ui";
import RunContextBanner from "../../components/RunContextBanner";

export default function AdminTimetable({
  runs = [],
  activeRun,
  activeRunId,
  setActiveRunId,
  setPage,
}) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Tab view: "grid", "sections", "workload"
  const [viewTab, setViewTab] = useState("grid");

  // Filters for sections tab
  const [sectionSearch, setSectionSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");

  // Roster modal
  const [activeRosterSection, setActiveRosterSection] = useState(null);

  const loadSummary = useCallback(async () => {
    if (!activeRunId) {
      setSummary(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await getRunSummary(activeRunId);
      setSummary(data);
    } catch (err) {
      setError(apiErrorMessage(err));
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, [activeRunId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadSummary();
  }, [loadSummary]);

  const sections = useMemo(() => summary?.sections || [], [summary]);
  const weeklyGrid = useMemo(() => summary?.weekly_grid || {}, [summary]);

  // Build a slot lookup for the weekly calendar grid: { `${day}-${slot_key}`: [entries] }
  const slotGrid = useMemo(() => {
    const map = {};
    for (const d of DAYS) {
      const dayEntries = weeklyGrid[d] || [];
      for (const entry of dayEntries) {
        if (!entry.slot_key) continue;
        if (!map[entry.slot_key]) map[entry.slot_key] = [];
        map[entry.slot_key].push(entry);
      }
    }
    return map;
  }, [weeklyGrid]);

  // Compute teacher workload breakdown
  const teacherWorkload = useMemo(() => {
    const map = {};
    for (const sec of sections) {
      const tid = sec.teacher_id || "UNASSIGNED";
      const tname = sec.teacher_name || (sec.teacher_id ? `Teacher ${sec.teacher_id}` : "Unassigned");
      if (!map[tid]) {
        map[tid] = {
          teacher_id: tid,
          teacher_name: tname,
          sectionsCount: 0,
          totalSlots: 0,
          subjects: new Set(),
        };
      }
      map[tid].sectionsCount += 1;
      map[tid].totalSlots += (sec.meetings || []).length;
      map[tid].subjects.add(sec.subject_code);
    }
    return Object.values(map).sort((a, b) => b.totalSlots - a.totalSlots);
  }, [sections]);

  const filteredSections = useMemo(() => {
    return sections.filter(s => {
      if (typeFilter !== "all" && s.subject_type !== typeFilter) return false;
      if (sectionSearch.trim()) {
        const q = sectionSearch.toLowerCase();
        const code = (s.subject_code || "").toLowerCase();
        const name = (s.subject_name || "").toLowerCase();
        const label = (s.label || "").toLowerCase();
        const teacher = (s.teacher_name || s.teacher_id || "").toLowerCase();
        if (!code.includes(q) && !name.includes(q) && !label.includes(q) && !teacher.includes(q)) {
          return false;
        }
      }
      return true;
    });
  }, [sections, sectionSearch, typeFilter]);

  const totalEnrollments = sections.reduce((sum, s) => sum + (s.enrolled_count || 0), 0);
  const totalSlotsScheduled = Object.values(slotGrid).reduce((sum, arr) => sum + arr.length, 0);

  return (
    <div>
      <PageHeader
        title="Published Department Timetable"
        sub="Full semester timetable review, section roster membership, and teacher workload balance."
      />

      <RunContextBanner
        activeRun={activeRun}
        runs={runs}
        onSelectRun={setActiveRunId}
        onGoToRuns={() => setPage && setPage("admin-runs")}
      />

      {loading ? (
        <Card><div style={{ padding: "30px 0", textAlign: "center", color: "#888" }}>⏳ Loading published timetable…</div></Card>
      ) : error || !summary ? (
        <Card>
          <div style={{ textAlign: "center", padding: "30px 0" }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: "#333", marginBottom: 6 }}>
              No Published Timetable for this Run
            </div>
            <div style={{ fontSize: 13, color: "#777", marginBottom: 16 }}>
              {error || "Run the solver to optimize and auto-publish the timetable."}
            </div>
            {setPage && (
              <button
                onClick={() => setPage("admin-solver")}
                style={{
                  padding: "8px 20px",
                  background: "#185FA5",
                  color: "#fff",
                  border: "none",
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Open Solver →
              </button>
            )}
          </div>
        </Card>
      ) : (
        <>
          {/* Metrics */}
          <MetricsRow
            items={[
              { val: summary.section_count, label: "Total Sections", tip: "Count of all scheduled class sections." },
              { val: totalSlotsScheduled, label: "Scheduled Meetings", tip: "Sum of weekly meeting occurrences across all days." },
              { val: totalEnrollments, label: "Student Seats Filled", tip: "Sum of enrolled students across all sections." },
              { val: teacherWorkload.filter(t => t.teacher_id !== "UNASSIGNED").length, label: "Teaching Faculty", tip: "Faculty members assigned to at least one section." },
            ]}
          />

          {/* Navigation View Tabs */}
          <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
            {[
              { key: "grid", label: "📅 Weekly Matrix View" },
              { key: "sections", label: `📋 Section List (${sections.length})` },
              { key: "workload", label: `👨‍🏫 Teacher Workload (${teacherWorkload.length})` },
            ].map(tab => (
              <button
                key={tab.key}
                onClick={() => setViewTab(tab.key)}
                style={{
                  padding: "8px 16px",
                  borderRadius: 8,
                  border: "1px solid #d1cfc7",
                  background: viewTab === tab.key ? "#185FA5" : "#fff",
                  color: viewTab === tab.key ? "#fff" : "#444",
                  fontWeight: viewTab === tab.key ? 700 : 500,
                  fontSize: 13,
                  cursor: "pointer",
                  boxShadow: viewTab === tab.key ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* 1. WEEKLY MATRIX VIEW */}
          {viewTab === "grid" && (
            <Card>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 14 }}>
                    Semester {summary.semester} Weekly Schedule Matrix
                  </div>
                  <div style={{ fontSize: 12, color: "#777" }}>
                    Showing all section meetings scheduled by the CP-SAT engine.
                  </div>
                </div>

                <div style={{ display: "flex", gap: 10, fontSize: 11 }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ width: 10, height: 10, background: "#E6F1FB", border: "1px solid #B5D4F4", borderRadius: 2 }} /> Theory
                  </span>
                  <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ width: 10, height: 10, background: "#EEEDFB", border: "1px solid #C4C0F0", borderRadius: 2 }} /> Lab
                  </span>
                </div>
              </div>

              {/* Day headers */}
              <div style={{ display: "grid", gridTemplateColumns: "110px repeat(5, 1fr)", gap: 6, marginBottom: 6 }}>
                <div />
                {DAYS.map(d => (
                  <div
                    key={d}
                    style={{
                      textAlign: "center",
                      fontSize: 12,
                      fontWeight: 700,
                      color: "#444",
                      padding: "6px",
                      background: "#f9f8f5",
                      borderRadius: 6,
                    }}
                  >
                    {d}
                  </div>
                ))}
              </div>

              {/* Matrix Rows */}
              {SLOT_NUMBERS.map(slotNum => (
                <div
                  key={slotNum}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "110px repeat(5, 1fr)",
                    gap: 6,
                    marginBottom: 6,
                  }}
                >
                  {/* Period label */}
                  <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", paddingRight: 6 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#444" }}>
                      Slot {slotNum} ({SLOT_SHORT[slotNum]})
                    </div>
                    <div style={{ fontSize: 9, color: "#888" }}>
                      {SLOT_LABELS[slotNum]}
                    </div>
                  </div>

                  {/* Day cells */}
                  {DAYS.map(day => {
                    const sk = `${day}-${slotNum}`;
                    const entries = slotGrid[sk] || [];
                    const isMon1 = day === "Mon" && slotNum === 1;

                    return (
                      <div
                        key={day}
                        style={{
                          background: entries.length > 0 ? "#fff" : isMon1 ? "#f0efeb" : "#fbfaf8",
                          border: entries.length > 0 ? "1px solid #d1cfc7" : "1px dashed #e5e3dc",
                          borderRadius: 8,
                          padding: "6px",
                          minHeight: 74,
                          display: "flex",
                          flexDirection: "column",
                          gap: 4,
                          maxHeight: 140,
                          overflowY: "auto",
                        }}
                      >
                        {isMon1 && entries.length === 0 && (
                          <div style={{ fontSize: 9, color: "#aaa", textAlign: "center", margin: "auto" }}>
                            Reserved
                          </div>
                        )}

                        {entries.map((entry, idx) => {
                          const isLab = entry.subject_code?.toLowerCase().includes("lab") || false;
                          return (
                            <div
                              key={idx}
                              style={{
                                background: isLab ? "#EEEDFB" : "#E6F1FB",
                                border: isLab ? "1px solid #C4C0F0" : "1px solid #B5D4F4",
                                borderRadius: 6,
                                padding: "4px 6px",
                                fontSize: 10,
                              }}
                            >
                              <div style={{ fontWeight: 700, color: isLab ? "#453EA6" : "#0C447C", display: "flex", justifyContent: "space-between" }}>
                                <span>{entry.subject_code} ({entry.section_label})</span>
                                <span>{entry.enrolled_count} stus</span>
                              </div>
                              <div style={{ color: "#444", marginTop: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                👤 {entry.teacher_name || "Unassigned"}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              ))}
            </Card>
          )}

          {/* 2. SECTION LIST VIEW */}
          {viewTab === "sections" && (
            <Card>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: "#666" }}>Type Filter:</span>
                  <select
                    value={typeFilter}
                    onChange={e => setTypeFilter(e.target.value)}
                    style={{ padding: "4px 8px", borderRadius: 6, border: "1px solid #ccc", fontSize: 12 }}
                  >
                    <option value="all">All Types</option>
                    <option value="theory">Theory Only</option>
                    <option value="lab">Lab Only</option>
                  </select>
                </div>

                <input
                  type="text"
                  value={sectionSearch}
                  onChange={e => setSectionSearch(e.target.value)}
                  placeholder="Search subject, teacher, label…"
                  style={{
                    padding: "6px 12px",
                    border: "1px solid #ccc",
                    borderRadius: 6,
                    fontSize: 13,
                    width: 240,
                  }}
                />
              </div>

              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: "#f9f8f5", borderBottom: "1.5px solid #e0ddd8" }}>
                      <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Section</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Subject</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Faculty</th>
                      <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Scheduled Meetings</th>
                      <th style={{ textAlign: "center", padding: "8px 10px", color: "#555" }}>Enrolled / Cap</th>
                      <th style={{ textAlign: "right", padding: "8px 10px", color: "#555" }}>Roster</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredSections.map(sec => (
                      <tr key={sec.id} style={{ borderBottom: "1px solid #f0efeb" }}>
                        <td style={{ ...td, fontWeight: 700 }}>
                          <span style={{ background: "#f1efe8", padding: "2px 8px", borderRadius: 4 }}>
                            {sec.label}
                          </span>
                        </td>
                        <td style={td}>
                          <div style={{ fontWeight: 600 }}>{sec.subject_code}</div>
                          <div style={{ fontSize: 11, color: "#666" }}>{sec.subject_name}</div>
                          <Badge color={sec.subject_type === "lab" ? "amber" : "blue"}>
                            {sec.subject_type === "lab" ? "Lab" : "Theory"}
                          </Badge>
                        </td>
                        <td style={{ ...td, fontWeight: 500 }}>
                          {sec.teacher_name || (sec.teacher_id ? `Teacher ${sec.teacher_id}` : "—")}
                        </td>
                        <td style={td}>
                          {sec.meetings && sec.meetings.length > 0 ? (
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                              {sec.meetings.map((m, i) => (
                                <span
                                  key={i}
                                  style={{
                                    background: "#F4F8FC",
                                    border: "1px solid #B5D4F4",
                                    borderRadius: 4,
                                    padding: "2px 6px",
                                    fontSize: 11,
                                    color: "#0C447C",
                                  }}
                                >
                                  {m.day} {m.start_time}–{m.end_time}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span style={{ color: "#aaa", fontSize: 11 }}>No meeting assigned</span>
                          )}
                        </td>
                        <td style={{ ...td, textAlign: "center" }}>
                          <span style={{ fontWeight: 700, color: sec.enrolled_count >= sec.capacity ? "#791F1F" : "#27500A" }}>
                            {sec.enrolled_count}
                          </span>
                          {" / "}
                          <span style={{ color: "#777" }}>{sec.capacity}</span>
                        </td>
                        <td style={{ ...td, textAlign: "right" }}>
                          <button
                            onClick={() => setActiveRosterSection(sec)}
                            style={{
                              padding: "4px 10px",
                              background: "#f1efe8",
                              border: "1px solid #d1cfc7",
                              borderRadius: 6,
                              fontSize: 11,
                              fontWeight: 600,
                              cursor: "pointer",
                            }}
                          >
                            View ({sec.enrolled_count}) →
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {/* 3. TEACHER WORKLOAD SUMMARY */}
          {viewTab === "workload" && (
            <Card>
              <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 4 }}>
                Faculty Teaching Workload & Load Balance
              </div>
              <div style={{ fontSize: 12, color: "#777", marginBottom: 16 }}>
                Review assigned teaching loads across faculty members to ensure equitable distribution.
              </div>

              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ background: "#f9f8f5", borderBottom: "1.5px solid #e0ddd8" }}>
                    <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Teacher ID</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Faculty Name</th>
                    <th style={{ textAlign: "center", padding: "8px 10px", color: "#555" }}>Sections</th>
                    <th style={{ textAlign: "center", padding: "8px 10px", color: "#555" }}>Weekly Slot Hours</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Assigned Courses</th>
                  </tr>
                </thead>
                <tbody>
                  {teacherWorkload.map(t => (
                    <tr key={t.teacher_id} style={{ borderBottom: "1px solid #f0efeb" }}>
                      <td style={{ ...td, fontWeight: 700 }}>
                        <code style={{ background: "#f1efe8", padding: "2px 6px", borderRadius: 4 }}>
                          {t.teacher_id}
                        </code>
                      </td>
                      <td style={{ ...td, fontWeight: 600 }}>{t.teacher_name}</td>
                      <td style={{ ...td, textAlign: "center", fontWeight: 700 }}>
                        {t.sectionsCount}
                      </td>
                      <td style={{ ...td, textAlign: "center" }}>
                        <span style={{
                          background: t.totalSlots >= 8 ? "#FAEEDA" : "#EAF3DE",
                          color: t.totalSlots >= 8 ? "#633806" : "#27500A",
                          padding: "2px 8px",
                          borderRadius: 10,
                          fontWeight: 700,
                        }}>
                          {t.totalSlots * 2} hrs ({t.totalSlots} slots)
                        </span>
                      </td>
                      <td style={td}>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                          {Array.from(t.subjects).map(code => (
                            <span
                              key={code}
                              style={{
                                background: "#f1efe8",
                                borderRadius: 4,
                                padding: "1px 6px",
                                fontSize: 11,
                                fontWeight: 500,
                              }}
                            >
                              {code}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}

          {/* Roster Modal */}
          {activeRosterSection && (
            <div style={{
              position: "fixed",
              top: 0, left: 0, right: 0, bottom: 0,
              background: "rgba(0,0,0,0.5)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 999,
              padding: 20,
            }}>
              <div style={{
                background: "#fff",
                borderRadius: 12,
                maxWidth: 480,
                width: "100%",
                padding: "24px",
                maxHeight: "85vh",
                overflowY: "auto",
                boxShadow: "0 10px 30px rgba(0,0,0,0.2)",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 16 }}>
                      {activeRosterSection.subject_code} — {activeRosterSection.label}
                    </div>
                    <div style={{ fontSize: 12, color: "#777", marginTop: 2 }}>
                      {activeRosterSection.subject_name} · Faculty: {activeRosterSection.teacher_name || "Unassigned"}
                    </div>
                  </div>
                  <button
                    onClick={() => setActiveRosterSection(null)}
                    style={{ background: "transparent", border: "none", fontSize: 18, cursor: "pointer", color: "#888" }}
                  >
                    ✕
                  </button>
                </div>

                <div style={{ fontSize: 12, color: "#555", marginBottom: 12 }}>
                  Enrolled: <strong>{activeRosterSection.enrolled_count}</strong> of <strong>{activeRosterSection.capacity}</strong> capacity.
                </div>

                <div style={{ borderTop: "1px solid #eee", paddingTop: 12 }}>
                  <div style={{ fontWeight: 600, fontSize: 12, color: "#444", marginBottom: 8 }}>
                    Student Roll Numbers:
                  </div>
                  {activeRosterSection.enrolled_students && activeRosterSection.enrolled_students.length > 0 ? (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {activeRosterSection.enrolled_students.map(roll => (
                        <span
                          key={roll}
                          style={{
                            background: "#F4F8FC",
                            border: "1px solid #B5D4F4",
                            borderRadius: 4,
                            padding: "3px 8px",
                            fontSize: 12,
                            fontFamily: "monospace",
                            color: "#0C447C",
                          }}
                        >
                          {roll}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: "#888", fontStyle: "italic" }}>
                      No students enrolled in this section.
                    </div>
                  )}
                </div>

                <div style={{ marginTop: 20, textAlign: "right" }}>
                  <button
                    onClick={() => setActiveRosterSection(null)}
                    style={{
                      padding: "6px 16px",
                      background: "#185FA5",
                      color: "#fff",
                      border: "none",
                      borderRadius: 6,
                      fontSize: 13,
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
