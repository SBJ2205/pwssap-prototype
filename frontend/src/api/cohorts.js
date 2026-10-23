// Traditional Division & Batch mode API (all admin-only).
import { client } from "./client";

// GET → tracks, dispersal / in-class electives, suggested sizes for a semester
export const detectClusters = (semester) =>
  client.get("/admin/cohorts/detect-clusters", { params: { semester } }).then((r) => r.data);

// GET → { semester, classes: [...] } suggested balanced divisions
export const suggestClasses = (semester) =>
  client.get("/admin/cohorts/suggest", { params: { semester } }).then((r) => r.data);

// GET → saved setup { semester, classes: [...] }
export const getCohortConfig = (semester) =>
  client.get("/admin/cohorts", { params: { semester } }).then((r) => r.data);

// POST { semester, classes } → { status, config, warnings }
export const saveCohortConfig = (payload) =>
  client.post("/admin/cohorts/save", payload).then((r) => r.data);

export const deleteCohortConfig = (semester) =>
  client.delete("/admin/cohorts", { params: { semester } }).then((r) => r.data);

// POST { run_id } → { generated_count, students_pinned, synchronised_groups, warnings, ... }
export const generateTraditionalSections = (runId) =>
  client.post("/admin/cohorts/generate-sections", { run_id: runId }).then((r) => r.data);

// GET → { mode, solved, published, validation, ... } for one run
export const getCohortStatus = (runId) =>
  client.get("/admin/cohorts/status", { params: { run_id: runId } }).then((r) => r.data);
