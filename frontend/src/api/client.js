import axios from "axios";

// Env-based backend URL (Vite exposes anything prefixed VITE_ via
// import.meta.env). Falls back to localhost for local dev if unset —
// see frontend/.env for the default.
export const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const client = axios.create({ baseURL: API_BASE_URL });

// Minimal local-prototype role concept (see backend/api/deps.py). No real
// auth — every request just carries whatever role the caller last set,
// and the backend enforces it on admin-only routes.
export function setRole(role) {
  client.defaults.headers.common["X-Role"] = role;
}
