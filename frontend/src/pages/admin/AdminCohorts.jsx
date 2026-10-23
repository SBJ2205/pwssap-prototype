import { useCallback, useEffect, useMemo, useState } from "react";
import {
  detectClusters,
  generateTraditionalSections,
  getCohortConfig,
  getCohortStatus,
  saveCohortConfig,
  suggestClasses,
} from "../../api/cohorts";
import { initializeCycle } from "../../api/cycle";
import { apiErrorMessage } from "../../api/client";
import { Badge, Card, MetricsRow, PageHeader } from "../../components/ui";
import {
  MAX_BATCHES,
  MIN_BATCHES,
  addDivision,
  batchLabels,
  batchSizes,
  groupOf,
  localProblems,
  moveStudents,
  rebalanceGroup,
  removeDivision,
  sameSetup,
  toSavePayload,
} from "./cohortsLogic";

const normalize = (c) => ({
  class_id: c.class_id,
  class_name: c.class_name || c.class_id,
  track: c.track || null,
  track_tag: c.track_tag || null,
  student_rolls: [...(c.student_rolls || [])],
  lab_batch_count: Number(c.lab_batch_count) || 3,
});

const buttonStyle = (color, disabled) => ({
  padding: "7px 16px",
  borderRadius: 6,
  border: `1px solid ${disabled ? "#bbb" : color}`,
  background: disabled ? "#bbb" : color,
  color: "#fff",
  fontSize: 13,
  fontWeight: 600,
  cursor: disabled ? "not-allowed" : "pointer",
});
const ghostButton = {
  padding: "6px 12px",
  borderRadius: 6,
  border: "1px solid #dcdad5",
  background: "#fff",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
};

function Banner({ type, children }) {
  const palette = {
    success: ["#EAF3DE", "#27500A", "#b7e089"],
    error: ["#FCEBEB", "#791F1F", "#f7c1c1"],
    warn: ["#FDF8EE", "#633806", "#f2e2be"],
    info: ["#F0F7FF", "#0C447C", "#c8e0fc"],
  }[type];
  return (
    <div
      style={{
        padding: "10px 14px",
        borderRadius: 8,
        marginBottom: 12,
        background: palette[0],
        color: palette[1],
        border: `1px solid ${palette[2]}`,
        fontSize: 13,
      }}
    >
      {children}
    </div>
  );
}

