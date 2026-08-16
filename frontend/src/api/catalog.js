// Read-only "what exists" endpoints — sections (admin-only, the concrete
// teacher timetable), the student-safe subject catalog, students,
// timeslots, and which faculty teach each subject.
import { client } from "./client";

export const getSections = () => client.get("/sections").then(r => r.data);
export const getSubjects = () => client.get("/subjects").then(r => r.data);
export const getStudents = () => client.get("/students").then(r => r.data);
export const getTimeslots = () => client.get("/timeslots").then(r => r.data);
export const getFacultyBySubject = () => client.get("/faculty-by-subject").then(r => r.data);
