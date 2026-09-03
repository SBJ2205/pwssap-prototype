// Read-only catalog endpoints — subjects, students, teachers, timeslots.
// All paths match the real backend API (Phase 1–4 implementation).
import { client } from "./client";

// GET /subjects  →  [{subject_code, subject_name, subject_tag, semester, type, weekly_hours, capacity}]
export const getSubjects = (semester) => {
  const params = semester != null ? { semester } : {};
  return client.get("/subjects", { params }).then(r => r.data);
};

// GET /admin/subjects/tags  →  {tags: ["CORE", "PE1", ...]}
export const getSubjectTags = (semester) => {
  const params = semester != null ? { semester } : {};
  return client.get("/admin/subjects/tags", { params }).then(r => r.data);
};

// GET /admin/students/{roll_number}/choices?run_id=N  →  [{choice_column, numeric_value, tag}]
export const getStudentChoices = (rollNumber, runId) =>
  client.get(`/admin/students/${rollNumber}/choices`, { params: { run_id: runId } }).then(r => r.data);

// GET /students  →  [{roll_number, name, semester}]
export const getStudents = (semester) => {
  const params = semester != null ? { semester } : {};
  return client.get("/students", { params }).then(r => r.data);
};

// GET /teachers  →  [{teacher_id, teacher_name}]
export const getTeachers = () => client.get("/teachers").then(r => r.data);

// GET /timeslots  →  [{key, day, slot_index, start_time, end_time, allowed_types, allows_theory, allows_lab}]
export const getTimeslots = () =>
  client.get("/timeslots").then(r => {
    return (r.data || []).map(slot => {
      const allowed = slot.allowed_types || [];
      return {
        ...slot,
        allowed_types: allowed,
        allows_theory: allowed.includes("theory"),
        allows_lab: allowed.includes("lab"),
      };
    });
  });

// GET /admin/teachers/{id}/capabilities  →  {teacher_id, subject_codes: [...]}
export const getTeacherCapabilities = (teacherId) =>
  client.get(`/admin/teachers/${teacherId}/capabilities`).then(r => r.data);

// GET /admin/subjects/{code}/teachers  →  {subject_code, teacher_ids: [...]}
export const getSubjectTeachers = (subjectCode) =>
  client.get(`/admin/subjects/${subjectCode}/teachers`).then(r => r.data);

// POST /admin/subjects/import  (multipart form with CSV file)
// Returns {status, count, subjects, row_errors}
export const importSubjects = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return client.post("/admin/subjects/import", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then(r => r.data);
};

// POST /admin/students/import?run_id=N  (multipart form with CSV file)
export const importStudents = (file, runId) => {
  const fd = new FormData();
  fd.append("file", file);
  const params = runId != null ? { run_id: runId } : {};
  return client.post("/admin/students/import", fd, {
    headers: { "Content-Type": "multipart/form-data" },
    params,
  }).then(r => r.data);
};

// POST /admin/teachers/import  (multipart form with CSV file)
export const importTeachers = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return client.post("/admin/teachers/import", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then(r => r.data);
};

// Look up a single student by roll_number from a list (local utility, no extra API call).
export const findStudent = (students, rollNumber) =>
  students.find(s => s.roll_number === rollNumber) || null;

// Look up a single teacher by teacher_id from a list (local utility).
export const findTeacher = (teachers, teacherId) =>
  teachers.find(t => t.teacher_id === teacherId) || null;
