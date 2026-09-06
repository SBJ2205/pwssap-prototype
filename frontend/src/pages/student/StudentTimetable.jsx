import { useEffect, useState } from "react";
import { getStudentTimetable } from "../../api/preferences";
import { apiErrorMessage } from "../../api/client";
import { DAYS, SLOT_NUMBERS, SLOT_LABELS, SLOT_SHORT, slotKey } from "../../constants";
import { Card, EmptyState, PageHeader } from "../../components/ui";

export default function StudentTimetable({ session }) {
  const { identity: rollNumber } = session;

  const [timetable, setTimetable] = useState(null); // null = not loaded yet
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
     
    setError(null);
    getStudentTimetable(rollNumber)
      .then(data => {
        if (!cancelled) setTimetable(data);
      })
      .catch(e => {
        if (!cancelled) setError(apiErrorMessage(e));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [rollNumber]);

  if (loading) return (
    <div>
      <PageHeader title="My Timetable" />
      <Card><div style={{ color: "#888", fontSize: 13 }}>⏳ Loading timetable…</div></Card>
    </div>
  );

  if (error) return (
    <div>
      <PageHeader title="My Timetable" />
      <div style={{ background: "#FCEBEB", border: "1px solid #F7C1C1", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#791F1F" }}>
        ✕ {error}
      </div>
    </div>
  );

  const entries = timetable?.timetable || [];

  if (entries.length === 0) {
    return (
      <div>
        <PageHeader
          title="My Timetable"
          sub={`Roll number: ${rollNumber}`}
        />
        <EmptyState
          title="No timetable yet"
          message="Results are not published yet. Check back after the admin runs the solver."
        />
      </div>
    );
  }

  // Build a grid: { "Mon-1": [ { ...entry, activeMeeting: meeting } ] }
  const grid = {};
  for (const entry of entries) {
    for (const meeting of entry.meetings) {
      if (meeting.slot_key) {
        if (!grid[meeting.slot_key]) grid[meeting.slot_key] = [];
        grid[meeting.slot_key].push({ ...entry, activeMeeting: meeting });
      }
    }
  }

  return (
    <div>
      <PageHeader
        title="My Timetable"
        sub={`${timetable.name} · ${rollNumber} · Semester ${timetable.semester}`}
      />

      {/* Subject list */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10, marginBottom: 20 }}>
        {entries.map(e => (
          <div key={e.section_id} style={{
            background: "#fff",
            border: "1px solid #e5e3dc",
            borderRadius: 10,
            padding: "12px 16px",
          }}>
            <div style={{ fontWeight: 600, fontSize: 13, color: "#222", marginBottom: 2 }}>
              {e.subject_name || e.subject_code}
            </div>
            <div style={{ fontSize: 11, color: "#888", marginBottom: 6 }}>
              <code style={{ background: "#f1efe8", padding: "1px 4px", borderRadius: 3 }}>{e.subject_code}</code>
              {" · "}
              <span style={{
                background: e.subject_type === "lab" ? "#EEEDFB" : "#E6F1FB",
                color: e.subject_type === "lab" ? "#5a54c0" : "#0C447C",
                padding: "1px 6px", borderRadius: 10, fontSize: 10, fontWeight: 600,
              }}>
                {e.subject_type === "lab" ? "Lab" : "Theory"}
              </span>
            </div>
            <div style={{ fontSize: 11, color: "#555" }}>
              <div>📋 {e.section_label}</div>
              <div>👤 {e.teacher_name || e.teacher_id || "—"}</div>
              <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 4 }}>
                {e.meetings.map((m, i) => (
                  <span
                    key={i}
                    style={{
                      background: m.duration_hours === 1 ? "#F0F9FF" : "#F4F8FC",
                      border: m.duration_hours === 1 ? "1px solid #7DD3FC" : "1px solid #B5D4F4",
                      borderRadius: 4,
                      padding: "2px 6px",
                      fontSize: 10,
                      color: m.duration_hours === 1 ? "#0369A1" : "#0C447C",
                      fontWeight: 500,
                    }}
                  >
                    {m.day} {m.start_time}–{m.end_time} ({m.duration_hours || 2}h)
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Weekly grid */}
      <Card>
        <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 13 }}>Weekly Schedule Grid</div>
        <div style={{ fontSize: 12, color: "#888", marginBottom: 14 }}>
          Exact class schedule with accurate 2-hour and 1-hour remainder intervals.
        </div>

        {/* Header */}
        <div style={{ display: "grid", gridTemplateColumns: "110px repeat(5, 1fr)", gap: 4, marginBottom: 4 }}>
          <div />
          {DAYS.map(d => (
            <div key={d} style={{
              textAlign: "center", fontSize: 12, fontWeight: 600,
              color: "#444", padding: "6px 4px",
              background: "#f9f8f5", borderRadius: 6,
            }}>{d}</div>
          ))}
        </div>

        {SLOT_NUMBERS.map(slotNum => (
          <div key={slotNum} style={{ display: "grid", gridTemplateColumns: "110px repeat(5, 1fr)", gap: 4, marginBottom: 4 }}>
            {/* Slot label */}
            <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", paddingRight: 6 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#555" }}>{SLOT_SHORT[slotNum]}</div>
              <div style={{ fontSize: 9, color: "#aaa" }}>{SLOT_LABELS[slotNum]}</div>
            </div>

            {DAYS.map(day => {
              const key = slotKey(day, slotNum);
              const cellEntries = grid[key] || [];
              const isMon1 = day === "Mon" && slotNum === 1;
              const hasEntries = cellEntries.length > 0;
              const bg = hasEntries ? "#fff" : (isMon1 ? "#f0efeb" : "#f9f8f5");
              return (
                <div key={day} style={{
                  background: bg,
                  borderRadius: 6,
                  padding: "6px",
                  minHeight: 64,
                  border: hasEntries ? "1px solid #B5D4F4" : "0.5px solid #e5e3dc",
                  opacity: isMon1 && !hasEntries ? 0.4 : 1,
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                }}>
                  {cellEntries.map((item, idx) => {
                    const isOneHour = item.activeMeeting?.duration_hours === 1;
                    return (
                      <div
                        key={idx}
                        style={{
                          background: isOneHour ? "#F0F9FF" : "#E6F1FB",
                          border: isOneHour ? "1px solid #7DD3FC" : "1px solid #B5D4F4",
                          borderRadius: 4,
                          padding: "4px 6px",
                        }}
                      >
                        <div style={{ fontSize: 10, fontWeight: 700, color: isOneHour ? "#0369A1" : "#0C447C", lineHeight: 1.3 }}>
                          {item.subject_code} ({item.section_label})
                        </div>
                        <div style={{ fontSize: 9, color: "#333", marginTop: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {item.subject_name}
                        </div>
                        <div style={{ fontSize: 9, color: "#666", marginTop: 2 }}>
                          👤 {item.teacher_name || item.teacher_id || "—"}
                        </div>
                        <div style={{ fontSize: 9, color: isOneHour ? "#0369A1" : "#555", marginTop: 2, fontWeight: 600 }}>
                          ⏰ {item.activeMeeting?.start_time}–{item.activeMeeting?.end_time} {isOneHour && "(1h)"}
                        </div>
                      </div>
                    );
                  })}
                  {isMon1 && !hasEntries && (
                    <div style={{ fontSize: 9, color: "#ccc", display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
                      reserved
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </Card>
    </div>
  );
}
