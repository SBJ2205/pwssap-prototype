import { useCallback, useEffect, useState } from "react";
import {
  getStudentAvailableChoices,
  getStudentLockIn,
  getStudentEnrolledSubjects,
} from "../../api/catalog";
import { apiErrorMessage } from "../../api/client";
import { Badge } from "../../components/ui";

export default function StudentLockIn({ studentRoll, onNavigate }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [semester, setSemester] = useState(null);
  const [availableChoices, setAvailableChoices] = useState({});
  const [electiveSubjects, setElectiveSubjects] = useState([]);
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

      const currentLocked = lockRes?.locked_in || {};
      setLockedInChoices(currentLocked);
      setIsComplete(Boolean(lockRes?.complete));
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

  const choiceTags = Object.keys(availableChoices);

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


      <div style={{
        background: "#eff6ff",
        border: "1px solid #bfdbfe",
        borderRadius: 8,
        padding: "14px 18px",
        marginBottom: 24,
        fontSize: 13,
        color: "#1e40af",
        lineHeight: 1.5,
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
      }}>
        <span style={{ fontSize: 18 }}>ℹ️</span>
        <div>
          <strong style={{ color: "#1e3a8a" }}>Department Notice:</strong> Elective courses are allocated centrally by department administration. Contact your coordinator for change requests.
        </div>
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
            All subjects in Semester {semester} are core curriculum subjects. No elective allocation is required.
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
        <div>
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {choiceTags.map((tag) => {
              const subtags = availableChoices[tag] || [];
              const allocatedSubtag = lockedInChoices[tag];

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
                  <div style={{ marginBottom: 16, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                    <div>
                      <h2 style={{ margin: "0 0 4px", fontSize: 16, fontWeight: 700, color: "#0f172a" }}>
                        {tag.replace(/_/g, " ").toUpperCase()}
                      </h2>
                      <span style={{ fontSize: 12, color: "#64748b" }}>
                        Centralized department elective track allocation
                      </span>
                    </div>
                    {allocatedSubtag ? (
                      <Badge color="green">✓ Allocated: {allocatedSubtag}</Badge>
                    ) : (
                      <Badge color="amber">Pending Allocation</Badge>
                    )}
                  </div>

                  {allocatedSubtag ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      <div
                        style={{
                          border: "1.5px solid #22c55e",
                          borderRadius: 8,
                          padding: 16,
                          background: "#f0fdf4",
                        }}
                      >
                        <div style={{ fontWeight: 700, fontSize: 15, color: "#166534", marginBottom: 6 }}>
                          Track: {allocatedSubtag}
                        </div>
                        {electiveSubjects
                          .filter(
                            s => s.subject_tag === tag && (s.subtag || "")
                              .split("|")
                              .map(v => v.trim())
                              .includes(allocatedSubtag)
                          )
                          .map(s => (
                            <div key={s.subject_code} style={{ fontSize: 13, color: "#1f2937", marginTop: 4 }}>
                              <strong>{s.subject_code}</strong>: {s.subject_name}
                              <div style={{ fontSize: 11, color: "#4b5563", marginTop: 2 }}>
                                {s.weekly_hours}h/wk ({s.type}) · Section Capacity: {s.capacity}
                                {s.weekly_hours === 3 && " · (2h lecture + 1h remainder)"}
                              </div>
                            </div>
                          ))}
                      </div>

                      {subtags.length > 1 && (
                        <div style={{ fontSize: 12, color: "#64748b", marginTop: 4 }}>
                          Other tracks in this group: {subtags.filter(st => st !== allocatedSubtag).join(", ")}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div>
                      <p style={{ margin: "0 0 10px", fontSize: 13, color: "#64748b" }}>
                        Department administration has not yet imported allocations for this elective group.
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                        {subtags.map(st => (
                          <span
                            key={st}
                            style={{
                              background: "#f1f5f9",
                              padding: "4px 10px",
                              borderRadius: 6,
                              fontSize: 12,
                              color: "#475569",
                              fontFamily: "monospace",
                            }}
                          >
                            {st}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div style={{ marginTop: 24, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
            <div style={{ fontSize: 13 }}>
              {isComplete ? (
                <span style={{ color: "#166534", fontWeight: 600 }}>
                  ✓ All elective courses have been allocated and confirmed.
                </span>
              ) : (
                <span style={{ color: "#b45309" }}>
                  ⏳ Awaiting central elective allocation by department administration.
                </span>
              )}
            </div>

            {onNavigate && (
              <button
                type="button"
                onClick={() => onNavigate("student-prefs")}
                style={{
                  padding: "9px 20px",
                  background: "#185FA5",
                  color: "#fff",
                  border: "none",
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Proceed to Time Preferences →
              </button>
            )}
          </div>
        </div>
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
