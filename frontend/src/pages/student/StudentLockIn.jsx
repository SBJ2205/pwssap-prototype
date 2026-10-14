import { useCallback, useEffect, useState } from "react";
import {
  getStudentAvailableChoices,
  getStudentLockIn,
  saveStudentLockIn,
  getStudentEnrolledSubjects,
} from "../../api/catalog";
import { apiErrorMessage } from "../../api/client";
import { Badge } from "../../components/ui";

export default function StudentLockIn({ studentRoll, onLockInComplete, onNavigate }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const [semester, setSemester] = useState(null);
  const [availableChoices, setAvailableChoices] = useState({});
  const [electiveSubjects, setElectiveSubjects] = useState([]);
  const [selectedChoices, setSelectedChoices] = useState({});
  const [lockedInChoices, setLockedInChoices] = useState({});
  const [isComplete, setIsComplete] = useState(false);
  const [enrolledSubjects, setEnrolledSubjects] = useState([]);

  const loadData = useCallback(async () => {
    if (!studentRoll) return;
    setLoading(true);
    setError(null);
    try {
      const [availRes, lockRes, enrolledRes] = await Promise.all([
        getStudentAvailableChoices(studentRoll),
        getStudentLockIn(studentRoll),
        getStudentEnrolledSubjects(studentRoll).catch(() => []),
      ]);

      setSemester(availRes.semester);
      setAvailableChoices(availRes.available_choices || {});
      setElectiveSubjects(availRes.subjects || []);

      const currentLocked = lockRes.locked_in || {};
      setLockedInChoices(currentLocked);
      setSelectedChoices({ ...currentLocked });
      setIsComplete(Boolean(lockRes.complete));
      setEnrolledSubjects(enrolledRes || []);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [studentRoll]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData();
  }, [loadData]);

  const handleSelectSubtag = (tag, subtag) => {
    setSelectedChoices(prev => ({
      ...prev,
      [tag]: subtag,
    }));
    setSuccess(null);
  };

  const choiceTags = Object.keys(availableChoices);
  const allTagsSelected = choiceTags.every(t => Boolean(selectedChoices[t]));
  const isChanged = JSON.stringify(selectedChoices) !== JSON.stringify(lockedInChoices);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!allTagsSelected) {
      setError("Please select a subtag for every elective group.");
      return;
    }

    if (isComplete && isChanged) {
      const confirmed = window.confirm(
        "Changing your locked-in elective choices will reset any time-slot and faculty preferences you have already saved. Do you wish to continue?"
      );
      if (!confirmed) return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await saveStudentLockIn(studentRoll, selectedChoices);
      setIsComplete(Boolean(res.complete));
      setLockedInChoices({ ...selectedChoices });
      setSuccess("Your elective choices have been successfully locked in!");

      // Refresh enrolled subjects
      const updatedEnrolled = await getStudentEnrolledSubjects(studentRoll);
      setEnrolledSubjects(updatedEnrolled);

      if (onLockInComplete) {
        onLockInComplete(selectedChoices);
      }
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: "40px 0", textAlign: "center", color: "#64748b" }}>
        Loading elective choices...
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", paddingBottom: 40 }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h1 style={{ margin: "0 0 4px", fontSize: 22, fontWeight: 700, color: "#0f172a" }}>
              Elective Course Lock-In
            </h1>
            <p style={{ margin: 0, fontSize: 14, color: "#64748b" }}>
              Roll Number: <strong>{studentRoll}</strong> · Semester: <strong>{semester ?? "–"}</strong>
            </p>
          </div>
          <div>
            {isComplete ? (
              <Badge color="green">✓ Lock-In Complete</Badge>
            ) : (
              <Badge color="amber">Action Required</Badge>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div style={{
          background: "#fef2f2",
          border: "1px solid #fecaca",
          borderRadius: 8,
          padding: "12px 16px",
          color: "#b91c1c",
          marginBottom: 20,
          fontSize: 13,
        }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {success && (
        <div style={{
          background: "#f0fdf4",
          border: "1px solid #bbf7d0",
          borderRadius: 8,
          padding: "14px 18px",
          color: "#15803d",
          marginBottom: 20,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 12,
        }}>
          <div>
            <strong>Success!</strong> {success}
          </div>
          {onNavigate && (
            <button
              type="button"
              onClick={() => onNavigate("student-prefs")}
              style={{
                padding: "6px 14px",
                background: "#166534",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Proceed to Time Preferences →
            </button>
          )}
        </div>
      )}

      <div style={{
        background: "#f8fafc",
        border: "1px solid #e2e8f0",
        borderRadius: 8,
        padding: "14px 18px",
        marginBottom: 24,
        fontSize: 13,
        color: "#334155",
        lineHeight: 1.5,
      }}>
        <strong style={{ color: "#0f172a" }}>Notice:</strong> You must lock in your elective course selections before submitting your time-slot and faculty preferences. If you modify your choices later, your previously submitted time and faculty preferences will be reset.
      </div>

      {choiceTags.length === 0 ? (
        <div style={{
          background: "#ffffff",
          border: "1px solid #e2e8f0",
          borderRadius: 10,
          padding: "32px 24px",
          textAlign: "center",
        }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>📚</div>
          <h3 style={{ margin: "0 0 8px", fontSize: 16, fontWeight: 600, color: "#1e293b" }}>
            No Elective Choices Required
          </h3>
          <p style={{ margin: "0 0 20px", fontSize: 13, color: "#64748b" }}>
            All subjects in Semester {semester} are core curriculum subjects. No elective lock-in is required.
          </p>
          {onNavigate && (
            <button
              type="button"
              onClick={() => onNavigate("student-prefs")}
              style={{
                padding: "8px 18px",
                background: "#185FA5",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Continue to Time Preferences →
            </button>
          )}
        </div>
      ) : (
        <form onSubmit={handleSubmit}>
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            {choiceTags.map((tag) => {
              const subtags = availableChoices[tag] || [];
              const selectedSubtag = selectedChoices[tag];

              return (
                <div
                  key={tag}
                  style={{
                    background: "#ffffff",
                    border: "1px solid #e2e8f0",
                    borderRadius: 10,
                    padding: 20,
                    boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
                  }}
                >
                  <div style={{ marginBottom: 14, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div>
                      <h2 style={{ margin: "0 0 4px", fontSize: 16, fontWeight: 600, color: "#0f172a" }}>
                        {tag.replace(/_/g, " ").toUpperCase()}
                      </h2>
                      <span style={{ fontSize: 12, color: "#64748b" }}>
                        Select exactly one elective course from this group
                      </span>
                    </div>
                    {selectedSubtag && (
                      <Badge color="blue">Selected: {selectedSubtag}</Badge>
                    )}
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12 }}>
                    {subtags.map((subtag) => {
                      const subjects = electiveSubjects.filter(
                        s => s.subject_tag === tag && (s.subtag || "")
                          .split("|")
                          .map(value => value.trim())
                          .includes(subtag)
                      );
                      const isSelected = selectedSubtag === subtag;

                      return (
                        <div
                          key={subtag}
                          onClick={() => handleSelectSubtag(tag, subtag)}
                          style={{
                            border: `2px solid ${isSelected ? "#185FA5" : "#e2e8f0"}`,
                            borderRadius: 8,
                            padding: 14,
                            cursor: "pointer",
                            background: isSelected ? "#f0f7ff" : "#ffffff",
                            transition: "all 0.15s ease",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                            <input
                              type="radio"
                              name={tag}
                              value={subtag}
                              checked={isSelected}
                              onChange={() => handleSelectSubtag(tag, subtag)}
                              style={{ marginTop: 3, cursor: "pointer" }}
                            />
                            <div style={{ flex: 1 }}>
                              <div style={{ fontWeight: 600, fontSize: 14, color: isSelected ? "#185FA5" : "#1e293b", marginBottom: 4 }}>
                                {subtag}
                              </div>
                              {subjects.map(s => (
                                <div key={s.subject_code} style={{ fontSize: 12, color: "#475569" }}>
                                  <strong>{s.subject_code}</strong>: {s.subject_name}
                                  <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
                                    {s.weekly_hours}h/wk ({s.type}) · Cap: {s.capacity}
                                    {s.weekly_hours === 3 && " · (2h + 1h remainder)"}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{ marginTop: 28, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
            <div style={{ fontSize: 13, color: "#64748b" }}>
              {allTagsSelected ? (
                <span>All elective groups selected. Click below to lock in.</span>
              ) : (
                <span style={{ color: "#dc2626" }}>Please select one subtag for all elective groups.</span>
              )}
            </div>

            <div style={{ display: "flex", gap: 12 }}>
              {isComplete && onNavigate && (
                <button
                  type="button"
                  onClick={() => onNavigate("student-prefs")}
                  style={{
                    padding: "8px 18px",
                    background: "#f1efe8",
                    color: "#333",
                    border: "1px solid #d1cfc7",
                    borderRadius: 6,
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Go to Time Preferences →
                </button>
              )}
              <button
                type="submit"
                disabled={!allTagsSelected || saving}
                style={{
                  padding: "8px 20px",
                  background: !allTagsSelected || saving ? "#ccc" : "#185FA5",
                  color: "#fff",
                  border: "none",
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: !allTagsSelected || saving ? "not-allowed" : "pointer",
                }}
              >
                {saving ? "Saving Lock-In..." : isComplete ? "Update Lock-In" : "Lock In Choices"}
              </button>
            </div>
          </div>
        </form>
      )}

      {/* Enrolled subjects summary */}
      {enrolledSubjects.length > 0 && (
        <div style={{ marginTop: 40, borderTop: "1px solid #e2e8f0", paddingTop: 24 }}>
          <h2 style={{ fontSize: 15, fontWeight: 600, color: "#0f172a", marginBottom: 12 }}>
            Your Enrolled Subjects for this Cycle ({enrolledSubjects.length})
          </h2>
          <div style={{
            background: "#ffffff",
            border: "1px solid #e2e8f0",
            borderRadius: 8,
            overflow: "hidden",
          }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", textAlign: "left" }}>
                  <th style={{ padding: "8px 12px", color: "#475569" }}>Code</th>
                  <th style={{ padding: "8px 12px", color: "#475569" }}>Subject Name</th>
                  <th style={{ padding: "8px 12px", color: "#475569" }}>Tag</th>
                  <th style={{ padding: "8px 12px", color: "#475569" }}>Subtag</th>
                  <th style={{ padding: "8px 12px", color: "#475569" }}>Hours</th>
                  <th style={{ padding: "8px 12px", color: "#475569" }}>Type</th>
                </tr>
              </thead>
              <tbody>
                {enrolledSubjects.map((s) => (
                  <tr key={s.subject_code} style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "8px 12px", fontWeight: 600, color: "#1e293b" }}>{s.subject_code}</td>
                    <td style={{ padding: "8px 12px", color: "#334155" }}>{s.subject_name}</td>
                    <td style={{ padding: "8px 12px" }}>
                      <Badge color={s.subtag ? "blue" : "gray"}>{s.subject_tag}</Badge>
                    </td>
                    <td style={{ padding: "8px 12px", color: "#64748b" }}>{s.subtag || "–"}</td>
                    <td style={{ padding: "8px 12px", color: "#475569" }}>
                      {s.weekly_hours}h {s.weekly_hours === 3 ? "(2+1)" : ""}
                    </td>
                    <td style={{ padding: "8px 12px", color: "#64748b", textTransform: "capitalize" }}>{s.type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
