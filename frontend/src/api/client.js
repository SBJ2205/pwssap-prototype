import axios from "axios";

// Env-based backend URL. Falls back to localhost:8000 for local dev.
export const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const client = axios.create({ baseURL: API_BASE_URL });

// Minimal local-prototype role concept (see backend/api/deps.py). No real
// auth — every request just carries whatever role the caller set,
// and the backend enforces it on admin-only routes.
export function setRole(role) {
  client.defaults.headers.common["X-Role"] = role;
}

// Extract a human-readable error message from an axios error.
export function apiErrorMessage(err) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(d => d.msg || JSON.stringify(d)).join("; ");
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return err?.message || "Unknown error";
}
