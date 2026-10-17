import { client } from "./client";

export const detectClusters = (semester) =>
  client.get("/admin/cohorts/detect-clusters", { params: { semester } }).then((r) => r.data);

export const getCohortConfig = (semester) =>
  client.get("/admin/cohorts", { params: { semester } }).then((r) => r.data);

export const saveCohortConfig = (payload) =>
  client.post("/admin/cohorts/save", payload).then((r) => r.data);

export const deleteCohortConfig = (semester) =>
  client.delete("/admin/cohorts", { params: { semester } }).then((r) => r.data);

export const generateTraditionalSections = (semester) =>
  client.post("/admin/cohorts/generate-sections", { semester }).then((r) => r.data);
