import { PENALTY_BG } from "../constants";
import { Card, EmptyState, PageHeader, Tooltip } from "../components/ui";

export default function TimetablePage({ students, results, selStudent, setSelStudent }) {
  if (!results || results.status !== "OPTIMAL") {
    return (
      <div>
        <PageHeader title="My timetable" sub="Run the solver first to generate timetables" />
        <EmptyState message="No timetable yet — run the solver first." />
      </div>
    );
  }
  const studentResult = results.assignments.find(a => a.student_id === selStudent);
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
  const TIMES = ["9:00", "10:00", "11:00", "12:00", "14:00", "15:00", "16:00"];

  function getEntry(day, time) {
    return studentResult?.assignments.find(a => a.meetings.some(m => m.day === day && m.time === time));
  }

  return (
    <div>
      <PageHeader title="My timetable" sub="Your final assigned schedule, colour-coded by how well it matched your preferences" />
      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 14 }}>
        <div>
          <Card>
            <div style={{ fontWeight: 500, marginBottom: 10, fontSize: 13 }}>Students</div>
            {students.map(s => {
              const res = results.assignments.find(a => a.student_id === s.id);
              return (
                <div key={s.id} onClick={() => setSelStudent(s.id)}
                  style={{
                    padding: "8px 10px", borderRadius: 6, cursor: "pointer", marginBottom: 4,
                    background: s.id === selStudent ? "#E6F1FB" : "#f9f8f5",
                    border: s.id === selStudent ? "1px solid #B5D4F4" : "1px solid transparent"
                  }}>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{s.name}</div>
                  <div style={{ fontSize: 11, color: "#888" }}>
                    Penalty:{" "}
                    <Tooltip text={`Total penalty = ${res?.penalty ?? "?"}\n\nThis is the sum of penalty points for every assigned class:\n  Preferred time slot → 0 pts\n  Tolerable time slot → +1 pt\n  Disliked time slot  → +3 pts\n\nLower = the solver found a schedule closer to your ideal.`}>
                      <span style={{ fontWeight: 600, color: (res?.penalty ?? 0) <= 3 ? "#27500A" : (res?.penalty ?? 0) <= 6 ? "#0C447C" : "#633806", cursor: "help" }}>
                        {res?.penalty ?? "?"}
                      </span>
                    </Tooltip>
                  </div>
                </div>
              );
            })}
          </Card>
          <Card>
            <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 8 }}>Colour legend</div>
            <div style={{ fontSize: 11, color: "#888", marginBottom: 8, lineHeight: 1.5 }}>
              Cell colour shows whether the assigned time slot matched your preference.
            </div>
            {[
              ["#EAF3DE", "#27500A", "Preferred",  "0 pts — you asked for this time"],
              ["#E6F1FB", "#0C447C", "Tolerable",  "+1 pt — acceptable but not ideal"],
              ["#FAEEDA", "#633806", "Disliked",   "+3 pts — inconvenient, no better option was available"],
            ].map(([bg, fg, title, note]) => (
              <div key={title} style={{ display: "flex", alignItems: "flex-start", gap: 7, marginBottom: 8 }}>
                <div style={{ width: 14, height: 14, borderRadius: 3, background: bg, border: `1px solid ${fg}44`, flexShrink: 0, marginTop: 1 }} />
                <div>
                  <div style={{ fontSize: 11, fontWeight: 600, color: fg }}>{title}</div>
                  <div style={{ fontSize: 10, color: "#999" }}>{note}</div>
                </div>
              </div>
            ))}
          </Card>
        </div>
        <Card>
          {studentResult ? (
            <>
              <div style={{ fontWeight: 500, marginBottom: 2 }}>{studentResult.name}</div>
              <div style={{ fontSize: 12, color: "#888", marginBottom: 14, display: "flex", alignItems: "center", gap: 6 }}>
                Total penalty:{" "}
                <b style={{ color: studentResult.penalty <= 3 ? "#1D9E75" : "#D85A30" }}>{studentResult.penalty}</b>
                <Tooltip text={`Your penalty = ${studentResult.penalty}\n\nHow it's calculated:\n• Each class in a Preferred slot → 0 pts\n• Each class in a Tolerable slot → +1 pt\n• Each class in a Disliked slot  → +3 pts\n\nA score of 0 is perfect — all classes are in your best time slots.`}>
                  <span style={{ fontSize: 11, color: "#888", cursor: "help", opacity: 0.7 }}>ⓘ what is this?</span>
                </Tooltip>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "50px repeat(5,1fr)", gap: 3 }}>
                <div />
                {DAYS.map(d => <div key={d} style={{ textAlign: "center", fontSize: 12, fontWeight: 500, color: "#555", padding: "4px 0" }}>{d}</div>)}
                {TIMES.map(t => (
                  <>
                    <div key={t} style={{ fontSize: 10, color: "#aaa", display: "flex", alignItems: "center" }}>{t}</div>
                    {DAYS.map(d => {
                      const e = getEntry(d, t);
                      const bg = e ? PENALTY_BG[e.rating] || "#EAF3DE" : "#f9f8f5";
                      return (
                        <div key={d} style={{ background: bg, borderRadius: 4, padding: e ? "6px 8px" : "4px", minHeight: 52, border: "0.5px solid #e5e3dc" }}>
                          {e && <>
                            <div style={{ fontSize: 10, fontWeight: 600, color: "#333", lineHeight: 1.3 }}>{e.subject}</div>
                            <div style={{ fontSize: 9, color: "#666", marginTop: 2, lineHeight: 1.3, wordBreak: "break-word" }}>{e.faculty}</div>
                            <div style={{ fontSize: 9, color: "#999", marginTop: 1 }}>Sec {e.section}</div>
                          </>}
                        </div>
                      );
                    })}
                  </>
                ))}
              </div>
            </>
          ) : (
            <div style={{ color: "#888", fontSize: 13 }}>Select a student to see their timetable.</div>
          )}
        </Card>
      </div>
    </div>
  );
}
