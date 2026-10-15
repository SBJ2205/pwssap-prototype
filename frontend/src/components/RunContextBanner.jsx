import { Badge } from "./ui";

export default function RunContextBanner({ activeRun, runs = [], onSelectRun, onGoToRuns }) {
  if (!activeRun && runs.length === 0) {
    return (
      <div style={{
        background: "#FFF9E6",
        border: "1px solid #FFE08A",
        borderRadius: 8,
        padding: "10px 16px",
        marginBottom: 16,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        fontSize: 13,
        color: "#7A5200",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span>⚠</span>
          <span><strong>No run created yet.</strong> Create a run for your target semester to configure choices, import students, and solve.</span>
        </div>
        {onGoToRuns && (
          <button
            onClick={onGoToRuns}
            style={{
              background: "#185FA5",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              padding: "5px 12px",
              fontSize: 12,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Create Run →
          </button>
        )}
      </div>
    );
  }

  const statusColor =
    activeRun?.status === "PUBLISHED" ? "green" :
    activeRun?.status === "SECTION_GENERATED" ? "blue" :
    activeRun?.status === "SOLVING" ? "blue" : "amber";

  const choiceCount = (activeRun?.choice_tag_configs || []).filter(c => c.is_choice_based).length;

  return (
    <div style={{
      background: "#fff",
      border: "1px solid #e5e3dc",
      borderRadius: 8,
      padding: "10px 16px",
      marginBottom: 16,
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      flexWrap: "wrap",
      gap: 12,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "#888", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Active Run:
        </span>
        {runs.length > 1 ? (
          <select
            value={activeRun?.id || ""}
            onChange={e => onSelectRun && onSelectRun(Number(e.target.value))}
            style={{
              padding: "4px 8px",
              borderRadius: 6,
              border: "1.5px solid #185FA5",
              fontSize: 13,
              fontWeight: 600,
              color: "#185FA5",
              background: "#E6F1FB",
              cursor: "pointer",
            }}
          >
            {runs.map(r => (
              <option key={r.id} value={r.id}>
                Run #{r.id} — Semester {r.semester} ({r.status})
              </option>
            ))}
          </select>
        ) : (
          <span style={{ fontWeight: 600, fontSize: 13, color: "#222" }}>
            Run #{activeRun?.id} — Semester {activeRun?.semester}
          </span>
        )}

        <Badge color={statusColor}>{activeRun?.status || "CREATED"}</Badge>

        <span style={{ fontSize: 12, color: "#666" }}>
          {choiceCount} choice tag{choiceCount !== 1 ? "s" : ""}
        </span>
      </div>

      {onGoToRuns && (
        <button
          onClick={onGoToRuns}
          style={{
            background: "transparent",
            color: "#185FA5",
            border: "1px solid #c0d9f7",
            borderRadius: 6,
            padding: "4px 10px",
            fontSize: 12,
            fontWeight: 500,
            cursor: "pointer",
          }}
        >
          Configure Runs / Tags ⚙
        </button>
      )}
    </div>
  );
}
