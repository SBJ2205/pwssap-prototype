import { Card, InfoBox, PageHeader, Tooltip } from "../components/ui";

export default function SolverPage({ solving, progress, results, fairness, setFairness, facultyWeight, setFacultyWeight, enableGapReduction, setEnableGapReduction, runSolver, setPage }) {
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
          <b style={{ color: "var(--text-primary)" }}>Fairness Index</b>{" "}
          <Tooltip text={"Maximum total penalty allowed for any single student.\n\nWith a low value (e.g. 4) the solver cannot put one student into all disliked slots just to make others happier.\n\nWith a high value (e.g. 50) the solver focuses only on the global total — one unlucky student may end up with many bad slots.\n\nRecommended: 8–15."}>
            <span style={{ fontSize: 11, color: "var(--accent-blue)", cursor: "help", borderBottom: "1px dashed var(--accent-blue)" }}>what is this?</span>
          </Tooltip>
        </div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 14, lineHeight: 1.6 }}>
          Set the <strong>maximum penalty</strong> any one student is allowed to accumulate.
          Lower = more fair (no student gets all bad slots). Higher = globally optimal but potentially unfair.
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <input type="number" value={fairness} min={1} max={50}
            onChange={e => setFairness(Number(e.target.value))}
            style={{ width: 80, padding: "6px 10px", border: "1px solid var(--border-subtle)", borderRadius: 6, fontSize: 13 }} />
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Each student's accumulated penalty is capped at this number.</span>
        </div>

        <div style={{ marginBottom: 6, fontSize: 13 }}>
          <b style={{ color: "var(--text-primary)" }}>Faculty Mismatch Weight</b>{" "}
          <Tooltip text={"How strongly the solver weighs faculty preference vs time-slot preference.\n\nThis is a SECONDARY term — it only breaks ties between sections that are otherwise equally good on time. It can never override a better time-slot match.\n\n0 = ignore faculty preference entirely. 1 = equal weight to time-slot penalty."}>
            <span style={{ fontSize: 11, color: "var(--accent-blue)", cursor: "help", borderBottom: "1px dashed var(--accent-blue)" }}>what is this?</span>
          </Tooltip>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <input type="number" value={facultyWeight} min={0} max={5}
            onChange={e => setFacultyWeight(Number(e.target.value))}
            style={{ width: 80, padding: "6px 10px", border: "1px solid var(--border-subtle)", borderRadius: 6, fontSize: 13 }} />
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Multiplier applied to the faculty-mismatch penalty term.</span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
          <input type="checkbox" checked={enableGapReduction} onChange={e => setEnableGapReduction(e.target.checked)} id="gapReduction" />
          <label htmlFor="gapReduction" style={{ fontSize: 13, cursor: "pointer" }}>Enable gap-reduction post-processing pass</label>
          <Tooltip text={"After the CP-SAT solve finds the optimal assignment, a second heuristic pass looks for idle gaps between a student's classes and tries to shift them to an equally-good (never worse) alternative section that removes the gap."}>
            <span style={{ fontSize: 11, color: "var(--accent-blue)", cursor: "help", borderBottom: "1px dashed var(--accent-blue)" }}>what is this?</span>
          </Tooltip>
        </div>

        <button onClick={runSolver} disabled={solving}
          style={{ padding: "8px 20px", background: solving ? "var(--text-muted)" : "var(--accent-blue)", color: "var(--on-accent)", border: "none", borderRadius: 6, cursor: solving ? "not-allowed" : "pointer", fontSize: 13, fontWeight: 500 }}>
          {solving ? "Solving..." : "▶  Run Solver"}
        </button>
      </Card>

      <Card>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>Solver progress</div>
        <div style={{ background: "var(--bg-surface-alt)", borderRadius: 4, overflow: "hidden", height: 10, marginBottom: 8 }}>
          <div style={{ height: "100%", background: "var(--accent-blue)", width: progress + "%", transition: "width .2s", borderRadius: 4 }} />
        </div>
        <div style={{ fontSize: 13, fontWeight: 500, color: results?.status === "OPTIMAL" ? "var(--accent-green)" : "var(--text-secondary)" }}>
          {stages[stageIdx]} {solving && <span style={{ color: "var(--accent-blue)" }}>{progress}%</span>}
        </div>
        {results?.status === "OPTIMAL" && (
          <div style={{ marginTop: 12, background: "var(--rating-green-bg)", border: "1px solid var(--success-border)", borderRadius: 6, padding: "10px 14px", fontSize: 13, color: "var(--rating-green-fg)" }}>
            ✓ Optimal assignment found — total penalty: <b>{results.total_penalty}</b>
            {results.gap_reduction && results.gap_reduction.swaps_applied > 0 && (
              <span> (CP-SAT optimum was {results.objective_total_penalty}; gap-reduction made {results.gap_reduction.swaps_applied} swap{results.gap_reduction.swaps_applied > 1 ? "s" : ""}, cutting idle gaps from {results.gap_reduction.total_gaps_before} to {results.gap_reduction.total_gaps_after})</span>
            )}
            {" "}· solved in <b>{results.solver_time_ms}ms</b>
            &nbsp;&nbsp;<span style={{ cursor: "pointer", textDecoration: "underline", color: "var(--accent-blue)" }} onClick={() => setPage("dashboard")}>View Dashboard →</span>
          </div>
        )}
        {results?.status === "INFEASIBLE" && (
          <div style={{ marginTop: 12, background: "var(--rating-red-bg)", border: "1px solid var(--danger-border)", borderRadius: 6, padding: "10px 14px", fontSize: 13, color: "var(--rating-red-fg)" }}>
            ✗ {results.message}
            <div style={{ marginTop: 6, fontSize: 12, color: "var(--danger-text-strong)" }}>
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
          <div key={title} style={{ marginBottom: 14, paddingBottom: 14, borderBottom: "1px solid var(--bg-surface-alt)" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 3 }}>{title}</div>
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 3 }}>{short}</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", fontStyle: "italic" }}>{detail}</div>
          </div>
        ))}
      </Card>

      <Card>
        <div style={{ fontWeight: 500, marginBottom: 10 }}>Penalty points — quick reference</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
          {[
            { label: "Preferred ★",  pts: "0 pts",   bg: "var(--rating-green-bg)", fg: "var(--rating-green-fg)", border: "var(--rating-green-border-soft)", note: "No cost — your ideal slot" },
            { label: "Tolerable ✓",  pts: "+1 pt",  bg: "var(--rating-blue-bg)", fg: "var(--rating-blue-fg)", border: "var(--rating-blue-border-soft)", note: "Slight inconvenience" },
            { label: "Disliked ↓",  pts: "+3 pts",  bg: "var(--rating-amber-bg)", fg: "var(--rating-amber-fg)", border: "var(--rating-amber-border-soft)", note: "Worse — avoid if possible" },
            { label: "Blocked ✕",   pts: "N/A",     bg: "var(--rating-red-bg)", fg: "var(--rating-red-fg)", border: "var(--rating-red-border-soft)", note: "Never assigned to you" },
          ].map(({ label, pts, bg, fg, border, note }) => (
            <div key={label} style={{ background: bg, borderRadius: 8, padding: "10px 12px", border: `1px solid ${border}` }}>
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
