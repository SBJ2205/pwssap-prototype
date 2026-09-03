// Student preference endpoints — time-slot ratings and faculty rankings.
// Paths match the real backend (Phase 6 and Phase 7).
import { client } from "./client";

// ── Time-slot preferences ───────────────────────────────────────────────
// GET /students/{roll}/time-preferences
// Returns list: [{slot_key, day, slot_index, start_time, end_time, rating}]
export const getTimePrefs = (rollNumber) =>
  client.get(`/students/${rollNumber}/time-preferences`).then(r => {
    const list = r.data || [];
    const preferences = {};
    for (const item of list) {
      if (item.rating != null && item.rating > 0) {
        preferences[item.slot_key] = item.rating;
      }
    }
    return { roll_number: rollNumber, preferences, raw: list };
  });

// PUT /students/{roll}/time-preferences
// Body: {ratings: {slot_key: rating_int}}
// Response: {status: "saved", warnings: [...]}
export const saveTimePrefs = (rollNumber, preferences) =>
  client.put(`/students/${rollNumber}/time-preferences`, { ratings: preferences }).then(r => r.data);

// ── Faculty preferences ─────────────────────────────────────────────────
// GET /students/{roll}/rankable-subjects
// Response: [{subject_code, teachers: [{teacher_id, teacher_name}]}]
export const getRankableSubjects = (rollNumber) =>
  client.get(`/students/${rollNumber}/rankable-subjects`).then(r => r.data);

// GET /students/{roll}/faculty-preferences
// Response: {subject_code: {teacher_id: rating_int}}
export const getFacultyPrefs = (rollNumber) =>
  client.get(`/students/${rollNumber}/faculty-preferences`).then(r => ({
    roll_number: rollNumber,
    preferences: r.data || {},
  }));

// PUT /students/{roll}/faculty-preferences
// Body: {preferences: {subject_code: {teacher_id: rating_int}}}
// Response: {status: "saved"}
export const saveFacultyPrefs = (rollNumber, preferences) =>
  client.put(`/students/${rollNumber}/faculty-preferences`, { preferences }).then(r => r.data);

// ── Student timetable view (after publish) ──────────────────────────────
// GET /students/{roll}/sections
// Response: {roll_number, name, semester, timetable: [{subject_code, subject_name,
//   subject_type, section_id, section_label, teacher_id, teacher_name,
//   meetings: [{slot_key, day, start_time, end_time}]}]}
export const getStudentTimetable = (rollNumber) =>
  client.get(`/students/${rollNumber}/sections`).then(r => r.data);
