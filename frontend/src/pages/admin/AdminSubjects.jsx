import { useEffect, useState, useMemo } from "react";
import { getSubjects, importSubjects } from "../../api/catalog";
import { apiErrorMessage, getApiErrorDetails } from "../../api/client";
import { downloadCsv, parseCsvText, SUBJECT_CSV_TEMPLATE } from "../../utils/csv";
import { ALL_SEMESTERS, td } from "../../constants";
import { Card, PageHeader, Badge, InfoBox, MetricsRow } from "../../components/ui";

export default function AdminSubjects() {
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
        const matchesType = (s.type || "").toLowerCase().includes(q);
        if (!matchesCode && !matchesName && !matchesTag && !matchesType) {
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
              Columns required: <code style={{ background: "#f1efe8", padding: "1px 4px", borderRadius: 3 }}>subject_code, subject_name, subject_tag, semester, type, weekly_hours, capacity</code>
            </div>
          </div>

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

      {/* Catalog Display */}
      <Card>
        {/* Controls: Search & Semester Tabs */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
          {/* Semester Tabs */}
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            <button
              onClick={() => setSelectedSemester("all")}
              style={{
                padding: "5px 12px",
                borderRadius: 6,
                border: "1px solid #d1cfc7",
                background: selectedSemester === "all" ? "#185FA5" : "#fff",
                color: selectedSemester === "all" ? "#fff" : "#444",
                fontWeight: selectedSemester === "all" ? 600 : 400,
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              All Semesters ({subjects.length})
            </button>
            {ALL_SEMESTERS.map(sem => {
              const count = subjects.filter(s => s.semester === sem).length;
              return (
                <button
                  key={sem}
                  onClick={() => setSelectedSemester(sem)}
                  style={{
                    padding: "5px 10px",
                    borderRadius: 6,
                    border: "1px solid #d1cfc7",
                    background: selectedSemester === sem ? "#185FA5" : "#fff",
                    color: selectedSemester === sem ? "#fff" : "#444",
                    fontWeight: selectedSemester === sem ? 600 : 400,
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
              placeholder="Search code, name, tag…"
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
                  <th style={{ textAlign: "center", padding: "8px 10px", color: "#555" }}>Semester</th>
                  <th style={{ textAlign: "center", padding: "8px 10px", color: "#555" }}>Type</th>
                  <th style={{ textAlign: "center", padding: "8px 10px", color: "#555" }}>Weekly Hrs</th>
                  <th style={{ textAlign: "center", padding: "8px 10px", color: "#555" }}>Capacity</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Slot Structure</th>
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
                      <Badge color={s.subject_tag === "CORE" ? "blue" : "amber"}>
                        {s.subject_tag || "—"}
                      </Badge>
                    </td>
                    <td style={{ ...td, textAlign: "center" }}>Sem {s.semester}</td>
                    <td style={{ ...td, textAlign: "center" }}>
                      <Badge color={s.type === "lab" ? "amber" : "green"}>
                        {s.type === "lab" ? "Lab" : "Theory"}
                      </Badge>
                    </td>
                    <td style={{ ...td, textAlign: "center" }}>{s.weekly_hours}h</td>
                    <td style={{ ...td, textAlign: "center", fontWeight: 600 }}>{s.capacity}</td>
                    <td style={{ ...td, color: "#777", fontSize: 11 }}>
                      {s.slot_structure || "Standard"}
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
