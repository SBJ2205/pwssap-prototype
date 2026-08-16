import { DAYS, PERIODS, PERIOD_LABELS, RATING_META } from "../constants";
import { Card, EmptyState, InfoBox, PageHeader } from "../components/ui";

export default function PrefsPage({ students, selStudent, setSelStudent, prefs, cycleRating, savePrefs, warnings, lockedStudentId }) {
  const visibleStudents = lockedStudentId != null ? students.filter(s => s.id === lockedStudentId) : students;
  const ratedCount  = Object.keys(prefs).length;
  const blockedCount = Object.values(prefs).filter(v => v === 4).length;
  const preferredCount = Object.values(prefs).filter(v => v === 1).length;

  return (
    <div>
      <PageHeader
        title="Set Time Preferences"
        sub="Rate each time slot of the week — not subject to subject, just time period by time period."
      />
      <InfoBox title="How does this work?">
        You <strong>don't need to know which subject</strong> will be scheduled in any slot.
        Simply mark each time period of the week based on how suitable that time is for you:
        ★ <strong>Preferred</strong> (best), ✓ <strong>Tolerable</strong> (ok), ↓ <strong>Disliked</strong> (bad),
        or ✕ <strong>Blocked</strong> (impossible — e.g. you have another commitment).
        The solver will then assign your classes to the time slots you like most.
        Leaving a slot unrated is fine — it's treated as <strong>Indifferent</strong> (same as Preferred,
        no penalty), so you can submit with as many or as few ratings as you like.
      </InfoBox>

      {students.length === 0 ? (
        <EmptyState message="No students in the roster yet — ask an admin to add students first." />
      ) : (
      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 14 }}>
        {/* Left column */}
        <div>
          <Card>
            <div style={{ fontWeight: 500, marginBottom: 10, fontSize: 13 }}>{lockedStudentId != null ? "You" : "Students"}</div>
            {visibleStudents.map(s => (
              <div key={s.id} onClick={() => setSelStudent(s.id)}
                style={{
                  padding: "8px 10px", borderRadius: 6, cursor: "pointer", marginBottom: 4,
                  background: s.id === selStudent ? "var(--rating-blue-bg)" : "var(--bg-surface-hover)",
                  border: s.id === selStudent ? "1px solid var(--select-border)" : "1px solid transparent"
                }}>
                <div style={{ fontWeight: 500, fontSize: 13 }}>{s.name}</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{s.roll}</div>
              </div>
            ))}
          </Card>

          {/* Summary stats */}
          <Card>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8 }}>Your ratings</div>
            {[
              { label: "Preferred slots",  val: preferredCount,              color: "var(--rating-green-fg)", bg: "var(--rating-green-bg)" },
              { label: "Rated total",      val: ratedCount,                  color: "var(--rating-blue-fg)", bg: "var(--rating-blue-bg)" },
              { label: "Blocked slots",    val: blockedCount,                color: "var(--rating-red-fg)", bg: "var(--rating-red-bg)" },
              { label: "Unrated slots",    val: 24 - ratedCount,             color: "var(--text-muted)",   bg: "var(--bg-surface-alt)" },
            ].map(({ label, val, color, bg }) => (
              <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{label}</span>
                <span style={{ fontSize: 12, fontWeight: 600, background: bg, color, padding: "1px 8px", borderRadius: 10 }}>{val}</span>
              </div>
            ))}
          </Card>

          {/* Legend */}
          <Card>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8, fontWeight: 500 }}>What each rating means</div>
            {[
              { r: "0", desc: "No opinion — solver treats this as Preferred.",       penalty: "0 pts" },
              { r: "1", desc: "Great time for you. Solver prioritises these.",        penalty: "0 pts" },
              { r: "2", desc: "Acceptable but not ideal.",                            penalty: "+1 pt" },
              { r: "3", desc: "Inconvenient. Solver avoids these where possible.",    penalty: "+3 pts" },
              { r: "4", desc: "Cannot attend. Never assigned to you.",                penalty: "N/A" },
            ].map(({ r, desc, penalty }) => {
              const m = RATING_META[r];
              return (
                <div key={r} style={{
                  display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 8,
                  paddingBottom: 8, borderBottom: "1px solid var(--bg-surface-alt)",
                }}>
                  <div style={{
                    width: 28, height: 22, borderRadius: 4, background: m.bg,
                    border: `1px solid ${Number(r) > 0 ? m.color : "var(--border-subtle)"}`,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 13, fontWeight: 700, color: m.color, flexShrink: 0,
                  }}>{m.label}</div>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: m.color }}>{m.title}</div>
                    <div style={{ fontSize: 10, color: "var(--text-muted)", lineHeight: 1.4 }}>{desc}</div>
                    <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Penalty: {penalty}</div>
                  </div>
                </div>
              );
            })}
            <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>Click any cell to cycle through ratings.</div>
          </Card>
        </div>

        {/* Right column: weekly grid */}
        <div>
          {warnings.length > 0 && (
            <div style={{ background: "var(--rating-amber-bg)", border: "1px solid var(--warn-border)", borderRadius: 6, padding: "10px 14px", fontSize: 13, color: "var(--rating-amber-fg)", marginBottom: 12 }}>
              ⚠ {warnings.join(" | ")}
            </div>
          )}
          {blockedCount === 0 && ratedCount > 0 && (
            <div style={{ background: "var(--rating-green-bg)", border: "1px solid var(--success-border)", borderRadius: 6, padding: "10px 14px", fontSize: 13, color: "var(--rating-green-fg)", marginBottom: 12 }}>
              ✓ Preferences look good — the solver will assign your classes to best-matching time slots.
            </div>
          )}

          <Card>
            <div style={{ fontWeight: 500, marginBottom: 4 }}>Weekly Time-Slot Grid</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 14 }}>
              Click any cell to cycle through ratings. The system will automatically assign your classes to slots you prefer.
            </div>

            {/* Grid header: days */}
            <div style={{ display: "grid", gridTemplateColumns: "80px repeat(6, 1fr)", gap: 4, marginBottom: 4 }}>
              <div />
              {DAYS.map(d => (
                <div key={d} style={{
                  textAlign: "center", fontSize: 12, fontWeight: 600,
                  color: "var(--text-secondary)", padding: "6px 4px",
                  background: "var(--bg-surface-hover)", borderRadius: 6
                }}>{d}</div>
              ))}
            </div>

            {/* Grid rows: periods */}
            {PERIODS.map(period => (
              <div key={period} style={{ display: "grid", gridTemplateColumns: "80px repeat(6, 1fr)", gap: 4, marginBottom: 4 }}>
                {/* Period label */}
                <div style={{
                  display: "flex", flexDirection: "column", justifyContent: "center",
                  paddingRight: 8, fontSize: 11, color: "var(--text-muted)", fontWeight: 500
                }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)" }}>{PERIOD_LABELS[period]}</div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Slot {PERIODS.indexOf(period) + 1}</div>
                </div>

                {/* Day cells */}
                {DAYS.map(day => {
                  const tsKey = `${day}|${period}`;
                  const rating = prefs[tsKey] ?? 0;
                  const m = RATING_META[rating];
                  return (
                    <div
                      key={tsKey}
                      onClick={() => cycleRating(tsKey)}
                      title={`${day} ${PERIOD_LABELS[period]} — ${m.title} (click to change)`}
                      style={{
                        cursor: "pointer",
                        background: m.bg,
                        border: `1.5px solid ${rating > 0 ? m.color : "var(--border-subtle)"}`,
                        borderRadius: 8,
                        padding: "10px 6px",
                        minHeight: 62,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 4,
                        transition: "all 0.12s ease",
                        userSelect: "none",
                      }}
                    >
                      <div style={{
                        fontSize: 18,
                        fontWeight: 700,
                        color: m.color,
                        lineHeight: 1,
                      }}>{m.label}</div>
                      <div style={{
                        fontSize: 10,
                        fontWeight: 500,
                        color: m.color,
                        opacity: rating === 0 ? 0.5 : 1,
                      }}>{m.pill}</div>
                    </div>
                  );
                })}
              </div>
            ))}
          </Card>

          <button onClick={savePrefs}
            style={{
              padding: "10px 28px", background: "var(--accent-blue)", color: "var(--on-accent)",
              border: "none", borderRadius: 6, cursor: "pointer",
              fontSize: 13, fontWeight: 600, marginTop: 4,
              boxShadow: "0 1px 4px rgba(24,95,165,0.25)",
            }}>
            Save Preferences
          </button>
        </div>
      </div>
      )}
    </div>
  );
}
