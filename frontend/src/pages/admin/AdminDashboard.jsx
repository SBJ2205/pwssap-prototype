import { useEffect, useState } from "react";
import { getSubjects, getStudents, getTeachers } from "../../api/catalog";
import { Card, PageHeader, InfoBox, MetricsRow } from "../../components/ui";
import RunContextBanner from "../../components/RunContextBanner";

export default function AdminDashboard({
  runs = [],
  activeRun,
  setActiveRunId,
  setPage,
}) {
  const [subjects, setSubjects] = useState([]);
  const [students, setStudents] = useState([]);
  const [teachers, setTeachers] = useState([]);

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

  const activeChoices = (activeRun?.choice_tag_configs || []).filter(c => c.is_choice_based);
  const subjectsInRunSem = activeRun ? subjects.filter(s => s.semester === activeRun.semester) : [];
  const studentsInRunSem = activeRun ? students.filter(s => s.semester === activeRun.semester) : [];

  // Setup checklist items
  const steps = [
    {
      id: "run",
      title: "1. Select Active Generation Run",
      done: !!activeRun,
      desc: activeRun ? `Run #${activeRun.id} active (Semester ${activeRun.semester}, Status: ${activeRun.status})` : "No run selected. Create or select a run for your target semester.",
      actionLabel: "Manage Runs →",
      pageKey: "admin-runs",
    },
    {
      id: "subjects",
      title: "2. Ingest Subject Catalog",
      done: subjectsInRunSem.length > 0,
      desc: subjectsInRunSem.length > 0 ? `${subjectsInRunSem.length} subjects found for Semester ${activeRun?.semester || "active run"}` : "Upload subject CSV with code, tags, capacity, and weekly hours.",
      actionLabel: "Subject Catalog →",
      pageKey: "admin-subjects",
    },
    {
      id: "choice-tags",
      title: "3. Configure Elective Choice Tags",
      done: activeRun && (activeChoices.length > 0 || (activeRun.choice_tag_configs && activeRun.choice_tag_configs.length > 0)),
      desc: activeChoices.length > 0 ? `${activeChoices.length} choice tag(s) configured (${activeChoices.map(c => c.tag).join(", ")})` : "Configure which tags represent student choice electives (e.g. PE1, MDM).",
      actionLabel: "Configure Tags →",
      pageKey: "admin-runs",
    },
    {
      id: "students",
      title: "4. Import Student Cohort",
      done: studentsInRunSem.length > 0,
      desc: studentsInRunSem.length > 0 ? `${studentsInRunSem.length} students enrolled in Semester ${activeRun?.semester || "active run"}` : "Upload student CSV with roll numbers and choice preference numbers.",
      actionLabel: "Student Roster →",
      pageKey: "admin-students",
    },
    {
      id: "teachers",
      title: "5. Ingest Faculty & Capabilities",
      done: teachers.length > 0,
      desc: teachers.length > 0 ? `${teachers.length} faculty members registered in department` : "Upload teacher CSV mapping teacher IDs to capable subject codes.",
      actionLabel: "Teacher Roster →",
      pageKey: "admin-teachers",
    },
    {
      id: "availability",
      title: "6. Set Faculty Availability Constraints",
      done: teachers.length > 0,
      desc: "Specify blocked timeslots for faculty (hard constraints).",
      actionLabel: "Availability Matrix →",
      pageKey: "admin-availability",
    },
    {
      id: "solver",
      title: "7. Generate Sections & Solve Timetable",
      done: activeRun?.status === "PUBLISHED",
      desc: activeRun?.status === "PUBLISHED" ? "Timetable successfully solved and published!" : "Generate section instances and execute CP-SAT solver.",
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

      <RunContextBanner
        activeRun={activeRun}
        runs={runs}
        onSelectRun={setActiveRunId}
        onGoToRuns={() => setPage && setPage("admin-runs")}
      />

      <InfoBox title="Department-Scoped Timetable System">
        This system manages semester-wise timetable scheduling for a single department.
        Data flows from uploaded CSVs through choice-based tag configuration and student/teacher preferences,
        into the CP-SAT solver which generates section assignments and balances teacher loads.
      </InfoBox>

      {/* Overview Metrics */}
      <MetricsRow
        items={[
          { val: runs.length, label: "Total Runs", tip: "Total number of generation runs created." },
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
            <div
              key={step.id}
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

              {step.actionLabel && setPage && (
                <button
                  onClick={() => setPage(step.pageKey)}
                  style={{
                    padding: "6px 12px",
                    background: step.done ? "#fff" : "#185FA5",
                    color: step.done ? "#27500A" : "#fff",
                    border: step.done ? "1px solid #C0DD97" : "none",
                    borderRadius: 6,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: "pointer",
                    whiteSpace: "nowrap",
                  }}
                >
                  {step.actionLabel}
                </button>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* Quick Action Navigation Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
        {[
          {
            title: "Runs & Semesters",
            desc: "Create runs and configure choice tag mappings.",
            page: "admin-runs",
            icon: "⚙",
            color: "#1D9E75",
          },
          {
            title: "Subjects Catalog",
            desc: "Upload subject CSV, manage capacities and slots.",
            page: "admin-subjects",
            icon: "📚",
            color: "#7F77DD",
          },
          {
            title: "Student Roster",
            desc: "Upload student CSV, inspect elective & time choices.",
            page: "admin-students",
            icon: "🎓",
            color: "#C2478D",
          },
          {
            title: "Faculty & Capabilities",
            desc: "Upload teacher CSV and inspect qualified courses.",
            page: "admin-teachers",
            icon: "👨‍🏫",
            color: "#D85A30",
          },
          {
            title: "Solver & Execution",
            desc: "Generate sections and solve with CP-SAT engine.",
            page: "admin-solver",
            icon: "⚡",
            color: "#185FA5",
          },
          {
            title: "Published Timetable",
            desc: "View full department weekly schedule matrix.",
            page: "admin-timetable",
            icon: "📅",
            color: "#BA7517",
          },
        ].map(card => (
          <div
            key={card.page}
            onClick={() => setPage && setPage(card.page)}
            style={{
              background: "#fff",
              border: "1px solid #e5e3dc",
              borderRadius: 10,
              padding: "16px",
              cursor: "pointer",
              transition: "transform 0.1s, box-shadow 0.1s",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <span style={{ fontSize: 20 }}>{card.icon}</span>
              <span style={{ fontWeight: 700, fontSize: 14, color: "#222" }}>{card.title}</span>
            </div>
            <p style={{ fontSize: 12, color: "#777", margin: 0, lineHeight: 1.5 }}>
              {card.desc}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
