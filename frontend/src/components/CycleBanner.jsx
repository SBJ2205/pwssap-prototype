import { Badge } from "./ui";

export default function CycleBanner({ cycleStatus, onInitializeCycle, onNavigate }) {
  if (!cycleStatus) return null;

  const {
    active_semesters = [],
    total_subjects = 0,
    subjects_per_semester = {},
    students_per_semester = {},
    lock_in_complete_count = 0,
    lock_in_total_students = 0,
    current_run,
  } = cycleStatus;

  const totalStudents = lock_in_total_students ||
    Object.values(students_per_semester || {}).reduce((a, b) => a + b, 0);
  const totalSubjects = total_subjects ||
    Object.values(subjects_per_semester || {}).reduce((a, b) => a + b, 0);

  const hasStudentData = totalStudents > 0;
  const hasSubjectData = totalSubjects > 0;
  const hasDataReady = hasStudentData && hasSubjectData;
  const runStatus = current_run?.status?.toUpperCase();

  const statusColor =
    runStatus === "PUBLISHED" ? "green" :
    runStatus === "DRAFT" ? "amber" : "gray";

  return (
    <div style={{
      background: "#ffffff",
      border: "1px solid #e2e8f0",
      borderRadius: 10,
      padding: "10px 18px",
      marginBottom: 20,
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      flexWrap: "wrap",
      gap: 12,
      boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 16 }}>🏛</span>
          <span style={{ fontWeight: 600, fontSize: 13, color: "#1e293b" }}>
            Department Cycle
          </span>
          <Badge color="blue">
            {active_semesters.length > 0
              ? `Semesters ${active_semesters.join(", ")}`
              : "No Semesters Active"}
          </Badge>
        </div>

        {lock_in_total_students > 0 && (
          <>
            <div style={{ height: 16, width: 1, background: "#cbd5e1" }} />
            <div style={{ fontSize: 12, color: "#475569" }}>
              Elective Lock-In:{" "}
              <strong style={{ color: lock_in_complete_count === lock_in_total_students ? "#15803d" : "#b45309" }}>
                {lock_in_complete_count}/{lock_in_total_students}
              </strong>
            </div>
          </>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {current_run ? (
          <Badge color={statusColor}>
            {runStatus === "PUBLISHED" ? "✓ Timetable Published" : "Run " + current_run.id + ": " + runStatus}
          </Badge>
        ) : hasDataReady ? (
          onInitializeCycle && (
            <button
              onClick={onInitializeCycle}
              style={{
                background: "#185FA5",
                color: "#ffffff",
                border: "none",
                borderRadius: 6,
                padding: "5px 12px",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Initialize Cycle Run →
            </button>
          )
        ) : !hasStudentData ? (
          <button
            onClick={() => onNavigate && onNavigate("admin-students")}
            style={{
              background: "#f1f5f9",
              color: "#334155",
              border: "1px solid #cbd5e1",
              borderRadius: 6,
              padding: "5px 12px",
              fontSize: 12,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Import Students to Start →
          </button>
        ) : (
          <button
            onClick={() => onNavigate && onNavigate("admin-subjects")}
            style={{
              background: "#f1f5f9",
              color: "#334155",
              border: "1px solid #cbd5e1",
              borderRadius: 6,
              padding: "5px 12px",
              fontSize: 12,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Import Subjects & Choices →
          </button>
        )}
      </div>
    </div>
  );
}
