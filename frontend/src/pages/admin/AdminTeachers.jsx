import { useEffect, useState, useMemo } from "react";
import { getTeachers, getSubjects, importTeachers, getTeacherCapabilities } from "../../api/catalog";
import { apiErrorMessage, getApiErrorDetails } from "../../api/client";
import { downloadCsv, parseCsvText, TEACHER_CSV_TEMPLATE } from "../../utils/csv";
import { td } from "../../constants";
import { Card, PageHeader, InfoBox, MetricsRow } from "../../components/ui";

export default function AdminTeachers({ reload }) {
  const [teachers, setTeachers] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [capabilities, setCapabilities] = useState({}); // { [teacherId]: [subjectCode, ...] }
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // File upload state
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(null);
  const [uploadErrors, setUploadErrors] = useState(null);

  // Filter & search
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSubjectFilter, setSelectedSubjectFilter] = useState("all");

  async function loadTeacherData() {
    setLoading(true);
    setError(null);
    try {
      const [tData, sData] = await Promise.all([
        getTeachers(),
        getSubjects(),
      ]);
      setTeachers(tData || []);
      setSubjects(sData || []);

      // Fetch capabilities for each teacher
      const caps = {};
      await Promise.all(
        (tData || []).map(async t => {
          try {
            const res = await getTeacherCapabilities(t.teacher_id);
            caps[t.teacher_id] = res.subject_codes || [];
          } catch {
            caps[t.teacher_id] = [];
          }
        })
      );
      setCapabilities(caps);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadTeacherData();
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
      const res = await importTeachers(selectedFile);
      setUploadSuccess(`Successfully imported ${res.count} teachers with ${res.capabilities} subject capabilities!`);
      setSelectedFile(null);
      setPreviewData(null);
      await loadTeacherData();
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

  const subjectMap = useMemo(() => {
    return Object.fromEntries(subjects.map(s => [s.subject_code, s]));
  }, [subjects]);

  const filteredTeachers = useMemo(() => {
    return teachers.filter(t => {
      const caps = capabilities[t.teacher_id] || [];
      if (selectedSubjectFilter !== "all" && !caps.includes(selectedSubjectFilter)) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesId = t.teacher_id.toLowerCase().includes(q);
        const matchesName = t.teacher_name.toLowerCase().includes(q);
        const matchesSubj = caps.some(c => c.toLowerCase().includes(q));
        if (!matchesId && !matchesName && !matchesSubj) return false;
      }
      return true;
    });
  }, [teachers, capabilities, selectedSubjectFilter, searchQuery]);

  const totalCapsCount = Object.values(capabilities).reduce((sum, list) => sum + list.length, 0);

  return (
    <div>
      <PageHeader
        title="Teacher Roster & Capabilities"
        sub="Faculty profiles and their qualified course assignments across the department."
      />

      <InfoBox title="Teacher Capability Rules">
        The teacher CSV uses a flexible format: <code style={{ background: "#f1efe8", padding: "1px 4px", borderRadius: 3 }}>teacher_id, teacher_name</code>,
        followed by <strong>subject codes</strong> in subsequent cells (e.g. <code style={{ background: "#f1efe8", padding: "1px 4px", borderRadius: 3 }}>T001, Dr. Sharma, IT301, IT302</code>).
        <br />
        <strong>Prerequisite:</strong> Referenced subject codes must already exist in the Subject Catalog.
        Upload subjects first before importing teachers.
      </InfoBox>

      {/* Metrics */}
      <MetricsRow
        items={[
          { val: teachers.length, label: "Total Faculty", tip: "Count of all teachers imported." },
          { val: totalCapsCount, label: "Total Capabilities", tip: "Sum of all teacher-to-subject capability qualifications." },
          { val: teachers.length > 0 ? (totalCapsCount / teachers.length).toFixed(1) : 0, label: "Avg Subjects / Teacher", tip: "Average number of qualified subjects per teacher." },
          { val: subjects.length, label: "Subjects in Catalog", tip: "Total subjects available for capability mapping." },
        ]}
      />

      {/* Import & Template Card */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 10 }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Import Teachers via CSV</div>
            <div style={{ fontSize: 12, color: "#777" }}>
              Columns required: <code style={{ background: "#f1efe8", padding: "1px 4px", borderRadius: 3 }}>teacher_id, teacher_name, subject_1, subject_2, ...</code>
            </div>
          </div>

          <button
            onClick={() => downloadCsv("teachers_template.csv", TEACHER_CSV_TEMPLATE)}
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
              {uploading ? "Importing…" : "Upload & Map Capabilities"}
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

      {/* Roster & Capabilities List */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
          {/* Subject Filter */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#666" }}>Filter by Subject:</span>
            <select
              value={selectedSubjectFilter}
              onChange={e => setSelectedSubjectFilter(e.target.value)}
              style={{ padding: "5px 10px", borderRadius: 6, border: "1px solid #ccc", fontSize: 12 }}
            >
              <option value="all">All Subjects</option>
              {subjects.map(s => (
                <option key={s.subject_code} value={s.subject_code}>
                  {s.subject_code} — {s.subject_name}
                </option>
              ))}
            </select>
          </div>

          {/* Search box */}
          <input
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder="Search teacher ID, name, code…"
            style={{
              padding: "6px 12px",
              border: "1px solid #ccc",
              borderRadius: 6,
              fontSize: 13,
              width: 240,
            }}
          />
        </div>

        {loading ? (
          <div style={{ padding: "24px 0", textAlign: "center", color: "#888" }}>⏳ Loading teachers…</div>
        ) : error ? (
          <div style={{ color: "#791F1F", padding: "12px 0" }}>✕ {error}</div>
        ) : filteredTeachers.length === 0 ? (
          <div style={{ padding: "24px 0", textAlign: "center", color: "#888", fontSize: 13 }}>
            {teachers.length === 0 ? "No teachers imported yet. Upload a CSV above." : "No teachers match your search."}
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f9f8f5", borderBottom: "1.5px solid #e0ddd8" }}>
                  <th style={{ textAlign: "left", padding: "8px 10px", color: "#555", width: 120 }}>Teacher ID</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", color: "#555", width: 200 }}>Name</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Subject Capabilities</th>
                </tr>
              </thead>
              <tbody>
                {filteredTeachers.map(t => {
                  const caps = capabilities[t.teacher_id] || [];
                  return (
                    <tr key={t.teacher_id} style={{ borderBottom: "1px solid #f0efeb" }}>
                      <td style={{ ...td, fontWeight: 700 }}>
                        <code style={{ background: "#f1efe8", padding: "2px 6px", borderRadius: 4 }}>
                          {t.teacher_id}
                        </code>
                      </td>
                      <td style={{ ...td, fontWeight: 600 }}>{t.teacher_name}</td>
                      <td style={td}>
                        {caps.length === 0 ? (
                          <span style={{ color: "#aaa", fontSize: 12, fontStyle: "italic" }}>
                            No capabilities assigned
                          </span>
                        ) : (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                            {caps.map(code => {
                              const s = subjectMap[code];
                              return (
                                <span
                                  key={code}
                                  title={s ? `${s.subject_name} (${s.type}, Sem ${s.semester})` : code}
                                  style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: 4,
                                    background: "#F4F8FC",
                                    border: "1px solid #B5D4F4",
                                    borderRadius: 6,
                                    padding: "2px 8px",
                                    fontSize: 11,
                                    color: "#0C447C",
                                  }}
                                >
                                  <strong>{code}</strong>
                                  {s && <span style={{ color: "#666" }}>{s.subject_name}</span>}
                                </span>
                              );
                            })}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
