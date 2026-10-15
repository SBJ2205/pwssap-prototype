import { useEffect, useState } from "react";
import { downloadElectiveTemplate, importElectiveAllocations, getCycleStatus } from "../api/cycle";
import { apiErrorMessage } from "../api/client";
import { Badge } from "./ui";

export default function ElectiveAllocationsModal({
  isOpen,
  onClose,
  cycleData,
  refreshCycle,
  onNavigateToTeachers,
}) {
  const [internalCycle, setInternalCycle] = useState(null);
  const [downloadingSem, setDownloadingSem] = useState(null);
  const [uploadingSem, setUploadingSem] = useState(null);
  const [errorDetails, setErrorDetails] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [successMessage, setSuccessMessage] = useState(null);

  useEffect(() => {
    if (isOpen) {
      getCycleStatus()
        .then(data => setInternalCycle(data))
        .catch(() => {});
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const activeCycle = internalCycle || cycleData;
  const electiveSemesters = activeCycle?.elective_semesters || [];

  const handleDownload = async (sem) => {
    setDownloadingSem(sem);
    setErrorMessage(null);
    try {
      await downloadElectiveTemplate(sem);
    } catch (e) {
      setErrorMessage(apiErrorMessage(e));
    } finally {
      setDownloadingSem(null);
    }
  };

  const handleFileUpload = async (e, sem) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadingSem(sem);
    setErrorMessage(null);
    setErrorDetails(null);
    setSuccessMessage(null);

    try {
      const res = await importElectiveAllocations(file, sem);
      setSuccessMessage(`Successfully updated ${res.updated_count} student elective allocations for Semester ${sem}!`);
      try {
        const fresh = await getCycleStatus();
        setInternalCycle(fresh);
      } catch {
        // ignore
      }
      if (refreshCycle) refreshCycle();
    } catch (err) {
      const responseData = err?.response?.data;
      if (responseData?.detail && typeof responseData.detail === "object" && responseData.detail.errors) {
        setErrorMessage(responseData.detail.message || "Validation failed on some rows.");
        setErrorDetails(responseData.detail.errors);
      } else {
        setErrorMessage(apiErrorMessage(err));
      }
    } finally {
      setUploadingSem(null);
      e.target.value = "";
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "rgba(15, 23, 42, 0.6)",
        backdropFilter: "blur(3px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        style={{
          background: "#fff",
          borderRadius: 12,
          maxWidth: 780,
          width: "100%",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.2)",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "20px 24px 16px",
            borderBottom: "1px solid #e2e8f0",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
          }}
        >
          <div>
            <h2 style={{ margin: "0 0 4px", fontSize: 18, fontWeight: 700, color: "#0f172a" }}>
              Import Student Elective Allocations
            </h2>
            <p style={{ margin: 0, fontSize: 13, color: "#64748b" }}>
              Download pre-filled CSV templates with student roll numbers, enter their allocated elective track, and import in bulk.
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              fontSize: 20,
              color: "#94a3b8",
              cursor: "pointer",
              padding: "4px 8px",
              lineHeight: 1,
            }}
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: "20px 24px", overflowY: "auto", flex: 1 }}>
          {successMessage && (
            <div
              style={{
                background: "#f0fdf4",
                border: "1px solid #bbf7d0",
                borderRadius: 8,
                padding: "12px 16px",
                color: "#166534",
                fontSize: 13,
                marginBottom: 16,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div>✓ {successMessage}</div>
              <button
                onClick={() => setSuccessMessage(null)}
                style={{ background: "none", border: "none", color: "#166534", cursor: "pointer", fontSize: 14 }}
              >
                ✕
              </button>
            </div>
          )}

          {errorMessage && (
            <div
              style={{
                background: "#fef2f2",
                border: "1px solid #fecaca",
                borderRadius: 8,
                padding: "12px 16px",
                color: "#991b1b",
                fontSize: 13,
                marginBottom: 16,
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Error: {errorMessage}</div>
              {errorDetails && errorDetails.length > 0 && (
                <div style={{ marginTop: 8, maxHeight: 150, overflowY: "auto", fontSize: 12, background: "#fff", padding: 8, borderRadius: 4, border: "1px solid #fee2e2" }}>
                  {errorDetails.slice(0, 15).map((err, idx) => (
                    <div key={idx} style={{ marginBottom: 4 }}>
                      • <strong>Row {err.row}</strong> ({err.roll_number}): {err.error}
                    </div>
                  ))}
                  {errorDetails.length > 15 && (
                    <div style={{ color: "#64748b", fontStyle: "italic", marginTop: 4 }}>
                      ...and {errorDetails.length - 15} more errors.
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {electiveSemesters.length === 0 ? (
            <div style={{ padding: 32, textAlign: "center", color: "#64748b" }}>
              <p style={{ margin: "0 0 8px", fontWeight: 600, color: "#334155" }}>
                No active choice-based electives configured yet.
              </p>
              <p style={{ margin: 0, fontSize: 13 }}>
                Configure choice tags in the "Cycle Elective Choice Configuration" section above to enable elective allocation templates.
              </p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {electiveSemesters.map((semInfo) => {
                const sem = semInfo.semester;
                const isComplete = semInfo.is_complete;
                const progressText = `${semInfo.allocated_count} / ${semInfo.student_count} Allocated`;

                return (
                  <div
                    key={sem}
                    style={{
                      border: "1px solid #e2e8f0",
                      borderRadius: 10,
                      padding: 16,
                      background: isComplete ? "#f8fafc" : "#fff",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "#0f172a" }}>
                          Semester {sem}
                        </h3>
                        <Badge color={isComplete ? "green" : semInfo.allocated_count > 0 ? "amber" : "gray"}>
                          {progressText}
                        </Badge>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <button
                          type="button"
                          onClick={() => handleDownload(sem)}
                          disabled={downloadingSem === sem}
                          style={{
                            background: "#f1f5f9",
                            color: "#1e293b",
                            border: "1px solid #cbd5e1",
                            borderRadius: 6,
                            padding: "6px 12px",
                            fontSize: 12,
                            fontWeight: 600,
                            cursor: downloadingSem === sem ? "not-allowed" : "pointer",
                            display: "flex",
                            alignItems: "center",
                            gap: 6,
                          }}
                        >
                          {downloadingSem === sem ? "Downloading…" : "↓ Download Template (CSV)"}
                        </button>

                        <label
                          style={{
                            background: "#185FA5",
                            color: "#fff",
                            borderRadius: 6,
                            padding: "6px 14px",
                            fontSize: 12,
                            fontWeight: 600,
                            cursor: uploadingSem === sem ? "not-allowed" : "pointer",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 6,
                            opacity: uploadingSem === sem ? 0.7 : 1,
                          }}
                        >
                          {uploadingSem === sem ? "Uploading…" : "↑ Upload Allocations (CSV)"}
                          <input
                            type="file"
                            accept=".csv"
                            onChange={(e) => handleFileUpload(e, sem)}
                            disabled={uploadingSem === sem}
                            style={{ display: "none" }}
                          />
                        </label>
                      </div>
                    </div>

                    {/* Elective tags details */}
                    <div style={{ background: "#f8fafc", padding: "10px 12px", borderRadius: 6, fontSize: 12, color: "#475569" }}>
                      <div style={{ fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                        Configured Electives & Allowed Subtags:
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
                        {semInfo.tags.map((t) => (
                          <div key={t.tag} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <span style={{ fontWeight: 700, color: "#0f172a" }}>{t.tag}:</span>
                            <div style={{ display: "flex", gap: 4 }}>
                              {t.subtags.map((st) => (
                                <span
                                  key={st}
                                  style={{
                                    background: "#e2e8f0",
                                    padding: "2px 6px",
                                    borderRadius: 4,
                                    fontSize: 11,
                                    fontFamily: "monospace",
                                    color: "#1e293b",
                                  }}
                                >
                                  {st}
                                </span>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "14px 24px",
            borderTop: "1px solid #e2e8f0",
            background: "#f8fafc",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div style={{ fontSize: 12, color: "#64748b" }}>
            Need to change an individual student later? You can override choices via the Admin Dashboard.
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                background: "#fff",
                border: "1px solid #cbd5e1",
                borderRadius: 6,
                padding: "8px 16px",
                fontSize: 13,
                fontWeight: 600,
                color: "#334155",
                cursor: "pointer",
              }}
            >
              Close
            </button>
            {onNavigateToTeachers && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onNavigateToTeachers();
                }}
                style={{
                  background: "#0284c7",
                  border: "none",
                  borderRadius: 6,
                  padding: "8px 18px",
                  fontSize: 13,
                  fontWeight: 600,
                  color: "#fff",
                  cursor: "pointer",
                }}
              >
                Proceed to Teachers →
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
