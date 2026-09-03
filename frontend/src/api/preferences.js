// Student preference endpoints — time-slot ratings and faculty rankings.
// Paths match the real backend (Phase 6 and Phase 7).
import { client } from "./client";

// ── Time-slot preferences ───────────────────────────────────────────────
// GET /students/{roll}/time-preferences
// Response: {roll_number, preferences: {slot_key: rating_int}}
// rating_int: 1=preferred, 2=tolerable, 3=disliked, 4=blocked
// Missing key means unrated (indifferent).
export const getTimePrefs = (rollNumber) =>
  client.get(`/students/${rollNumber}/time-preferences`).then(r => r.data);

// POST /students/{roll}/time-preferences
// Body: {preferences: {slot_key: rating_int}}
// Response: {roll_number, saved_count, warnings: [...]}
export const saveTimePrefs = (rollNumber, preferences) =>
  client.post(`/students/${rollNumber}/time-preferences`, { preferences }).then(r => r.data);

// ── Faculty preferences ─────────────────────────────────────────────────
// GET /students/{roll}/faculty-preferences
// Response: {roll_number, preferences: {subject_code: {teacher_id: rating_int}}}
// rating_int: 1=preferred, 2=tolerable, 3=disliked  (no blocked — soft penalty only)
export const getFacultyPrefs = (rollNumber) =>
  client.get(`/students/${rollNumber}/faculty-preferences`).then(r => r.data);

// POST /students/{roll}/faculty-preferences
// Body: {preferences: {subject_code: {teacher_id: rating_int}}}
// Response: {roll_number, saved_count}
export const saveFacultyPrefs = (rollNumber, preferences) =>
  client.post(`/students/${rollNumber}/faculty-preferences`, { preferences }).then(r => r.data);

// ── Student timetable view (after publish) ──────────────────────────────
// GET /students/{roll}/sections
// Response: {roll_number, name, semester, timetable: [{subject_code, subject_name,
//   subject_type, section_id, section_label, teacher_id, teacher_name,
//   meetings: [{slot_key, day, start_time, end_time}]}]}
export const getStudentTimetable = (rollNumber) =>
  client.get(`/students/${rollNumber}/sections`).then(r => r.data);
