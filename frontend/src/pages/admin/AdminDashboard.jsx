import { useEffect, useState, useMemo } from "react";
import { getSubjects, getStudents, getTeachers } from "../../api/catalog";
import { initializeCycle, autoLockInPending } from "../../api/cycle";
import { apiErrorMessage } from "../../api/client";
import { Card, PageHeader, InfoBox, MetricsRow, Badge } from "../../components/ui";
import CycleBanner from "../../components/CycleBanner";
import StudentLockInOverrideModal from "../../components/StudentLockInOverrideModal";
import ElectiveAllocationsModal from "../../components/ElectiveAllocationsModal";

export default function AdminDashboard({
  cycleStatus,
  refreshCycle,
  setPage,
}) {
  const [subjects, setSubjects] = useState([]);
  const [students, setStudents] = useState([]);
  const [teachers, setTeachers] = useState([]);

  // Student lock-in inspection & override state
  const [showLockInBreakdown, setShowLockInBreakdown] = useState(false);
  const [lockInFilter, setLockInFilter] = useState("all");
  const [overrideModalStudent, setOverrideModalStudent] = useState(null);
  const [showAllocationsModal, setShowAllocationsModal] = useState(false);
  const [autoLocking, setAutoLocking] = useState(false);
  const [autoLockMsg, setAutoLockMsg] = useState(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getSubjects().catch(() => []),
      getStudents().catch(() => []),
      getTeachers().catch(() => []),
    ]).then(([sub, stu, tea]) => {
      if (!cancelled) {
        setSubjects(sub);
        setStudents(stu);
        setTeachers(tea);
      }
    });
    return () => { cancelled = true; };
  }, []);

  const choiceTags = cycleStatus?.tags_detail?.filter(t => t.is_choice_based) || [];
  const currentRun = cycleStatus?.current_run;
  const isPublished = currentRun?.status === "PUBLISHED" || currentRun?.status === "published";

  const lockInStudents = useMemo(() => {
    if (cycleStatus?.students_lock_in && cycleStatus.students_lock_in.length > 0) {
      return cycleStatus.students_lock_in;
    }
    return students.map(s => ({
      roll_number: s.roll_number,
      name: s.name,
      semester: s.semester,
      is_complete: false,
      locked_in: {},
      applicable_tags: [],
      missing_tags: [],
    }));
  }, [cycleStatus?.students_lock_in, students]);

  const pendingStudents = useMemo(() => {
    return lockInStudents.filter(s => !s.is_complete);
  }, [lockInStudents]);

  const completedStudents = useMemo(() => {
    return lockInStudents.filter(s => s.is_complete);
  }, [lockInStudents]);

  const filteredLockInStudents = useMemo(() => {
    if (lockInFilter === "pending") return pendingStudents;
    if (lockInFilter === "complete") return completedStudents;
    return lockInStudents;
  }, [lockInFilter, lockInStudents, pendingStudents, completedStudents]);

  const handleInitCycle = async () => {
    try {
      await initializeCycle();
      if (refreshCycle) refreshCycle();
    } catch {
      // handled
    }
  };

  const handleAutoLockIn = async () => {
    if (!window.confirm("Auto-assign the first available elective subtag to all pending students?")) return;
    setAutoLocking(true);
    setAutoLockMsg(null);
    try {
      const res = await autoLockInPending();
      setAutoLockMsg(`Auto-assigned elective choices for ${res.auto_locked_count} student(s)!`);
      if (refreshCycle) await refreshCycle();
    } catch (err) {
      setAutoLockMsg(`Failed to auto-assign choices: ${apiErrorMessage(err)}`);
    } finally {
      setAutoLocking(false);
    }
  };

  // Setup checklist items
  const steps = [
    {
      id: "students",
      title: "1. Take the Students",
      done: students.length > 0,
      desc: students.length > 0
        ? `${students.length} students enrolled across active semesters`
        : "Upload clean student roster (roll_number, name, semester).",
      actionLabel: "Student Roster →",
      pageKey: "admin-students",
    },
    {
      id: "subjects",
      title: "2. Ingest Subject Catalog, Elective Choice & Allocations",
      done: subjects.length > 0 && choiceTags.length > 0,
      desc: subjects.length > 0
        ? `${subjects.length} subjects imported across semester(s): ${cycleStatus?.active_semesters?.join(", ") || "–"}${choiceTags.length > 0 ? ` (${choiceTags.length} elective tag(s) configured)` : ""}`
        : "Upload subject CSV, configure elective choice tags, and upload elective allocations CSV.",
      actionLabel: "Subject Catalog →",
      pageKey: "admin-subjects",
    },
    {
      id: "teachers",
      title: "3. Ingest Faculty & Capabilities",
      done: teachers.length > 0,
      desc: teachers.length > 0
        ? `${teachers.length} faculty members registered in department`
        : "Upload teacher CSV mapping teacher IDs to capable subject codes.",
      actionLabel: "Teacher Roster →",
      pageKey: "admin-teachers",
    },
    {
      id: "availability",
      title: "4. Faculty Availability",
      done: teachers.length > 0,
      desc: "Specify blocked timeslots for faculty (hard constraints).",
      actionLabel: "Availability Matrix →",
      pageKey: "admin-availability",
    },
    {
      id: "lock-in",
      title: "5. Student Elective Lock-In / Override",
      done: (cycleStatus?.lock_in_total_students > 0) && (cycleStatus?.lock_in_complete_count === cycleStatus?.lock_in_total_students),
      desc: cycleStatus?.lock_in_total_students > 0
        ? (cycleStatus.lock_in_complete_count === cycleStatus.lock_in_total_students
            ? `All ${cycleStatus.lock_in_total_students} students have locked in their elective choices!`
            : `${cycleStatus.lock_in_complete_count}/${cycleStatus.lock_in_total_students} students have locked in their elective choices (${pendingStudents.length} pending).`)
        : "Inspect and override individual student elective allocations before solving.",
      actionLabel: showLockInBreakdown ? "Hide Choices ▲" : "Inspect & Override Choices ▼",
      pageKey: "admin-students",
    },
    {
      id: "solver",
      title: "6. Solver",
      done: isPublished,
      desc: isPublished
        ? "Timetable successfully solved and published for all active semesters!"
        : "Run CP-SAT solver with 3-hour subject interval splitting and teacher load balancing.",
      actionLabel: "Open Solver →",
      pageKey: "admin-solver",
    },
  ];

  const completedSteps = steps.filter(s => s.done).length;

  return (
    <div>
      <PageHeader
        title="Department Admin Dashboard"
        sub="Department-level academic timetable generation management."
      />

      <CycleBanner
        cycleStatus={cycleStatus}
        onInitializeCycle={handleInitCycle}
        onNavigate={setPage}
      />

      <InfoBox title="Department-Scoped Timetable System">
        This system manages timetable scheduling for a single department across all active semesters together.
        Data flows from uploaded catalogs through elective subtag lock-in and student/teacher preferences into the CP-SAT solver.
        3-hour subjects are accurately scheduled as one 2-hour meeting and one 1-hour remainder with interval clash checking.
      </InfoBox>

      {/* Overview Metrics */}
      <MetricsRow
        items={[
          { val: cycleStatus?.active_semesters?.length ?? 0, label: "Active Semesters", tip: "Semesters with active subjects in department catalog." },
          { val: subjects.length, label: "Total Subjects", tip: "Subjects in department catalog." },
          { val: students.length, label: "Enrolled Students", tip: "Students across all semesters." },
          { val: teachers.length, label: "Faculty Members", tip: "Teachers in department roster." },
          { val: `${completedSteps}/${steps.length}`, label: "Setup Progress", tip: "Workflow checklist steps completed." },
        ]}
      />

      {/* Workflow Checklist Card */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: "#111" }}>Timetable Generation Workflow</div>
            <div style={{ fontSize: 12, color: "#777" }}>
              Complete the steps below in sequence to configure data and prepare for solver execution.
            </div>
          </div>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#185FA5", background: "#E6F1FB", padding: "4px 10px", borderRadius: 12 }}>
            {completedSteps} of {steps.length} Steps Ready
          </span>
        </div>

        {/* Progress bar */}
        <div style={{ background: "#f1efe8", borderRadius: 4, overflow: "hidden", height: 8, marginBottom: 16 }}>
          <div
            style={{
              height: "100%",
              background: completedSteps === steps.length ? "#1D9E75" : "#185FA5",
              width: `${(completedSteps / steps.length) * 100}%`,
              transition: "width 0.3s ease",
            }}
          />
        </div>

        {/* Steps List */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {steps.map(step => (
            <div key={step.id}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "12px 14px",
                  borderRadius: 8,
                  background: step.done ? "#F7FAF4" : "#fff",
                  border: step.done ? "1px solid #C0DD97" : "1px solid #e5e3dc",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div
                    style={{
                      width: 24,
                      height: 24,
                      borderRadius: "50%",
                      background: step.done ? "#1D9E75" : "#f1efe8",
                      color: step.done ? "#fff" : "#888",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 12,
                      fontWeight: 700,
                      flexShrink: 0,
                    }}
                  >
                    {step.done ? "✓" : "○"}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13, color: step.done ? "#27500A" : "#333" }}>
                      {step.title}
                    </div>
                    <div style={{ fontSize: 12, color: "#666", marginTop: 2 }}>
                      {step.desc}
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                  {step.id === "lock-in" ? (
                    <button
                      onClick={() => setShowLockInBreakdown(prev => !prev)}
                      style={{
                        padding: "7px 14px",
                        background: showLockInBreakdown ? "#0f172a" : (step.done ? "#fff" : "#185FA5"),
                        color: showLockInBreakdown ? "#fff" : (step.done ? "#27500A" : "#fff"),
                        border: step.done && !showLockInBreakdown ? "1px solid #C0DD97" : "none",
                        borderRadius: 6,
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: "pointer",
                        whiteSpace: "nowrap",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        transition: "all 0.15s ease",
                      }}
                    >
                      <span>{showLockInBreakdown ? "Hide Choices ▲" : "Inspect & Override Choices ▼"}</span>
                      {pendingStudents.length > 0 && (
                        <span style={{ background: "#ef4444", color: "#fff", borderRadius: 10, padding: "1px 6px", fontSize: 10 }}>
                          {pendingStudents.length} pending
                        </span>
                      )}
                    </button>
                  ) : (
                    step.actionLabel && setPage && (
                      <button
                        onClick={() => setPage(step.pageKey)}
                        style={{
                          padding: "7px 14px",
                          background: step.done ? "#fff" : "#185FA5",
                          color: step.done ? "#27500A" : "#fff",
                          border: step.done ? "1px solid #C0DD97" : "none",
                          borderRadius: 6,
                          fontSize: 12,
                          fontWeight: 600,
                          cursor: "pointer",
                          whiteSpace: "nowrap",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 6,
                          transition: "all 0.15s ease",
                        }}
                      >
                        {step.actionLabel}
                      </button>
                    )
                  )}
                </div>
              </div>

              {/* Step 6 Lock-In Interactive Breakdown Drawer */}
              {step.id === "lock-in" && showLockInBreakdown && (
                <div
                  style={{
                    marginTop: 8,
                    marginBottom: 4,
                    padding: "14px 16px",
                    background: "#f8fafc",
                    borderRadius: 8,
                    border: "1px solid #cbd5e1",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: 10,
                      marginBottom: 12,
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700, fontSize: 13, color: "#0f172a" }}>
                        Student Elective Lock-In Roster ({completedStudents.length} of {lockInStudents.length} Complete)
                      </div>
                      <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
                        Inspect submissions and choose or override elective subtags directly for any student.
                      </div>
                    </div>

                    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                      <button
                        type="button"
                        onClick={() => setShowAllocationsModal(true)}
                        style={{
                          padding: "4px 10px",
                          background: "#0284c7",
                          color: "#fff",
                          border: "none",
                          borderRadius: 6,
                          fontSize: 11,
                          fontWeight: 600,
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                      >
                        📥 Bulk CSV Allocations
                      </button>

                      {pendingStudents.length > 0 && (
                        <button
                          onClick={handleAutoLockIn}
                          disabled={autoLocking}
                          style={{
                            padding: "4px 10px",
                            background: "#fff",
                            color: "#185FA5",
                            border: "1px solid #185FA5",
                            borderRadius: 6,
                            fontSize: 11,
                            fontWeight: 600,
                            cursor: autoLocking ? "not-allowed" : "pointer",
                          }}
                        >
                          {autoLocking ? "Assigning…" : `⚡ Auto-Fill All Pending (${pendingStudents.length})`}
                        </button>
                      )}

                      <div style={{ display: "flex", background: "#e2e8f0", padding: 2, borderRadius: 6 }}>
                        {[
                          { key: "all", label: `All (${lockInStudents.length})` },
                          { key: "pending", label: `Pending (${pendingStudents.length})` },
                          { key: "complete", label: `Complete (${completedStudents.length})` },
                        ].map(f => (
                          <button
                            key={f.key}
                            onClick={() => setLockInFilter(f.key)}
                            style={{
                              padding: "3px 8px",
                              border: "none",
                              borderRadius: 4,
                              background: lockInFilter === f.key ? "#fff" : "transparent",
                              color: lockInFilter === f.key ? "#0f172a" : "#64748b",
                              fontWeight: lockInFilter === f.key ? 700 : 500,
                              fontSize: 11,
                              cursor: "pointer",
                            }}
                          >
                            {f.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {autoLockMsg && (
                    <div
                      style={{
                        padding: "6px 10px",
                        background: "#f0fdf4",
                        border: "1px solid #bbf7d0",
                        borderRadius: 6,
                        fontSize: 11,
                        color: "#166534",
                        marginBottom: 10,
                      }}
                    >
                      {autoLockMsg}
                    </div>
                  )}

                  {filteredLockInStudents.length === 0 ? (
                    <div
                      style={{
                        padding: "16px 0",
                        textAlign: "center",
                        color: "#64748b",
                        fontSize: 12,
                        background: "#fff",
                        borderRadius: 6,
                        border: "1px solid #e2e8f0",
                      }}
                    >
                      {lockInFilter === "pending"
                        ? "🎉 All students have completed their elective choices!"
                        : "No students match this filter."}
                    </div>
                  ) : (
                    <div
                      style={{
                        overflowX: "auto",
                        background: "#fff",
                        borderRadius: 6,
                        border: "1px solid #e2e8f0",
                      }}
                    >
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                        <thead>
                          <tr style={{ background: "#f1f5f9", borderBottom: "1px solid #e2e8f0" }}>
                            <th style={{ textAlign: "left", padding: "6px 10px", color: "#475569" }}>Roll No</th>
                            <th style={{ textAlign: "left", padding: "6px 10px", color: "#475569" }}>Student Name</th>
                            <th style={{ textAlign: "center", padding: "6px 10px", color: "#475569" }}>Semester</th>
                            <th style={{ textAlign: "left", padding: "6px 10px", color: "#475569" }}>Status</th>
                            <th style={{ textAlign: "left", padding: "6px 10px", color: "#475569" }}>Locked-In Electives</th>
                            <th style={{ textAlign: "right", padding: "6px 10px", color: "#475569" }}>Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredLockInStudents.map(s => {
                            const hasChoices = Object.keys(s.locked_in || {}).length > 0;
                            return (
                              <tr key={s.roll_number} style={{ borderBottom: "1px solid #f1f5f9" }}>
                                <td style={{ padding: "6px 10px", fontWeight: 700 }}>
                                  <code style={{ background: "#f1efe8", padding: "2px 5px", borderRadius: 3 }}>
                                    {s.roll_number}
                                  </code>
                                </td>
                                <td style={{ padding: "6px 10px", fontWeight: 500 }}>{s.name}</td>
                                <td style={{ padding: "6px 10px", textAlign: "center" }}>Sem {s.semester}</td>
                                <td style={{ padding: "6px 10px" }}>
                                  {s.is_complete ? (
                                    <Badge color="green">✓ Complete</Badge>
                                  ) : (
                                    <Badge color="amber">
                                      ⚠ Pending {s.missing_tags?.length > 0 ? `(${s.missing_tags.join(", ")})` : ""}
                                    </Badge>
                                  )}
                                </td>
                                <td style={{ padding: "6px 10px", color: hasChoices ? "#185FA5" : "#94a3b8" }}>
                                  {hasChoices ? (
                                    Object.entries(s.locked_in)
                                      .map(([t, sub]) => `${t}: ${sub}`)
                                      .join(" · ")
                                  ) : (
                                    <span style={{ fontStyle: "italic" }}>None locked in</span>
                                  )}
                                </td>
                                <td style={{ padding: "6px 10px", textAlign: "right" }}>
                                  <button
                                    onClick={() => setOverrideModalStudent(s)}
                                    style={{
                                      padding: "3px 8px",
                                      background: s.is_complete ? "#f1f5f9" : "#185FA5",
                                      color: s.is_complete ? "#0f172a" : "#fff",
                                      border: s.is_complete ? "1px solid #cbd5e1" : "none",
                                      borderRadius: 4,
                                      fontSize: 11,
                                      fontWeight: 600,
                                      cursor: "pointer",
                                    }}
                                  >
                                    {s.is_complete ? "Edit Choices" : "Override Choice →"}
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* Student Lock-In Override Modal */}
      <StudentLockInOverrideModal
        student={overrideModalStudent}
        isOpen={Boolean(overrideModalStudent)}
        onClose={() => setOverrideModalStudent(null)}
        onSuccess={() => {
          if (refreshCycle) refreshCycle();
        }}
      />

      {/* Student Elective Allocations Batch Import Modal */}
      <ElectiveAllocationsModal
        isOpen={showAllocationsModal}
        onClose={() => setShowAllocationsModal(false)}
        cycleData={cycleStatus}
        refreshCycle={refreshCycle}
        onNavigateToTeachers={() => setPage && setPage("admin-teachers")}
      />

      {/* Student Elective Allocations Batch Import Modal */}
      <ElectiveAllocationsModal
        isOpen={showAllocationsModal}
        onClose={() => setShowAllocationsModal(false)}
        cycleData={cycleStatus}
        refreshCycle={refreshCycle}
        onNavigateToTeachers={() => setPage && setPage("admin-teachers")}
      />
    </div>
  );
}
