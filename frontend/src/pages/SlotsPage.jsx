import { td } from "../constants";
import { Badge, Card, EmptyState, InfoBox, MetricsRow, PageHeader } from "../components/ui";

export default function SlotsPage({ slots }) {
  const subjects = [...new Set(slots.map(s => s.code))];
  return (
    <div>
      <PageHeader title="Slot instances" sub="Pre-scheduled section instances for this semester" />
      <InfoBox title="What are slot instances?">
        Each row below is one <strong>section</strong> of a subject — a specific class with a fixed teacher and room, meeting at
        one or more fixed times per week (some sections meet twice a week, e.g. a lecture on Mon + Wed).
        Each subject has multiple sections (A, B, C…). The solver will pick <strong>exactly one section per subject</strong> for
        every student, based on their time preferences — and a student is scheduled into ALL of that section's weekly meetings.
      </InfoBox>
      <MetricsRow items={[
        { val: slots.length, label: "Total instances",
          tip: "Total number of class sections across all subjects (e.g. Data Structures Sec A, Sec B, Sec C = 3 instances)." },
        { val: subjects.length, label: "Subjects",
          tip: "Number of distinct subjects offered this semester. Every student must be assigned one section of each subject." },
        { val: slots.reduce((a, s) => a + s.capacity, 0), label: "Total seats",
          tip: "Sum of all section capacities. Each section can accommodate at most this many students." },
        { val: "CP-SAT", label: "Solver engine",
          tip: "Google OR-Tools CP-SAT — a Constraint Programming / Boolean SAT hybrid solver used to find the optimal assignment." },
      ]} />
      {slots.length === 0 ? (
        <EmptyState message="No sections have been created yet." />
      ) : (
        <Card>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>{["Subject", "Code", "Section", "Faculty", "Meetings", "Room", "Capacity"].map(h => (
                <th key={h} style={{ textAlign: "left", padding: "6px 10px", fontSize: 11, fontWeight: 500, color: "#888", borderBottom: "1px solid #eee" }}>{h}</th>
              ))}</tr>
            </thead>
            <tbody>
              {slots.map(s => (
                <tr key={s.id}>
                  <td style={td}>{s.subject}</td>
                  <td style={td}><code style={{ fontSize: 11, background: "#f1efe8", padding: "1px 5px", borderRadius: 3 }}>{s.code}</code></td>
                  <td style={td}><Badge color="blue">Sec {s.section}</Badge></td>
                  <td style={td}>{s.faculty}</td>
                  <td style={td}>
                    {s.meetings.map((m, i) => (
                      <span key={i} style={{ marginRight: 6, whiteSpace: "nowrap" }}>{m.day} {m.time}{i < s.meetings.length - 1 ? "," : ""}</span>
                    ))}
                    {s.meetings.length > 1 && <span style={{ fontSize: 10, color: "#888" }}> ({s.meetings.length}x/week)</span>}
                  </td>
                  <td style={td}>{s.room}</td>
                  <td style={td}>{s.capacity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
