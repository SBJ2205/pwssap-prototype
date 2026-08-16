// Admin-only catalog management: teachers, subjects, students, and sections
// (the concrete slot-instance timetable). Every call here requires the
// X-Role: admin header (set globally via api/client.js setRole) — the
// backend rejects these with 403 for any other role. See backend/api/admin.py.
import { client } from "./client";

// ── Teachers ────────────────────────────────────────────────────────────
export const listTeachers = () => client.get("/admin/teachers").then(r => r.data);
export const createTeacher = (payload) => client.post("/admin/teachers", payload).then(r => r.data);
export const updateTeacher = (id, payload) => client.put(`/admin/teachers/${id}`, payload).then(r => r.data);
export const deleteTeacher = (id) => client.delete(`/admin/teachers/${id}`).then(r => r.data);

// ── Subjects ────────────────────────────────────────────────────────────
export const createSubject = (payload) => client.post("/admin/subjects", payload).then(r => r.data);
export const updateSubject = (code, payload) => client.put(`/admin/subjects/${code}`, payload).then(r => r.data);
export const deleteSubject = (code) => client.delete(`/admin/subjects/${code}`).then(r => r.data);

// ── Students ────────────────────────────────────────────────────────────
export const createStudent = (payload) => client.post("/admin/students", payload).then(r => r.data);
export const updateStudent = (id, payload) => client.put(`/admin/students/${id}`, payload).then(r => r.data);
export const deleteStudent = (id) => client.delete(`/admin/students/${id}`).then(r => r.data);

// ── Sections (slot instances) ──────────────────────────────────────────
export const createSection = (payload) => client.post("/admin/sections", payload).then(r => r.data);
export const updateSection = (id, payload) => client.put(`/admin/sections/${id}`, payload).then(r => r.data);
export const deleteSection = (id) => client.delete(`/admin/sections/${id}`).then(r => r.data);
