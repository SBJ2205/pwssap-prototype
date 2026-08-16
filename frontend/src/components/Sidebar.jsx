import { NAV } from "../constants";
import { useTheme } from "../context/ThemeContext";

export default function Sidebar({ role, name, onLogout, page, setPage }) {
  const { theme, toggleTheme } = useTheme();
  return (
    <div className="no-print" style={{ width: 220, background: "var(--bg-surface)", borderRight: "1px solid var(--border-default)", display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ padding: "18px 16px 12px", borderBottom: "1px solid var(--border-default)" }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>PWSSAP</div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>Section Assignment System</div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>VIT Mumbai · IT 2025–26</div>
      </div>
      <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border-default)" }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Logged in as</div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 500, fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{role === "admin" ? "Admin" : "Student"}</div>
          </div>
          <button onClick={onLogout}
            style={{
              padding: "4px 10px", borderRadius: 6, border: "1px solid var(--border-default)", cursor: "pointer",
              fontSize: 11, background: "var(--bg-surface)", color: "var(--text-secondary)", flexShrink: 0,
            }}>
            Log out
          </button>
        </div>
      </div>
      {(role === "admin" ? ["Admin", "Student"] : ["Student"]).map(group => (
        <div key={group}>
          <div style={{ padding: "10px 14px 4px", fontSize: 10, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>{group}</div>
          {NAV.filter(n => n.group === group).map(n => (
            <div key={n.key}
              onClick={() => setPage(n.key)}
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "7px 12px", margin: "1px 6px", borderRadius: 6, cursor: "pointer",
                background: page === n.key ? "var(--bg-surface-alt)" : "transparent",
                fontWeight: page === n.key ? 500 : 400, fontSize: 13,
                color: page === n.key ? "var(--text-primary)" : "var(--text-secondary)",
              }}>
              <div style={{ width: 7, height: 7, borderRadius: "50%", background: n.color, flexShrink: 0 }} />
              {n.label}
            </div>
          ))}
        </div>
      ))}

      <div style={{ flex: 1 }} />

      <div style={{ padding: "12px 14px", borderTop: "1px solid var(--border-default)" }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Appearance</div>
        <div style={{ display: "flex", borderRadius: 6, overflow: "hidden", border: "1px solid var(--border-subtle)" }}>
          {[
            { key: "light", label: "☀ Light" },
            { key: "dark", label: "☾ Dark" },
          ].map(({ key, label }) => (
            <div key={key}
              onClick={() => { if (theme !== key) toggleTheme(); }}
              style={{
                flex: 1, textAlign: "center", padding: "5px 0", cursor: "pointer", fontSize: 12,
                fontWeight: theme === key ? 600 : 400,
                background: theme === key ? "var(--accent-blue)" : "var(--bg-surface)",
                color: theme === key ? "var(--on-accent)" : "var(--text-secondary)",
              }}>
              {label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
