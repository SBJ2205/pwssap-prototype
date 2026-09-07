import { useEffect, useState, useMemo } from "react";
import {
  getStudents,
  importStudents,
  getStudentLockIn,
  getStudentEnrolledSubjects,
} from "../../api/catalog";
import { getTimePrefs, getFacultyPrefs } from "../../api/preferences";
import { apiErrorMessage, getApiErrorDetails } from "../../api/client";
import { downloadCsv, parseCsvText, generateStudentCsvTemplate } from "../../utils/csv";
import { td, RATING_META } from "../../constants";
import { Card, PageHeader, Badge, InfoBox } from "../../components/ui";
import StudentLockInOverrideModal from "../../components/StudentLockInOverrideModal";

export default function AdminStudents({
  reload,
}) {
  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [overrideModalStudent, setOverrideModalStudent] = useState(null);

  // File upload state
  const [selectedFile, setSelectedFile] = useState(null);
  const [previewData, setPreviewData] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadSuccess, setUploadSuccess] = useState(null);
  const [uploadErrors, setUploadErrors] = useState(null);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSemester, setSelectedSemester] = useState("all");

  // Selected student for preferences inspection
  const [inspectStudent, setInspectStudent] = useState(null);
  const [studentLockIn, setStudentLockIn] = useState(null);
  const [studentEnrolled, setStudentEnrolled] = useState([]);
  const [studentTimePrefs, setStudentTimePrefs] = useState(null);
  const [studentFacultyPrefs, setStudentFacultyPrefs] = useState(null);
  const [inspectLoading, setInspectLoading] = useState(false);

  async function loadStudentRoster() {
    setLoading(true);
    setError(null);
    try {
      const data = await getStudents();
      setStudents(data || []);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadStudentRoster();
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
      const res = await importStudents(selectedFile);
      setUploadSuccess(`Successfully imported ${res.count} student(s) across department cohorts!`);
      setSelectedFile(null);
      setPreviewData(null);
      await loadStudentRoster();
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

  // Load preferences, lock-in, and enrolled subjects when inspecting a student
  async function openStudentInspector(student) {
    setInspectStudent(student);
    setInspectLoading(true);
    setStudentLockIn(null);
    setStudentEnrolled([]);
    setStudentTimePrefs(null);
    setStudentFacultyPrefs(null);

    try {
      const [lockData, enrolledData, tp, fp] = await Promise.all([
        getStudentLockIn(student.roll_number).catch(() => null),
        getStudentEnrolledSubjects(student.roll_number).catch(() => []),
        getTimePrefs(student.roll_number).catch(() => null),
        getFacultyPrefs(student.roll_number).catch(() => null),
      ]);
      if (lockData) setStudentLockIn(lockData);
      if (enrolledData) setStudentEnrolled(enrolledData);
      if (tp) setStudentTimePrefs(tp.preferences || {});
      if (fp) setStudentFacultyPrefs(fp.preferences || {});
    } finally {
      setInspectLoading(false);
    }
  }

  const filteredStudents = useMemo(() => {
    return students.filter(s => {
      if (selectedSemester !== "all" && s.semester !== Number(selectedSemester)) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesRoll = s.roll_number.toLowerCase().includes(q);
        const matchesName = s.name.toLowerCase().includes(q);
        if (!matchesRoll && !matchesName) return false;
      }
      return true;
    });
  }, [students, selectedSemester, searchQuery]);

  return (
    <div>
      <PageHeader
        title="Student Roster & Elective Choices"
        sub="Ingest department student cohorts and inspect elective lock-ins and preference submissions."
      />

      <InfoBox title="Department Student Roster">
        Student CSV import accepts students belonging to any active semester in the department with columns:{" "}
        <code style={{ background: "#f1efe8", padding: "1px 4px", borderRadius: 3 }}>
          roll_number, name, semester
        </code>.
        Elective courses are locked in directly by students via their portal based on defined subtags rather than numeric CSV columns.
      </InfoBox>

      {/* CSV Import Card */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 10 }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>
              Import Students Roster
            </div>
            <div style={{ fontSize: 12, color: "#777" }}>
              Expected columns:{" "}
              <code style={{ background: "#f1efe8", padding: "1px 4px", borderRadius: 3 }}>
                roll_number, name, semester
              </code>
            </div>
          </div>

          <button
            onClick={() => {
              const content = generateStudentCsvTemplate();
              downloadCsv("students_template.csv", content);
            }}
            style={{
              padding: "5px 12px",
              background: "#fff",
              border: "1px solid #d1cfc7",
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            ↓ Download Template
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
              {uploading ? "Importing…" : "Upload Student Roster"}
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

      {/* Roster Display and Inspector */}
      <div style={{ display: "grid", gridTemplateColumns: inspectStudent ? "1.2fr 1fr" : "1fr", gap: 16 }}>
        {/* Student Table */}
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "#666" }}>Semester:</span>
              <select
                value={selectedSemester}
                onChange={e => setSelectedSemester(e.target.value)}
                style={{ padding: "4px 8px", borderRadius: 6, border: "1px solid #ccc", fontSize: 12 }}
              >
                <option value="all">All Semesters</option>
                {[3, 4, 5, 6, 7, 8].map(s => (
                  <option key={s} value={s}>Semester {s}</option>
                ))}
              </select>
            </div>

            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search roll number or name…"
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
            <div style={{ padding: "24px 0", textAlign: "center", color: "#888" }}>⏳ Loading students…</div>
          ) : error ? (
            <div style={{ color: "#791F1F", padding: "12px 0" }}>✕ {error}</div>
          ) : filteredStudents.length === 0 ? (
            <div style={{ padding: "24px 0", textAlign: "center", color: "#888", fontSize: 13 }}>
              {students.length === 0 ? "No students in the roster yet. Upload a CSV above." : "No students match your search."}
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ background: "#f9f8f5", borderBottom: "1.5px solid #e0ddd8" }}>
                    <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Roll Number</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", color: "#555" }}>Student Name</th>
                    <th style={{ textAlign: "center", padding: "8px 10px", color: "#555" }}>Semester</th>
                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#555" }}>Preferences</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredStudents.map(s => {
                    const isSelected = inspectStudent?.roll_number === s.roll_number;
                    return (
                      <tr
                        key={s.roll_number}
                        style={{
                          borderBottom: "1px solid #f0efeb",
                          background: isSelected ? "#F4F8FC" : "transparent",
                        }}
                      >
                        <td style={{ ...td, fontWeight: 700 }}>
                          <code style={{ background: "#f1efe8", padding: "2px 6px", borderRadius: 4 }}>
                            {s.roll_number}
                          </code>
                        </td>
                        <td style={{ ...td, fontWeight: 500 }}>{s.name}</td>
                        <td style={{ ...td, textAlign: "center" }}>Sem {s.semester}</td>
                        <td style={{ ...td, textAlign: "right" }}>
                          <button
                            onClick={() => openStudentInspector(s)}
                            style={{
                              padding: "4px 10px",
                              background: isSelected ? "#185FA5" : "#f1efe8",
                              color: isSelected ? "#fff" : "#185FA5",
                              border: "1px solid #d1cfc7",
                              borderRadius: 6,
                              fontSize: 12,
                              fontWeight: 500,
                              cursor: "pointer",
                            }}
                          >
                            {isSelected ? "Inspecting" : "Inspect →"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Student Inspector Drawer */}
        {inspectStudent && (
          <Card>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 15, color: "#111" }}>{inspectStudent.name}</div>
                <div style={{ fontSize: 12, color: "#777" }}>
                  <code style={{ background: "#f1efe8", padding: "1px 4px", borderRadius: 3 }}>{inspectStudent.roll_number}</code> · Semester {inspectStudent.semester}
                </div>
              </div>
              <button
                onClick={() => setInspectStudent(null)}
                style={{ background: "transparent", border: "none", fontSize: 16, cursor: "pointer", color: "#888" }}
              >
                ✕
              </button>
            </div>

            {inspectLoading ? (
              <div style={{ padding: "20px 0", textAlign: "center", color: "#888" }}>⏳ Loading preferences…</div>
            ) : (
              <div>
                {/* Elective Lock-In Status & Subtags */}
                <div style={{ marginBottom: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <div style={{ fontWeight: 600, fontSize: 12, color: "#555", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                      Elective Lock-In
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {studentLockIn?.complete ? (
                        <Badge color="green">Complete</Badge>
                      ) : (
                        <Badge color="amber">Incomplete</Badge>
                      )}
                      <button
                        onClick={() => setOverrideModalStudent(inspectStudent)}
                        style={{
                          padding: "3px 8px",
                          background: "#185FA5",
                          color: "#fff",
                          border: "none",
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Override Choices →
                      </button>
                    </div>
                  </div>

                  {!studentLockIn || Object.keys(studentLockIn.locked_in || {}).length === 0 ? (
                    <div style={{ fontSize: 12, color: "#888", fontStyle: "italic" }}>
                      No elective choices locked in yet.
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      {Object.entries(studentLockIn.locked_in).map(([tag, subtag]) => (
                        <div key={tag} style={{ display: "flex", justifyContent: "space-between", background: "#f9f8f5", padding: "6px 10px", borderRadius: 6, fontSize: 12 }}>
                          <span style={{ fontWeight: 500, color: "#555" }}>{tag}:</span>
                          <span style={{ fontWeight: 600, color: "#185FA5" }}>
                            {subtag}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Enrolled Subjects */}
                {studentEnrolled.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontWeight: 600, fontSize: 12, color: "#555", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
                      Active Enrolled Subjects ({studentEnrolled.length})
                    </div>
                    <div style={{ maxHeight: 120, overflowY: "auto", display: "flex", flexDirection: "column", gap: 4 }}>
                      {studentEnrolled.map(s => (
                        <div key={s.subject_code} style={{ display: "flex", justifyContent: "space-between", background: "#f1f5f9", padding: "4px 8px", borderRadius: 4, fontSize: 11 }}>
                          <span style={{ fontWeight: 600, color: "#334155" }}>{s.subject_code}</span>
                          <span style={{ color: "#64748b" }}>{s.subject_name} ({s.weekly_hours}h)</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Time Preferences Summary */}
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontWeight: 600, fontSize: 12, color: "#555", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
                    Time-Slot Ratings
                  </div>
                  {studentTimePrefs && Object.keys(studentTimePrefs).length > 0 ? (
                    <div>
                      <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
                        {[
                          { label: "Preferred", count: Object.values(studentTimePrefs).filter(v => v === 1).length, color: "#27500A", bg: "#EAF3DE" },
                          { label: "Tolerable", count: Object.values(studentTimePrefs).filter(v => v === 2).length, color: "#0C447C", bg: "#E6F1FB" },
                          { label: "Disliked", count: Object.values(studentTimePrefs).filter(v => v === 3).length, color: "#633806", bg: "#FAEEDA" },
                          { label: "Blocked", count: Object.values(studentTimePrefs).filter(v => v === 4).length, color: "#791F1F", bg: "#FCEBEB" },
                        ].map(({ label, count, color, bg }) => (
                          <span key={label} style={{ background: bg, color, fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 10 }}>
                            {label}: {count}
                          </span>
                        ))}
                      </div>
                      <div style={{ maxHeight: 160, overflowY: "auto", border: "1px solid #eee", borderRadius: 6, padding: "4px 8px" }}>
                        {Object.entries(studentTimePrefs).map(([slotKey, rating]) => {
                          const m = RATING_META[rating] || RATING_META[0];
                          return (
                            <div key={slotKey} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 11, borderBottom: "1px solid #f5f4f0" }}>
                              <span style={{ color: "#555" }}>{slotKey}</span>
                              <span style={{ fontWeight: 600, color: m.color }}>{m.title}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: "#888", fontStyle: "italic" }}>
                      No time-slot preferences submitted yet (defaults to indifferent).
                    </div>
                  )}
                </div>

                {/* Faculty Preferences Summary */}
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12, color: "#555", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
                    Faculty Preferences
                  </div>
                  {studentFacultyPrefs && Object.keys(studentFacultyPrefs).length > 0 ? (
                    <div style={{ maxHeight: 180, overflowY: "auto", border: "1px solid #eee", borderRadius: 6, padding: "6px 8px" }}>
                      {Object.entries(studentFacultyPrefs).map(([subj, teachersMap]) => (
                        <div key={subj} style={{ marginBottom: 6 }}>
                          <div style={{ fontSize: 11, fontWeight: 700, color: "#333" }}>{subj}</div>
                          {Object.entries(teachersMap).map(([tid, rating]) => (
                            <div key={tid} style={{ display: "flex", justifyContent: "space-between", fontSize: 11, paddingLeft: 8, color: "#666" }}>
                              <span>Teacher {tid}:</span>
                              <Badge color={rating === 1 ? "green" : rating === 2 ? "blue" : "amber"}>
                                {rating === 1 ? "Preferred" : rating === 2 ? "Tolerable" : "Disliked"}
                              </Badge>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: "#888", fontStyle: "italic" }}>
                      No faculty rankings submitted yet.
                    </div>
                  )}
                </div>
              </div>
            )}
          </Card>
        )}
      </div>

      <StudentLockInOverrideModal
        student={overrideModalStudent}
        isOpen={Boolean(overrideModalStudent)}
        onClose={() => setOverrideModalStudent(null)}
        onSuccess={() => {
          if (inspectStudent) openStudentInspector(inspectStudent);
          if (reload) reload();
        }}
      />
    </div>
  );
}
