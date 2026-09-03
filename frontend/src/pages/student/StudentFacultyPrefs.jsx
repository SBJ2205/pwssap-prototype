import { useEffect, useState } from "react";
import { getFacultyPrefs, saveFacultyPrefs } from "../../api/preferences";
import { getSubjects, getTeachers, getSubjectTeachers } from "../../api/catalog";
import { apiErrorMessage } from "../../api/client";
import { RATING_META } from "../../constants";
import { Card, EmptyState, InfoBox, PageHeader } from "../../components/ui";

// Faculty preferences use ratings 1=preferred, 2=tolerable, 3=disliked (no 4/blocked).
const FACULTY_RATING_META = {
  0: RATING_META[0],
  1: RATING_META[1],
  2: RATING_META[2],
  3: RATING_META[3],
};

export default function StudentFacultyPrefs({ session }) {
  const { identity: rollNumber } = session;

  const [subjects,        setSubjects]        = useState([]);
  const [teachers,        setTeachers]        = useState([]);
  const [subjectTeachers, setSubjectTeachers] = useState({}); // code -> [teacher_id, ...]
  const [prefs,           setPrefs]           = useState({}); // {subject_code: {teacher_id: rating}}

  const [loading, setLoading] = useState(true);
  const [saving,  setSaving]  = useState(false);
  const [error,   setError]   = useState(null);
  const [saveMsg, setSaveMsg] = useState(null);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
     
    setError(null);

    Promise.all([
      getSubjects(),
      getTeachers(),
      getFacultyPrefs(rollNumber),
    ])
      .then(async ([subjectsData, teachersData, prefsData]) => {
        if (cancelled) return;
        setSubjects(subjectsData);
        setTeachers(teachersData);
        setPrefs(prefsData.preferences || {});

        // For each subject, fetch which teacher_ids can teach it.
        const entries = await Promise.all(
          subjectsData.map(async s => {
            try {
              const r = await getSubjectTeachers(s.subject_code);
              return [s.subject_code, r.teacher_ids || []];
            } catch {
              return [s.subject_code, []];
            }
          })
        );
        if (!cancelled) {
          setSubjectTeachers(Object.fromEntries(entries));
        }
      })
      .catch(e => {
        if (!cancelled) setError(apiErrorMessage(e));
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [rollNumber]);

  const teacherMap = Object.fromEntries(teachers.map(t => [t.teacher_id, t.teacher_name]));
  const subjectMap = Object.fromEntries(subjects.map(s => [s.subject_code, s.subject_name]));

  // Subjects where >1 teacher is capable (only these are rankable).
  const rankable = subjects.filter(
    s => (subjectTeachers[s.subject_code] || []).length > 1
  );
  const singleTeacher = subjects.filter(
    s => (subjectTeachers[s.subject_code] || []).length === 1
  );
  const noTeacher = subjects.filter(
    s => (subjectTeachers[s.subject_code] || []).length === 0
  );

  function cycleRating(subjectCode, teacherId) {
    const cur = (prefs[subjectCode] || {})[teacherId] ?? 0;
    const next = cur >= 3 ? 0 : cur + 1; // max is 3 (disliked) — no blocked for faculty
    setPrefs(prev => {
      const updated = { ...prev, [subjectCode]: { ...(prev[subjectCode] || {}) } };
      if (next === 0) delete updated[subjectCode][teacherId];
      else updated[subjectCode][teacherId] = next;
      return updated;
    });
    setSaveMsg(null);
  }

  async function handleSave() {
    setSaving(true);
    setSaveMsg(null);
    setError(null);
    try {
      await saveFacultyPrefs(rollNumber, prefs);
      setSaveMsg("Faculty preferences saved successfully.");
    } catch (e) {
      setError(apiErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  const ratedCount = Object.values(prefs).reduce(
    (sum, subjPrefs) => sum + Object.keys(subjPrefs).length, 0
  );
  const rankableCount = rankable.reduce(
    (sum, s) => sum + (subjectTeachers[s.subject_code] || []).length, 0
  );

  if (loading) return (
    <div>
      <PageHeader title="Faculty Preferences" />
      <Card><div style={{ color: "#888", fontSize: 13 }}>⏳ Loading…</div></Card>
    </div>
  );

  return (
    <div>
      <PageHeader
        title="Faculty Preferences"
        sub="Optional secondary ranking, done subject by subject. Only used when multiple teachers are equally good on time."
      />

      <InfoBox title="How does this work?">
        This is <strong>optional and secondary</strong> to your time-slot preferences.
        Rate faculty <strong>separately for each subject</strong> — e.g. your preference for the
        professor teaching Networks is independent from your preference for the one teaching OS.
        If two sections fit your schedule equally well, the solver prefers the one taught by
        the faculty you ranked higher for that subject. There is no "Blocked" option —
        a mismatch is always a soft penalty, never a hard restriction.
      </InfoBox>

      {error && (
        <div style={{ background: "#FCEBEB", border: "1px solid #F7C1C1", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#791F1F", marginBottom: 12 }}>
          ✕ {error}
        </div>
      )}
      {saveMsg && (
        <div style={{ background: "#EAF3DE", border: "1px solid #C0DD97", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#27500A", marginBottom: 12 }}>
          ✓ {saveMsg}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "190px 1fr", gap: 14 }}>
        {/* Left: summary */}
        <div>
          <Card>
            <div style={{ fontWeight: 600, marginBottom: 10, fontSize: 13 }}>Summary</div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span style={{ fontSize: 11, color: "#555" }}>Faculty rated</span>
              <span style={{ fontSize: 12, fontWeight: 600, background: "#E6F1FB", color: "#0C447C", padding: "1px 8px", borderRadius: 10 }}>
                {ratedCount} / {rankableCount}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 11, color: "#555" }}>Rankable subjects</span>
              <span style={{ fontSize: 12, fontWeight: 600, background: "#f1efe8", color: "#555", padding: "1px 8px", borderRadius: 10 }}>
                {rankable.length}
              </span>
            </div>
          </Card>

          <Card>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#555", marginBottom: 8 }}>Rating guide</div>
            {[0, 1, 2, 3].map(r => {
              const m = FACULTY_RATING_META[r];
              return (
                <div key={r} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <div style={{
                    width: 24, height: 20, borderRadius: 4, background: m.bg,
                    border: `1px solid ${r > 0 ? m.color : "#ddd"}`,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 11, fontWeight: 700, color: m.color, flexShrink: 0,
                  }}>{m.label}</div>
                  <div style={{ fontSize: 11, color: "#555" }}>{m.title}</div>
                </div>
              );
            })}
            <div style={{ fontSize: 10, color: "#bbb", marginTop: 4 }}>Click to cycle. No "Blocked" — faculty is always a soft preference.</div>
          </Card>
        </div>

        {/* Right: subject cards */}
        <div>
          {rankable.length === 0 && singleTeacher.length === 0 && (
            <EmptyState
              title="No subjects loaded"
              message="Ask an admin to import subjects and teachers first."
            />
          )}

          {rankable.map(subj => {
            const code = subj.subject_code;
            const tids = subjectTeachers[code] || [];
            const subjPrefs = prefs[code] || {};
            return (
              <Card key={code}>
                <div style={{ fontWeight: 600, marginBottom: 2 }}>
                  {subjectMap[code] || code}{" "}
                  <code style={{ fontSize: 11, background: "#f1efe8", padding: "1px 5px", borderRadius: 3 }}>{code}</code>
                </div>
                <div style={{ fontSize: 12, color: "#888", marginBottom: 12 }}>
                  {tids.length} faculty — click to cycle: Indifferent → Preferred → Tolerable → Disliked
                </div>
                {tids.map(tid => {
                  const rating = subjPrefs[tid] ?? 0;
                  const m = FACULTY_RATING_META[rating];
                  return (
                    <div
                      key={tid}
                      onClick={() => cycleRating(code, tid)}
                      style={{
                        display: "flex", alignItems: "center", justifyContent: "space-between",
                        cursor: "pointer", padding: "10px 14px", marginBottom: 6, borderRadius: 8,
                        background: m.bg, border: `1.5px solid ${rating > 0 ? m.color : "#e0ddd8"}`,
                        transition: "all 0.1s",
                      }}
                    >
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 500, color: "#333" }}>
                          {teacherMap[tid] || tid}
                        </div>
                        <div style={{ fontSize: 10, color: "#aaa" }}>{tid}</div>
                      </div>
                      <span style={{ fontSize: 12, fontWeight: 600, color: m.color }}>
                        {m.label} {m.pill}
                      </span>
                    </div>
                  );
                })}
              </Card>
            );
          })}

          {singleTeacher.length > 0 && (
            <Card>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>No ranking needed</div>
              <div style={{ fontSize: 12, color: "#888" }}>
                {singleTeacher.map(s => (
                  <div key={s.subject_code} style={{ marginBottom: 4 }}>
                    <strong>{subjectMap[s.subject_code] || s.subject_code}</strong> —
                    only one faculty member ({teacherMap[(subjectTeachers[s.subject_code] || [])[0]] || "—"}).
                  </div>
                ))}
              </div>
            </Card>
          )}

          {noTeacher.length > 0 && (
            <Card>
              <div style={{ fontWeight: 600, marginBottom: 4, color: "#888" }}>No teacher assigned yet</div>
              <div style={{ fontSize: 12, color: "#aaa" }}>
                {noTeacher.map(s => (
                  <div key={s.subject_code}>{subjectMap[s.subject_code] || s.subject_code}</div>
                ))}
              </div>
            </Card>
          )}

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
            {saving ? "Saving…" : "Save Faculty Preferences"}
          </button>
        </div>
      </div>
    </div>
  );
}
