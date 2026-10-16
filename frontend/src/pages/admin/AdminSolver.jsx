import { useCallback, useEffect, useState } from "react";
import { checkFeasibility, generateSections, runSolve, getSections } from "../../api/runs";
import { getSubjects, getStudents, getTeachers } from "../../api/catalog";
import { initializeCycle } from "../../api/cycle";
import { apiErrorMessage } from "../../api/client";
import { Card, PageHeader, InfoBox, MetricsRow } from "../../components/ui";
import CycleBanner from "../../components/CycleBanner";

export default function AdminSolver({
  cycleStatus,
  refreshCycle,
  setPage,
  activeRunId,
  setActiveRunId,
}) {
  const [internalRunId, setInternalRunId] = useState(null);
  const currentRun = cycleStatus?.current_run;
  const currentRunId = internalRunId != null ? internalRunId : (currentRun?.id != null ? currentRun.id : activeRunId);

  // Preflight data counts
  const [subjectsCount, setSubjectsCount] = useState(0);
  const [studentsCount, setStudentsCount] = useState(0);
  const [teachersCount, setTeachersCount] = useState(0);
  const [sectionsCount, setSectionsCount] = useState(0);
  const [preflightLoading, setPreflightLoading] = useState(false);

  // Time limit for solve
  const [timeLimit, setTimeLimit] = useState(30);

  // Section generation state
  const [generating, setGenerating] = useState(false);
  const [genSuccess, setGenSuccess] = useState(null);
  const [genWarnings, setGenWarnings] = useState([]);
  const [genError, setGenError] = useState(null);

  // Solver execution state
  const [solving, setSolving] = useState(false);
  const [progress, setProgress] = useState(0);
  const [solveResult, setSolveResult] = useState(null);
  const [solveError, setSolveError] = useState(null);
  const [checkingFeasibility, setCheckingFeasibility] = useState(false);
  const [feasibilityResult, setFeasibilityResult] = useState(null);

  const checkPreflight = useCallback(async () => {
    setPreflightLoading(true);
    try {
      const [subs, stus, teas] = await Promise.all([
        getSubjects().catch(() => []),
        getStudents().catch(() => []),
        getTeachers().catch(() => []),
      ]);
      setSubjectsCount(subs.length);
      setStudentsCount(stus.length);
      setTeachersCount(teas.length);

      const runId = internalRunId != null ? internalRunId : currentRunId;
      if (runId != null && !isNaN(Number(runId))) {
        const secs = await getSections(Number(runId)).catch(() => ({ count: 0 }));
        setSectionsCount(secs?.count || (Array.isArray(secs?.sections) ? secs.sections.length : 0));
      } else {
        setSectionsCount(0);
      }
    } finally {
      setPreflightLoading(false);
    }
  }, [internalRunId, currentRunId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    checkPreflight();
  }, [checkPreflight]);

  async function handleInitCycle() {
    try {
      const res = await initializeCycle();
      const rid = res?.run_id ?? res?.current_run?.id;
      if (rid != null && !isNaN(Number(rid))) {
        const numId = Number(rid);
        setInternalRunId(numId);
        if (setActiveRunId) setActiveRunId(numId);
      }
      if (refreshCycle) await refreshCycle();
      checkPreflight();
    } catch (err) {
      setGenError(apiErrorMessage(err));
    }
  }

  async function handleGenerateSections() {
    let runIdToUse = internalRunId != null ? internalRunId : (currentRunId != null ? currentRunId : activeRunId);
    if (runIdToUse == null || isNaN(Number(runIdToUse))) {
      try {
        const res = await initializeCycle();
        const newId = res?.run_id ?? res?.current_run?.id;
        if (newId != null && !isNaN(Number(newId))) {
          runIdToUse = Number(newId);
          setInternalRunId(runIdToUse);
          if (setActiveRunId) setActiveRunId(runIdToUse);
        }
        if (refreshCycle) await refreshCycle();
      } catch (err) {
        setGenError(apiErrorMessage(err));
        return;
      }
    }

    if (runIdToUse == null || isNaN(Number(runIdToUse))) {
      setGenError("Unable to initialize or find a valid department scheduling cycle. Please ensure subjects are uploaded.");
      return;
    }

    setGenerating(true);
    setGenError(null);
    setGenSuccess(null);
    setGenWarnings([]);

    try {
      const res = await generateSections(Number(runIdToUse));
      setGenSuccess(
        `Generated ${res.generated_count} section instance(s) across active semesters! (Cleared ${res.cleared_count} previous sections).`
      );
      setGenWarnings(res.warnings || []);
      setSectionsCount(res.generated_count);
      if (refreshCycle) refreshCycle();
    } catch (err) {
      setGenError(apiErrorMessage(err));
    } finally {
      setGenerating(false);
    }
  }

  async function handleRunSolver() {
    let runIdToUse = internalRunId != null ? internalRunId : (currentRunId != null ? currentRunId : activeRunId);
    if (runIdToUse == null || isNaN(Number(runIdToUse))) {
      setSolveError("No cycle run initialized. Click 'Generate Sections' first.");
      return;
    }

    setSolving(true);
    setProgress(15);
    setSolveError(null);
    setSolveResult(null);

    // Progress animation
    const timer = setInterval(() => {
      setProgress(p => (p < 85 ? p + Math.floor(Math.random() * 12) + 6 : p));
    }, 200);

    try {
      const res = await runSolve(runIdToUse, timeLimit);
      clearInterval(timer);
      setProgress(100);
      setSolveResult(res);
      if (refreshCycle) refreshCycle();
    } catch (err) {
      clearInterval(timer);
      setSolveError(apiErrorMessage(err));
    } finally {
      setSolving(false);
    }
  }

  async function handleCheckFeasibility() {
    const runIdToUse = internalRunId != null ? internalRunId : (currentRunId != null ? currentRunId : activeRunId);
    if (runIdToUse == null || isNaN(Number(runIdToUse))) {
      setSolveError("No cycle run initialized. Generate sections first.");
      return;
    }
    setCheckingFeasibility(true);
    setSolveError(null);
    setFeasibilityResult(null);
    try {
      const result = await checkFeasibility(Number(runIdToUse), timeLimit);
      setFeasibilityResult(result);
    } catch (err) {
      setSolveError(apiErrorMessage(err));
    } finally {
      setCheckingFeasibility(false);
    }
  }

  const isReady = subjectsCount > 0 && studentsCount > 0 && teachersCount > 0;

  return (
    <div>
      <PageHeader
        title="Department Timetable Solver"
        sub="Configure and execute the Google OR-Tools CP-SAT constraint optimization engine for all active semesters."
      />

      <CycleBanner
        cycleStatus={cycleStatus}
        onInitializeCycle={handleInitCycle}
        onNavigate={setPage}
      />

      <InfoBox title="CP-SAT Department Optimization Priorities">
        The solver executes a unified department-wide optimization across all active semesters:
        <ol style={{ margin: "6px 0 0", paddingLeft: 20 }}>
          <li><strong>Hard Constraints:</strong> Section capacities, teacher availability, cross-semester teacher no-clash, student no-clash.</li>
          <li><strong>3-Hour Subjects:</strong> Accurately represented as 1 linked 2-hour meeting + 1 linked 1-hour remainder occupying a sub-slot interval (09:00–10:00 or 10:00–11:00) with physical slot compatibility.</li>
          <li><strong>Student Time Preferences:</strong> Maximizes student schedule satisfaction across preferred timeslots.</li>
          <li><strong>Faculty Preferences:</strong> Secondary tie-breaker for eligible faculty.</li>
          <li><strong>Teacher Load Balance:</strong> Minimizes teaching load spread across faculty.</li>
        </ol>
      </InfoBox>

      {/* Preflight Checklist Card */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14 }}>Solver Preflight Readiness</div>
            <div style={{ fontSize: 12, color: "#777" }}>
              Verifies whether catalog data, student cohorts, and faculty availability are ready for solving.
            </div>
          </div>
          <button
            onClick={checkPreflight}
            disabled={preflightLoading}
            style={{
              padding: "4px 10px",
              background: "#f1efe8",
              border: "1px solid #d1cfc7",
              borderRadius: 6,
              fontSize: 11,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            {preflightLoading ? "Checking…" : "↻ Refresh Preflight"}
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10, marginBottom: 14 }}>
          {[
            {
              label: "Semester Subjects",
              val: `${subjectsCount} subjects`,
              ready: subjectsCount > 0,
              page: "admin-subjects",
            },
            {
              label: "Cohort Students",
              val: `${studentsCount} students`,
              ready: studentsCount > 0,
              page: "admin-students",
            },
            {
              label: "Faculty Members",
              val: `${teachersCount} teachers`,
              ready: teachersCount > 0,
              page: "admin-teachers",
            },
            {
              label: "Generated Sections",
              val: `${sectionsCount} sections`,
              ready: sectionsCount > 0,
              page: null,
            },
          ].map(item => (
            <div
              key={item.label}
              style={{
                background: item.ready ? "#F7FAF4" : "#FFF9F5",
                border: item.ready ? "1px solid #C0DD97" : "1px solid #F5C7A9",
                borderRadius: 8,
                padding: "10px 12px",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 11, color: "#666", fontWeight: 600 }}>{item.label}</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: item.ready ? "#27500A" : "#BA7517" }}>
                  {item.ready ? "✓ Ready" : "⚠ Missing"}
                </span>
              </div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#222", marginTop: 4 }}>
                {item.val}
              </div>
              {item.page && setPage && !item.ready && (
                <div
                  onClick={() => setPage(item.page)}
                  style={{ fontSize: 11, color: "#185FA5", marginTop: 4, cursor: "pointer", textDecoration: "underline" }}
                >
                  Configure {item.label} →
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Section Generation Action */}
        <div style={{
          background: "#F4F8FC",
          border: "1px solid #B5D4F4",
          borderRadius: 8,
          padding: "12px 14px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 10,
        }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 13, color: "#0C447C" }}>
              Section Instance Generation
            </div>
            <div style={{ fontSize: 11, color: "#555", marginTop: 2 }}>
              Builds concrete theory and parallel lab section objects based on subject catalog and student choices. (Idempotent: safe to re-run).
            </div>
          </div>
          <button
            onClick={handleGenerateSections}
            disabled={generating || subjectsCount === 0}
            style={{
              padding: "7px 16px",
              background: generating || subjectsCount === 0 ? "#aaa" : "#185FA5",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: generating || subjectsCount === 0 ? "not-allowed" : "pointer",
            }}
          >
            {generating ? "Generating…" : "Generate Sections"}
          </button>
        </div>

        {genSuccess && (
          <div style={{ background: "#EAF3DE", border: "1px solid #C0DD97", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#27500A", marginTop: 10 }}>
            ✓ {genSuccess}
          </div>
        )}
        {genError && (
          <div style={{ background: "#FCEBEB", border: "1px solid #F7C1C1", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#791F1F", marginTop: 10 }}>
            ✕ {genError}
          </div>
        )}
        {genWarnings.length > 0 && (
          <div style={{ background: "#FAEEDA", border: "1px solid #FAC775", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#633806", marginTop: 10 }}>
            <strong>Warnings during generation:</strong>
            <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
              {genWarnings.map((w, idx) => (
                <li key={idx}>{w.subject_code ? `[${w.subject_code}] ` : ""}{w.message}</li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      {/* Solver Execution Card */}
      <Card>
        <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 4 }}>
          Execute CP-SAT Solver
        </div>
        <div style={{ fontSize: 12, color: "#777", marginBottom: 14 }}>
          Runs the CP-SAT optimization engine for the department cycle (Run #{currentRunId || "—"}).
        </div>

        {/* Solver Configuration */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: "#444" }}>
            Solver Time Limit:
          </label>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <input
              type="number"
              min="5"
              max="3600"
              step="5"
              value={timeLimit}
              onChange={e => setTimeLimit(Number(e.target.value))}
              style={{
                width: 76,
                padding: "6px 8px",
                border: "1px solid #ccc",
                borderRadius: 6,
                fontSize: 13,
                fontWeight: 600,
              }}
            />
            <span style={{ fontSize: 12, color: "#888" }}>seconds (up to 3600s / 1 hr)</span>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              {[
                { label: "30s", val: 30 },
                { label: "1m", val: 60 },
                { label: "5m", val: 300 },
                { label: "10m", val: 600 },
                { label: "30m", val: 1800 },
              ].map(preset => (
                <button
                  key={preset.val}
                  type="button"
                  onClick={() => setTimeLimit(preset.val)}
                  style={{
                    background: timeLimit === preset.val ? "#185FA5" : "#f1efe8",
                    color: timeLimit === preset.val ? "#fff" : "#475569",
                    border: "1px solid",
                    borderColor: timeLimit === preset.val ? "#185FA5" : "#d1cfc7",
                    borderRadius: 4,
                    padding: "3px 8px",
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: "pointer",
                    transition: "all 0.1s ease",
                  }}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Action Button */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 8 }}>
            <button
              onClick={handleCheckFeasibility}
              disabled={checkingFeasibility || solving || !isReady || sectionsCount === 0}
              style={{
                padding: "10px 20px",
                background: checkingFeasibility || solving || !isReady || sectionsCount === 0 ? "#aaa" : "#185FA5",
                color: "#fff",
                border: "none",
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 700,
                cursor: checkingFeasibility || solving || !isReady || sectionsCount === 0 ? "not-allowed" : "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                transition: "background 0.15s",
              }}
            >
              {checkingFeasibility ? "Checking Hard Constraints…" : "✓ Check Feasibility First"}
            </button>
            <button
              onClick={handleRunSolver}
              disabled={solving || !isReady}
              style={{
                padding: "10px 28px",
                background: solving || !isReady ? "#aaa" : "#1D9E75",
                color: "#fff",
                border: "none",
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 700,
                cursor: solving || !isReady ? "not-allowed" : "pointer",
                boxShadow: "0 2px 6px rgba(29, 158, 117, 0.25)",
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                transition: "background 0.15s",
              }}
            >
              <span>{solving ? "Solving Timetable…" : "▶ Run Solver"}</span>
            </button>
          </div>
          {!isReady && (
            <div style={{ fontSize: 11, color: "#791F1F", marginTop: 6 }}>
              ⚠ Please complete the missing items in the preflight checklist above before running the solver.
            </div>
          )}
        </div>

        {feasibilityResult && (
          <div style={{ background: feasibilityResult.feasible ? "#F7FAF4" : "#FCEBEB", border: `1px solid ${feasibilityResult.feasible ? "#C0DD97" : "#F7C1C1"}`, borderRadius: 8, padding: "12px 14px", fontSize: 12, marginBottom: 14, color: feasibilityResult.feasible ? "#27500A" : "#791F1F" }}>
            <strong>Feasibility check: {feasibilityResult.status}</strong>
            <span> · completed in {feasibilityResult.wall_time_seconds?.toFixed(2) || "0"}s</span>
            {feasibilityResult.warnings?.length > 0 && (
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {feasibilityResult.warnings.map((warning, index) => <li key={index}>{warning}</li>)}
              </ul>
            )}
          </div>
        )}

        {/* Progress Bar while solving */}
        {solving && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#185FA5", fontWeight: 600, marginBottom: 4 }}>
              <span>Searching for optimal timetable assignment…</span>
              <span>{progress}%</span>
            </div>
            <div style={{ background: "#f1efe8", borderRadius: 4, height: 8, overflow: "hidden" }}>
              <div style={{ height: "100%", background: "#185FA5", width: `${progress}%`, transition: "width 0.2s" }} />
            </div>
          </div>
        )}

        {/* Solver Errors */}
        {solveError && (
          <div style={{ background: "#FCEBEB", border: "1px solid #F7C1C1", borderRadius: 8, padding: "12px 14px", fontSize: 13, color: "#791F1F", marginBottom: 14 }}>
            <div style={{ fontWeight: 700 }}>✕ Solver Error:</div>
            <div style={{ marginTop: 4 }}>{solveError}</div>
          </div>
        )}

        {/* Solver Results */}
        {solveResult && (
          <div style={{
            background: solveResult.status === "OPTIMAL" || solveResult.status === "FEASIBLE" ? "#F7FAF4" : "#FFF9F5",
            border: solveResult.status === "OPTIMAL" || solveResult.status === "FEASIBLE" ? "1.5px solid #C0DD97" : "1.5px solid #FAC775",
            borderRadius: 8,
            padding: "16px",
            marginTop: 10,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 18 }}>
                  {solveResult.status === "OPTIMAL" ? "🎉" : solveResult.status === "FEASIBLE" ? "✓" : "⚠"}
                </span>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 15, color: "#222" }}>
                    Solver Result: {solveResult.status}
                  </div>
                  <div style={{ fontSize: 12, color: "#666" }}>
                    Run status: <strong>{solveResult.run_status}</strong>
                    {solveResult.status === "OPTIMAL" || solveResult.status === "FEASIBLE"
                      ? " (Results are now live)."
                      : " (No timetable was published)."}
                  </div>
                </div>
              </div>

              {setPage && (solveResult.status === "OPTIMAL" || solveResult.status === "FEASIBLE") && (
                <button
                  onClick={() => setPage("admin-timetable")}
                  style={{
                    padding: "7px 16px",
                    background: "#185FA5",
                    color: "#fff",
                    border: "none",
                    borderRadius: 6,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  View Published Timetable →
                </button>
              )}
            </div>

            <MetricsRow
              items={[
                { val: solveResult.objective_value ?? 0, label: "Objective Penalty", tip: "Total weighted penalty across time-slot, faculty preferences, and load balancing." },
                { val: `${solveResult.wall_time_seconds?.toFixed(2) || "0"}s`, label: "Solve Duration", tip: "Total execution time taken by the CP-SAT engine." },
                { val: solveResult.num_conflicts ?? 0, label: "Solver Conflicts", tip: "Internal search conflicts explored before reaching optimality." },
                { val: solveResult.sections?.length || 0, label: "Assigned Sections", tip: "Total class sections scheduled." },
              ]}
            />

            {solveResult.warnings?.length > 0 && (
              <div style={{ background: "#FAEEDA", border: "1px solid #FAC775", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#633806", marginTop: 10 }}>
                <strong>Solver Warnings:</strong>
                <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                  {solveResult.warnings.map((w, idx) => (
                    <li key={idx}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
