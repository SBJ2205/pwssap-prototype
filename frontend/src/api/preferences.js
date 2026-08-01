// Student preference submission: time-slot ratings and subject-scoped
// faculty rankings.
import { client } from "./client";

export const getPrefs = (studentId) => client.get(`/prefs/${studentId}`).then(r => r.data);
export const savePrefs = (studentId, prefs) =>
  client.post(`/prefs/${studentId}`, { prefs }).then(r => r.data);

export const getFacultyPrefs = (studentId) => client.get(`/faculty-prefs/${studentId}`).then(r => r.data);
export const saveFacultyPrefs = (studentId, prefs) =>
  client.post(`/faculty-prefs/${studentId}`, { prefs }).then(r => r.data);
