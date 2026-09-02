// Solver run (admin-only server-side) and result retrieval (open to any
// caller — students read this for their own post-solve timetable).
import { client } from "./client";

export const runSolve = (payload) => client.post("/solve", payload).then(r => r.data);
export const getResults = () => client.get("/results").then(r => r.data);
