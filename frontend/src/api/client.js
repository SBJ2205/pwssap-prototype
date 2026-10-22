import axios from "axios";

// Env-based backend URL. Uses relative URL by default so Vite proxy forwards requests
// properly whether accessed via localhost or a Cloudflare tunnel.
export const API_BASE_URL = import.meta.env.VITE_API_URL || "";

export const client = axios.create({ baseURL: API_BASE_URL });

let accessToken = null;

export function setToken(token) {
  accessToken = token;
  if (token) client.defaults.headers.common.Authorization = `Bearer ${token}`;
  else delete client.defaults.headers.common.Authorization;
}

client.interceptors.request.use(config => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});

client.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401 && !error.config?.url?.includes("/auth/login")) {
      window.dispatchEvent(new Event("pwssap:unauthorized"));
    }
    return Promise.reject(error);
  },
);

// Extract a human-readable error message from an axios error.
export function apiErrorMessage(err) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(d => d.msg || JSON.stringify(d)).join("; ");
  if (detail && typeof detail === "object") {
    if (detail.message) return detail.message;
    if (detail.errors) return Array.isArray(detail.errors) ? detail.errors.join("; ") : JSON.stringify(detail.errors);
    return JSON.stringify(detail);
  }
  return err?.message || "Unknown error";
}

// Extract raw structured error detail (e.g. { message, row_errors: [...] })
export function getApiErrorDetails(err) {
  const detail = err?.response?.data?.detail;
  if (detail && typeof detail === "object") return detail;
  return null;
}
