// Shared, presentation-only UI primitives used across every page.
// NOTE: this file must export components only (no plain constants) so Vite's
// fast-refresh keeps working — see ../constants.js for the shared `td` style.
import { useRef, useState } from "react";

export function Card({ children }) {
  return <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-default)", borderRadius: 10, padding: "16px 20px", marginBottom: 14 }}>{children}</div>;
}

export function PageHeader({ title, sub }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h2 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>{title}</h2>
      {sub && <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "4px 0 0" }}>{sub}</p>}
    </div>
  );
}

export function MetricsRow({ items }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${items.length},1fr)`, gap: 10, marginBottom: 14 }}>
      {items.map(({ val, label, tip }) => (
        <div key={label} style={{ background: "var(--bg-surface-alt)", borderRadius: 8, padding: "12px 14px", position: "relative" }}>
          <div style={{ fontSize: 22, fontWeight: 600 }}>{val}</div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2, display: "flex", alignItems: "center", gap: 4 }}>
            {label}{tip && <Tooltip text={tip}><span style={{ cursor: "help", opacity: 0.6 }}>ⓘ</span></Tooltip>}
          </div>
        </div>
      ))}
    </div>
  );
}

export function Badge({ color, children }) {
  const colors = {
    green: { bg: "var(--rating-green-bg)", fg: "var(--rating-green-fg)" },
    blue: { bg: "var(--rating-blue-bg)", fg: "var(--rating-blue-fg)" },
    amber: { bg: "var(--rating-amber-bg)", fg: "var(--rating-amber-fg)" },
    red: { bg: "var(--rating-red-bg)", fg: "var(--rating-red-fg)" },
  };
  const c = colors[color] || colors.blue;
  return <span style={{ background: c.bg, color: c.fg, padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 500 }}>{children}</span>;
}

// ── Tooltip ───────────────────────────────────────────────────────────────
// Uses position:fixed + viewport-aware placement so it never clips off screen.
const TIP_W = 260;   // fixed tooltip width in px

export function Tooltip({ text, children }) {
  const [coords, setCoords] = useState(null); // { top, left, above }
  const triggerRef = useRef(null);

  function handleEnter() {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const above = spaceBelow < 140; // flip up if < 140px below

    // Horizontal: centre on trigger, then clamp inside viewport with 8px margin
    let left = rect.left + rect.width / 2 - TIP_W / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - TIP_W - 8));

    setCoords({
      top:   above ? rect.top - 8   : rect.bottom + 8,
      left,
      above,
    });
  }

  if (!coords) {
    return (
      <span
        ref={triggerRef}
        style={{ display: "inline-flex", alignItems: "center" }}
        onMouseEnter={handleEnter}
        onMouseLeave={() => setCoords(null)}
      >
        {children}
      </span>
    );
  }

  const bubbleStyle = {
    position: "fixed",
    top:    coords.above ? undefined : coords.top,
    bottom: coords.above ? window.innerHeight - coords.top : undefined,
    left:   coords.left,
    width:  TIP_W,
    background: "var(--tooltip-bg)",
    color: "var(--tooltip-fg)",
    fontSize: 12,
    lineHeight: 1.6,
    padding: "10px 13px",
    borderRadius: 8,
    whiteSpace: "pre-wrap",
    boxShadow: "0 6px 20px rgba(0,0,0,0.35)",
    zIndex: 9999,
    pointerEvents: "none",
    textAlign: "left",
    border: "1px solid rgba(255,255,255,0.08)",
  };

  return (
    <span
      ref={triggerRef}
      style={{ display: "inline-flex", alignItems: "center" }}
      onMouseEnter={handleEnter}
      onMouseLeave={() => setCoords(null)}
    >
      {children}
      <span style={bubbleStyle}>{text}</span>
    </span>
  );
}

// ── InfoBox ───────────────────────────────────────────────────────────────
// A pale blue callout card for page-level orientation text.
export function InfoBox({ title, children }) {
  return (
    <div style={{
      background: "var(--info-bg)", border: "1px solid var(--info-border)",
      borderRadius: 8, padding: "12px 16px", marginBottom: 14,
      fontSize: 13, color: "var(--info-title)",
    }}>
      {title && <div style={{ fontWeight: 600, marginBottom: 5, fontSize: 13 }}>ℹ {title}</div>}
      <div style={{ color: "var(--info-body)", lineHeight: 1.6 }}>{children}</div>
    </div>
  );
}

// ── Loading / error / empty states ─────────────────────────────────────────
export function LoadingState({ label = "Loading…" }) {
  return (
    <Card>
      <div style={{ color: "var(--text-muted)", fontSize: 13 }}>⏳ {label}</div>
    </Card>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <Card>
      <div style={{ color: "var(--rating-red-fg)", fontSize: 13, marginBottom: onRetry ? 10 : 0 }}>
        ✕ {message || "Something went wrong."}
      </div>
      {onRetry && (
        <button onClick={onRetry}
          style={{ padding: "6px 14px", background: "var(--rating-red-fg)", color: "var(--on-accent)", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 12, fontWeight: 500 }}>
          Retry
        </button>
      )}
    </Card>
  );
}

export function EmptyState({ title, message }) {
  return (
    <Card>
      <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
        {title && <div style={{ fontWeight: 500, marginBottom: 4, color: "var(--text-secondary)" }}>{title}</div>}
        {message}
      </div>
    </Card>
  );
}
