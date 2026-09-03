import { useEffect, useState, useMemo } from "react";
import { getTeacherAvailability, setTeacherAvailability } from "../../api/overrides";
import { getTeachers } from "../../api/catalog";
import { apiErrorMessage } from "../../api/client";
import { DAYS, SLOT_NUMBERS, SLOT_LABELS, SLOT_SHORT, getSlotRestriction, slotKey } from "../../constants";
import { Card, PageHeader, InfoBox } from "../../components/ui";

export default function AdminAvailability({ teachers: initialTeachers = [] }) {
  const [teachers, setTeachers] = useState(initialTeachers);
  const [selectedTeacherId, setSelectedTeacherId] = useState("");
  const [teacherSearch, setTeacherSearch] = useState("");

  // Availability map: { [slot_key]: boolean }
  const [availability, setAvailability] = useState({});
  const [loadingTeachers, setLoadingTeachers] = useState(false);
  const [loadingGrid, setLoadingGrid] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(null);
  const [saveError, setSaveError] = useState(null);

  // Load teacher list if not provided
  useEffect(() => {
    if (teachers.length === 0) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLoadingTeachers(true);
      getTeachers()
        .then(data => {
          setTeachers(data || []);
          if (data && data.length > 0 && !selectedTeacherId) {
            setSelectedTeacherId(data[0].teacher_id);
          }
        })
        .catch(() => {})
        .finally(() => setLoadingTeachers(false));
    } else if (!selectedTeacherId && teachers.length > 0) {
      setSelectedTeacherId(teachers[0].teacher_id);
    }
  }, [teachers, selectedTeacherId]);

  // Load availability when selectedTeacherId changes
  useEffect(() => {
    if (!selectedTeacherId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAvailability({});
      return;
    }

    let cancelled = false;
    setLoadingGrid(true);
    setSaveSuccess(null);
    setSaveError(null);

    getTeacherAvailability(selectedTeacherId)
      .then(data => {
        if (cancelled) return;
        const map = {};
        for (const slot of data || []) {
          map[slot.slot_key] = slot.available !== false;
        }
        setAvailability(map);
      })
      .catch(err => {
        if (!cancelled) setSaveError(apiErrorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoadingGrid(false);
      });

    return () => { cancelled = true; };
  }, [selectedTeacherId]);

  function toggleSlot(day, slotNum) {
    const key = slotKey(day, slotNum);
    setAvailability(prev => ({
      ...prev,
      [key]: prev[key] === false ? true : false,
    }));
    setSaveSuccess(null);
    setSaveError(null);
  }

  function setAllSlots(available) {
    const updated = {};
    for (const d of DAYS) {
      for (const s of SLOT_NUMBERS) {
        updated[slotKey(d, s)] = available;
      }
    }
    setAvailability(updated);
    setSaveSuccess(null);
  }

  async function handleSave() {
    if (!selectedTeacherId) return;
    setSaving(true);
    setSaveSuccess(null);
    setSaveError(null);

    try {
      await setTeacherAvailability(selectedTeacherId, availability);
      setSaveSuccess("Teacher availability constraints saved successfully!");
    } catch (err) {
      setSaveError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const filteredTeachers = useMemo(() => {
    if (!teacherSearch.trim()) return teachers;
    const q = teacherSearch.toLowerCase();
    return teachers.filter(
      t => t.teacher_id.toLowerCase().includes(q) || t.teacher_name.toLowerCase().includes(q)
    );
  }, [teachers, teacherSearch]);

  const selectedTeacher = teachers.find(t => t.teacher_id === selectedTeacherId);

  // Count blocked slots for current teacher
  const blockedCount = Object.values(availability).filter(v => v === false).length;
  const availableCount = 20 - blockedCount;

  return (
    <div>
      <PageHeader
        title="Teacher Availability Constraints"
        sub="Hard constraints specifying which weekly timeslots faculty members cannot be scheduled into."
      />

      <InfoBox title="Hard Constraint Rule">
        Unlike student preferences, <strong>teacher availability is a strict, hard constraint</strong>.
        When a slot is marked <strong>Unavailable (Blocked)</strong>, the CP-SAT solver is completely forbidden
        from assigning that teacher to any class meeting during that slot.
      </InfoBox>

      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 16 }}>
        {/* Left: Teacher Selector */}
        <Card>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8, color: "#444" }}>
            Select Faculty Member
          </div>

          <input
            type="text"
            value={teacherSearch}
            onChange={e => setTeacherSearch(e.target.value)}
            placeholder="Search by ID or name…"
            style={{
              width: "100%",
              padding: "6px 10px",
              border: "1px solid #ccc",
              borderRadius: 6,
              fontSize: 12,
              marginBottom: 10,
              boxSizing: "border-box",
            }}
          />

          {loadingTeachers ? (
            <div style={{ padding: "16px 0", textAlign: "center", color: "#888", fontSize: 12 }}>
              ⏳ Loading teachers…
            </div>
          ) : filteredTeachers.length === 0 ? (
            <div style={{ padding: "16px 0", textAlign: "center", color: "#888", fontSize: 12 }}>
              No teachers found.
            </div>
          ) : (
            <div style={{ maxHeight: 420, overflowY: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
              {filteredTeachers.map(t => {
                const isSelected = t.teacher_id === selectedTeacherId;
                return (
                  <div
                    key={t.teacher_id}
                    onClick={() => setSelectedTeacherId(t.teacher_id)}
                    style={{
                      padding: "8px 10px",
                      borderRadius: 6,
                      cursor: "pointer",
                      border: isSelected ? "1.5px solid #185FA5" : "1px solid #eee",
                      background: isSelected ? "#E6F1FB" : "#f9f8f5",
                    }}
                  >
                    <div style={{ fontWeight: 600, fontSize: 13, color: isSelected ? "#0C447C" : "#333" }}>
                      {t.teacher_name}
                    </div>
                    <div style={{ fontSize: 11, color: isSelected ? "#185FA5" : "#888" }}>
                      <code style={{ background: isSelected ? "#fff" : "#eee", padding: "1px 4px", borderRadius: 3 }}>
                        {t.teacher_id}
                      </code>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        {/* Right: Availability Matrix */}
        <div>
          <Card>
            {/* Header with selected teacher info and action buttons */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: 16, color: "#111" }}>
                    {selectedTeacher?.teacher_name || "Select Teacher"}
                  </span>
                  {selectedTeacher && (
                    <code style={{ background: "#f1efe8", padding: "2px 6px", borderRadius: 4, fontSize: 12 }}>
                      {selectedTeacher.teacher_id}
                    </code>
                  )}
                </div>
                <div style={{ fontSize: 12, color: "#666", marginTop: 2 }}>
                  Status: <strong>{availableCount} slots available</strong>, <strong>{blockedCount} slots blocked</strong>. Click cells to toggle.
                </div>
              </div>

              {/* Quick bulk actions */}
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <button
                  type="button"
                  onClick={() => setAllSlots(true)}
                  style={{
                    padding: "4px 10px",
                    background: "#EAF3DE",
                    color: "#27500A",
                    border: "1px solid #C0DD97",
                    borderRadius: 6,
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  ✓ All Available
                </button>
                <button
                  type="button"
                  onClick={() => setAllSlots(false)}
                  style={{
                    padding: "4px 10px",
                    background: "#FCEBEB",
                    color: "#791F1F",
                    border: "1px solid #F7C1C1",
                    borderRadius: 6,
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  ✕ Block All
                </button>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saving || !selectedTeacherId}
                  style={{
                    padding: "6px 18px",
                    background: saving ? "#aaa" : "#185FA5",
                    color: "#fff",
                    border: "none",
                    borderRadius: 6,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: saving ? "not-allowed" : "pointer",
                    boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
                  }}
                >
                  {saving ? "Saving…" : "Save Constraints"}
                </button>
              </div>
            </div>

            {/* Success & Error alerts */}
            {saveSuccess && (
              <div style={{ background: "#EAF3DE", border: "1px solid #C0DD97", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#27500A", marginBottom: 12 }}>
                ✓ {saveSuccess}
              </div>
            )}
            {saveError && (
              <div style={{ background: "#FCEBEB", border: "1px solid #F7C1C1", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#791F1F", marginBottom: 12 }}>
                ✕ {saveError}
              </div>
            )}

            {/* Matrix Grid */}
            {loadingGrid ? (
              <div style={{ padding: "40px 0", textAlign: "center", color: "#888", fontSize: 13 }}>
                ⏳ Loading availability grid…
              </div>
            ) : !selectedTeacherId ? (
              <div style={{ padding: "40px 0", textAlign: "center", color: "#888", fontSize: 13 }}>
                Select a faculty member from the roster on the left.
              </div>
            ) : (
              <div>
                {/* Header row: Days */}
                <div style={{ display: "grid", gridTemplateColumns: "110px repeat(5, 1fr)", gap: 6, marginBottom: 6 }}>
                  <div />
                  {DAYS.map(d => (
                    <div
                      key={d}
                      style={{
                        textAlign: "center",
                        fontSize: 12,
                        fontWeight: 700,
                        color: "#444",
                        padding: "6px 4px",
                        background: "#f9f8f5",
                        borderRadius: 6,
                      }}
                    >
                      {d}
                    </div>
                  ))}
                </div>

                {/* Period rows */}
                {SLOT_NUMBERS.map(slotNum => (
                  <div
                    key={slotNum}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "110px repeat(5, 1fr)",
                      gap: 6,
                      marginBottom: 6,
                    }}
                  >
                    {/* Period label */}
                    <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", paddingRight: 6 }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: "#444" }}>
                        Slot {slotNum} ({SLOT_SHORT[slotNum]})
                      </div>
                      <div style={{ fontSize: 9, color: "#888" }}>
                        {SLOT_LABELS[slotNum]}
                      </div>
                    </div>

                    {/* Day Cells */}
                    {DAYS.map(day => {
                      const key = slotKey(day, slotNum);
                      const isAvailable = availability[key] !== false; // defaults to true
                      const restriction = getSlotRestriction(day, slotNum);
                      const isMon1 = restriction === "restricted";

                      return (
                        <div
                          key={key}
                          onClick={() => toggleSlot(day, slotNum)}
                          title={`${day} Slot ${slotNum} (${SLOT_LABELS[slotNum]}): ${isAvailable ? "Available" : "Blocked"}\nClick to toggle.`}
                          style={{
                            cursor: "pointer",
                            borderRadius: 8,
                            padding: "10px 6px",
                            minHeight: 54,
                            display: "flex",
                            flexDirection: "column",
                            alignItems: "center",
                            justifyContent: "center",
                            gap: 3,
                            userSelect: "none",
                            transition: "all 0.1s ease",
                            background: isAvailable ? "#EAF3DE" : "#FCEBEB",
                            border: isAvailable ? "1.5px solid #C0DD97" : "1.5px solid #F7C1C1",
                          }}
                        >
                          <span style={{ fontSize: 16, fontWeight: 700, color: isAvailable ? "#27500A" : "#791F1F" }}>
                            {isAvailable ? "✓" : "✕"}
                          </span>
                          <span style={{ fontSize: 10, fontWeight: 600, color: isAvailable ? "#27500A" : "#791F1F" }}>
                            {isAvailable ? "Available" : "Blocked"}
                          </span>
                          {isMon1 && (
                            <span style={{ fontSize: 8, color: "#888" }}>reserved</span>
                          )}
                          {restriction === "lab-only" && (
                            <span style={{ fontSize: 8, color: "#BA7517" }}>labs only</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Helper Legend Card */}
          <Card>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8, color: "#444" }}>
              Constraint Legend & Guidelines
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 12, color: "#666" }}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                <span style={{ background: "#EAF3DE", color: "#27500A", fontWeight: 700, padding: "2px 8px", borderRadius: 4 }}>
                  ✓ Available
                </span>
                <span>The solver may schedule any capable theory or lab section for this teacher in this slot.</span>
              </div>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                <span style={{ background: "#FCEBEB", color: "#791F1F", fontWeight: 700, padding: "2px 8px", borderRadius: 4 }}>
                  ✕ Blocked
                </span>
                <span>The solver will never schedule this teacher in this slot. Useful for admin duties, external commitments, or part-time schedules.</span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
