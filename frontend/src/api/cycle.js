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

// GET /admin/cycle/elective-template/{semester} → CSV file download
export const downloadElectiveTemplate = async (semester) => {
  const response = await client.get(`/admin/cycle/elective-template/${semester}`, {
    responseType: "blob",
  });
  const url = window.URL.createObjectURL(new Blob([response.data], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", `semester_${semester}_elective_allocations.csv`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};

// POST /admin/cycle/import-elective-allocations → {status, updated_count, cycle}
export const importElectiveAllocations = async (file, semester = null) => {
  const formData = new FormData();
  formData.append("file", file);
  if (semester !== null && semester !== undefined) {
    formData.append("semester", semester);
  }
  const response = await client.post("/admin/cycle/import-elective-allocations", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
};


