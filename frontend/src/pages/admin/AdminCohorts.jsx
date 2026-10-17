import { useEffect, useState } from "react";
import {
  detectClusters,
  getCohortConfig,
  saveCohortConfig,
  deleteCohortConfig,
  generateTraditionalSections,
} from "../../api/cohorts";
import { Badge, Card, MetricsRow, PageHeader, Tooltip } from "../../components/ui";

const SEMESTERS = [4, 6];

export default function AdminCohorts({ setPage }) {
  const [semester, setSemester] = useState(6);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [clusterInfo, setClusterInfo] = useState(null);
  const [existingConfig, setExistingConfig] = useState(null);
  const [classesState, setClassesState] = useState([]);
  const [feedback, setFeedback] = useState(null);
  const [generationResult, setGenerationResult] = useState(null);

  useEffect(() => {
    loadData(semester);
  }, [semester]);

  async function loadData(sem) {
    setLoading(true);
    setFeedback(null);
    setGenerationResult(null);
    try {
      const [clusters, config] = await Promise.all([
        detectClusters(sem),
        getCohortConfig(sem),
      ]);
      setClusterInfo(clusters);
      setExistingConfig(config);

      if (config && config.classes && config.classes.length > 0) {
        setClassesState(config.classes);
      } else {
        // Auto-initialize suggested divisions from detected clusters
        initDefaultDivisions(clusters);
      }
    } catch (err) {
      setFeedback({ type: "error", message: `Failed to load cohort data: ${err.message}` });
    } finally {
      setLoading(false);
    }
  }

  function initDefaultDivisions(clusters) {
    if (!clusters || !clusters.clusters) return;
    const initialClasses = [];
    let divLetterCode = 65; // 'A'

    clusters.clusters.forEach((cl) => {
      const students = cl.students || [];
      const total = students.length;
      const numDivs = Math.max(1, Math.round(total / 60)) || 1;
      const perDiv = Math.ceil(total / numDivs);

      for (let d = 0; d < numDivs; d++) {
        const divLetter = String.fromCharCode(divLetterCode++);
        const slice = students.slice(d * perDiv, (d + 1) * perDiv);
        const rolls = slice.map((s) => s.roll_number);

        initialClasses.push({
          class_id: `Div-${divLetter}`,
          class_name: cl.track_id !== "ALL" ? `Division ${divLetter} (${cl.track_id})` : `Division ${divLetter}`,
          pe_tag: clusters.pe_tag,
          pe_subject_code: cl.subject_code,
          pe_subtag: cl.track_id !== "ALL" ? cl.track_id : null,
          student_rolls: rolls,
          lab_batch_count: 3, // Default Mumbai University standard (A1, A2, A3)
        });
      }
    });

    setClassesState(initialClasses);
  }

  function updateClassField(idx, field, value) {
    setClassesState((prev) => {
      const copy = [...prev];
      copy[idx] = { ...copy[idx], [field]: value };
      return copy;
    });
  }

  function addDivisionForCluster(trackId, subjectCode) {
    const divLetter = String.fromCharCode(65 + classesState.length);
    setClassesState((prev) => [
      ...prev,
      {
        class_id: `Div-${divLetter}`,
        class_name: trackId !== "ALL" ? `Division ${divLetter} (${trackId})` : `Division ${divLetter}`,
        pe_tag: clusterInfo?.pe_tag,
        pe_subject_code: subjectCode,
        pe_subtag: trackId !== "ALL" ? trackId : null,
        student_rolls: [],
        lab_batch_count: 3,
      },
    ]);
  }

  function removeDivision(idx) {
    setClassesState((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleSave() {
    setSaving(true);
    setFeedback(null);
    try {
      const payload = {
        semester,
        classes: classesState.map((c) => ({
          class_id: c.class_id,
          class_name: c.class_name,
          pe_tag: c.pe_tag,
          pe_subject_code: c.pe_subject_code,
          pe_subtag: c.pe_subtag,
          student_rolls: c.student_rolls,
          lab_batch_count: Number(c.lab_batch_count) || 3,
        })),
      };
      const res = await saveCohortConfig(payload);
      setExistingConfig(res.config);
      setClassesState(res.config.classes);
      setFeedback({
        type: "success",
        message: `Saved ${res.config.classes.length} divisions for Semester ${semester} with lab batches.`,
      });
    } catch (err) {
      setFeedback({ type: "error", message: `Save error: ${err.message}` });
    } finally {
      setSaving(false);
    }
  }

  async function handleGenerateSections() {
    setGenerating(true);
    setFeedback(null);
    try {
      // First auto-save configuration
      await handleSave();
      const res = await generateTraditionalSections(semester);
      setGenerationResult(res);
      setFeedback({
        type: "success",
        message: `Successfully generated ${res.sections_created} sections (-T and -L) and assigned ${res.students_assigned} students!`,
      });
    } catch (err) {
      setFeedback({ type: "error", message: `Section generation failed: ${err.message}` });
    } finally {
      setGenerating(false);
    }
  }

  if (loading) {
    return (
      <div style={{ padding: "32px 40px" }}>
        <PageHeader title="Traditional Cohorts & Batches" sub="Loading semester rosters and elective tracks..." />
      </div>
    );
  }

  const totalStudents = clusterInfo?.total_students || 0;
  const assignedStudents = classesState.reduce((sum, c) => sum + (c.student_rolls?.length || 0), 0);
  const unassignedCount = totalStudents - assignedStudents;

  return (
    <div style={{ padding: "32px 40px", maxWidth: 1100, margin: "0 auto" }}>
      <PageHeader
        title="Traditional Division & Batch Setup"
        sub="Configure fixed classes (Div A, Div B...) and lab batches (A1..A3 or A1..A4) for departmental scheduling."
      />

      {/* Semester Switcher Tabs */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
        {SEMESTERS.map((s) => (
          <button
            key={s}
            onClick={() => setSemester(s)}
            style={{
              padding: "8px 18px",
              borderRadius: 8,
              border: semester === s ? "2px solid #185FA5" : "1px solid #dcdad5",
              background: semester === s ? "#E6F1FB" : "#fff",
              color: semester === s ? "#185FA5" : "#555",
              fontWeight: 600,
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            Semester {s}
          </button>
        ))}
      </div>

      {/* Metrics Row */}
      <MetricsRow
        items={[
          { val: totalStudents, label: `Total Students (Sem ${semester})` },
          { val: classesState.length, label: "Classes / Divisions" },
          {
            val: classesState.reduce((sum, c) => sum + (Number(c.lab_batch_count) || 3), 0),
            label: "Total Lab Batches",
          },
          {
            val: unassignedCount === 0 ? "100%" : `${assignedStudents}/${totalStudents}`,
            label: unassignedCount === 0 ? "Coverage Complete" : `${unassignedCount} Unassigned`,
          },
        ]}
      />

      {/* Feedback Banner */}
      {feedback && (
        <div
          style={{
            padding: "12px 16px",
            borderRadius: 8,
            marginBottom: 16,
            background: feedback.type === "success" ? "#EAF3DE" : "#FCEBEB",
            color: feedback.type === "success" ? "#27500A" : "#791F1F",
            border: `1px solid ${feedback.type === "success" ? "#b7e089" : "#f7c1c1"}`,
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          {feedback.message}
        </div>
      )}

      {/* Generation Result Banner with Quick Jump */}
      {generationResult && (
        <Card>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, color: "#1D9E75" }}>
                ✓ Traditional Sections & Enrollments Generated
              </div>
              <div style={{ fontSize: 13, color: "#666", marginTop: 4 }}>
                Created <b>{generationResult.sections_created}</b> sections tagged with <code>-T</code> and <code>-L</code>. All student assignments are locked in for solving.
              </div>
            </div>
            <button
              onClick={() => setPage && setPage("admin-solver")}
              style={{
                background: "#1D9E75",
                color: "#fff",
                border: "none",
                borderRadius: 8,
                padding: "9px 18px",
                fontWeight: 600,
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              Open Solver →
            </button>
          </div>
        </Card>
      )}

      {/* Curriculum & Elective Behavior Notice */}
      <Card>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: "#222" }}>
          Curriculum & Dispersal Rules (Semester {semester})
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {/* PE Status */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
            <Badge color={clusterInfo?.has_pe ? "blue" : "green"}>
              {clusterInfo?.has_pe ? "PE Tracked Semester" : "Unified Pool Semester"}
            </Badge>
            <span style={{ color: "#444" }}>
              {clusterInfo?.has_pe
                ? `Students clustered by Professional Elective (${clusterInfo.pe_tag}). Divisions are aligned with PE tracks.`
                : "No PE track in this semester. Students form a unified pool partitioned directly into divisions."}
            </span>
          </div>

          {/* In-Class Elective Edge Case Badge (e.g. Sem 6 MDM) */}
          {clusterInfo?.in_class_electives?.map((ice) => (
            <div
              key={ice.subject_code}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                fontSize: 13,
                background: "#fdf8ee",
                padding: "8px 12px",
                borderRadius: 6,
                border: "1px solid #f2e2be",
              }}
            >
              <Badge color="amber">In-Class Elective</Badge>
              <div>
                <b>{ice.subject_code} ({ice.subject_name})</b> —{" "}
                <span style={{ color: "#633806" }}>{ice.note}</span>
              </div>
            </div>
          ))}

          {/* Dispersal Electives (e.g. Sem 4 MDM) */}
          {clusterInfo?.dispersal_electives?.map((de) => (
            <div
              key={de.tag}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                fontSize: 13,
                background: "#f0f7ff",
                padding: "8px 12px",
                borderRadius: 6,
                border: "1px solid #c8e0fc",
              }}
            >
              <Badge color="blue">Dispersal Elective ({de.tag})</Badge>
              <div>
                <b>{de.subjects?.length} Subjects offered</b> ({de.subjects?.map((s) => s.subject_code).join(", ")}) —{" "}
                <span style={{ color: "#0C447C" }}>{de.note}</span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Division Partitioning Cards */}
      <div style={{ marginTop: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Classes & Lab Batches</h3>
          <div style={{ display: "flex", gap: 10 }}>
            <button
              onClick={() => addDivisionForCluster("ALL", null)}
              style={{
                padding: "6px 14px",
                borderRadius: 6,
                border: "1px solid #dcdad5",
                background: "#fff",
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              + Add Division
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: "7px 18px",
                borderRadius: 6,
                border: "1px solid #185FA5",
                background: "#185FA5",
                color: "#fff",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {saving ? "Saving..." : "Save Setup"}
            </button>
            <button
              onClick={handleGenerateSections}
              disabled={generating}
              style={{
                padding: "7px 18px",
                borderRadius: 6,
                border: "1px solid #1D9E75",
                background: "#1D9E75",
                color: "#fff",
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {generating ? "Generating..." : "⚡ Generate Sections (-T / -L)"}
            </button>
          </div>
        </div>

        {classesState.map((cls, idx) => {
          const rolls = cls.student_rolls || [];
          const numBatches = Number(cls.lab_batch_count) || 3;
          const batchSize = rolls.length > 0 ? Math.ceil(rolls.length / numBatches) : 0;
          const clsLetter = cls.class_id.replace("Div-", "").replace("DIV-", "").trim() || `${idx + 1}`;

          return (
            <Card key={idx}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                  <input
                    type="text"
                    value={cls.class_id}
                    onChange={(e) => updateClassField(idx, "class_id", e.target.value)}
                    style={{
                      fontWeight: 700,
                      fontSize: 15,
                      width: 90,
                      padding: "4px 8px",
                      borderRadius: 6,
                      border: "1px solid #ccc",
                    }}
                  />
                  <input
                    type="text"
                    value={cls.class_name}
                    onChange={(e) => updateClassField(idx, "class_name", e.target.value)}
                    style={{
                      fontSize: 14,
                      width: 240,
                      padding: "4px 8px",
                      borderRadius: 6,
                      border: "1px solid #ccc",
                    }}
                    placeholder="Class Description"
                  />
                  {cls.pe_subtag && (
                    <Badge color="blue">Track: {cls.pe_subtag}</Badge>
                  )}
                </div>

                <button
                  onClick={() => removeDivision(idx)}
                  style={{
                    background: "none",
                    border: "none",
                    color: "#c0392b",
                    fontSize: 12,
                    cursor: "pointer",
                    textDecoration: "underline",
                  }}
                >
                  Remove Division
                </button>
              </div>

              {/* Lab Batch Selector */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                  padding: "10px 14px",
                  background: "#f9f8f6",
                  borderRadius: 8,
                  marginBottom: 12,
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 600, color: "#444" }}>
                  Lab Batches for {cls.class_id}:
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  {[2, 3, 4].map((count) => (
                    <button
                      key={count}
                      onClick={() => updateClassField(idx, "lab_batch_count", count)}
                      style={{
                        padding: "5px 12px",
                        borderRadius: 6,
                        border: numBatches === count ? "2px solid #185FA5" : "1px solid #dcdad5",
                        background: numBatches === count ? "#E6F1FB" : "#fff",
                        color: numBatches === count ? "#185FA5" : "#555",
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      Class / {count} ({count} Batches)
                    </button>
                  ))}
                </div>

                <div style={{ fontSize: 12, color: "#666", marginLeft: "auto" }}>
                  Partition:{" "}
                  {Array.from({ length: numBatches }, (_, bIdx) => {
                    const bId = `${clsLetter}${bIdx + 1}`;
                    const count = Math.min(
                      batchSize,
                      Math.max(0, rolls.length - bIdx * batchSize)
                    );
                    return `${bId} (${count} studs)`;
                  }).join(" · ")}
                </div>
              </div>

              {/* Student Rolls Count & Details */}
              <div style={{ fontSize: 12, color: "#666" }}>
                <b>{rolls.length} students enrolled</b>
                {rolls.length > 0 && (
                  <div
                    style={{
                      marginTop: 6,
                      fontSize: 11,
                      color: "#777",
                      fontFamily: "monospace",
                      maxHeight: 48,
                      overflowY: "auto",
                      background: "#faf9f6",
                      padding: "4px 8px",
                      borderRadius: 4,
                      border: "1px solid #f0efeb",
                    }}
                  >
                    {rolls.join(", ")}
                  </div>
                )}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
