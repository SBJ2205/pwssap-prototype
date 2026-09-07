// Department-level cycle management API (admin-only).
import { client } from "./client";

// GET /admin/cycle  →  {active_semesters, subjects_per_semester, students_per_semester, tags_detail, current_run, ...}
export const getCycleStatus = () => client.get("/admin/cycle").then(r => r.data);

// PUT /admin/cycle/choice-tags  →  cycle status object
// configs: [{tag: str, is_choice_based: bool}] or {configs: {tag: bool}}
export const setCycleChoiceTags = (configs) =>
  client.put("/admin/cycle/choice-tags", configs).then(r => r.data);

// POST /admin/cycle/initialize  →  cycle status object with initialized current_run
export const initializeCycle = () =>
  client.post("/admin/cycle/initialize").then(r => r.data);

// POST /admin/cycle/auto-lock-in  →  {status, auto_locked_count, cycle}
export const autoLockInPending = () =>
  client.post("/admin/cycle/auto-lock-in").then(r => r.data);

