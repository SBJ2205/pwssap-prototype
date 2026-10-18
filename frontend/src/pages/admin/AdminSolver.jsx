import { useCallback, useEffect, useRef, useState } from "react";
import {
  checkFeasibility,
  generateSections,
  runSolve,
  getSections,
  getSolveResult,
  cancelSolve,
  getSolveStatus,
  listSavedRuns,
  saveRunSnapshot,
  activateSavedRun,
  compareRuns,
  deleteSavedRun,
} from "../../api/runs";
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

  // Saved Run Snapshots & Comparison State
  const [savedSnapshots, setSavedSnapshots] = useState([]);
  const [loadingSnapshots, setLoadingSnapshots] = useState(false);
  const [snapshotActionMsg, setSnapshotActionMsg] = useState(null);
  const [selectedRunA, setSelectedRunA] = useState("");
  const [selectedRunB, setSelectedRunB] = useState("");
  const [comparisonResult, setComparisonResult] = useState(null);
  const [comparing, setComparing] = useState(false);
  const [customLabel, setCustomLabel] = useState("");
  const [savingSnapshot, setSavingSnapshot] = useState(false);

  const fetchSnapshots = useCallback(async () => {
    try {
      setLoadingSnapshots(true);
      const res = await listSavedRuns();
      const list = res?.snapshots || [];
      setSavedSnapshots(list);
      if (list.length >= 2) {
        setSelectedRunA((prev) => prev || list[1]?.snapshot_id || list[0]?.snapshot_id || "");
        setSelectedRunB((prev) => prev || list[0]?.snapshot_id || "");
      } else if (list.length === 1) {
        setSelectedRunA((prev) => prev || list[0]?.snapshot_id || "");
      }
    } catch (e) {
      console.warn("Failed fetching saved runs", e);
    } finally {
      setLoadingSnapshots(false);
    }
  }, []);

  useEffect(() => {
    fetchSnapshots();
  }, [fetchSnapshots]);

  const handleSaveSnapshot = async () => {
    const runIdToUse = internalRunId != null ? internalRunId : (currentRunId != null ? currentRunId : activeRunId);
    if (!runIdToUse) return;
    try {
      setSavingSnapshot(true);
      await saveRunSnapshot(Number(runIdToUse), customLabel.trim() || undefined);
      setCustomLabel("");
      setSnapshotActionMsg({ type: "success", text: "Timetable run snapshot saved to disk!" });
      fetchSnapshots();
    } catch (e) {
      setSnapshotActionMsg({ type: "error", text: apiErrorMessage(e, "Failed to save snapshot.") });
    } finally {
      setSavingSnapshot(false);
    }
  };

  const handleActivateSnapshot = async (snapshotId) => {
    try {
      const res = await activateSavedRun(snapshotId);
      setSnapshotActionMsg({ type: "success", text: `✓ Activated "${res.label || snapshotId}" as the live timetable!` });
      if (setActiveRunId) setActiveRunId(res.active_run_id);
      if (setInternalRunId) setInternalRunId(res.active_run_id);
      if (refreshCycle) refreshCycle();
      try {
        const diag = await getSolveResult(res.active_run_id);
        setSolveResult(diag);
      } catch (err) {}
      fetchSnapshots();
    } catch (e) {
      setSnapshotActionMsg({ type: "error", text: apiErrorMessage(e, "Failed to activate timetable.") });
    }
  };

  const handleDeleteSnapshot = async (snapshotId) => {
    if (!window.confirm(`Delete saved snapshot "${snapshotId}"?`)) return;
    try {
      await deleteSavedRun(snapshotId);
      setSnapshotActionMsg({ type: "info", text: "Snapshot deleted." });
      if (comparisonResult && (selectedRunA === snapshotId || selectedRunB === snapshotId)) {
        setComparisonResult(null);
      }
      fetchSnapshots();
    } catch (e) {
      setSnapshotActionMsg({ type: "error", text: apiErrorMessage(e, "Failed to delete snapshot.") });
    }
  };

  const handleCompare = async () => {
    if (!selectedRunA || !selectedRunB) {
      setSnapshotActionMsg({ type: "error", text: "Please select both Run A and Run B to compare." });
      return;
    }
    try {
      setComparing(true);
      const res = await compareRuns(selectedRunA, selectedRunB);
      setComparisonResult(res);
    } catch (e) {
      setSnapshotActionMsg({ type: "error", text: apiErrorMessage(e, "Comparison failed.") });
    } finally {
      setComparing(false);
    }
  };


  // A solve started elsewhere (another tab, or before this page was reloaded).
  // The backend allows only one at a time, so reattach to it instead of racing it.
  const [remoteSolve, setRemoteSolve] = useState(null);
  const wasRemoteActiveRef = useRef(false);
  const remoteActive = !!remoteSolve?.active && !solving && !checkingFeasibility;

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const st = await getSolveStatus();
        if (cancelled) return;
        setRemoteSolve(st);
        if (wasRemoteActiveRef.current && !st.active) {
          // It just finished: pull in its result.
          const rid = st.run_id ?? currentRunId;
          if (rid != null) {
            getSolveResult(Number(rid)).then(res => { if (!cancelled && res) setSolveResult(res); }).catch(() => {});
          }
          if (refreshCycle) refreshCycle();
        }
        wasRemoteActiveRef.current = !!st.active;
      } catch {
        /* backend briefly unreachable: keep last state */
      }
    }
    poll();
    const id = setInterval(poll, 3000);
    return () => { cancelled = true; clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentRunId]);

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
      fetchSnapshots();
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
            <span style={{ fontSize: 12, color: "#888" }}>seconds TOTAL, shared by all candidates (up to 3600s / 1 hr)</span>
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
              ? "Recommended for the full department: 180s+ (about 70% goes to the master timetable; the rest minimises blocked slots)"
              : `Recommended: ${Math.max(240, candidateCount * 80)}s+. About 60% of the time builds and scores ${candidateCount} candidate timetables (~${Math.round((timeLimit * 0.6) / candidateCount)}s each); the best one then gets the remaining ~${Math.round(timeLimit * 0.4)}s+`}
          </span>
        </div>

        {/* Action Button */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 8 }}>
            <button
              onClick={handleCheckFeasibility}
              disabled={checkingFeasibility || solving || remoteActive || !isReady || sectionsCount === 0}
              style={{
                padding: "10px 20px",
                background: checkingFeasibility || solving || remoteActive || !isReady || sectionsCount === 0 ? "#aaa" : "#185FA5",
                color: "#fff",
                border: "none",
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 700,
                cursor: checkingFeasibility || solving || remoteActive || !isReady || sectionsCount === 0 ? "not-allowed" : "pointer",
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
              disabled={solving || remoteActive || !isReady}
              style={{
                padding: "10px 28px",
                background: solving || remoteActive || !isReady ? "#aaa" : "#1D9E75",
                color: "#fff",
                border: "none",
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 700,
                cursor: solving || remoteActive || !isReady ? "not-allowed" : "pointer",
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

        {remoteActive && (
          <div style={{ background: "#F0F7FD", border: "1px solid #C2DCF2", borderRadius: 8, padding: "12px 14px", fontSize: 12, color: "#0C447C", marginBottom: 14, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span>
              ⏳ A <strong>{remoteSolve.kind}</strong> is already running for Run #{remoteSolve.run_id} ({Math.round(remoteSolve.elapsed_seconds)}s elapsed).
              Its result will appear here when it finishes.
            </span>
            <button
              type="button"
              onClick={() => cancelSolve(Number(remoteSolve.run_id)).catch(() => {})}
              style={{ background: "#FCEBEB", color: "#A51D24", border: "1px solid #F7C1C1", borderRadius: 6, padding: "4px 10px", fontSize: 11, fontWeight: 700, cursor: "pointer" }}
            >
              ⏹ Stop it
            </button>
          </div>
        )}

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
                📊 <strong>Budget:</strong>{" "}
                {candidateCount > 1
                  ? `Phase 1: build & score ${candidateCount} candidates (~${Math.round(timeLimit * 0.6)}s) → Phase 2: optimise the best (rest)`
                  : "single candidate, ~70% master timetable → rest student sectioning"}
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
                  {solveResult.stage1_status && (
                    <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
                      Master timetable: <strong>{solveResult.stage1_status}</strong>
                      {" · "}Student sectioning: <strong>{solveResult.stage2_status || "n/a"}</strong>
                      {" · "}OPTIMAL only when both are proven optimal
                    </div>
                  )}
                </div>
              </div>

              {setPage && (solveResult.status === "OPTIMAL" || solveResult.status === "FEASIBLE") && (
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <button
                    onClick={handleSaveSnapshot}
                    disabled={savingSnapshot}
                    style={{
                      padding: "7px 14px",
                      background: "#fff",
                      color: "#0f766e",
                      border: "1.5px solid #0f766e",
                      borderRadius: 6,
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                    title="Persist this run's assignments and diagnostics as a saved snapshot"
                  >
                    {savingSnapshot ? "Saving..." : "💾 Save Snapshot"}
                  </button>
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
                </div>
              )}
            </div>

            <MetricsRow
              items={[
                { val: solveResult.objective_value ?? 0, label: "Objective Penalty", tip: "Total weighted penalty of the delivered assignment (blocked slots 2000 each, plus time-slot, faculty and section-balance terms)." },
                { val: solveResult.blocked_placements ?? "—", label: solveResult.blocked_minimum_proven ? "Blocked Placements (proven min)" : "Blocked Placements", tip: "Students placed in a slot they blocked. 'Proven min' means no assignment of this master timetable can do better." },
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
                    (Each layout is built and scored on blocked slots only; the one with the fewest is fully optimised and auto-published)
                  </span>
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr style={{ background: "#f8fafc", textAlign: "left", color: "#475569" }}>
                        <th style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>Candidate</th>
                        <th style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>Random Seed</th>
                        <th style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>Status</th>
                        <th style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>Blocked</th>
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
                              color: c.status === "OPTIMAL" ? "#166534" : (c.status === "INFEASIBLE" || c.status === "UNKNOWN") ? "#991b1b" : "#854d0e",
                              background: c.status === "OPTIMAL" ? "#dcfce7" : (c.status === "INFEASIBLE" || c.status === "UNKNOWN") ? "#fee2e2" : "#fef9c3",
                              padding: "2px 6px",
                              borderRadius: 4,
                              fontSize: 11,
                              fontWeight: 700,
                            }}>
                              {c.status}
                            </span>
                          </td>
                          <td style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>
                            {c.blocked_placements == null
                              ? "—"
                              : c.status === "SCORED"
                                ? <span title="Quick score from a short search: an upper bound, not the final figure">≤ {c.blocked_placements}</span>
                                : `${c.blocked_placements}${c.blocked_minimum_proven ? " (proven min)" : ""}`}
                          </td>
                          <td style={{ padding: "6px 10px", borderBottom: "1px solid #e2e8f0" }}>
                            <strong style={{ color: c.is_best ? "#15803d" : "#0f172a" }}>
                              {c.status === "OPTIMAL" || c.status === "FEASIBLE" ? c.objective_value : "—"}
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
                              <span style={{ color: "#b45309" }}>Timed out before a valid layout</span>
                            ) : c.status === "INFEASIBLE" ? (
                              <span style={{ color: "#b91c1c" }}>No valid student assignment</span>
                            ) : c.status === "SCORED" ? (
                              <span style={{ color: "#94a3b8" }}>Scored only (more blocked slots)</span>
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

      {/* Saved Runs & Multi-Cycle Comparison Card */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16, color: "#0f172a", display: "flex", alignItems: "center", gap: 8 }}>
              <span>📁 Saved Timetable Runs & Academic Cycle Archive</span>
            </div>
            <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>
              Persist solved timetables to disk across Traditional (Cohort) vs. PWSSAP Elective modes and multiple semester cycles (e.g. Even [4, 6, 8] vs. Odd [3, 5, 7]). You can activate any saved run as the live published timetable or generate a side-by-side faculty comparison report.
            </div>
          </div>
          <button
            onClick={fetchSnapshots}
            disabled={loadingSnapshots}
            style={{
              padding: "6px 12px",
              background: "#f8fafc",
              border: "1px solid #cbd5e1",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            {loadingSnapshots ? "Refreshing…" : "↻ Refresh Archive"}
          </button>
        </div>

        {/* Snapshot Action Message */}
        {snapshotActionMsg && (
          <div
            style={{
              background: snapshotActionMsg.type === "error" ? "#fef2f2" : "#f0fdf4",
              border: `1px solid ${snapshotActionMsg.type === "error" ? "#fecaca" : "#bbf7d0"}`,
              borderRadius: 6,
              padding: "8px 12px",
              fontSize: 12,
              color: snapshotActionMsg.type === "error" ? "#991b1b" : "#166534",
              marginBottom: 14,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>{snapshotActionMsg.text}</span>
            <button
              onClick={() => setSnapshotActionMsg(null)}
              style={{ background: "transparent", border: "none", cursor: "pointer", fontSize: 14, color: "inherit" }}
            >
              ×
            </button>
          </div>
        )}

        {/* Quick Save Current Run Bar */}
        <div
          style={{
            background: "#f8fafc",
            border: "1px solid #e2e8f0",
            borderRadius: 8,
            padding: "12px 14px",
            marginBottom: 16,
            display: "flex",
            alignItems: "center",
            gap: 10,
            flexWrap: "wrap",
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 600, color: "#334155" }}>
            Save Current Timetable:
          </span>
          <input
            type="text"
            placeholder="Custom label (e.g. Even Sem 2026 - Elective Optimized)"
            value={customLabel}
            onChange={(e) => setCustomLabel(e.target.value)}
            style={{
              flex: 1,
              minWidth: 240,
              padding: "6px 10px",
              border: "1px solid #cbd5e1",
              borderRadius: 6,
              fontSize: 12,
            }}
          />
          <button
            onClick={handleSaveSnapshot}
            disabled={savingSnapshot || (!currentRunId && !activeRunId)}
            style={{
              padding: "6px 14px",
              background: savingSnapshot || (!currentRunId && !activeRunId) ? "#cbd5e1" : "#0f766e",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: savingSnapshot || (!currentRunId && !activeRunId) ? "not-allowed" : "pointer",
            }}
          >
            {savingSnapshot ? "Saving…" : "💾 Save Snapshot"}
          </button>
        </div>

        {/* Table of Saved Runs */}
        <div style={{ overflowX: "auto", marginBottom: 20 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ background: "#f1f5f9", textAlign: "left", color: "#475569" }}>
                <th style={{ padding: "8px 10px", borderBottom: "1px solid #cbd5e1" }}>Run Label</th>
                <th style={{ padding: "8px 10px", borderBottom: "1px solid #cbd5e1" }}>Mode</th>
                <th style={{ padding: "8px 10px", borderBottom: "1px solid #cbd5e1" }}>Semesters</th>
                <th style={{ padding: "8px 10px", borderBottom: "1px solid #cbd5e1" }}>Sections / Students</th>
                <th style={{ padding: "8px 10px", borderBottom: "1px solid #cbd5e1" }}>Blocked Slots</th>
                <th style={{ padding: "8px 10px", borderBottom: "1px solid #cbd5e1" }}>Status / Score</th>
                <th style={{ padding: "8px 10px", borderBottom: "1px solid #cbd5e1" }}>Saved At</th>
                <th style={{ padding: "8px 10px", borderBottom: "1px solid #cbd5e1", textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {savedSnapshots.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ padding: "20px", textAlign: "center", color: "#94a3b8" }}>
                    No saved snapshots yet. After running the solver or traditional baseline, click "Save Snapshot" to archive it.
                  </td>
                </tr>
              ) : (
                savedSnapshots.map((s) => {
                  const isActive = (currentRunId != null && s.run_id === Number(currentRunId)) || (activeRunId != null && s.run_id === Number(activeRunId));
                  const isElective = s.mode === "pwssap_elective" || s.mode === "elective";
                  return (
                    <tr
                      key={s.snapshot_id}
                      style={{
                        background: isActive ? "#f0fdf4" : "#fff",
                        borderBottom: "1px solid #f1f5f9",
                      }}
                    >
                      <td style={{ padding: "8px 10px", fontWeight: 600, color: "#1e293b" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <span>{s.label}</span>
                          {isActive && (
                            <span style={{
                              background: "#dcfce7",
                              color: "#166534",
                              fontSize: 10,
                              fontWeight: 700,
                              padding: "2px 6px",
                              borderRadius: 4,
                            }}>
                              ACTIVE LIVE
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: 10, color: "#94a3b8", fontFamily: "monospace" }}>{s.snapshot_id}</div>
                      </td>
                      <td style={{ padding: "8px 10px" }}>
                        <span style={{
                          background: isElective ? "#e0f2fe" : "#fef3c7",
                          color: isElective ? "#0369a1" : "#92400e",
                          padding: "2px 6px",
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 600,
                        }}>
                          {isElective ? "⚡ PWSSAP Elective" : "🏛 Traditional Cohort"}
                        </span>
                      </td>
                      <td style={{ padding: "8px 10px", color: "#334155" }}>
                        {s.semesters?.length ? `Sem ${s.semesters.join(", ")}` : "All"}
                      </td>
                      <td style={{ padding: "8px 10px", color: "#475569" }}>
                        {s.section_count} sections · {s.student_count} students
                      </td>
                      <td style={{ padding: "8px 10px" }}>
                        <span style={{
                          fontWeight: 700,
                          color: s.metrics?.blocked_placements === 0 ? "#16a34a" : (s.metrics?.blocked_placements > 0 ? "#dc2626" : "#64748b"),
                        }}>
                          {s.metrics?.blocked_placements ?? "—"}
                        </span>
                      </td>
                      <td style={{ padding: "8px 10px" }}>
                        <span style={{
                          color: s.metrics?.status === "OPTIMAL" ? "#166534" : (s.metrics?.status === "FEASIBLE" ? "#854d0e" : "#475569"),
                          fontWeight: 600,
                        }}>
                          {s.metrics?.status || "DONE"}
                        </span>
                        {s.metrics?.objective_value != null && (
                          <span style={{ fontSize: 11, color: "#64748b", marginLeft: 4 }}>
                            (pen: {s.metrics.objective_value})
                          </span>
                        )}
                      </td>
                      <td style={{ padding: "8px 10px", color: "#64748b", fontSize: 11 }}>
                        {s.created_at ? new Date(s.created_at).toLocaleString() : "—"}
                      </td>
                      <td style={{ padding: "8px 10px", textAlign: "right" }}>
                        <div style={{ display: "inline-flex", gap: 6 }}>
                          {!isActive && (
                            <button
                              onClick={() => handleActivateSnapshot(s.snapshot_id)}
                              style={{
                                padding: "4px 8px",
                                background: "#0284c7",
                                color: "#fff",
                                border: "none",
                                borderRadius: 4,
                                fontSize: 11,
                                fontWeight: 600,
                                cursor: "pointer",
                              }}
                              title="Set this saved timetable as the active published timetable"
                            >
                              Activate
                            </button>
                          )}
                          <button
                            onClick={() => handleDeleteSnapshot(s.snapshot_id)}
                            style={{
                              padding: "4px 8px",
                              background: "#fee2e2",
                              color: "#991b1b",
                              border: "none",
                              borderRadius: 4,
                              fontSize: 11,
                              fontWeight: 600,
                              cursor: "pointer",
                            }}
                            title="Delete this snapshot file from disk"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Side-by-Side Comparison Section */}
        <div style={{ borderTop: "1px solid #e2e8f0", paddingTop: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: "#1e293b", marginBottom: 4, display: "flex", alignItems: "center", gap: 6 }}>
            <span>⚖️ Side-by-Side Faculty Comparison Matrix</span>
          </div>
          <div style={{ fontSize: 12, color: "#64748b", marginBottom: 12 }}>
            Select any two saved timetable runs (for example: Traditional Cohort vs. PWSSAP Elective, or Multi-Candidate runs) to review improvements for faculty presentation.
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>Baseline (Run A):</span>
              <select
                value={selectedRunA}
                onChange={(e) => setSelectedRunA(e.target.value)}
                style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12, background: "#fff" }}
              >
                <option value="">-- Select Run A --</option>
                {savedSnapshots.map((s) => (
                  <option key={s.snapshot_id} value={s.snapshot_id}>
                    {s.label} ({s.mode === "traditional_plan" ? "Traditional" : "PWSSAP"})
                  </option>
                ))}
              </select>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>Candidate (Run B):</span>
              <select
                value={selectedRunB}
                onChange={(e) => setSelectedRunB(e.target.value)}
                style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #cbd5e1", fontSize: 12, background: "#fff" }}
              >
                <option value="">-- Select Run B --</option>
                {savedSnapshots.map((s) => (
                  <option key={s.snapshot_id} value={s.snapshot_id}>
                    {s.label} ({s.mode === "traditional_plan" ? "Traditional" : "PWSSAP"})
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={handleCompare}
              disabled={comparing || !selectedRunA || !selectedRunB}
              style={{
                padding: "6px 16px",
                background: comparing || !selectedRunA || !selectedRunB ? "#cbd5e1" : "#4338ca",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: comparing || !selectedRunA || !selectedRunB ? "not-allowed" : "pointer",
              }}
            >
              {comparing ? "Comparing…" : "Compare Runs"}
            </button>
          </div>

          {/* Comparison Result Display */}
          {comparisonResult && (
            <div style={{ background: "#f8fafc", border: "1.5px solid #cbd5e1", borderRadius: 8, padding: "14px 16px" }}>
              {/* Takeaway Highlight Box */}
              <div style={{
                background: "#f0fdf4",
                border: "1px solid #86efac",
                borderRadius: 6,
                padding: "10px 14px",
                color: "#166534",
                fontSize: 13,
                fontWeight: 600,
                marginBottom: 14,
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}>
                <span>💡 Faculty Review Takeaway:</span>
                <span>{comparisonResult.takeaway}</span>
              </div>

              {/* Comparison Matrix Table */}
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ background: "#e2e8f0", textAlign: "left", color: "#334155" }}>
                    <th style={{ padding: "8px 10px", borderBottom: "1px solid #cbd5e1" }}>Metric / Dimension</th>
                    <th style={{ padding: "8px 10px", borderBottom: "1px solid #cbd5e1" }}>
                      Run A: {comparisonResult.run_a?.label}
                    </th>
                    <th style={{ padding: "8px 10px", borderBottom: "1px solid #cbd5e1" }}>
                      Run B: {comparisonResult.run_b?.label}
                    </th>
                    <th style={{ padding: "8px 10px", borderBottom: "1px solid #cbd5e1" }}>Delta / Impact</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style={{ borderBottom: "1px solid #e2e8f0" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 600 }}>Scheduling Paradigm</td>
                    <td style={{ padding: "8px 10px" }}>{comparisonResult.run_a?.mode === "traditional_plan" ? "Traditional Cohort" : "PWSSAP Elective"}</td>
                    <td style={{ padding: "8px 10px" }}>{comparisonResult.run_b?.mode === "traditional_plan" ? "Traditional Cohort" : "PWSSAP Elective"}</td>
                    <td style={{ padding: "8px 10px", color: "#64748b" }}>—</td>
                  </tr>
                  <tr style={{ borderBottom: "1px solid #e2e8f0" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 600 }}>Semesters Covered</td>
                    <td style={{ padding: "8px 10px" }}>{comparisonResult.run_a?.semesters?.join(", ") || "All"}</td>
                    <td style={{ padding: "8px 10px" }}>{comparisonResult.run_b?.semesters?.join(", ") || "All"}</td>
                    <td style={{ padding: "8px 10px", color: "#64748b" }}>—</td>
                  </tr>
                  <tr style={{ borderBottom: "1px solid #e2e8f0" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 600 }}>Blocked Student Slots</td>
                    <td style={{ padding: "8px 10px", color: comparisonResult.run_a?.blocked_placements > 0 ? "#dc2626" : "#16a34a", fontWeight: 700 }}>
                      {comparisonResult.run_a?.blocked_placements ?? "—"}
                    </td>
                    <td style={{ padding: "8px 10px", color: comparisonResult.run_b?.blocked_placements > 0 ? "#dc2626" : "#16a34a", fontWeight: 700 }}>
                      {comparisonResult.run_b?.blocked_placements ?? "—"}
                    </td>
                    <td style={{ padding: "8px 10px", fontWeight: 700 }}>
                      {comparisonResult.deltas?.blocked_improvement_pct != null ? (
                        <span style={{ color: comparisonResult.deltas.blocked_improvement_pct > 0 ? "#16a34a" : "#dc2626" }}>
                          {comparisonResult.deltas.blocked_improvement_pct > 0 ? `▼ ${comparisonResult.deltas.blocked_improvement_pct}% reduction` : `▲ ${Math.abs(comparisonResult.deltas.blocked_improvement_pct)}% increase`}
                        </span>
                      ) : "Identical"}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: "1px solid #e2e8f0" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 600 }}>Objective Penalty Score</td>
                    <td style={{ padding: "8px 10px" }}>{comparisonResult.run_a?.objective_value ?? "—"}</td>
                    <td style={{ padding: "8px 10px" }}>{comparisonResult.run_b?.objective_value ?? "—"}</td>
                    <td style={{ padding: "8px 10px", fontWeight: 700 }}>
                      {comparisonResult.deltas?.penalty_improvement_pct != null ? (
                        <span style={{ color: comparisonResult.deltas.penalty_improvement_pct > 0 ? "#16a34a" : "#dc2626" }}>
                          {comparisonResult.deltas.penalty_improvement_pct > 0 ? `▼ ${comparisonResult.deltas.penalty_improvement_pct}% penalty reduction` : `▲ ${Math.abs(comparisonResult.deltas.penalty_improvement_pct)}% penalty increase`}
                        </span>
                      ) : "—"}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: "1px solid #e2e8f0" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 600 }}>Solve Time (Wall Clock)</td>
                    <td style={{ padding: "8px 10px" }}>{comparisonResult.run_a?.wall_time_seconds != null ? `${Number(comparisonResult.run_a.wall_time_seconds).toFixed(1)}s` : "—"}</td>
                    <td style={{ padding: "8px 10px" }}>{comparisonResult.run_b?.wall_time_seconds != null ? `${Number(comparisonResult.run_b.wall_time_seconds).toFixed(1)}s` : "—"}</td>
                    <td style={{ padding: "8px 10px", color: "#64748b" }}>—</td>
                  </tr>
                  <tr>
                    <td style={{ padding: "8px 10px", fontWeight: 600 }}>Students Enrolled</td>
                    <td style={{ padding: "8px 10px" }}>{comparisonResult.run_a?.total_students ?? "—"}</td>
                    <td style={{ padding: "8px 10px" }}>{comparisonResult.run_b?.total_students ?? "—"}</td>
                    <td style={{ padding: "8px 10px", color: "#64748b" }}>—</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
