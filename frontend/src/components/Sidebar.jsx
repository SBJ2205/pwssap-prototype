import { NAV } from "../constants";

export default function Sidebar({ role, setRole, page, setPage }) {
  return (
    <div style={{ width: 220, background: "#fff", borderRight: "1px solid #e5e3dc", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "18px 16px 12px", borderBottom: "1px solid #e5e3dc" }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>PWSSAP</div>
        <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>Section Assignment System</div>
        <div style={{ fontSize: 11, color: "#bbb", marginTop: 1 }}>VIT Mumbai · IT 2025–26</div>
      </div>
      <div style={{ padding: "12px 14px", borderBottom: "1px solid #e5e3dc" }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: "#bbb", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>Viewing as</div>
        <div style={{ display: "flex", borderRadius: 6, overflow: "hidden", border: "1px solid #e0ddd8" }}>
          {["admin", "student"].map(r => (
            <div key={r}
              onClick={() => {
                setRole(r);
                if (r === "student" && NAV.find(n => n.key === page)?.group === "Admin") {
                  setPage("prefs");
                }
              }}
              style={{
                flex: 1, textAlign: "center", padding: "5px 0", cursor: "pointer", fontSize: 12,
                fontWeight: role === r ? 600 : 400,
                background: role === r ? "#185FA5" : "#fff",
                color: role === r ? "#fff" : "#666",
              }}>
              {r === "admin" ? "Admin" : "Student"}
            </div>
          ))}
        </div>
      </div>
      {(role === "admin" ? ["Admin", "Student"] : ["Student"]).map(group => (
        <div key={group}>
          <div style={{ padding: "10px 14px 4px", fontSize: 10, fontWeight: 600, color: "#bbb", textTransform: "uppercase", letterSpacing: "0.06em" }}>{group}</div>
          {NAV.filter(n => n.group === group).map(n => (
            <div key={n.key}
              onClick={() => setPage(n.key)}
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "7px 12px", margin: "1px 6px", borderRadius: 6, cursor: "pointer",
                background: page === n.key ? "#f1efe8" : "transparent",
                fontWeight: page === n.key ? 500 : 400, fontSize: 13,
                color: page === n.key ? "#222" : "#666",
              }}>
              <div style={{ width: 7, height: 7, borderRadius: "50%", background: n.color, flexShrink: 0 }} />
              {n.label}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
