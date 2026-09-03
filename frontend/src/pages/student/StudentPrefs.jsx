import { useEffect, useState } from "react";
import { getTimePrefs, saveTimePrefs } from "../../api/preferences";
import { apiErrorMessage } from "../../api/client";
import { DAYS, SLOT_NUMBERS, SLOT_LABELS, SLOT_SHORT, RATING_META, getSlotRestriction, slotKey } from "../../constants";
import { Card, InfoBox, PageHeader } from "../../components/ui";

// Total usable slot count: Mon-1 is blocked entirely (no theory, no lab), so it
// doesn't appear as ratable. All other 19 slots are ratable.
// We keep Mon-1 visible but dimmed / not clickable, per the spec.
const TOTAL_RATABLE_SLOTS = DAYS.length * SLOT_NUMBERS.length - 1; // 20 - 1 = 19

function SlotCell({ day, slotNum, rating, disabled, restrictionType, onClick }) {
  const m = RATING_META[rating];
  const key = slotKey(day, slotNum);

  let cellBg = m.bg;
  let cellBorder = rating > 0 ? m.color : "#e0ddd8";
  let tooltip = `${day} ${SLOT_LABELS[slotNum]} — ${m.title} (click to cycle)`;

  if (disabled) {
    cellBg = "#f0efeb";
    cellBorder = "#ddd";
    tooltip = `${day} ${SLOT_LABELS[slotNum]} — restricted (no classes scheduled here)`;
  }

  if (restrictionType === "lab-only") {
    tooltip += "\n⚠ Labs only — theory is not allowed in this slot";
  }

  return (
    <div
      key={key}
      title={tooltip}
      onClick={disabled ? undefined : onClick}
      style={{
        cursor: disabled ? "default" : "pointer",
        background: cellBg,
        border: `1.5px solid ${cellBorder}`,
        borderRadius: 8,
        padding: "10px 6px",
        minHeight: 64,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 3,
        transition: "all 0.12s ease",
        userSelect: "none",
        opacity: disabled ? 0.45 : 1,
        position: "relative",
      }}
    >
      {restrictionType === "lab-only" && !disabled && (
        <div style={{
          position: "absolute", top: 3, right: 4,
          fontSize: 8, color: "#BA7517", fontWeight: 600,
          background: "#FAEEDA", borderRadius: 3, padding: "1px 3px",
        }}>
          LAB
        </div>
      )}
      <div style={{ fontSize: 18, fontWeight: 700, color: disabled ? "#bbb" : m.color, lineHeight: 1 }}>
        {disabled ? "—" : m.label}
      </div>
      <div style={{
        fontSize: 9, fontWeight: 500,
        color: disabled ? "#ccc" : m.color,
        opacity: rating === 0 ? 0.55 : 1,
      }}>
        {disabled ? "restricted" : m.pill}
      </div>
    </div>
  );
}

