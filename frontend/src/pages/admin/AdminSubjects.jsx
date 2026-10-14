import { useCallback, useEffect, useState, useMemo } from "react";
import { clearSubjects, getSubjects, importSubjects } from "../../api/catalog";
import { getCycleStatus, setCycleChoiceTags } from "../../api/cycle";
import { apiErrorMessage, getApiErrorDetails } from "../../api/client";
import { downloadCsv, parseCsvText, SUBJECT_CSV_TEMPLATE } from "../../utils/csv";
import { ALL_SEMESTERS, td } from "../../constants";
import { Card, PageHeader, Badge, InfoBox, MetricsRow } from "../../components/ui";

export default function AdminSubjects({ refreshCycle, reload }) {
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // File upload state
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(null);
  const [uploadErrors, setUploadErrors] = useState(null); // { message, row_errors: [...] }

  // Filters
  const [selectedSemester, setSelectedSemester] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");

  async function loadCatalog() {
    setLoading(true);
    setError(null);
    try {
      const data = await getSubjects();
      setSubjects(data || []);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadCatalog();
  }, []);

  function handleFileSelect(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setUploadErrors(null);
    setUploadSuccess(null);

    const reader = new FileReader();
    reader.onload = evt => {
      const text = evt.target?.result;
      if (typeof text === "string") {
        const parsed = parseCsvText(text, 10);
        setPreviewData(parsed);
      }
    };
    reader.readAsText(file, "UTF-8");
  }

  async function handleImport() {
    if (!selectedFile) return;
    setUploading(true);
    setUploadErrors(null);
    setUploadSuccess(null);

    try {
      const res = await importSubjects(selectedFile);
      setUploadSuccess(`Successfully imported ${res.count} subjects across semester(s): ${res.semesters?.join(", ")}!`);
      setSelectedFile(null);
      setPreviewData(null);
      await loadCatalog();
      if (refreshCycle) await refreshCycle();
      if (reload) reload();
    } catch (err) {
      const details = getApiErrorDetails(err);
      if (details?.row_errors) {
        setUploadErrors(details);
      } else {
        setUploadErrors({ message: apiErrorMessage(err), row_errors: [] });
      }
    } finally {
      setUploading(false);
    }
  }

  async function handleClearCatalog() {
    const confirmed = window.confirm(
      "Clear every subject from the catalog? This also removes generated sections, solver cycles, teacher capabilities, and elective configuration. Students and teachers will remain."
    );
    if (!confirmed) return;

    setError(null);
    setUploadSuccess(null);
    try {
      const result = await clearSubjects();
      setSubjects([]);
      setUploadSuccess(`Cleared ${result.cleared_count} subject(s). Upload the replacement CSV to continue.`);
      if (refreshCycle) await refreshCycle();
      if (reload) reload();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  const filteredSubjects = useMemo(() => {
    return subjects.filter(s => {
      if (selectedSemester !== "all" && s.semester !== Number(selectedSemester)) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesCode = s.subject_code.toLowerCase().includes(q);
        const matchesName = s.subject_name.toLowerCase().includes(q);
        const matchesTag = (s.subject_tag || "").toLowerCase().includes(q);
        const matchesSubtag = (s.subtag || "").toLowerCase().includes(q);
        const matchesType = (s.type || "").toLowerCase().includes(q);
        if (!matchesCode && !matchesName && !matchesTag && !matchesSubtag && !matchesType) {
          return false;
        }
      }
      return true;
    });
  }, [subjects, selectedSemester, searchQuery]);

  const theoryCount = subjects.filter(s => s.type === "theory").length;
  const labCount = subjects.filter(s => s.type === "lab").length;
  const distinctTags = new Set(subjects.map(s => s.subject_tag).filter(Boolean)).size;
  const totalCapacity = subjects.reduce((sum, s) => sum + (s.capacity || 0), 0);

  return (
    <div>
      <PageHeader
        title="Subject Catalog"
        sub="Department-level course offerings, weekly hours, capacities, and scheduling patterns."
      />

      <InfoBox title="CSV Import Rules">
        The subject CSV is imported on an <strong>all-or-nothing</strong> basis: if any row contains invalid data
        (unknown type, missing fields, non-numeric values), the entire file is rejected and row-level errors are
        displayed below so you can correct the CSV in one pass.
      </InfoBox>

      {/* Metrics */}
      <MetricsRow
        items={[
          { val: subjects.length, label: "Total Subjects", tip: "Count of all subjects imported in the catalog." },
          { val: theoryCount, label: "Theory Courses", tip: "Courses with standard lecture slot structures." },
          { val: labCount, label: "Lab Courses", tip: "Hands-on courses with 2-hour lab slot assignments." },
          { val: distinctTags, label: "Distinct Tags", tip: "Distinct tags like CORE, PE1, MDM for choice-based selection." },
          { val: totalCapacity, label: "Total Seat Capacity", tip: "Sum of capacities across all subject offerings." },
        ]}
      />

      {/* Import & Template Card */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 10 }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Import Subjects via CSV</div>
            <div style={{ fontSize: 12, color: "#777" }}>
              Columns required: <code style={{ background: "#f1efe8", padding: "1px 4px", borderRadius: 3 }}>subject_code, subject_name, subject_tag, subtag, semester, type, weekly_hours, capacity</code>
            </div>
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button
            onClick={handleClearCatalog}
            disabled={uploading || subjects.length === 0}
            style={{
              padding: "6px 12px",
              background: uploading || subjects.length === 0 ? "#eee" : "#FCEBEB",
              color: uploading || subjects.length === 0 ? "#aaa" : "#791F1F",
              border: "1px solid #F7C1C1",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: uploading || subjects.length === 0 ? "not-allowed" : "pointer",
            }}
          >
            Clear All Subjects
          </button>
          <button
            onClick={() => downloadCsv("subject_template.csv", SUBJECT_CSV_TEMPLATE)}
            style={{
              padding: "6px 14px",
              background: "#f1efe8",
              border: "1px solid #d1cfc7",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            📥 Download Template CSV
          </button>
          </div>
        </div>

        {/* File input & action */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
          <input
            type="file"
            accept=".csv"
            onChange={handleFileSelect}
            style={{ fontSize: 13 }}
          />
          {selectedFile && (
            <button
              onClick={handleImport}
              disabled={uploading}
              style={{
                padding: "8px 20px",
                background: uploading ? "#aaa" : "#185FA5",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                fontSize: 13,
                fontWeight: 600,
                cursor: uploading ? "not-allowed" : "pointer",
              }}
            >
              {uploading ? "Importing…" : "Upload & Commit"}
            </button>
          )}
        </div>

        {/* Success message */}
        {uploadSuccess && (
          <div style={{ background: "#EAF3DE", border: "1px solid #C0DD97", borderRadius: 6, padding: "10px 14px", fontSize: 13, color: "#27500A", marginBottom: 12 }}>
            ✓ {uploadSuccess}
          </div>
        )}

        {/* Server Validation Errors */}
        {uploadErrors && (
          <div style={{ background: "#FCEBEB", border: "1px solid #F7C1C1", borderRadius: 8, padding: "12px 16px", fontSize: 13, color: "#791F1F", marginBottom: 12 }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>
              ✕ Import Rejected: {uploadErrors.message || "Please resolve the errors below and re-upload."}
            </div>
            {uploadErrors.row_errors?.length > 0 && (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, marginTop: 8, background: "#fff", borderRadius: 6, overflow: "hidden" }}>
                <thead>
                  <tr style={{ background: "#F7D8D8", textAlign: "left" }}>
                    <th style={{ padding: "6px 10px", width: 80 }}>Row #</th>
                    <th style={{ padding: "6px 10px" }}>Errors</th>
                  </tr>
                </thead>
                <tbody>
                  {uploadErrors.row_errors.map((err, idx) => (
                    <tr key={idx} style={{ borderBottom: "1px solid #FCEBEB" }}>
                      <td style={{ padding: "6px 10px", fontWeight: 600 }}>{err.row === 0 ? "File" : `Row ${err.row}`}</td>
                      <td style={{ padding: "6px 10px" }}>{err.errors?.join("; ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* Preview of selected CSV */}
        {previewData && (
          <div style={{ marginTop: 12, borderTop: "1px solid #eee", paddingTop: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "#555", marginBottom: 6 }}>
              CSV Preview (Showing first {previewData.rows.length} of {previewData.totalRows} data rows):
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, background: "#faf9f6" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #ddd" }}>
                    {previewData.header.map((h, i) => (
                      <th key={i} style={{ padding: "4px 8px", textAlign: "left", color: "#666" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {previewData.rows.map((row, rIdx) => (
                    <tr key={rIdx} style={{ borderBottom: "1px solid #eee" }}>
                      {row.map((cell, cIdx) => (
                        <td key={cIdx} style={{ padding: "4px 8px" }}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Card>

      {/* Cycle Elective Configuration */}
      <CycleElectiveConfigCard
        subjects={subjects}
        refreshCycle={refreshCycle}
        onConfigSaved={() => {
          loadCatalog();
          if (refreshCycle) refreshCycle();
        }}
      />

      {/* Catalog Display */}
      <Card>
        {/* Controls: Search & Semester Tabs */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
          {/* Semester Tabs */}
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            <button
              onClick={() => setSelectedSemester("all")}
              style={{
                padding: "4px 10px",
                borderRadius: 6,
                border: "1px solid",
                borderColor: selectedSemester === "all" ? "#185FA5" : "#ddd",
                background: selectedSemester === "all" ? "#E6F1FB" : "#fff",
                color: selectedSemester === "all" ? "#0C447C" : "#555",
                fontWeight: selectedSemester === "all" ? 600 : 400,
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              All ({subjects.length})
            </button>
            {ALL_SEMESTERS.map(sem => {
              const count = subjects.filter(s => s.semester === sem).length;
              if (count === 0) return null;
              return (
                <button
                  key={sem}
                  onClick={() => setSelectedSemester(String(sem))}
                  style={{
                    padding: "4px 10px",
                    borderRadius: 6,
                    border: "1px solid",
                    borderColor: selectedSemester === String(sem) ? "#185FA5" : "#ddd",
                    background: selectedSemester === String(sem) ? "#E6F1FB" : "#fff",
                    color: selectedSemester === String(sem) ? "#0C447C" : "#555",
                    fontWeight: selectedSemester === String(sem) ? 600 : 400,
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  Sem {sem} ({count})
                </button>
              );
            })}
          </div>

          {/* Search box */}
          <div>
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search code, name, tag, subtag…"
              style={{
                padding: "6px 12px",
                border: "1px solid #ccc",
                borderRadius: 6,
                fontSize: 13,
                width: 220,
              }}
            />
          </div>
        </div>

        {loading ? (
          <div style={{ padding: "24px 0", textAlign: "center", color: "#888" }}>⏳ Loading subjects…</div>
        ) : error ? (
          <div style={{ color: "#791F1F", padding: "12px 0" }}>✕ {error}</div>
        ) : filteredSubjects.length === 0 ? (
          <div style={{ padding: "24px 0", textAlign: "center", color: "#888", fontSize: 13 }}>
            {subjects.length === 0 ? "No subjects imported yet. Upload a CSV above." : "No subjects match your current filter."}
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f9f8f5", borderBottom: "1.5px solid #e0ddd8" }}>
                  <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Code</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Subject Name</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Tag</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Subtag</th>
                  <th style={{ textAlign: "center", padding: "8px 10px", color: "#555" }}>Semester</th>
                  <th style={{ textAlign: "center", padding: "8px 10px", color: "#555" }}>Type</th>
                  <th style={{ textAlign: "center", padding: "8px 10px", color: "#555" }}>Weekly Hrs</th>
                  <th style={{ textAlign: "center", padding: "8px 10px", color: "#555" }}>Capacity</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Structure</th>
                </tr>
              </thead>
              <tbody>
                {filteredSubjects.map(s => (
                  <tr key={s.subject_code} style={{ borderBottom: "1px solid #f0efeb" }}>
                    <td style={{ ...td, fontWeight: 700 }}>
                      <code style={{ background: "#f1efe8", padding: "2px 6px", borderRadius: 4 }}>
                        {s.subject_code}
                      </code>
                    </td>
                    <td style={{ ...td, fontWeight: 500 }}>{s.subject_name}</td>
                    <td style={td}>
                      <Badge color={s.subject_tag === "program_core" || s.subject_tag === "CORE" ? "blue" : "amber"}>
                        {s.subject_tag || "—"}
                      </Badge>
                    </td>
                    <td style={{ ...td, color: "#64748b" }}>
                      {s.subtag ? (
                        <span style={{ background: "#f1f5f9", padding: "2px 6px", borderRadius: 4, fontWeight: 500 }}>
                          {s.subtag}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td style={{ ...td, textAlign: "center" }}>Sem {s.semester}</td>
                    <td style={{ ...td, textAlign: "center" }}>
                      <Badge color={s.type === "lab" ? "amber" : "green"}>
                        {s.type === "lab" ? "Lab" : "Theory"}
                      </Badge>
                    </td>
                    <td style={{ ...td, textAlign: "center" }}>
                      {s.weekly_hours}h
                      {s.weekly_hours === 3 && (
                        <span style={{ display: "block", fontSize: 10, color: "#0284c7" }}>2h + 1h rem</span>
                      )}
                    </td>
                    <td style={{ ...td, textAlign: "center", fontWeight: 600 }}>{s.capacity}</td>
                    <td style={{ ...td, color: "#777", fontSize: 11 }}>
                      {s.weekly_hours === 3 ? "2+1" : (s.slot_structure || "Standard")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function CycleElectiveConfigCard({ subjects, onConfigSaved, refreshCycle }) {
  const [cycleData, setCycleData] = useState(null);
  const [tagMap, setTagMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);

  const fetchCycleData = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    getCycleStatus()
      .then(data => {
        if (cancelled) return;
        setCycleData(data);
        const tags = data?.tags_detail || data?.choice_tags || [];
        const map = {};
        tags.forEach(t => {
          map[t.tag] = Boolean(t.is_choice_based);
        });
        setTagMap(map);
      })
      .catch(e => {
        if (!cancelled) setErr(apiErrorMessage(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    const cancel = fetchCycleData();
    return () => {
      if (typeof cancel === "function") cancel();
    };
  }, [fetchCycleData, subjects]);

  const handleToggle = (tag) => {
    setTagMap(prev => ({
      ...prev,
      [tag]: !prev[tag],
    }));
    setMsg(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setMsg(null);
    setErr(null);
    try {
      const updated = await setCycleChoiceTags(tagMap);
      setCycleData(updated);
      setMsg("Cycle elective tag configuration saved successfully!");
      if (onConfigSaved) onConfigSaved();
      if (refreshCycle) refreshCycle();
    } catch (e) {
      setErr(apiErrorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const tagsDetail = cycleData?.tags_detail || cycleData?.choice_tags || [];

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 8 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15, color: "#0f172a" }}>
            Cycle Elective Choice Configuration
          </div>
          <div style={{ fontSize: 12, color: "#64748b" }}>
            Configure which subject tags represent student electives. Students lock in exactly one subtag for each choice tag.
          </div>
        </div>
        {tagsDetail.length > 0 && (
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              background: "#185FA5",
              color: "#fff",
              border: "none",
              borderRadius: 6,
              padding: "6px 14px",
              fontSize: 12,
              fontWeight: 600,
              cursor: saving ? "not-allowed" : "pointer",
            }}
          >
            {saving ? "Saving…" : "Save Elective Config"}
          </button>
        )}
      </div>

      {msg && (
        <div style={{ background: "#EAF3DE", border: "1px solid #C0DD97", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#27500A", marginBottom: 12 }}>
          ✓ {msg}
        </div>
      )}
      {err && (
        <div style={{ background: "#FCEBEB", border: "1px solid #F7C1C1", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#791F1F", marginBottom: 12 }}>
          ✕ {err}
        </div>
      )}

      {loading ? (
        <div style={{ fontSize: 12, color: "#888", padding: "8px 0" }}>Loading cycle tag configurations…</div>
      ) : tagsDetail.length === 0 ? (
        <div style={{ fontSize: 12, color: "#64748b", padding: "8px 0" }}>
          No subject tags found in catalog. Upload subjects above to configure electives.
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
          {tagsDetail.map(t => {
            const isChoice = Boolean(tagMap[t.tag]);
            return (
              <div
                key={t.tag}
                onClick={() => handleToggle(t.tag)}
                style={{
                  border: `1.5px solid ${isChoice ? "#185FA5" : "#e2e8f0"}`,
                  borderRadius: 8,
                  padding: "10px 14px",
                  background: isChoice ? "#f0f7ff" : "#fff",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  transition: "all 0.15s ease",
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: isChoice ? "#185FA5" : "#1e293b" }}>
                    {t.tag}
                  </div>
                  <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
                    {t.subtags?.length > 0 ? (
                      <span>Subtags: {t.subtags.join(", ")}</span>
                    ) : (
                      <span>No subtags defined</span>
                    )}
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={isChoice}
                  onChange={() => handleToggle(t.tag)}
                  style={{ cursor: "pointer", width: 16, height: 16 }}
                />
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
