// Teacher availability and post-publication admin override endpoints.
import { client } from "./client";

// ── Teacher availability ────────────────────────────────────────────────
// GET /admin/teachers/{id}/availability
// →  [{slot_key, day, slot_index, start_time, end_time, available: bool}]
export const getTeacherAvailability = (teacherId) =>
  client.get(`/admin/teachers/${teacherId}/availability`).then(r => r.data);

// PUT /admin/teachers/{id}/availability
// body: {slots: {[slot_key]: bool}}
// →  [{slot_key, day, slot_index, start_time, end_time, available: bool}]
export const setTeacherAvailability = (teacherId, slotsMap) =>
  client.put(`/admin/teachers/${teacherId}/availability`, { slots: slotsMap })
    .then(r => r.data);

// ── Section overrides (post-publication) ────────────────────────────────
// POST /admin/sections/{id}/enroll
// body: {roll_number}
// →  {enrolled, roll_number, section_id, subject_code, warnings: [...], section}
export const enrollStudent = (sectionId, rollNumber) =>
  client.post(`/admin/sections/${sectionId}/enroll`, { roll_number: rollNumber })
    .then(r => r.data);

// DELETE /admin/sections/{id}/students/{roll}
// →  {unenrolled, roll_number, section_id, subject_code, section}
export const unenrollStudent = (sectionId, rollNumber) =>
  client.delete(`/admin/sections/${sectionId}/students/${rollNumber}`)
    .then(r => r.data);

// PUT /admin/sections/{id}/teacher
// body: {teacher_id}
// →  {teacher_id, section_id, warnings: [...], section}
export const reassignTeacher = (sectionId, teacherId) =>
  client.put(`/admin/sections/${sectionId}/teacher`, { teacher_id: teacherId })
    .then(r => r.data);

// PUT /admin/sections/{id}/capacity
// body: {capacity}
// →  {capacity, section_id, warnings: [...], section}
export const overrideCapacity = (sectionId, capacity) =>
  client.put(`/admin/sections/${sectionId}/capacity`, { capacity })
    .then(r => r.data);
