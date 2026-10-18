// Run management and solver endpoints (all admin-only).
// Paths match the real backend Phase 8–11 implementation.
import { client } from "./client";

// ── Runs ────────────────────────────────────────────────────────────────
// POST /admin/runs  →  {id, semester, status, choice_tag_configs: []}
export const createRun = (semester, choiceTags = []) =>
  client.post("/admin/runs", { semester, choice_tags: choiceTags }).then(r => r.data);

// GET /admin/runs  →  [{id, semester, status, choice_tag_configs}]
export const listRuns = (semester) => {
  const params = semester != null ? { semester } : {};
  return client.get("/admin/runs", { params }).then(r => r.data);
};

// GET /admin/runs/{id}  →  run object
export const getRun = (runId) =>
  client.get(`/admin/runs/${runId}`).then(r => r.data);

// PUT /admin/runs/{id}/choice-tags  →  run object
// body: [{tag: str, numeric_value: int, is_choice_based: bool}]
export const setRunChoiceTags = (runId, configs) =>
  client.put(`/admin/runs/${runId}/choice-tags`, configs).then(r => r.data);

// ── Section generation ──────────────────────────────────────────────────
// POST /admin/runs/{id}/generate-sections
// →  {run_id, cleared_count, generated_count, sections: [...], warnings: [...]}
export const generateSections = (runId) =>
  client.post(`/admin/runs/${runId}/generate-sections`).then(r => r.data);

// GET /admin/runs/{id}/sections  →  {run_id, count, sections: [...]}
export const getSections = (runId, subjectCode) => {
  const params = subjectCode ? { subject_code: subjectCode } : {};
  return client.get(`/admin/runs/${runId}/sections`, { params }).then(r => r.data);
};

// ── Solver ──────────────────────────────────────────────────────────────
// POST /admin/runs/{id}/solve  →  {status, sections: [...], warnings: [...]}
// status: "OPTIMAL" | "FEASIBLE" | "INFEASIBLE"
// After a successful solve the run transitions to PUBLISHED automatically.
export const runSolve = (runId, timeLimit, candidates, signal) => {
  const params = {
    ...(timeLimit != null ? { time_limit: timeLimit } : {}),
    ...(candidates != null ? { candidates } : {}),
  };
  return client.post(`/admin/runs/${runId}/solve`, null, { params, signal }).then(r => r.data);
};

export const getSolveResult = (runId) =>
  client.get(`/admin/runs/${runId}/solve-result`).then(r => r.data);

// GET /admin/runs/solve/status → {active: bool, run_id?, kind?, elapsed_seconds?}
export const getSolveStatus = () =>
  client.get("/admin/runs/solve/status").then(r => r.data);

export const cancelSolve = (runId) =>
  client.post(`/admin/runs/${runId}/cancel`).then(r => r.data);

// POST /admin/runs/{id}/feasibility — hard constraints only, no publication.
export const checkFeasibility = (runId, timeLimit) => {
  const params = timeLimit != null ? { time_limit: timeLimit } : {};
  return client.post(`/admin/runs/${runId}/feasibility`, null, { params }).then(r => r.data);
};

// ── Published timetable (admin) ─────────────────────────────────────────
// GET /admin/runs/{id}/summary
// →  {run_id, semester, run_status, section_count, sections: [...], weekly_grid: {day: [...]}}
export const getRunSummary = (runId) =>
  client.get(`/admin/runs/${runId}/summary`).then(r => r.data);

// ── Teacher timetable ───────────────────────────────────────────────────
// GET /teachers/{id}/timetable?run_id=N
// →  {teacher_id, teacher_name, section_count, schedule: [...]}
export const getTeacherTimetable = (teacherId, runId) => {
  const params = runId != null ? { run_id: runId } : {};
  return client.get(`/teachers/${teacherId}/timetable`, { params }).then(r => r.data);
};

export const downloadSectionRosterCsv = (teacherId, sectionId) => {
  return client.get(`/teachers/${teacherId}/sections/${sectionId}/roster.csv`, {
    responseType: "blob",
  }).then(r => r.data);
};

export const downloadTeacherTimetableCsv = (teacherId, runId) => {
  const params = runId != null ? { run_id: runId } : {};
  return client.get(`/teachers/${teacherId}/timetable.csv`, {
    params,
    responseType: "blob",
  }).then(r => r.data);
};

// ── Saved Timetables & Comparison ─────────────────────────────────────────
export const listSavedRuns = () =>
  client.get("/admin/runs/saved").then(r => r.data);

export const saveRunSnapshot = (runId, label) =>
  client.post(`/admin/runs/${runId}/save-snapshot`, { label }).then(r => r.data);

export const activateSavedRun = (snapshotId) =>
  client.post(`/admin/runs/saved/${snapshotId}/activate`).then(r => r.data);

export const compareRuns = (runA, runB) =>
  client.get("/admin/runs/compare", { params: { run_a: runA, run_b: runB } }).then(r => r.data);

export const deleteSavedRun = (snapshotId) =>
  client.delete(`/admin/runs/saved/${snapshotId}`).then(r => r.data);

