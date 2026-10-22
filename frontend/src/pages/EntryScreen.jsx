import { useState } from "react";
import { authenticate, changeAdminPassword } from "../api/auth";
import { apiErrorMessage, setToken } from "../api/client";

const INPUT_STYLE = {
  width: "100%",
  padding: "12px 16px",
  border: "1.5px solid #d1cfc7",
  borderRadius: 10,
  fontSize: 15,
  fontFamily: "inherit",
  outline: "none",
  background: "#fff",
  color: "#222",
  boxSizing: "border-box",
  transition: "border-color 0.15s",
};

export default function EntryScreen({ onLogin }) {
  const [role, setRole] = useState("student");
  const [value, setValue] = useState("");
  const [password, setPassword] = useState("");
  const [changingAdminPassword, setChangingAdminPassword] = useState(false);
  const [currentAdminPassword, setCurrentAdminPassword] = useState("");
  const [setupToken, setSetupToken] = useState("");
  const [newAdminPassword, setNewAdminPassword] = useState("");
  const [confirmAdminPassword, setConfirmAdminPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    const input = value.trim();
    if (!input || !password) return;

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const auth = await authenticate(role, input, password);
      await onLogin(auth);
    } catch (err) {
      setError(apiErrorMessage(err) || "Could not connect to the server.");
    } finally {
      setLoading(false);
    }
  }

  async function handleAdminPasswordChange(event) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    if (newAdminPassword !== confirmAdminPassword) {
      setError("The new passwords do not match.");
      return;
    }

    setChangingPassword(true);
    try {
      const adminSession = await authenticate("admin", "admin", currentAdminPassword);
      setToken(adminSession.access_token);
      await changeAdminPassword(newAdminPassword, setupToken);
      setCurrentAdminPassword("");
      setSetupToken("");
      setNewAdminPassword("");
      setConfirmAdminPassword("");
      setPassword("");
      setSuccess("Admin password updated. Sign in with your new password.");
    } catch (err) {
      setError(apiErrorMessage(err) || "Could not update the Admin password.");
    } finally {
      setToken(null);
      setChangingPassword(false);
    }
  }

  function toggleAdminPasswordChange() {
    setChangingAdminPassword(value => !value);
    setError(null);
    setSuccess(null);
  }

  function handleRoleChange(event) {
    setRole(event.target.value);
    setChangingAdminPassword(false);
    setCurrentAdminPassword("");
    setSetupToken("");
    setNewAdminPassword("");
    setConfirmAdminPassword("");
    setError(null);
    setSuccess(null);
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "linear-gradient(135deg, #f5f4f0 0%, #eceae2 100%)",
      fontFamily: "'Inter', system-ui, sans-serif",
      padding: 24,
    }}>
      <div style={{
        width: "100%",
        maxWidth: 420,
        background: "#fff",
        borderRadius: 16,
        boxShadow: "0 4px 32px rgba(0,0,0,0.10)",
        border: "1px solid #e5e3dc",
        overflow: "hidden",
      }}>
        {/* Header */}
        <div style={{
          padding: "28px 32px 20px",
          borderBottom: "1px solid #f0efeb",
          background: "#f9f8f5",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 8,
              background: "#185FA5", display: "flex", alignItems: "center",
              justifyContent: "center", fontSize: 18,
            }}>📅</div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 17, color: "#111", letterSpacing: "-0.02em" }}>
                Preference-Weighted Student Section Assignment
              </div>
              <div style={{ fontSize: 11, color: "#888" }}>
                Department Timetable System
              </div>
            </div>
          </div>
          <p style={{ fontSize: 12, color: "#999", margin: "8px 0 0", lineHeight: 1.5 }}>
            INFT Department · VIT Mumbai · AY 2026–27
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} style={{ padding: "28px 32px" }}>
          <label style={{ display: "block", fontWeight: 600, fontSize: 14, color: "#333", marginBottom: 8 }}>
            Sign in
          </label>
          <select
            value={role}
            onChange={handleRoleChange}
            style={{ ...INPUT_STYLE, marginBottom: 12 }}
            disabled={loading}
          >
            <option value="admin">Admin</option>
            <option value="student">Student</option>
            <option value="teacher">Teacher</option>
          </select>
          <input
            autoFocus
            type="text"
            value={value}
            onChange={e => { setValue(e.target.value); setError(null); }}
            placeholder={role === "admin" ? "admin" : role === "student" ? "Roll number" : "Teacher ID"}
            style={INPUT_STYLE}
            disabled={loading}
          />
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={e => { setPassword(e.target.value); setError(null); }}
            placeholder="Password"
            style={{ ...INPUT_STYLE, marginTop: 12 }}
            disabled={loading}
          />
          <div style={{ fontSize: 11, color: "#aaa", marginTop: 7, lineHeight: 1.6 }}>
            Sign in with your role, account ID, and password. The initial Admin account is
            <code style={{ background: "#f1efe8", padding: "1px 5px", borderRadius: 3, marginLeft: 4 }}>admin</code>.
            Students use their roll number (e.g.{" "}
            <code style={{ background: "#f1efe8", padding: "1px 5px", borderRadius: 3 }}>23101C0006</code>) for the student view,
            and Teachers use their ID (e.g.{" "}
            <code style={{ background: "#f1efe8", padding: "1px 5px", borderRadius: 3 }}>T001</code>) for the teacher view.
          </div>

          {error && (
            <div style={{
              marginTop: 14,
              background: "#FCEBEB",
              border: "1px solid #F7C1C1",
              borderRadius: 8,
              padding: "10px 14px",
              fontSize: 12,
              color: "#791F1F",
              lineHeight: 1.5,
            }}>
              ✕ {error}
            </div>
          )}

          {success && (
            <div role="status" style={{
              marginTop: 14,
              background: "#E5F5EF",
              border: "1px solid #b7e4d3",
              borderRadius: 8,
              padding: "10px 14px",
              fontSize: 12,
              color: "#166534",
            }}>
              {success}
            </div>
          )}

          {!changingAdminPassword && (
            <button
              type="submit"
              disabled={loading || !value.trim() || !password}
              style={{
                marginTop: 20,
                width: "100%",
                padding: "12px 0",
                background: loading || !value.trim() || !password ? "#c5c3bb" : "#185FA5",
                color: "#fff",
                border: "none",
                borderRadius: 10,
                fontSize: 14,
                fontWeight: 600,
                cursor: loading || !value.trim() || !password ? "not-allowed" : "pointer",
                fontFamily: "inherit",
                transition: "background 0.15s",
              }}
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          )}
        </form>

        {role === "admin" && (
          <div style={{ padding: "0 32px 20px" }}>
            <button
              type="button"
              onClick={toggleAdminPasswordChange}
              style={{
                padding: 0,
                border: 0,
                background: "transparent",
                color: "#185FA5",
                fontSize: 12,
                cursor: "pointer",
                textDecoration: "underline",
              }}
            >
              {changingAdminPassword ? "Back to sign in" : "Change Admin password"}
            </button>
            {changingAdminPassword && (
              <form onSubmit={handleAdminPasswordChange} style={{ display: "grid", gap: 10, marginTop: 16 }}>
              <div style={{ fontWeight: 600, fontSize: 14, color: "#333" }}>Change Admin password</div>
              <div style={{ fontSize: 11, color: "#777", lineHeight: 1.5 }}>
                Verify the current Admin password and enter the configured setup token.
              </div>
              <input
                type="password"
                autoComplete="current-password"
                required
                value={currentAdminPassword}
                onChange={event => setCurrentAdminPassword(event.target.value)}
                placeholder="Current Admin password"
                style={INPUT_STYLE}
                disabled={changingPassword}
              />
              <input
                type="password"
                autoComplete="off"
                required
                value={setupToken}
                onChange={event => setSetupToken(event.target.value)}
                placeholder="Admin setup token"
                style={INPUT_STYLE}
                disabled={changingPassword}
              />
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                required
                value={newAdminPassword}
                onChange={event => setNewAdminPassword(event.target.value)}
                placeholder="New password (at least 8 characters)"
                style={INPUT_STYLE}
                disabled={changingPassword}
              />
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                required
                value={confirmAdminPassword}
                onChange={event => setConfirmAdminPassword(event.target.value)}
                placeholder="Confirm new password"
                style={INPUT_STYLE}
                disabled={changingPassword}
              />
              <button
                type="submit"
                disabled={changingPassword || !currentAdminPassword || !setupToken || newAdminPassword.length < 8 || !confirmAdminPassword}
                style={{
                  width: "100%",
                  padding: "12px 0",
                  background: changingPassword || !currentAdminPassword || !setupToken || newAdminPassword.length < 8 || !confirmAdminPassword ? "#c5c3bb" : "#185FA5",
                  color: "#fff",
                  border: "none",
                  borderRadius: 10,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: changingPassword || !currentAdminPassword || !setupToken || newAdminPassword.length < 8 || !confirmAdminPassword ? "not-allowed" : "pointer",
                  fontFamily: "inherit",
                }}
              >
                {changingPassword ? "Updating…" : "Update Admin password"}
              </button>
              </form>
            )}
          </div>
        )}

        {/* Role hints */}
        <div style={{
          padding: "0 32px 24px",
          display: "flex",
          gap: 8,
        }}>
          {[
            { label: "Admin", hint: "admin", color: "#185FA5", bg: "#E6F1FB" },
            { label: "Student", hint: "roll number", color: "#7F77DD", bg: "#EEEDFB" },
            { label: "Teacher", hint: "teacher ID", color: "#1D9E75", bg: "#E5F5EF" },
          ].map(({ label, hint, color, bg }) => (
            <div key={label} style={{
              flex: 1, textAlign: "center",
              background: bg, borderRadius: 8,
              padding: "8px 6px",
              border: `1px solid ${color}22`,
            }}>
              <div style={{ fontWeight: 600, fontSize: 11, color }}>{label}</div>
              <div style={{ fontSize: 10, color: "#888", marginTop: 2 }}>{hint}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
