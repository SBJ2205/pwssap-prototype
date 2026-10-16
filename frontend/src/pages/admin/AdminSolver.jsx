import { useCallback, useEffect, useRef, useState } from "react";
import { checkFeasibility, generateSections, runSolve, getSections, getSolveResult, cancelSolve } from "../../api/runs";
import { getSubjects, getStudents, getTeachers } from "../../api/catalog";
import { initializeCycle } from "../../api/cycle";
import { apiErrorMessage } from "../../api/client";
import { Card, PageHeader, InfoBox, MetricsRow } from "../../components/ui";
import CycleBanner from "../../components/CycleBanner";

const SOLVE_STORAGE_KEY_PREFIX = "pwssap_solve_result_";

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
  const [candidateCount, setCandidateCount] = useState(1);

  // Section generation state
  const [generating, setGenerating] = useState(false);
  const [genSuccess, setGenSuccess] = useState(null);
  const [genWarnings, setGenWarnings] = useState([]);
  const [genError, setGenError] = useState(null);

  // Solver execution state
  const [solving, setSolving] = useState(false);
  const [progress, setProgress] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [solveResult, setSolveResult] = useState(() => {
    if (currentRunId != null && !isNaN(Number(currentRunId))) {
      try {
        const cached = sessionStorage.getItem(`${SOLVE_STORAGE_KEY_PREFIX}${currentRunId}`);
        return cached ? JSON.parse(cached) : null;
      } catch (e) {
        return null;
      }
    }
    return null;
  });
  const [solveError, setSolveError] = useState(null);
  const [checkingFeasibility, setCheckingFeasibility] = useState(false);
  const [feasibilityResult, setFeasibilityResult] = useState(null);

  const abortControllerRef = useRef(null);

  // Restore cached solve results when switching runs or returning from another page
  useEffect(() => {
    const runIdToUse = internalRunId != null ? internalRunId : (currentRunId != null ? currentRunId : activeRunId);
    if (runIdToUse != null && !isNaN(Number(runIdToUse))) {
      const runIdNum = Number(runIdToUse);
      // 1. Try local session storage
      try {
        const cached = sessionStorage.getItem(`${SOLVE_STORAGE_KEY_PREFIX}${runIdNum}`);
        if (cached) {
          setSolveResult(JSON.parse(cached));
          return;
        }
      } catch (e) {}

      // 2. Fallback to backend cache
      getSolveResult(runIdNum)
        .then(res => {
          if (res) {
            setSolveResult(res);
            try {
              sessionStorage.setItem(`${SOLVE_STORAGE_KEY_PREFIX}${runIdNum}`, JSON.stringify(res));
            } catch (e) {}
          }
        })
        .catch(() => {});
    }
  }, [internalRunId, currentRunId, activeRunId]);

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
    setProgress(0);
    setElapsedSeconds(0);
    setSolveError(null);
    setSolveResult(null);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    const startTime = Date.now();
    const totalLimit = Math.max(5, Number(timeLimit) || 30);

    // Realistic time-based progress updates
    const timer = setInterval(() => {
      const elapsed = Math.max(0, (Date.now() - startTime) / 1000);
      setElapsedSeconds(Math.round(elapsed));
      const rawPct = Math.min(99, (elapsed / totalLimit) * 100);
      setProgress(Math.round(rawPct));
    }, 250);

    try {
      const res = await runSolve(runIdToUse, timeLimit, candidateCount, controller.signal);
      clearInterval(timer);
      setProgress(100);
      setSolveResult(res);
      try {
        sessionStorage.setItem(`${SOLVE_STORAGE_KEY_PREFIX}${runIdToUse}`, JSON.stringify(res));
      } catch (e) {}
      if (refreshCycle) refreshCycle();
    } catch (err) {
      clearInterval(timer);
      if (err?.name === "CanceledError" || err?.name === "AbortError") {
        setSolveError("Solver execution stopped by user.");
      } else {
        setSolveError(apiErrorMessage(err));
      }
    } finally {
      clearInterval(timer);
      setSolving(false);
      abortControllerRef.current = null;
    }
  }

  async function handleStopSolve() {
    const runIdToUse = internalRunId != null ? internalRunId : (currentRunId != null ? currentRunId : activeRunId);
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    if (runIdToUse != null && !isNaN(Number(runIdToUse))) {
      try {
        await cancelSolve(Number(runIdToUse));
      } catch (e) {}
    }
    setSolving(false);
    setSolveError("Solver execution stopped by user.");
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

        {/* Candidate Solutions Selector */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: "#444" }}>
            Candidate Master TTs:
          </label>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <input
              type="number"
              min="1"
              max="10"
              step="1"
              value={candidateCount}
              onChange={e => {
                const val = parseInt(e.target.value, 10);
                setCandidateCount(isNaN(val) ? 1 : Math.max(1, Math.min(10, val)));
              }}
              style={{
                width: 58,
                padding: "6px 8px",
                border: "1px solid #ccc",
                borderRadius: 6,
                fontSize: 13,
                fontWeight: 600,
                textAlign: "center",
              }}
            />
            <span style={{ fontSize: 12, color: "#888" }}>candidates (1 to 10)</span>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              {[
                { label: "1 (Single)", val: 1 },
                { label: "3 (Balanced)", val: 3 },
                { label: "5 (Thorough)", val: 5 },
                { label: "10 (Max)", val: 10 },
              ].map(preset => (
                <button
                  key={preset.val}
                  type="button"
                  onClick={() => setCandidateCount(preset.val)}
                  style={{
                    background: candidateCount === preset.val ? "#185FA5" : "#f1efe8",
                    color: candidateCount === preset.val ? "#fff" : "#475569",
                    border: "1px solid",
                    borderColor: candidateCount === preset.val ? "#185FA5" : "#d1cfc7",
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
          <span style={{ fontSize: 11, color: "#888" }}>
            {candidateCount === 1
              ? "Recommended time: 30s–60s"
              : `Recommended time: ~${Math.max(60, candidateCount * 30)}s+ (~${Math.round(timeLimit / candidateCount)}s per candidate)`}
          </span>
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
          <div style={{
            marginBottom: 16,
            background: "#F0F7FD",
            border: "1px solid #C2DCF2",
            borderRadius: 8,
            padding: "14px 16px"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{
                  display: "inline-block",
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "#185FA5",
                }} />
                <span style={{ fontSize: 13, color: "#0C447C", fontWeight: 700 }}>
                  CP-SAT Solver in Progress: {candidateCount > 1 ? `Testing ${candidateCount} Candidate Master Schedules` : "Optimizing Department Timetable"}
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#185FA5" }}>
                  {progress}%
                </span>
                <button
                  type="button"
                  onClick={handleStopSolve}
                  style={{
                    background: "#FCEBEB",
                    color: "#A51D24",
                    border: "1px solid #F7C1C1",
                    borderRadius: 6,
                    padding: "4px 10px",
                    fontSize: 11,
                    fontWeight: 700,
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                  title="Cancel solving and stop CP-SAT search"
                >
                  ⏹ Stop Solver
                </button>
              </div>
            </div>

            {/* Smooth Progress Bar */}
            <div style={{ background: "#DCEBF7", borderRadius: 6, height: 10, overflow: "hidden", marginBottom: 8 }}>
              <div style={{
                height: "100%",
                background: "linear-gradient(90deg, #185FA5, #2B7CD3)",
                width: `${progress}%`,
                transition: "width 0.25s linear",
                borderRadius: 6,
              }} />
            </div>

            {/* Timing Diagnostics */}
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#475569", flexWrap: "wrap", gap: 8 }}>
              <span>
                ⏱ <strong>Elapsed:</strong> {elapsedSeconds}s / {timeLimit}s total
              </span>
              <span>
                ⏳ <strong>Est. Remaining:</strong> ~{Math.max(0, timeLimit - elapsedSeconds)}s
              </span>
              <span>
                📊 <strong>Budget:</strong> ~{(timeLimit / candidateCount).toFixed(1)}s per candidate
              </span>
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

            {/* Multi-Candidate Master TT Leaderboard */}
            {solveResult.candidates && solveResult.candidates.length > 1 && (
              <div style={{ marginTop: 14, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 16px" }}>
                <div style={{ fontWeight: 700, fontSize: 13, color: "#1e293b", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
                  <span>🏆 Multi-Candidate Master Timetable Leaderboard</span>
                  <span style={{ fontSize: 11, fontWeight: 500, color: "#64748b" }}>
                    (Evaluated {solveResult.candidates.length} distinct structural layouts; lowest penalty auto-published)
                  </span>
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr style={{ background: "#f8fafc", textAlign: "left", color: "#475569" }}>
                        <th style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>Candidate</th>
                        <th style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>Random Seed</th>
                        <th style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>Status</th>
                        <th style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>Objective Penalty</th>
                        <th style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>Solve Time</th>
                        <th style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>Outcome</th>
                      </tr>
                    </thead>
                    <tbody>
                      {solveResult.candidates.map((c, idx) => (
                        <tr
                          key={c.candidate_id || idx}
                          style={{
                            background: c.is_best ? "#f0fdf4" : idx % 2 === 1 ? "#fafafa" : "#fff",
                            fontWeight: c.is_best ? 600 : 400,
                          }}
                        >
                          <td style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>
                            Candidate #{c.candidate_id}
                          </td>
                          <td style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0", fontFamily: "monospace", color: "#64748b" }}>
                            {c.seed}
                          </td>
                          <td style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>
                            <span style={{
                              color: c.status === "OPTIMAL" ? "#166534" : "#854d0e",
                              background: c.status === "OPTIMAL" ? "#dcfce7" : "#fef9c3",
                              padding: "2px 6px",
                              borderRadius: 4,
                              fontSize: 11,
                              fontWeight: 700,
                            }}>
                              {c.status}
                            </span>
                          </td>
                          <td style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>
                            <strong style={{ color: c.is_best ? "#15803d" : "#0f172a" }}>
                              {c.objective_value}
                            </strong>
                          </td>
                          <td style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0", color: "#64748b" }}>
                            {c.wall_time_seconds != null ? `${Number(c.wall_time_seconds).toFixed(1)}s` : "—"}
                          </td>
                          <td style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>
                            {c.is_best ? (
                              <span style={{ color: "#166534", fontWeight: 700, display: "inline-flex", alignItems: "center", gap: 4 }}>
                                ★ Published (Best)
                              </span>
                            ) : c.status === "UNKNOWN" ? (
                              <span style={{ color: "#b45309" }}>Timed out</span>
                            ) : (
                              <span style={{ color: "#94a3b8" }}>Alternate layout</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

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