export default function AdminCohorts({
  setPage,
  activeRun,
  activeRunId,
  setActiveRunId,
  refreshRuns,
  refreshCycle,
  cycleStatus,
}) {
  const semesters = useMemo(() => {
    if (activeRun?.semesters?.length) return activeRun.semesters;
    if (cycleStatus?.active_semesters?.length) return cycleStatus.active_semesters;
    return [4, 6];
  }, [activeRun, cycleStatus]);

  const [semester, setSemester] = useState(null);
  const [bySem, setBySem] = useState({}); // sem -> { info, saved, classes }
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null); // "save" | "generate" | "run"
  const [feedback, setFeedback] = useState(null);
  const [saveWarnings, setSaveWarnings] = useState([]);
  const [status, setStatus] = useState(null);
  const [generation, setGeneration] = useState(null);
  const [selected, setSelected] = useState({}); // class idx -> Set of rolls
  const [open, setOpen] = useState({}); // class idx -> bool
  const [moveTarget, setMoveTarget] = useState({});

  const activeSem = semester ?? semesters[0];
  const current = bySem[activeSem];

  const loadSemester = useCallback(async (sem) => {
    const [info, saved] = await Promise.all([detectClusters(sem), getCohortConfig(sem)]);
    let savedClasses = (saved.classes || []).map(normalize);
    let classes = savedClasses;
    if (classes.length === 0) {
      const suggestion = await suggestClasses(sem);
      classes = (suggestion.classes || []).map(normalize);
    }
    setBySem((prev) => ({ ...prev, [sem]: { info, saved: savedClasses, classes } }));
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all(semesters.map(loadSemester))
      .catch((err) => !cancelled && setFeedback({ type: "error", message: `Failed to load: ${apiErrorMessage(err)}` }))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [semesters, loadSemester]);

  const [statusTick, setStatusTick] = useState(0);
  const refreshStatus = useCallback(() => setStatusTick((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    const request = activeRunId == null
      ? Promise.resolve(null)
      : getCohortStatus(activeRunId).catch((err) => {
          if (!cancelled) {
            setFeedback({ type: "error", message: `Could not read run status: ${apiErrorMessage(err)}` });
          }
          return null;
        });
    request.then((s) => !cancelled && setStatus(s));
    return () => {
      cancelled = true;
    };
  }, [activeRunId, statusTick]);

  function updateClasses(sem, updater) {
    setBySem((prev) => ({ ...prev, [sem]: { ...prev[sem], classes: updater(prev[sem].classes) } }));
  }

  function patchClass(idx, patch) {
    updateClasses(activeSem, (cs) => cs.map((c, i) => (i === idx ? { ...c, ...patch } : c)));
  }

  const isDirty = (sem) => {
    const d = bySem[sem];
    return !d || d.saved.length === 0 || !sameSetup(d.classes, d.saved);
  };

  // Returns true only when the setup is now saved on the server.
  async function saveSemester(sem) {
    const d = bySem[sem];
    const problems = localProblems(d.classes, d.info.total_students);
    if (problems.length) {
      setFeedback({ type: "error", message: `Semester ${sem}: ${problems.join(" ")}` });
      return false;
    }
    try {
      const res = await saveCohortConfig(toSavePayload(sem, d.classes));
      const saved = res.config.classes.map(normalize);
      setBySem((prev) => ({ ...prev, [sem]: { ...prev[sem], saved, classes: saved } }));
      setSaveWarnings((res.warnings || []).map((w) => `Semester ${sem}: ${w}`));
      return true;
    } catch (err) {
      setFeedback({ type: "error", message: `Semester ${sem} was not saved: ${apiErrorMessage(err)}` });
      return false;
    }
  }

  async function handleSave() {
    setBusy("save");
    setFeedback(null);
    if (await saveSemester(activeSem)) {
      setFeedback({ type: "success", message: `Saved the setup for semester ${activeSem}.` });
      refreshStatus();
    }
    setBusy(null);
  }

  async function handleResetToSuggestion() {
    if (isDirty(activeSem) && !window.confirm("Discard your edits and use the suggested divisions?")) return;
    try {
      const suggestion = await suggestClasses(activeSem);
      updateClasses(activeSem, () => (suggestion.classes || []).map(normalize));
      setSelected({});
    } catch (err) {
      setFeedback({ type: "error", message: apiErrorMessage(err) });
    }
  }

  async function handleCreateRun() {
    setBusy("run");
    try {
      const res = await initializeCycle();
      if (refreshRuns) await refreshRuns();
      if (setActiveRunId && res?.run_id != null) setActiveRunId(res.run_id);
      if (refreshCycle) refreshCycle();
      setFeedback({ type: "success", message: `Run #${res.run_id} is ready.` });
    } catch (err) {
      setFeedback({ type: "error", message: `Could not create a run: ${apiErrorMessage(err)}` });
    }
    setBusy(null);
  }

  async function handleGenerate() {
    if (activeRunId == null) {
      setFeedback({ type: "error", message: "Create or select a run first." });
      return;
    }
    setFeedback(null);
    setGeneration(null);
    setBusy("generate");
    try {
      // Save every semester of the run first; never generate from a setup that failed to save.
      for (const sem of semesters) {
        if (isDirty(sem) && !(await saveSemester(sem))) return;
      }
      if (status?.mode === "standard" && !window.confirm(
        "This run currently has standard (preference-weighted) sections. Generating traditional sections replaces them. Continue?"
      )) return;
      if (status?.solved && !window.confirm("This run is already solved. Regenerating resets it to unsolved. Continue?")) return;

      const res = await generateTraditionalSections(activeRunId);
      setGeneration(res);
      setFeedback({
        type: "success",
        message: `Generated ${res.generated_count} sections and pinned ${res.students_pinned} students to their division and batch.`,
      });
      if (refreshRuns) refreshRuns();
      if (refreshCycle) refreshCycle();
      refreshStatus();
    } catch (err) {
      setFeedback({ type: "error", message: `Section generation failed: ${apiErrorMessage(err)}` });
    } finally {
      setBusy(null);
    }
  }

  function toggleRoll(idx, roll) {
    setSelected((prev) => {
      const next = new Set(prev[idx] || []);
      if (next.has(roll)) next.delete(roll);
      else next.add(roll);
      return { ...prev, [idx]: next };
    });
  }

  function handleMove(idx) {
    const target = moveTarget[idx];
    const rolls = [...(selected[idx] || [])];
    if (target === undefined || target === "" || rolls.length === 0) return;
    const { classes, error } = moveStudents(current.classes, rolls, Number(target));
    if (error) {
      setFeedback({ type: "error", message: error });
      return;
    }
    updateClasses(activeSem, () => classes);
    setSelected((prev) => ({ ...prev, [idx]: new Set() }));
    setFeedback(null);
  }

  function handleAdd(group) {
    const trackTag = current.info.track_tag;
    updateClasses(activeSem, (cs) => addDivision(cs, group, trackTag));
  }

  function handleRemove(idx) {
    const { classes, error } = removeDivision(current.classes, idx);
    if (error) {
      setFeedback({ type: "error", message: error });
      return;
    }
    updateClasses(activeSem, () => classes);
    setSelected({});
    setOpen({});
    setFeedback(null);
  }

  if (loading || !current) {
    return (
      <div style={{ padding: "32px 40px" }}>
        <PageHeader title="Classes & Batches" sub="Loading semester rosters and elective tracks..." />
        {feedback && <Banner type={feedback.type}>{feedback.message}</Banner>}
      </div>
    );
  }

  const { info, classes } = current;
  const totalBatches = classes.reduce((s, c) => s + (Number(c.lab_batch_count) || 0), 0);
  const placed = classes.reduce((s, c) => s + c.student_rolls.length, 0);
  const problems = localProblems(classes, info.total_students);
  const dirty = isDirty(activeSem);
  const runSemesters = semesters.join(", ");
  const unsavedElsewhere = semesters.filter((s) => s !== activeSem && isDirty(s));
  const generating = busy === "generate";

  const groups = [];
  classes.forEach((c, i) => {
    const key = groupOf(c);
    if (!groups.length || groups[groups.length - 1].key !== key) groups.push({ key, idxs: [] });
    groups[groups.length - 1].idxs.push(i);
  });

  return (
    <div style={{ padding: "32px 40px", maxWidth: 1100, margin: "0 auto" }}>
      <PageHeader
        title="Classes & Batches (Traditional mode)"
        sub="Fixed divisions for theory and fixed lab batches for labs, as an alternative to preference-weighted sectioning."
      />

      {/* Run */}
      <Card>
        {activeRun ? (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <div style={{ fontSize: 13 }}>
              <b>Run #{activeRun.id}</b> covers semesters {runSemesters}
              {status && (
                <>
                  {" "}
                  <Badge color={status.mode === "traditional" ? "green" : status.mode === "standard" ? "amber" : "blue"}>
                    {status.mode === "traditional"
                      ? "Traditional sections"
                      : status.mode === "standard"
                        ? "Standard sections"
                        : "No sections yet"}
                  </Badge>{" "}
                  <Badge color={status.solved ? "green" : "amber"}>{status.solved ? "Solved" : "Not solved yet"}</Badge>
                </>
              )}
            </div>
            <button style={ghostButton} onClick={refreshStatus}>Refresh status</button>
          </div>
        ) : (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontSize: 13, color: "#633806" }}>No generation run exists yet. Traditional sections are generated inside a run.</div>
            <button style={buttonStyle("#185FA5", busy === "run")} disabled={busy === "run"} onClick={handleCreateRun}>
              {busy === "run" ? "Creating..." : "Create run"}
            </button>
          </div>
        )}
      </Card>

      {feedback && <Banner type={feedback.type}>{feedback.message}</Banner>}
      {saveWarnings.length > 0 && (
        <Banner type="warn">
          <b>Saved with notes:</b>
          <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>{saveWarnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </Banner>
      )}

      {/* Run status: generated / unsolved / validation */}
      {status && status.mode === "traditional" && (
        <Card>
          {status.stale_reason && <Banner type="warn">{status.stale_reason}</Banner>}
          {status.config_changed && (
            <Banner type="warn">The saved setup changed since these sections were generated. Generate again to apply it.</Banner>
          )}
          <div style={{ fontSize: 13, marginBottom: 8 }}>
            <b>{status.section_count}</b> sections generated, <b>{status.students_pinned}</b> students pinned to their division/batch,{" "}
            <b>{status.synchronised_groups}</b> synchronised elective group(s).
          </div>
          {!status.solved && (
            <Banner type="warn">
              <b>Not solved yet.</b> These sections have no times or teachers, and students see no timetable, until you
              run the solver.
            </Banner>
          )}
          {status.solved && status.validation && (
            status.validation.ok ? (
              <Banner type="success">
                <b>Verified.</b> No division, batch or teacher clashes, dispersal electives are synchronised, and all{" "}
                {status.validation.checked.students} students are in their saved division/batch.
                {!status.published && " (Not published.)"}
              </Banner>
            ) : (
              <Banner type="error">
                <b>{status.validation.violation_count} violation(s) found; the timetable was not published.</b>
                <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
                  {status.validation.violations.slice(0, 8).map((v, i) => (
                    <li key={i}>{v.kind}: {v.message}</li>
                  ))}
                </ul>
              </Banner>
            )
          )}
          {(status.generation_warnings || []).length > 0 && (
            <details style={{ fontSize: 12, color: "#633806", marginBottom: 8 }}>
              <summary>{status.generation_warnings.length} generation note(s)</summary>
              <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>
                {status.generation_warnings.slice(0, 20).map((w) => <li key={w}>{w}</li>)}
              </ul>
            </details>
          )}
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <button
              style={buttonStyle("#1D9E75", false)}
              onClick={() => {
                if (setActiveRunId) setActiveRunId(activeRunId);
                if (setPage) setPage("admin-solver");
              }}
            >
              Open Solver →
            </button>
            {status.solved && setPage && (
              <button style={ghostButton} onClick={() => setPage("admin-timetable")}>View published timetable</button>
            )}
            <span style={{ fontSize: 12, color: "#777" }}>
              Run the solver from its page. Do not use that page's own "Generate Sections" button: it replaces these
              with standard sections.
            </span>
          </div>
        </Card>
      )}
      {status && status.mode === "standard" && (
        <Banner type="info">
          This run currently holds standard preference-weighted sections. Generating below replaces them.
        </Banner>
      )}

      {/* Semester tabs */}
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        {semesters.map((s) => (
          <button
            key={s}
            onClick={() => { setSemester(s); setSelected({}); setOpen({}); }}
            style={{
              ...ghostButton,
              padding: "8px 18px",
              fontSize: 14,
              border: activeSem === s ? "2px solid #185FA5" : "1px solid #dcdad5",
              background: activeSem === s ? "#E6F1FB" : "#fff",
              color: activeSem === s ? "#185FA5" : "#555",
            }}
          >
            Semester {s}{isDirty(s) ? " •" : ""}
          </button>
        ))}
      </div>

      <MetricsRow
        items={[
          { val: info.total_students, label: `Students (Sem ${activeSem})` },
          { val: classes.length, label: "Divisions" },
          { val: totalBatches, label: "Lab batches" },
          {
            val: placed === info.total_students ? "All placed" : `${placed}/${info.total_students}`,
            label: placed === info.total_students ? "Coverage complete" : `${info.total_students - placed} unplaced`,
          },
        ]}
      />

      {(info.warnings || []).map((w) => <Banner key={w} type="warn">{w}</Banner>)}

      {/* How this semester's electives behave */}
      <Card>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>How semester {activeSem} is scheduled</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 13 }}>
          <div>
            <Badge color={info.has_tracks ? "blue" : "green"}>{info.has_tracks ? `${info.track_tag} tracks` : "One pool"}</Badge>{" "}
            {info.has_tracks
              ? `Students are grouped by their locked-in ${info.track_tag} track and every division stays inside one track.`
              : "No track elective: all students form one pool split into divisions."}
          </div>
          {info.dispersal_electives.map((d) => (
            <div key={d.tag}>
              <Badge color="blue">Dispersal elective ({d.tag})</Badge>{" "}
              {d.subjects.map((s) => `${s.subject_code} (${s.student_count})`).join(", ")}. {d.note}
            </div>
          ))}
          {info.in_class_electives.map((e) => (
            <div key={e.subject_code}>
              <Badge color="amber">In-class elective</Badge> <b>{e.subject_code}</b> ({e.subject_name}). {e.note}
            </div>
          ))}
        </div>
      </Card>

      {/* Actions */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", margin: "18px 0 12px" }}>
        <h3 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>
          Divisions & lab batches {dirty && <Badge color="amber">unsaved changes</Badge>}
        </h3>
        <div style={{ display: "flex", gap: 10 }}>
          <button style={ghostButton} onClick={handleResetToSuggestion}>Reset to suggestion</button>
          <button style={buttonStyle("#185FA5", busy === "save" || !dirty)} disabled={busy === "save" || !dirty} onClick={handleSave}>
            {busy === "save" ? "Saving..." : "Save setup"}
          </button>
          <button
            style={buttonStyle("#1D9E75", generating || activeRunId == null)}
            disabled={generating || activeRunId == null}
            onClick={handleGenerate}
          >
            {generating ? "Generating..." : `Save & generate sections (run #${activeRunId ?? "-"})`}
          </button>
        </div>
      </div>

      {problems.length > 0 && <Banner type="error">{problems.join(" ")}</Banner>}
      {unsavedElsewhere.length > 0 && (
        <Banner type="info">Semester(s) {unsavedElsewhere.join(", ")} also have unsaved changes; generating saves them too.</Banner>
      )}

      {groups.map((group) => {
        const groupRolls = group.idxs.reduce((s, i) => s + classes[i].student_rolls.length, 0);
        return (
          <div key={`${group.key}-${group.idxs[0]}`} style={{ marginBottom: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <b style={{ fontSize: 14 }}>{group.key === "ALL" ? "All students" : `${info.track_tag} track: ${group.key}`}</b>
              <span style={{ fontSize: 12, color: "#777" }}>{groupRolls} students in {group.idxs.length} division(s)</span>
              <button style={ghostButton} onClick={() => handleAdd(group.key)}>+ Add division (rebalances)</button>
              <button style={ghostButton} onClick={() => updateClasses(activeSem, (cs) => rebalanceGroup(cs, group.key))}>
                Rebalance evenly
              </button>
            </div>

            {group.idxs.map((idx) => {
              const cls = classes[idx];
              const sizes = batchSizes(cls.student_rolls.length, cls.lab_batch_count);
              const labels = batchLabels(cls.class_id, cls.lab_batch_count);
              const overDivision = cls.student_rolls.length > info.max_division_size;
              const overBatch = Math.max(0, ...sizes) > info.max_batch_size;
              const sel = selected[idx] || new Set();
              const siblings = group.idxs.filter((i) => i !== idx);
              return (
                <Card key={idx}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                      <input
                        value={cls.class_id}
                        onChange={(e) => patchClass(idx, { class_id: e.target.value })}
                        style={{ fontWeight: 700, fontSize: 15, width: 90, padding: "4px 8px", borderRadius: 6, border: "1px solid #ccc" }}
                      />
                      <input
                        value={cls.class_name}
                        onChange={(e) => patchClass(idx, { class_name: e.target.value })}
                        style={{ fontSize: 14, width: 230, padding: "4px 8px", borderRadius: 6, border: "1px solid #ccc" }}
                      />
                      {cls.track && <Badge color="blue">Track {cls.track}</Badge>}
                      <Badge color={overDivision ? "amber" : "green"}>
                        {cls.student_rolls.length} students{overDivision ? ` (over ${info.max_division_size})` : ""}
                      </Badge>
                    </div>
                    <button
                      onClick={() => handleRemove(idx)}
                      style={{ background: "none", border: "none", color: "#c0392b", fontSize: 12, cursor: "pointer", textDecoration: "underline" }}
                    >
                      Remove division
                    </button>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "8px 12px", background: "#f9f8f6", borderRadius: 8, marginBottom: 10, fontSize: 13 }}>
                    <label>
                      <b>Lab batches</b>{" "}
                      <select
                        value={cls.lab_batch_count}
                        onChange={(e) => patchClass(idx, { lab_batch_count: Number(e.target.value) })}
                      >
                        {Array.from({ length: MAX_BATCHES - MIN_BATCHES + 1 }, (_, k) => MIN_BATCHES + k).map((n) => (
                          <option key={n} value={n}>{n}</option>
                        ))}
                      </select>
                    </label>
                    <span style={{ color: overBatch ? "#633806" : "#555" }}>
                      {labels.map((l, i) => `${l} (${sizes[i] ?? 0})`).join(" · ")}
                      {overBatch ? `  (a batch exceeds lab capacity ${info.max_batch_size})` : ""}
                    </span>
                  </div>

                  <button style={ghostButton} onClick={() => setOpen((p) => ({ ...p, [idx]: !p[idx] }))}>
                    {open[idx] ? "Hide students" : "Manage students"}
                  </button>
                  {open[idx] && (
                    <div style={{ marginTop: 10 }}>
                      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6, fontSize: 12 }}>
                        <span>{sel.size} selected</span>
                        <select
                          value={moveTarget[idx] ?? ""}
                          onChange={(e) => setMoveTarget((p) => ({ ...p, [idx]: e.target.value }))}
                          disabled={siblings.length === 0}
                        >
                          <option value="">Move to...</option>
                          {siblings.map((i) => <option key={i} value={i}>{classes[i].class_id}</option>)}
                        </select>
                        <button style={ghostButton} disabled={sel.size === 0 || !moveTarget[idx]} onClick={() => handleMove(idx)}>
                          Move selected
                        </button>
                        {siblings.length === 0 && <span style={{ color: "#888" }}>No other division in this group to move to.</span>}
                      </div>
                      <div style={{ maxHeight: 180, overflowY: "auto", border: "1px solid #eee", borderRadius: 6, padding: 6, fontFamily: "monospace", fontSize: 12 }}>
                        {cls.student_rolls.map((roll) => (
                          <label key={roll} style={{ display: "inline-block", width: 150 }}>
                            <input type="checkbox" checked={sel.has(roll)} onChange={() => toggleRoll(idx, roll)} /> {roll}
                          </label>
                        ))}
                      </div>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        );
      })}

      {generation && (generation.warnings || []).length > 0 && (
        <Banner type="warn">
          <b>{generation.warnings.length} generation note(s):</b>
          <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>
            {generation.warnings.slice(0, 12).map((w) => <li key={w}>{w}</li>)}
          </ul>
        </Banner>
      )}
    </div>
  );
}
