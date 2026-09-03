import { NAV } from "../constants";

const ROLE_META = {
  admin:   { label: "Admin",   color: "#185FA5", bg: "#E6F1FB" },
  student: { label: "Student", color: "#7F77DD", bg: "#EEEDFB" },
  teacher: { label: "Teacher", color: "#1D9E75", bg: "#E5F5EF" },
};

export default function Sidebar({ session, page, setPage, onLogout }) {
  const { role, identity } = session;
  const roleItems = NAV.filter(n => n.group === role);
  const rm = ROLE_META[role] || ROLE_META.admin;

  return (
    <div className="app-sidebar" style={{
      width: 230,
      minWidth: 230,
      background: "#fff",
      borderRight: "1px solid #e5e3dc",
      display: "flex",
      flexDirection: "column",
      height: "100vh",
      overflowY: "auto",
      flexShrink: 0,
    }}>
      {/* Branding */}
      <div style={{ padding: "18px 16px 12px", borderBottom: "1px solid #e5e3dc" }}>
        <div style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-0.02em", color: "#111" }}>
          PWSSAP
        </div>
        <div style={{ fontSize: 11, color: "#888", marginTop: 1 }}>
          Department Timetable System
        </div>
        <div style={{ fontSize: 10, color: "#bbb", marginTop: 1 }}>
          VIT Mumbai · IT 2025–26
        </div>
      </div>

      {/* Identity badge */}
      <div style={{ padding: "12px 14px", borderBottom: "1px solid #e5e3dc" }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: "#bbb", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>
          Signed in as
        </div>
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          background: rm.bg, borderRadius: 8, padding: "8px 10px",
          border: `1px solid ${rm.color}22`,
        }}>
          <div style={{
            width: 8, height: 8, borderRadius: "50%",
            background: rm.color, flexShrink: 0,
          }} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 12, color: rm.color }}>{rm.label}</div>
            <div style={{
              fontSize: 11, color: "#666",
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
            }}>
              {identity}
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <div style={{ flex: 1, paddingTop: 8 }}>
        {roleItems.map(n => (
          <div
            key={n.key}
            onClick={() => setPage(n.key)}
            style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "7px 12px", margin: "1px 6px", borderRadius: 6,
              cursor: "pointer",
              background: page === n.key ? "#f1efe8" : "transparent",
              fontWeight: page === n.key ? 600 : 400,
              fontSize: 13,
              color: page === n.key ? "#222" : "#666",
              transition: "background 0.1s",
              userSelect: "none",
            }}
          >
            <div style={{
              width: 7, height: 7, borderRadius: "50%",
              background: page === n.key ? n.color : "#ccc",
              flexShrink: 0,
            }} />
            {n.label}
          </div>
        ))}
      </div>

      {/* Logout */}
      <div style={{ padding: "10px 12px 16px", borderTop: "1px solid #e5e3dc" }}>
        <div
          onClick={onLogout}
          style={{
            padding: "7px 12px", borderRadius: 6, cursor: "pointer",
            fontSize: 12, color: "#888",
            display: "flex", alignItems: "center", gap: 6,
          }}
        >
          ← Switch identity
        </div>
      </div>
    </div>
  );
}
