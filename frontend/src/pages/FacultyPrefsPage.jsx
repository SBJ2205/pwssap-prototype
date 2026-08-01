import { RATING_META } from "../constants";
import { Card, EmptyState, InfoBox, PageHeader } from "../components/ui";

export default function FacultyPrefsPage({ students, subjects, facultyBySubject, selStudent, setSelStudent, facultyPrefs, cycleFacultyRating, saveFacultyPrefs }) {
  // Subject code -> display name (e.g. "IT301" -> "Data Structures"), from
  // the student-safe /subjects catalog (no teacher/room/meeting data).
  const subjectNames = {};
  subjects.forEach(s => { subjectNames[s.code] = s.name; });

  // facultyBySubject is {subject_code: [{id, name}, ...]} — each entry is a teacher.
  const rankableSubjects = Object.entries(facultyBySubject).filter(([, teachers]) => teachers.length > 1);
  const singleFacultySubjects = Object.entries(facultyBySubject).filter(([, teachers]) => teachers.length <= 1);

  const ratedCount = Object.values(facultyPrefs).reduce((sum, subjPrefs) => sum + Object.keys(subjPrefs).length, 0);
  const rankableSlotCount = rankableSubjects.reduce((sum, [, teachers]) => sum + teachers.length, 0);

  return (
    <div>
      <PageHeader
        title="Faculty Preferences"
        sub="Optional secondary ranking, done SUBJECT BY SUBJECT — only used to break ties between equally time-convenient sections"
      />
      <InfoBox title="How does this work?">
        This is <strong>optional and secondary</strong> to your time-slot preferences, and it's rated{" "}
        <strong>separately for each subject</strong> — e.g. you rank the faculty teaching DBMS independently from
        the faculty teaching Data Structures. If two sections of the same subject fit your schedule equally
        well, the solver prefers the one taught by the faculty you ranked higher for THAT subject.
        Faculty preference can never override a better time-slot match, and there's no "Blocked" option —
        a mismatch costs a small penalty, it never makes a section unavailable. Subjects taught by only one
        faculty member have nothing to rank and are listed separately below. Leaving a faculty member unrated
        is fine — it's treated as <strong>Indifferent</strong> (no penalty), and you can save with none, some, or
        all faculty rated.
      </InfoBox>

      {students.length === 0 ? (
        <EmptyState message="No students in the roster yet — ask an admin to add students first." />
      ) : (
      <div style={{ display: "grid", gridTemplateColumns: "200px 1fr", gap: 14 }}>
        <div>
          <Card>
            <div style={{ fontWeight: 500, marginBottom: 10, fontSize: 13 }}>Students</div>
            {students.map(s => (
              <div key={s.id} onClick={() => setSelStudent(s.id)}
                style={{
                  padding: "8px 10px", borderRadius: 6, cursor: "pointer", marginBottom: 4,
                  background: s.id === selStudent ? "#E6F1FB" : "#f9f8f5",
                  border: s.id === selStudent ? "1px solid #B5D4F4" : "1px solid transparent"
                }}>
                <div style={{ fontWeight: 500, fontSize: 13 }}>{s.name}</div>
                <div style={{ fontSize: 11, color: "#888" }}>{s.roll}</div>
              </div>
            ))}
          </Card>

          <Card>
            <div style={{ fontSize: 12, color: "#555", marginBottom: 8 }}>Summary</div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 11, color: "#555" }}>Faculty rated</span>
              <span style={{ fontSize: 12, fontWeight: 600, background: "#E6F1FB", color: "#0C447C", padding: "1px 8px", borderRadius: 10 }}>{ratedCount} / {rankableSlotCount}</span>
            </div>
          </Card>
        </div>

        <div>
          {rankableSubjects.map(([code, teachers]) => {
            const subjPrefs = facultyPrefs[code] ?? {};
            return (
              <Card key={code}>
                <div style={{ fontWeight: 500, marginBottom: 2 }}>{subjectNames[code] || code}{" "}
                  <code style={{ fontSize: 11, background: "#f1efe8", padding: "1px 5px", borderRadius: 3 }}>{code}</code>
                </div>
                <div style={{ fontSize: 12, color: "#888", marginBottom: 12 }}>
                  Rank the {teachers.length} faculty teaching this subject. Click to cycle: Indifferent → Preferred → Tolerable → Disliked.
                </div>
                {teachers.map(t => {
                  const rating = subjPrefs[t.id] ?? 0;
                  const m = RATING_META[rating];
                  return (
                    <div key={t.id} onClick={() => cycleFacultyRating(code, t.id)}
                      style={{
                        display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer",
                        padding: "10px 14px", marginBottom: 6, borderRadius: 8,
                        background: m.bg, border: `1.5px solid ${rating > 0 ? m.color : "#e0ddd8"}`,
                      }}>
                      <span style={{ fontSize: 13, fontWeight: 500, color: "#333" }}>{t.name}</span>
                      <span style={{ fontSize: 12, fontWeight: 600, color: m.color }}>{m.label} {m.pill}</span>
                    </div>
                  );
                })}
              </Card>
            );
          })}

          {singleFacultySubjects.length > 0 && (
            <Card>
              <div style={{ fontWeight: 500, marginBottom: 4 }}>No ranking needed</div>
              <div style={{ fontSize: 12, color: "#888" }}>
                {singleFacultySubjects.map(([code, teachers]) => (
                  <div key={code} style={{ marginBottom: 4 }}>
                    <strong>{subjectNames[code] || code}</strong> is taught by only one faculty member ({teachers[0]?.name || "—"}) — there's no choice to rank.
                  </div>
                ))}
              </div>
            </Card>
          )}

          <button onClick={saveFacultyPrefs}
            style={{
              padding: "10px 28px", background: "#185FA5", color: "#fff",
              border: "none", borderRadius: 6, cursor: "pointer",
              fontSize: 13, fontWeight: 600, marginTop: 4,
              boxShadow: "0 1px 4px rgba(24,95,165,0.25)",
            }}>
            Save Faculty Preferences
          </button>
        </div>
      </div>
      )}
    </div>
  );
}
