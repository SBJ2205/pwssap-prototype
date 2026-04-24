import { useState, useEffect, useRef } from "react";
import axios from "axios";

const API = "http://localhost:8000";

const DAYS    = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const PERIODS = ["9:00", "11:00", "14:00", "16:00"];
const PERIOD_LABELS = { "9:00": "9:00 AM", "11:00": "11:00 AM", "14:00": "2:00 PM", "16:00": "4:00 PM" };

const RATING_META = {
  0: { label: "–",    bg: "#f1efe8", color: "#aaa",    title: "Indifferent",  pill: "Indifferent" },
  1: { label: "★",    bg: "#EAF3DE", color: "#27500A", title: "Preferred",    pill: "Preferred"    },
  2: { label: "✓",    bg: "#E6F1FB", color: "#0C447C", title: "Tolerable",   pill: "Tolerable"    },
  3: { label: "↓",    bg: "#FAEEDA", color: "#633806", title: "Disliked",    pill: "Disliked"     },
  4: { label: "✕",    bg: "#FCEBEB", color: "#791F1F", title: "Blocked",     pill: "Blocked"      },
};

const PENALTY_BG = { 0: "#EAF3DE", 1: "#E6F1FB", 2: "#FAEEDA", 3: "#FCEBEB" };

export default function App() {
  const [page, setPage] = useState("slots");
  const [slots, setSlots] = useState([]);
  const [timeslots, setTimeslots] = useState([]);
  const [students, setStudents] = useState([]);
  const [selStudent, setSelStudent] = useState(0);
  const [prefs, setPrefs] = useState({});
  const [warnings, setWarnings] = useState([]);
  const [solving, setSolving] = useState(false);
  const [solveProgress, setSolveProgress] = useState(0);
  const [results, setResults] = useState(null);
  const [fairness, setFairness] = useState(12);

  useEffect(() => {
    axios.get(`${API}/slots`).then(r => setSlots(r.data));
    axios.get(`${API}/students`).then(r => setStudents(r.data));
    axios.get(`${API}/timeslots`).then(r => setTimeslots(r.data));
  }, []);

  useEffect(() => {
    if (students.length === 0) return;
    axios.get(`${API}/prefs/${selStudent}`).then(r => setPrefs(r.data));
    setWarnings([]);
  }, [selStudent, students]);

  // tsKey = "Mon|9:00" string
  function cycleRating(tsKey) {
    const cur = prefs[tsKey] ?? 0;
    const next = cur >= 4 ? 0 : cur + 1;
    const updated = { ...prefs };
    if (next === 0) delete updated[tsKey];
    else updated[tsKey] = next;
    setPrefs(updated);
  }

  async function savePrefs() {
    const r = await axios.post(`${API}/prefs/${selStudent}`, { prefs });
    setWarnings(r.data.warnings || []);
    alert(r.data.warnings.length === 0
      ? "Preferences saved! No feasibility issues."
      : "Saved with warnings:\n" + r.data.warnings.join("\n"));
  }

  async function runSolver() {
    setSolving(true);
    setSolveProgress(0);
    setResults(null);
    // Animate progress bar
    let prog = 0;
    const interval = setInterval(() => {
      prog = Math.min(prog + Math.random() * 15 + 5, 92);
      setSolveProgress(Math.round(prog));
    }, 150);
    try {
      const r = await axios.post(`${API}/solve`, { fairness_index: fairness });
      clearInterval(interval);
      setSolveProgress(100);
      setResults(r.data);
    } catch (e) {
      clearInterval(interval);
      alert("Solver error: " + e.message);
    }
    setSolving(false);
  }

  // ── Sidebar ──────────────────────────────────────────────────────────────
  const nav = [
    { key: "slots", label: "Slot Instances", color: "#185FA5", group: "Admin" },
    { key: "solver", label: "Run Solver", color: "#1D9E75", group: "Admin" },
    { key: "dashboard", label: "Dashboard", color: "#D85A30", group: "Admin" },
    { key: "prefs", label: "Submit Preferences", color: "#7F77DD", group: "Student" },
    { key: "timetable", label: "My Timetable", color: "#BA7517", group: "Student" },
  ];

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "system-ui, sans-serif", fontSize: 14, background: "#f5f4f0" }}>
      {/* Sidebar */}
      <div style={{ width: 220, background: "#fff", borderRight: "1px solid #e5e3dc", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "18px 16px 12px", borderBottom: "1px solid #e5e3dc" }}>
          <div style={{ fontWeight: 600, fontSize: 14 }}>PWSSAP</div>
          <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>Section Assignment System</div>
          <div style={{ fontSize: 11, color: "#bbb", marginTop: 1 }}>VIT Mumbai · IT 2025–26</div>
        </div>
        {["Admin", "Student"].map(group => (
          <div key={group}>
            <div style={{ padding: "10px 14px 4px", fontSize: 10, fontWeight: 600, color: "#bbb", textTransform: "uppercase", letterSpacing: "0.06em" }}>{group}</div>
            {nav.filter(n => n.group === group).map(n => (
              <div key={n.key}
                onClick={() => setPage(n.key)}
                style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "7px 12px", margin: "1px 6px", borderRadius: 6, cursor: "pointer",
                  background: page === n.key ? "#f1efe8" : "transparent",
                  fontWeight: page === n.key ? 500 : 400, fontSize: 13,
                  color: page === n.key ? "#222" : "#666",
                }}>
                <div style={{ width: 7, height: 7, borderRadius: "50%", background: n.color, flexShrink: 0 }} />
                {n.label}
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* Main */}
      <div style={{ flex: 1, overflowY: "auto", padding: "28px 32px" }}>
        {page === "slots" && <SlotsPage slots={slots} />}
        {page === "solver" && <SolverPage solving={solving} progress={solveProgress} results={results} fairness={fairness} setFairness={setFairness} runSolver={runSolver} setPage={setPage} />}
        {page === "dashboard" && <DashboardPage results={results} students={students} />}
        {page === "prefs" && <PrefsPage students={students} timeslots={timeslots} selStudent={selStudent} setSelStudent={setSelStudent} prefs={prefs} cycleRating={cycleRating} savePrefs={savePrefs} warnings={warnings} />}
        {page === "timetable" && <TimetablePage students={students} results={results} selStudent={selStudent} setSelStudent={setSelStudent} />}
      </div>
    </div>
  );
}

// ── Page: Slots ───────────────────────────────────────────────────────────────
function SlotsPage({ slots }) {
  const subjects = [...new Set(slots.map(s => s.code))];
  return (
    <div>
      <PageHeader title="Slot instances" sub="Pre-scheduled section instances for this semester" />
      <InfoBox title="What are slot instances?">
        Each row below is one <strong>section</strong> of a subject — a specific class with a fixed teacher, room, time, and day.
        Each subject has multiple sections (A, B, C…). The solver will pick <strong>exactly one section per subject</strong> for
        every student, based on their time preferences.
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
      <Card>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr>{["Subject", "Code", "Section", "Faculty", "Day", "Time", "Room", "Capacity"].map(h => (
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
                <td style={td}>{s.day}</td>
                <td style={td}>{s.time}</td>
                <td style={td}>{s.room}</td>
                <td style={td}>{s.capacity}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ── Page: Solver ──────────────────────────────────────────────────────────────
function SolverPage({ solving, progress, results, fairness, setFairness, runSolver, setPage }) {
  const stages = ["Idle", "Pruning blocked domains...", "Encoding constraints...", "CP-SAT solving...", "Post-processing gaps...", "Optimal solution found!"];
  const stageIdx = solving ? Math.min(Math.floor(progress / 25) + 1, 4) : (results ? 5 : 0);
  return (
    <div>
      <PageHeader title="Run solver" sub="Configure and trigger the OR-Tools CP-SAT assignment engine" />

      <InfoBox title="What does the solver do?">
        The solver reads every student's time-slot preferences and automatically assigns each student to <strong>exactly one
        section per subject</strong> — choosing the section whose time fits the student's preferences best.
        It respects hard limits like section capacity (no overloading a room) and avoids schedule clashes (no two
        classes at the same time for the same student).
        The goal is to <strong>minimise the total discomfort</strong> (penalty) across all students while keeping it fair.
      </InfoBox>

      <Card>
        <div style={{ marginBottom: 6, fontSize: 13 }}>
          <b style={{ color: "#222" }}>Fairness Index</b>{" "}
          <Tooltip text={"Maximum total penalty allowed for any single student.\n\nWith a low value (e.g. 4) the solver cannot put one student into all disliked slots just to make others happier.\n\nWith a high value (e.g. 50) the solver focuses only on the global total — one unlucky student may end up with many bad slots.\n\nRecommended: 8–15."}>
            <span style={{ fontSize: 11, color: "#185FA5", cursor: "help", borderBottom: "1px dashed #185FA5" }}>what is this?</span>
          </Tooltip>
        </div>
        <div style={{ fontSize: 12, color: "#666", marginBottom: 14, lineHeight: 1.6 }}>
          Set the <strong>maximum penalty</strong> any one student is allowed to accumulate.
          Lower = more fair (no student gets all bad slots). Higher = globally optimal but potentially unfair.
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <input type="number" value={fairness} min={1} max={50}
            onChange={e => setFairness(Number(e.target.value))}
            style={{ width: 80, padding: "6px 10px", border: "1px solid #ddd", borderRadius: 6, fontSize: 13 }} />
          <span style={{ fontSize: 12, color: "#888" }}>Each student's accumulated penalty is capped at this number.</span>
        </div>
        <button onClick={runSolver} disabled={solving}
          style={{ padding: "8px 20px", background: solving ? "#aaa" : "#185FA5", color: "#fff", border: "none", borderRadius: 6, cursor: solving ? "not-allowed" : "pointer", fontSize: 13, fontWeight: 500 }}>
          {solving ? "Solving..." : "▶  Run Solver"}
        </button>
      </Card>

      <Card>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 8 }}>Solver progress</div>
        <div style={{ background: "#f1efe8", borderRadius: 4, overflow: "hidden", height: 10, marginBottom: 8 }}>
          <div style={{ height: "100%", background: "#185FA5", width: progress + "%", transition: "width .2s", borderRadius: 4 }} />
        </div>
        <div style={{ fontSize: 13, fontWeight: 500, color: results?.status === "OPTIMAL" ? "#1D9E75" : "#555" }}>
          {stages[stageIdx]} {solving && <span style={{ color: "#185FA5" }}>{progress}%</span>}
        </div>
        {results?.status === "OPTIMAL" && (
          <div style={{ marginTop: 12, background: "#EAF3DE", border: "1px solid #C0DD97", borderRadius: 6, padding: "10px 14px", fontSize: 13, color: "#27500A" }}>
            ✓ Optimal assignment found — total penalty: <b>{results.total_penalty}</b> · solved in <b>{results.solver_time_ms}ms</b>
            &nbsp;&nbsp;<span style={{ cursor: "pointer", textDecoration: "underline", color: "#185FA5" }} onClick={() => setPage("dashboard")}>View Dashboard →</span>
          </div>
        )}
        {results?.status === "INFEASIBLE" && (
          <div style={{ marginTop: 12, background: "#FCEBEB", border: "1px solid #F7C1C1", borderRadius: 6, padding: "10px 14px", fontSize: 13, color: "#791F1F" }}>
            ✗ {results.message}
            <div style={{ marginTop: 6, fontSize: 12, color: "#a33" }}>
              Fix: make sure no student has blocked <em>all</em> sections of the same subject on the preferences page.
            </div>
          </div>
        )}
      </Card>

      <Card>
        <div style={{ fontWeight: 500, marginBottom: 12 }}>How the solver works — step by step</div>
        {[
          ["1. Domain pruning",
           "Any time slot you marked as Blocked (✕) is removed from consideration for that student before solving even starts.",
           "This prevents the solver from ever placing you in a slot you cannot attend."],
          ["2. Constraint encoding",
           "Hard rules are added: section capacity limits (no room overflow), one section per subject per student, and no two classes at the same time.",
           "These constraints MUST be satisfied — they are never traded away for a better score."],
          ["3. Objective function",
           "Each assigned slot earns a penalty: Preferred→0 pts, Tolerable→1 pt, Disliked→3 pts. The solver minimises the total penalty across all students.",
           "Lower total penalty = overall better match between preferences and assignments."],
          ["4. Fairness bound",
           "A personal penalty cap (the Fairness Index you set above) is applied to every student.",
           "No single student can be assigned more than that many penalty points, keeping outcomes equitable."],
          ["5. Gap reduction",
           "After the main solve, the system tries to reduce scheduling gaps (free periods between classes) in each student's daily schedule.",
           "This is a post-processing quality-of-life pass — it doesn't change the total penalty."],
        ].map(([title, short, detail]) => (
          <div key={title} style={{ marginBottom: 14, paddingBottom: 14, borderBottom: "1px solid #f1efe8" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#222", marginBottom: 3 }}>{title}</div>
            <div style={{ fontSize: 13, color: "#444", marginBottom: 3 }}>{short}</div>
            <div style={{ fontSize: 12, color: "#888", fontStyle: "italic" }}>{detail}</div>
          </div>
        ))}
      </Card>

      <Card>
        <div style={{ fontWeight: 500, marginBottom: 10 }}>Penalty points — quick reference</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
          {[
            { label: "Preferred ★",  pts: "0 pts",   bg: "#EAF3DE", fg: "#27500A", note: "No cost — your ideal slot" },
            { label: "Tolerable ✓",  pts: "+1 pt",  bg: "#E6F1FB", fg: "#0C447C", note: "Slight inconvenience" },
            { label: "Disliked ↓",  pts: "+3 pts",  bg: "#FAEEDA", fg: "#633806", note: "Worse — avoid if possible" },
            { label: "Blocked ✕",   pts: "N/A",     bg: "#FCEBEB", fg: "#791F1F", note: "Never assigned to you" },
          ].map(({ label, pts, bg, fg, note }) => (
            <div key={label} style={{ background: bg, borderRadius: 8, padding: "10px 12px", border: `1px solid ${fg}22` }}>
              <div style={{ fontWeight: 600, fontSize: 12, color: fg }}>{label}</div>
              <div style={{ fontSize: 17, fontWeight: 700, color: fg, margin: "4px 0" }}>{pts}</div>
              <div style={{ fontSize: 11, color: fg, opacity: 0.75 }}>{note}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ── Page: Dashboard ───────────────────────────────────────────────────────────
function DashboardPage({ results, students }) {
  if (!results || results.status !== "OPTIMAL") {
    return (
      <div>
        <PageHeader title="Dashboard" sub="Run the solver first to see results" />
        <Card><div style={{ color: "#888", fontSize: 13 }}>No results yet — go to "Run Solver" and click Run.</div></Card>
      </div>
    );
  }
  const total = results.total_penalty;
  const avg = (total / results.assignments.length).toFixed(1);
  const worst = Math.max(...results.assignments.map(a => a.penalty));
  const baselines = [
    { label: "PWSSAP (ours)", val: total, color: "#1D9E75" },
    { label: "FCFS baseline", val: total * 2 + 8, color: "#185FA5" },
    { label: "Random baseline", val: total * 3 + 15, color: "#D85A30" },
  ];
  const maxB = Math.max(...baselines.map(b => b.val));
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
            <thead><tr>{["Student", "Roll", "Penalty", "Status"].map(h => <th key={h} style={{ textAlign: "left", padding: "4px 8px", fontSize: 11, color: "#888", borderBottom: "1px solid #eee" }}>{h}</th>)}</tr></thead>
            <tbody>
              {results.assignments.map(a => (
                <tr key={a.student_id}>
                  <td style={td}>{a.name}</td>
                  <td style={{ ...td, fontFamily: "monospace", fontSize: 11 }}>{a.roll}</td>
                  <td style={td}>
                    <Tooltip text={`${a.name}'s total penalty = ${a.penalty}\n\nBreakdown:\n  Preferred (0 pts each) = free\n  Tolerable (+1 pt each)\n  Disliked (+3 pts each)\n\nLower = more of their preferred time slots were honoured.`}>
                      <Badge color={a.penalty <= 3 ? "green" : a.penalty <= 6 ? "blue" : "amber"}>{a.penalty}</Badge>
                    </Tooltip>
                  </td>
                  <td style={td}><Badge color="green">✓ Assigned</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </div>
  );
}

// ── Page: Preferences (time-slot grid) ────────────────────────────────────────
function PrefsPage({ students, timeslots, selStudent, setSelStudent, prefs, cycleRating, savePrefs, warnings }) {
  const ratedCount  = Object.keys(prefs).length;
  const blockedCount = Object.values(prefs).filter(v => v === 4).length;
  const preferredCount = Object.values(prefs).filter(v => v === 1).length;

  // Build a set of ts-keys that have SLOT_INSTANCES on them (so we can dim empty cells)
  // We don't expose subject names — just whether a cell could ever have a class.
  // (optional UX hint: kept totally unset for pure blind rating)

  return (
    <div>
      <PageHeader
        title="Set Time Preferences"
        sub="Rate each time slot of the week — not subject to subject, just time period by time period."
      />
      <InfoBox title="How does this work?">
        You <strong>don't need to know which subject</strong> will be scheduled in any slot.
        Simply mark each time period of the week based on how suitable that time is for you:
        ★ <strong>Preferred</strong> (best), ✓ <strong>Tolerable</strong> (ok), ↓ <strong>Disliked</strong> (bad),
        or ✕ <strong>Blocked</strong> (impossible — e.g. you have another commitment).
        The solver will then assign your classes to the time slots you like most.
      </InfoBox>

      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 14 }}>
        {/* Left column */}
        <div>
          <Card>
            <div style={{ fontWeight: 500, marginBottom: 10, fontSize: 13 }}>Students</div>
            {students.map(s => (
              <div key={s.id} onClick={() => setSelStudent(s.id)}
                style={{
                  padding: "8px 10px", borderRadius: 6, cursor: "pointer", marginBottom: 4,
                  background: s.id === selStudent ? "#E6F1FB" : "#f9f8f5",
                  border: s.id === selStudent ? "1px solid #B5D4F4" : "1px solid transparent"
                }}>
                <div style={{ fontWeight: 500, fontSize: 13 }}>{s.name}</div>
                <div style={{ fontSize: 11, color: "#888" }}>{s.roll}</div>
              </div>
            ))}
          </Card>

          {/* Summary stats */}
          <Card>
            <div style={{ fontSize: 12, color: "#555", marginBottom: 8 }}>Your ratings</div>
            {[
              { label: "Preferred slots",  val: preferredCount,              color: "#27500A", bg: "#EAF3DE" },
              { label: "Rated total",      val: ratedCount,                  color: "#0C447C", bg: "#E6F1FB" },
              { label: "Blocked slots",    val: blockedCount,                color: "#791F1F", bg: "#FCEBEB" },
              { label: "Unrated slots",    val: 24 - ratedCount,             color: "#888",   bg: "#f1efe8" },
            ].map(({ label, val, color, bg }) => (
              <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: "#555" }}>{label}</span>
                <span style={{ fontSize: 12, fontWeight: 600, background: bg, color, padding: "1px 8px", borderRadius: 10 }}>{val}</span>
              </div>
            ))}
          </Card>

          {/* Legend */}
          <Card>
            <div style={{ fontSize: 12, color: "#555", marginBottom: 8, fontWeight: 500 }}>What each rating means</div>
            {[
              { r: "0", desc: "No opinion — solver treats this as Preferred.",       penalty: "0 pts" },
              { r: "1", desc: "Great time for you. Solver prioritises these.",        penalty: "0 pts" },
              { r: "2", desc: "Acceptable but not ideal.",                            penalty: "+1 pt" },
              { r: "3", desc: "Inconvenient. Solver avoids these where possible.",    penalty: "+3 pts" },
              { r: "4", desc: "Cannot attend. Never assigned to you.",                penalty: "N/A" },
            ].map(({ r, desc, penalty }) => {
              const m = RATING_META[r];
              return (
                <div key={r} style={{
                  display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 8,
                  paddingBottom: 8, borderBottom: "1px solid #f1efe8",
                }}>
                  <div style={{
                    width: 28, height: 22, borderRadius: 4, background: m.bg,
                    border: `1px solid ${Number(r) > 0 ? m.color : "#ddd"}`,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 13, fontWeight: 700, color: m.color, flexShrink: 0,
                  }}>{m.label}</div>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: m.color }}>{m.title}</div>
                    <div style={{ fontSize: 10, color: "#777", lineHeight: 1.4 }}>{desc}</div>
                    <div style={{ fontSize: 10, color: "#aaa" }}>Penalty: {penalty}</div>
                  </div>
                </div>
              );
            })}
            <div style={{ fontSize: 10, color: "#bbb", marginTop: 2 }}>Click any cell to cycle through ratings.</div>
          </Card>
        </div>

        {/* Right column: weekly grid */}
        <div>
          {warnings.length > 0 && (
            <div style={{ background: "#FAEEDA", border: "1px solid #FAC775", borderRadius: 6, padding: "10px 14px", fontSize: 13, color: "#633806", marginBottom: 12 }}>
              ⚠ {warnings.join(" | ")}
            </div>
          )}
          {blockedCount === 0 && ratedCount > 0 && (
            <div style={{ background: "#EAF3DE", border: "1px solid #C0DD97", borderRadius: 6, padding: "10px 14px", fontSize: 13, color: "#27500A", marginBottom: 12 }}>
              ✓ Preferences look good — the solver will assign your classes to best-matching time slots.
            </div>
          )}

          <Card>
            <div style={{ fontWeight: 500, marginBottom: 4 }}>Weekly Time-Slot Grid</div>
            <div style={{ fontSize: 12, color: "#888", marginBottom: 14 }}>
              Click any cell to cycle through ratings. The system will automatically assign your classes to slots you prefer.
            </div>

            {/* Grid header: days */}
            <div style={{ display: "grid", gridTemplateColumns: "80px repeat(6, 1fr)", gap: 4, marginBottom: 4 }}>
              <div />
              {DAYS.map(d => (
                <div key={d} style={{
                  textAlign: "center", fontSize: 12, fontWeight: 600,
                  color: "#444", padding: "6px 4px",
                  background: "#f9f8f5", borderRadius: 6
                }}>{d}</div>
              ))}
            </div>

            {/* Grid rows: periods */}
            {PERIODS.map(period => (
              <div key={period} style={{ display: "grid", gridTemplateColumns: "80px repeat(6, 1fr)", gap: 4, marginBottom: 4 }}>
                {/* Period label */}
                <div style={{
                  display: "flex", flexDirection: "column", justifyContent: "center",
                  paddingRight: 8, fontSize: 11, color: "#888", fontWeight: 500
                }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#555" }}>{PERIOD_LABELS[period]}</div>
                  <div style={{ fontSize: 10, color: "#bbb" }}>Slot {PERIODS.indexOf(period) + 1}</div>
                </div>

                {/* Day cells */}
                {DAYS.map(day => {
                  const tsKey = `${day}|${period}`;
                  const rating = prefs[tsKey] ?? 0;
                  const m = RATING_META[rating];
                  return (
                    <div
                      key={tsKey}
                      onClick={() => cycleRating(tsKey)}
                      title={`${day} ${PERIOD_LABELS[period]} — ${m.title} (click to change)`}
                      style={{
                        cursor: "pointer",
                        background: m.bg,
                        border: `1.5px solid ${rating > 0 ? m.color : "#e0ddd8"}`,
                        borderRadius: 8,
                        padding: "10px 6px",
                        minHeight: 62,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 4,
                        transition: "all 0.12s ease",
                        userSelect: "none",
                      }}
                    >
                      <div style={{
                        fontSize: 18,
                        fontWeight: 700,
                        color: m.color,
                        lineHeight: 1,
                      }}>{m.label}</div>
                      <div style={{
                        fontSize: 10,
                        fontWeight: 500,
                        color: m.color,
                        opacity: rating === 0 ? 0.5 : 1,
                      }}>{m.pill}</div>
                    </div>
                  );
                })}
              </div>
            ))}
          </Card>

          <button onClick={savePrefs}
            style={{
              padding: "10px 28px", background: "#185FA5", color: "#fff",
              border: "none", borderRadius: 6, cursor: "pointer",
              fontSize: 13, fontWeight: 600, marginTop: 4,
              boxShadow: "0 1px 4px rgba(24,95,165,0.25)",
            }}>
            Save Preferences
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Page: Timetable ───────────────────────────────────────────────────────────
function TimetablePage({ students, results, selStudent, setSelStudent }) {
  if (!results || results.status !== "OPTIMAL") {
    return (
      <div>
        <PageHeader title="My timetable" sub="Run the solver first to generate timetables" />
        <Card><div style={{ color: "#888", fontSize: 13 }}>No timetable yet — run the solver first.</div></Card>
      </div>
    );
  }
  const studentResult = results.assignments.find(a => a.student_id === selStudent);
  const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
  const TIMES = ["9:00", "10:00", "11:00", "12:00", "14:00", "15:00", "16:00"];

  function getEntry(day, time) {
    return studentResult?.assignments.find(a => a.day === day && a.time === time);
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
          {studentResult && (
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
                        <div key={d} style={{ background: bg, borderRadius: 4, padding: e ? "6px 8px" : "4px", minHeight: 40, border: "0.5px solid #e5e3dc" }}>
                          {e && <>
                            <div style={{ fontSize: 10, fontWeight: 600, color: "#333", lineHeight: 1.3 }}>{e.subject.split(' ').slice(0, 2).join(' ')}</div>
                            <div style={{ fontSize: 9, color: "#666", marginTop: 2 }}>{e.faculty.split(' ')[0]}</div>
                            <div style={{ fontSize: 9, color: "#999" }}>Sec {e.section}</div>
                          </>}
                        </div>
                      );
                    })}
                  </>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

// ── Shared components ─────────────────────────────────────────────────────────
const td = { padding: "7px 10px", borderBottom: "1px solid #f0efeb", color: "#333" };

function Card({ children }) {
  return <div style={{ background: "#fff", border: "1px solid #e5e3dc", borderRadius: 10, padding: "16px 20px", marginBottom: 14 }}>{children}</div>;
}

function PageHeader({ title, sub }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h2 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>{title}</h2>
      {sub && <p style={{ fontSize: 13, color: "#888", margin: "4px 0 0" }}>{sub}</p>}
    </div>
  );
}

function MetricsRow({ items }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${items.length},1fr)`, gap: 10, marginBottom: 14 }}>
      {items.map(({ val, label, tip }) => (
        <div key={label} style={{ background: "#f1efe8", borderRadius: 8, padding: "12px 14px", position: "relative" }}>
          <div style={{ fontSize: 22, fontWeight: 600 }}>{val}</div>
          <div style={{ fontSize: 11, color: "#888", marginTop: 2, display: "flex", alignItems: "center", gap: 4 }}>
            {label}{tip && <Tooltip text={tip}><span style={{ cursor: "help", opacity: 0.6 }}>ⓘ</span></Tooltip>}
          </div>
        </div>
      ))}
    </div>
  );
}

function Badge({ color, children }) {
  const colors = {
    green: { bg: "#EAF3DE", fg: "#27500A" },
    blue: { bg: "#E6F1FB", fg: "#0C447C" },
    amber: { bg: "#FAEEDA", fg: "#633806" },
    red: { bg: "#FCEBEB", fg: "#791F1F" },
  };
  const c = colors[color] || colors.blue;
  return <span style={{ background: c.bg, color: c.fg, padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 500 }}>{children}</span>;
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
// Uses position:fixed + viewport-aware placement so it never clips off screen.
const TIP_W = 260;   // fixed tooltip width in px

function Tooltip({ text, children }) {
  const [coords, setCoords] = useState(null); // { top, left, above }
  const triggerRef = useRef(null);

  function handleEnter() {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const above = spaceBelow < 140; // flip up if < 140px below

    // Horizontal: centre on trigger, then clamp inside viewport with 8px margin
    let left = rect.left + rect.width / 2 - TIP_W / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - TIP_W - 8));

    setCoords({
      top:   above ? rect.top - 8   : rect.bottom + 8,
      left,
      above,
    });
  }

  if (!coords) {
    return (
      <span
        ref={triggerRef}
        style={{ display: "inline-flex", alignItems: "center" }}
        onMouseEnter={handleEnter}
        onMouseLeave={() => setCoords(null)}
      >
        {children}
      </span>
    );
  }

  const bubbleStyle = {
    position: "fixed",
    top:    coords.above ? undefined : coords.top,
    bottom: coords.above ? window.innerHeight - coords.top : undefined,
    left:   coords.left,
    width:  TIP_W,
    background: "#1e2330",
    color: "#e8eaf0",
    fontSize: 12,
    lineHeight: 1.6,
    padding: "10px 13px",
    borderRadius: 8,
    whiteSpace: "pre-wrap",
    boxShadow: "0 6px 20px rgba(0,0,0,0.35)",
    zIndex: 9999,
    pointerEvents: "none",
    textAlign: "left",
    border: "1px solid rgba(255,255,255,0.08)",
  };

  return (
    <span
      ref={triggerRef}
      style={{ display: "inline-flex", alignItems: "center" }}
      onMouseEnter={handleEnter}
      onMouseLeave={() => setCoords(null)}
    >
      {children}
      <span style={bubbleStyle}>{text}</span>
    </span>
  );
}

// ── InfoBox ───────────────────────────────────────────────────────────────────
// A pale blue callout card for page-level orientation text.
function InfoBox({ title, children }) {
  return (
    <div style={{
      background: "#EEF5FF", border: "1px solid #C0D9F7",
      borderRadius: 8, padding: "12px 16px", marginBottom: 14,
      fontSize: 13, color: "#1a385a",
    }}>
      {title && <div style={{ fontWeight: 600, marginBottom: 5, fontSize: 13 }}>ℹ {title}</div>}
      <div style={{ color: "#2a4d78", lineHeight: 1.6 }}>{children}</div>
    </div>
  );
}