export default function StudentPrefs({ session }) {
  const { identity: rollNumber } = session;

  const [prefs, setPrefs]         = useState({});   // {slot_key: 1|2|3|4}
  const [loading, setLoading]     = useState(true);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState(null);
  const [saveMsg, setSaveMsg]     = useState(null);
  const [warnings, setWarnings]   = useState([]);

  // Load saved preferences on mount.
  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
     
    setError(null);
    getTimePrefs(rollNumber)
      .then(data => {
        if (!cancelled) setPrefs(data.preferences || {});
      })
      .catch(e => {
        if (!cancelled) setError(apiErrorMessage(e));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [rollNumber]);

  function cycleRating(key) {
    const cur = prefs[key] ?? 0;
    const next = cur >= 4 ? 0 : cur + 1;
    setPrefs(prev => {
      const updated = { ...prev };
      if (next === 0) delete updated[key];
      else updated[key] = next;
      return updated;
    });
    setSaveMsg(null);
  }

  // Validation: warn if the student has blocked/disliked so many slots
  // that the preference matrix is effectively useless.
  function validatePrefs(p) {
    const issues = [];
    const blocked  = Object.values(p).filter(v => v === 4).length;
    const disliked = Object.values(p).filter(v => v === 3).length;
    const rated    = Object.keys(p).length;
    const usable   = TOTAL_RATABLE_SLOTS - blocked;

    if (blocked >= TOTAL_RATABLE_SLOTS) {
      issues.push("You have blocked every available slot. The solver cannot assign you any class.");
    } else if (usable <= 2) {
      issues.push(`Only ${usable} unblocked slot(s) remaining. The solver may not be able to satisfy all subjects.`);
    } else if (blocked + disliked >= TOTAL_RATABLE_SLOTS) {
      issues.push("All available slots are either blocked or disliked. The solver will have no good options to work with.");
    } else if (rated === TOTAL_RATABLE_SLOTS && blocked === 0 && disliked === TOTAL_RATABLE_SLOTS) {
      issues.push("You have marked every slot as Disliked. The solver cannot give you a good schedule.");
    }
    return issues;
  }

  const preValidationIssues = validatePrefs(prefs);

  async function handleSave() {
    const issues = validatePrefs(prefs);
    if (issues.length > 0) {
      // Show issues but let the student confirm they still want to save.
      const confirm = window.confirm(
        "⚠ Preference issue:\n\n" + issues.join("\n") +
        "\n\nSave anyway?"
      );
      if (!confirm) return;
    }

    setSaving(true);
    setSaveMsg(null);
    setWarnings([]);
    setError(null);

    try {
      const data = await saveTimePrefs(rollNumber, prefs);
      setWarnings(data.warnings || []);
      setSaveMsg(
        data.warnings?.length > 0
          ? "Saved with warnings (see below)."
          : "Preferences saved successfully."
      );
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  const ratedCount    = Object.keys(prefs).length;
  const blockedCount  = Object.values(prefs).filter(v => v === 4).length;
  const preferredCount = Object.values(prefs).filter(v => v === 1).length;

  if (loading) return (
    <div>
      <PageHeader title="Time Preferences" sub="Loading your saved preferences…" />
      <Card><div style={{ color: "#888", fontSize: 13 }}>⏳ Loading…</div></Card>
    </div>
  );

  return (
    <div>
      <PageHeader
        title="Time Preferences"
        sub="Rate each time slot — the solver assigns your classes to slots you like most."
      />

      <InfoBox title="How does this work?">
        Mark each time slot with how suitable that time is for you:
        {" "}★ <strong>Preferred</strong> (best), ✓ <strong>Tolerable</strong> (ok),
        ↓ <strong>Disliked</strong> (inconvenient), ✕ <strong>Blocked</strong> (impossible — you have another commitment).
        Leaving a slot unrated means <strong>Indifferent</strong> (treated the same as Preferred).
        <br /><br />
        <strong style={{ color: "#633806" }}>Slot restrictions:</strong> Monday 9:00–11:00 is reserved and never assigned to students.
        The 15:45–17:45 slot is for labs only — theory is not scheduled there.
      </InfoBox>

      {error && (
        <div style={{ background: "#FCEBEB", border: "1px solid #F7C1C1", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#791F1F", marginBottom: 12 }}>
          ✕ {error}
        </div>
      )}

      {preValidationIssues.length > 0 && (
        <div style={{ background: "#FAEEDA", border: "1px solid #FAC775", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#633806", marginBottom: 12 }}>
          ⚠ {preValidationIssues.join(" · ")}
        </div>
      )}

      {saveMsg && warnings.length === 0 && (
        <div style={{ background: "#EAF3DE", border: "1px solid #C0DD97", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#27500A", marginBottom: 12 }}>
          ✓ {saveMsg}
        </div>
      )}
      {warnings.length > 0 && (
        <div style={{ background: "#FAEEDA", border: "1px solid #FAC775", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#633806", marginBottom: 12 }}>
          ⚠ Saved with warnings: {warnings.join(" · ")}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "190px 1fr", gap: 14 }}>
        {/* Left: summary + legend */}
        <div>
          <Card>
            <div style={{ fontWeight: 600, marginBottom: 10, fontSize: 13 }}>Your ratings</div>
            {[
              { label: "Preferred", val: preferredCount, color: "#27500A", bg: "#EAF3DE" },
              { label: "Rated total", val: ratedCount,   color: "#0C447C", bg: "#E6F1FB" },
              { label: "Blocked",    val: blockedCount,  color: "#791F1F", bg: "#FCEBEB" },
              { label: "Unrated",    val: TOTAL_RATABLE_SLOTS - ratedCount, color: "#888", bg: "#f1efe8" },
            ].map(({ label, val, color, bg }) => (
              <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: "#555" }}>{label}</span>
                <span style={{ fontSize: 12, fontWeight: 600, background: bg, color, padding: "1px 8px", borderRadius: 10 }}>{val}</span>
              </div>
            ))}
          </Card>

          <Card>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#555", marginBottom: 8 }}>Rating guide</div>
            {[
              { r: 0, desc: "No opinion — treated as Preferred.",   penalty: "0 pts" },
              { r: 1, desc: "Great time. Solver prioritises these.", penalty: "0 pts" },
              { r: 2, desc: "Acceptable but not ideal.",            penalty: "+1 pt"  },
              { r: 3, desc: "Inconvenient. Avoided where possible.", penalty: "+3 pts" },
              { r: 4, desc: "Cannot attend. Never assigned to you.", penalty: "N/A"   },
            ].map(({ r, desc, penalty }) => {
              const m = RATING_META[r];
              return (
                <div key={r} style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 8, paddingBottom: 8, borderBottom: "1px solid #f1efe8" }}>
                  <div style={{
                    width: 26, height: 22, borderRadius: 4, background: m.bg,
                    border: `1px solid ${r > 0 ? m.color : "#ddd"}`,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 12, fontWeight: 700, color: m.color, flexShrink: 0,
                  }}>{m.label}</div>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: m.color }}>{m.title}</div>
                    <div style={{ fontSize: 10, color: "#777", lineHeight: 1.4 }}>{desc}</div>
                    <div style={{ fontSize: 10, color: "#aaa" }}>Penalty: {penalty}</div>
                  </div>
                </div>
              );
            })}
            <div style={{ fontSize: 10, color: "#bbb", marginTop: 2 }}>Click a cell to cycle through ratings.</div>
          </Card>

          {/* Slot restriction legend */}
          <Card>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#555", marginBottom: 8 }}>Slot rules</div>
            <div style={{ fontSize: 11, color: "#777", lineHeight: 1.6 }}>
              <div style={{ marginBottom: 6 }}>
                <span style={{ background: "#f0efeb", borderRadius: 4, padding: "2px 6px", fontWeight: 600, color: "#aaa" }}>Mon 9:00</span>
                {" "}Reserved — no classes.
              </div>
              <div>
                <span style={{ background: "#FAEEDA", borderRadius: 4, padding: "2px 6px", fontWeight: 600, color: "#BA7517", fontSize: 10 }}>LAB</span>
                {" "}15:45–17:45 slot: labs only, no theory.
              </div>
            </div>
          </Card>
        </div>

        {/* Right: grid */}
        <div>
          <Card>
            <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 13 }}>Weekly Time-Slot Grid</div>
            <div style={{ fontSize: 12, color: "#888", marginBottom: 14 }}>
              Click any cell to cycle: Indifferent → Preferred → Tolerable → Disliked → Blocked → Indifferent
            </div>

            {/* Header row */}
            <div style={{ display: "grid", gridTemplateColumns: "100px repeat(5, 1fr)", gap: 4, marginBottom: 4 }}>
              <div />
              {DAYS.map(d => (
                <div key={d} style={{
                  textAlign: "center", fontSize: 12, fontWeight: 600,
                  color: "#444", padding: "6px 4px",
                  background: "#f9f8f5", borderRadius: 6,
                }}>
                  {d}
                </div>
              ))}
            </div>

            {/* Slot rows */}
            {SLOT_NUMBERS.map(slotNum => (
              <div key={slotNum} style={{ display: "grid", gridTemplateColumns: "100px repeat(5, 1fr)", gap: 4, marginBottom: 4 }}>
                {/* Row label */}
                <div style={{
                  display: "flex", flexDirection: "column", justifyContent: "center",
                  paddingRight: 8, fontSize: 11,
                }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "#555" }}>
                    {SLOT_SHORT[slotNum]}
                  </div>
                  <div style={{ fontSize: 9, color: "#aaa" }}>
                    {SLOT_LABELS[slotNum]}
                  </div>
                </div>

                {/* Day cells */}
                {DAYS.map(day => {
                  const restriction = getSlotRestriction(day, slotNum);
                  const disabled = restriction === "restricted";
                  const key = slotKey(day, slotNum);
                  const rating = prefs[key] ?? 0;
                  return (
                    <SlotCell
                      key={key}
                      day={day} slotNum={slotNum} rating={rating}
                      disabled={disabled}
                      restrictionType={restriction}
                      onClick={() => cycleRating(key)}
                    />
                  );
                })}
              </div>
            ))}
          </Card>

          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              padding: "10px 28px",
              background: saving ? "#aaa" : "#185FA5",
              color: "#fff", border: "none", borderRadius: 8,
              cursor: saving ? "not-allowed" : "pointer",
              fontSize: 13, fontWeight: 600, marginTop: 4,
              boxShadow: "0 1px 4px rgba(24,95,165,0.25)",
              fontFamily: "inherit",
            }}
          >
            {saving ? "Saving…" : "Save Preferences"}
          </button>
        </div>
      </div>
    </div>
  );
}
