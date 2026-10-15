import { useCallback, useEffect, useState } from "react";
import { getStudentAvailableChoices, getStudentLockIn, saveStudentLockIn } from "../api/catalog";
import { apiErrorMessage } from "../api/client";
import { Badge } from "./ui";

export default function StudentLockInOverrideModal({
  student,
  isOpen,
  onClose,
  onSuccess,
}) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const [availableChoices, setAvailableChoices] = useState({});
  const [electiveSubjects, setElectiveSubjects] = useState([]);
  const [selectedChoices, setSelectedChoices] = useState({});

  const rollNumber = student?.roll_number;

  const loadStudentChoices = useCallback(async () => {
    if (!rollNumber) return;
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const [availRes, lockRes] = await Promise.all([
        getStudentAvailableChoices(rollNumber),
        getStudentLockIn(rollNumber).catch(() => ({ locked_in: {} })),
      ]);

      setAvailableChoices(availRes.available_choices || {});
      setElectiveSubjects(availRes.subjects || []);

      const currentLocked = lockRes?.locked_in || {};
      setSelectedChoices({ ...currentLocked });
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [rollNumber]);

  useEffect(() => {
    if (isOpen && rollNumber) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadStudentChoices();
    }
  }, [isOpen, rollNumber, loadStudentChoices]);

  if (!isOpen || !student) return null;

  const choiceTags = Object.keys(availableChoices);
  const allTagsSelected = choiceTags.every(t => Boolean(selectedChoices[t]));

  const handleSelectSubtag = (tag, subtag) => {
    setSelectedChoices(prev => ({
      ...prev,
      [tag]: subtag,
    }));
    setError(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!allTagsSelected) {
      setError("Please select one subtag for every elective group.");
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(null);

    try {
      const res = await saveStudentLockIn(student.roll_number, selectedChoices);
      setSuccess("Student elective choices saved and locked in successfully!");
      if (onSuccess) {
        onSuccess({ student, choices: selectedChoices, res });
      }
      setTimeout(() => {
        if (onClose) onClose();
      }, 700);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(15, 23, 42, 0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
        backdropFilter: "blur(2px)",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: 12,
          maxWidth: 640,
          width: "100%",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.15), 0 8px 10px -6px rgba(0, 0, 0, 0.1)",
          overflow: "hidden",
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: "16px 20px",
            borderBottom: "1px solid #e2e8f0",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "#f8fafc",
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 16, fontWeight: 700, color: "#0f172a" }}>
                Override Elective Choices
              </span>
              <Badge color="blue">Sem {student.semester}</Badge>
            </div>
            <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
              Student: <strong>{student.name}</strong> ({student.roll_number})
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={saving}
            style={{
              background: "transparent",
              border: "none",
              fontSize: 18,
              cursor: "pointer",
              color: "#94a3b8",
              padding: 4,
            }}
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: "18px 20px", overflowY: "auto", flex: 1 }}>
          {error && (
            <div
              style={{
                background: "#fef2f2",
                border: "1px solid #fecaca",
                borderRadius: 8,
                padding: "10px 14px",
                color: "#b91c1c",
                fontSize: 12,
                marginBottom: 14,
              }}
            >
              <strong>Error:</strong> {error}
            </div>
          )}

          {success && (
            <div
              style={{
                background: "#f0fdf4",
                border: "1px solid #bbf7d0",
                borderRadius: 8,
                padding: "10px 14px",
                color: "#15803d",
                fontSize: 12,
                marginBottom: 14,
                fontWeight: 600,
              }}
            >
              ✓ {success}
            </div>
          )}

          {loading ? (
            <div style={{ padding: "32px 0", textAlign: "center", color: "#64748b", fontSize: 13 }}>
              Loading elective choices for student...
            </div>
          ) : choiceTags.length === 0 ? (
            <div
              style={{
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: 8,
                padding: "24px 16px",
                textAlign: "center",
                color: "#64748b",
                fontSize: 13,
              }}
            >
              <div style={{ fontSize: 28, marginBottom: 8 }}>ℹ️</div>
              <strong>No Elective Choices Required</strong>
              <p style={{ margin: "4px 0 0", fontSize: 12 }}>
                All subjects in Semester {student.semester} are core curriculum subjects.
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} id="admin-override-lockin-form">
              <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                {choiceTags.map(tag => {
                  const subtags = availableChoices[tag] || [];
                  const selectedSubtag = selectedChoices[tag];

                  return (
                    <div
                      key={tag}
                      style={{
                        border: "1px solid #e2e8f0",
                        borderRadius: 8,
                        padding: "14px 16px",
                        background: "#fff",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          marginBottom: 10,
                        }}
                      >
                        <div style={{ fontWeight: 700, fontSize: 14, color: "#1e293b" }}>
                          Elective Group: <span style={{ color: "#185FA5" }}>{tag}</span>
                        </div>
                        {selectedSubtag ? (
                          <span style={{ fontSize: 11, color: "#15803d", fontWeight: 600 }}>
                            ✓ Selected: {selectedSubtag}
                          </span>
                        ) : (
                          <span style={{ fontSize: 11, color: "#b45309", fontWeight: 600 }}>
                            ⚠ Choice required
                          </span>
                        )}
                      </div>

                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {subtags.map(subtag => {
                          const isChosen = selectedSubtag === subtag;
                          const matchingSubjects = electiveSubjects.filter(
                            s => s.subject_tag === tag && s.subtag === subtag
                          );

                          return (
                            <div
                              key={subtag}
                              onClick={() => handleSelectSubtag(tag, subtag)}
                              style={{
                                border: `1.5px solid ${isChosen ? "#185FA5" : "#e2e8f0"}`,
                                background: isChosen ? "#f0f7ff" : "#fbfbfc",
                                borderRadius: 8,
                                padding: "10px 12px",
                                cursor: "pointer",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "space-between",
                                transition: "all 0.15s ease",
                              }}
                            >
                              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                <input
                                  type="radio"
                                  name={`choice_${tag}`}
                                  checked={isChosen}
                                  onChange={() => handleSelectSubtag(tag, subtag)}
                                  style={{ cursor: "pointer", width: 16, height: 16 }}
                                />
                                <div>
                                  <div style={{ fontWeight: 600, fontSize: 13, color: isChosen ? "#185FA5" : "#1e293b" }}>
                                    {subtag}
                                  </div>
                                  {matchingSubjects.length > 0 && (
                                    <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
                                      {matchingSubjects.map(s => (
                                        <span key={s.subject_code}>
                                          <strong>{s.subject_code}</strong>: {s.subject_name} ({s.weekly_hours}h)
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </div>

                              <span
                                style={{
                                  fontSize: 11,
                                  color: isChosen ? "#185FA5" : "#64748b",
                                  fontWeight: 500,
                                }}
                              >
                                {isChosen ? "Selected" : "Select →"}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}

                <div
                  style={{
                    background: "#fffbeb",
                    border: "1px solid #fef3c7",
                    borderRadius: 6,
                    padding: "10px 12px",
                    fontSize: 11,
                    color: "#92400e",
                    lineHeight: 1.4,
                  }}
                >
                  <strong>Admin Note:</strong> Saving choices on behalf of the student will register their elective lock-in. Any previously saved time or faculty preferences for this student will be reset if enrolled courses change.
                </div>
              </div>
            </form>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "12px 20px",
            borderTop: "1px solid #e2e8f0",
            background: "#f8fafc",
            display: "flex",
            justifyContent: "flex-end",
            gap: 10,
          }}
        >
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            style={{
              padding: "7px 14px",
              background: "#fff",
              border: "1px solid #cbd5e1",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              color: "#475569",
              cursor: saving ? "not-allowed" : "pointer",
            }}
          >
            Cancel
          </button>
          <button
            type="submit"
            form="admin-override-lockin-form"
            disabled={saving || loading || choiceTags.length === 0 || !allTagsSelected}
            style={{
              padding: "7px 18px",
              background: saving || loading || choiceTags.length === 0 || !allTagsSelected ? "#94a3b8" : "#185FA5",
              border: "none",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              color: "#fff",
              cursor: saving || loading || choiceTags.length === 0 || !allTagsSelected ? "not-allowed" : "pointer",
            }}
          >
            {saving ? "Saving..." : "Save & Lock In Choice"}
          </button>
        </div>
      </div>
    </div>
  );
}
