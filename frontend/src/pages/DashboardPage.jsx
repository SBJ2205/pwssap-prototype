import { td } from "../constants";
import { Badge, Card, EmptyState, InfoBox, MetricsRow, PageHeader, Tooltip } from "../components/ui";

export default function DashboardPage({ results }) {
  if (!results || results.status !== "OPTIMAL") {
    return (
      <div>
        <PageHeader title="Dashboard" sub="Run the solver first to see results" />
        <EmptyState message='No results yet — go to "Run Solver" and click Run.' />
      </div>
    );
  }
  const total = results.total_penalty;
  const avg = (total / results.assignments.length).toFixed(1);
  const worst = Math.max(...results.assignments.map(a => a.penalty));
  const fcfs = results.baselines?.fcfs;
  const random = results.baselines?.random;
  const facultyPenaltyTotal = results.assignments.reduce(
    (sum, a) => sum + a.assignments.reduce((s2, x) => s2 + (x.faculty_penalty || 0), 0), 0);
  const baselines = [
    { label: "PWSSAP (ours)", val: total, color: "#1D9E75" },
    { label: "FCFS baseline", val: fcfs ? fcfs.total_penalty : 0, color: "#185FA5" },
    { label: "Random baseline", val: random ? random.total_penalty : 0, color: "#D85A30" },
  ];
  const maxB = Math.max(...baselines.map(b => b.val), 1);
  return (
    <div>
      <PageHeader title="Dashboard" sub="Assignment results and baseline comparison" />
      <InfoBox title="Reading the results">
        <strong>Penalty</strong> measures how far a student's assigned time slots deviate from their preferences.
        A penalty of <strong>0</strong> means every class landed in a slot the student marked Preferred.
        The lower the total, the better the overall outcome. Green = great, amber = acceptable, orange = suboptimal.
      </InfoBox>
      <MetricsRow items={[
        { val: total,   label: "Total penalty",
          tip: "Sum of all individual student penalties after assignment.\nPreferred slot = 0 pts, Tolerable = +1 pt, Disliked = +3 pts.\nLower is better — 0 would mean every student got their preferred slots." },
        { val: avg,     label: "Avg per student",
          tip: "Total penalty divided by the number of students.\nGives you a sense of how the typical student fared." },
        { val: worst,   label: "Worst-case penalty",
          tip: "The highest individual penalty among all students.\nThis is bounded by the Fairness Index you set in the solver." },
        { val: "100%",  label: "Hard constraints",
          tip: "All hard rules (capacity limits, no schedule clashes, one section per subject) are always satisfied 100%.\nThe solver never violates these — it would rather report INFEASIBLE than break them." },
        { val: facultyPenaltyTotal, label: "Faculty mismatch penalty",
          tip: "The portion of total penalty coming from the secondary faculty-preference term, rather than time-slot preference.\nThis is always weighted lower priority than time-slot fit." },
      ]} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <Card>
          <div style={{ fontWeight: 500, marginBottom: 4 }}>Penalty vs baselines{" "}
            <Tooltip text={"Comparison against two naive approaches:\n\n• FCFS (First Come First Served): assigns sections in the order students registered — no preference awareness.\n\n• Random: assigns sections randomly — purely by chance.\n\nLower bar = fewer unhappy slots."}>
              <span style={{ fontSize: 11, color: "#888", cursor: "help", borderBottom: "1px dashed #bbb" }}>what are baselines?</span>
            </Tooltip>
          </div>
          <div style={{ fontSize: 12, color: "#888", marginBottom: 12 }}>Lower bar = better outcome</div>
          {baselines.map(b => (
            <div key={b.label} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <div style={{ width: 110, fontSize: 12, color: "#555" }}>{b.label}</div>
              <div style={{ flex: 1, background: "#f1efe8", borderRadius: 3, overflow: "hidden", height: 22 }}>
                <div style={{ width: (b.val / maxB * 100) + "%", height: "100%", background: b.color, display: "flex", alignItems: "center", paddingLeft: 8, fontSize: 12, color: "#fff", fontWeight: 500 }}>
                  {b.val}
                </div>
              </div>
            </div>
          ))}
        </Card>
        <Card>
          <div style={{ fontWeight: 500, marginBottom: 4 }}>Per-student results</div>
          <div style={{ fontSize: 12, color: "#888", marginBottom: 10 }}>
            Each student's penalty: <Badge color="green">0–3 great</Badge>{" "}
            <Badge color="blue">4–6 ok</Badge>{" "}
            <Badge color="amber">7+ high</Badge>
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead><tr>{["Student", "Roll", "Penalty", "Faculty Pen.", "Status"].map(h => <th key={h} style={{ textAlign: "left", padding: "4px 8px", fontSize: 11, color: "#888", borderBottom: "1px solid #eee" }}>{h}</th>)}</tr></thead>
            <tbody>
              {results.assignments.map(a => {
                const facPen = a.assignments.reduce((s, x) => s + (x.faculty_penalty || 0), 0);
                return (
                <tr key={a.student_id}>
                  <td style={td}>{a.name}</td>
                  <td style={{ ...td, fontFamily: "monospace", fontSize: 11 }}>{a.roll}</td>
                  <td style={td}>
                    <Tooltip text={`${a.name}'s total penalty = ${a.penalty}\n\nBreakdown:\n  Preferred (0 pts each) = free\n  Tolerable (+1 pt each)\n  Disliked (+3 pts each)\n\nLower = more of their preferred time slots were honoured.`}>
                      <Badge color={a.penalty <= 3 ? "green" : a.penalty <= 6 ? "blue" : "amber"}>{a.penalty}</Badge>
                    </Tooltip>
                  </td>
                  <td style={td}>{facPen}</td>
                  <td style={td}><Badge color="green">✓ Assigned</Badge></td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      </div>

      {results.gap_reduction && (
        <Card>
          <div style={{ fontWeight: 500, marginBottom: 4 }}>Gap-reduction post-processing{" "}
            <Tooltip text={"After the CP-SAT optimum is found, a second pass looks for idle periods between a student's classes and tries swapping to an alternative section of the SAME subject that removes the gap.\n\nA swap is only applied if it does not increase that student's penalty — so the total penalty can only stay the same or improve, never get worse."}>
              <span style={{ fontSize: 11, color: "#888", cursor: "help", borderBottom: "1px dashed #bbb" }}>what is this?</span>
            </Tooltip>
          </div>
          <div style={{ fontSize: 12, color: "#888", marginBottom: 10 }}>
            {results.gap_reduction.swaps_applied} swap{results.gap_reduction.swaps_applied === 1 ? "" : "s"} applied · idle gaps reduced from{" "}
            <b>{results.gap_reduction.total_gaps_before}</b> to <b>{results.gap_reduction.total_gaps_after}</b> · total penalty unaffected or improved (CP-SAT optimum: {results.objective_total_penalty}, final: {results.total_penalty})
          </div>
          {results.gap_reduction.changes.length > 0 && (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead><tr>{["Student", "Subject", "From → To Section", "Gaps Before → After"].map(h => <th key={h} style={{ textAlign: "left", padding: "4px 8px", fontSize: 11, color: "#888", borderBottom: "1px solid #eee" }}>{h}</th>)}</tr></thead>
              <tbody>
                {results.gap_reduction.changes.map((c, i) => (
                  <tr key={i}>
                    <td style={td}>{c.name}</td>
                    <td style={td}>{c.subject_code}</td>
                    <td style={td}>Sec {c.from_section} → Sec {c.to_section}</td>
                    <td style={td}>{c.gap_before} → {c.gap_after}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}
    </div>
  );
}
