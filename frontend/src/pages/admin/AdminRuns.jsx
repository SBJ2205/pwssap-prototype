import { useEffect, useState } from "react";
import { createRun, setRunChoiceTags } from "../../api/runs";
import { getSubjectTags } from "../../api/catalog";
import { apiErrorMessage } from "../../api/client";
import { ODD_SEMESTERS, EVEN_SEMESTERS } from "../../constants";
import { Card, PageHeader, Badge, InfoBox } from "../../components/ui";

export default function AdminRuns({
  runs = [],
  activeRun,
  activeRunId,
  setActiveRunId,
  refreshRuns,
}) {
  const [newSemester, setNewSemester] = useState(3);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(null);
  const [createSuccess, setCreateSuccess] = useState(null);

  // Choice tag configuration for active run
  const [availableTags, setAvailableTags] = useState([]);
  const [tagConfigs, setTagConfigs] = useState([]); // [{tag, numeric_value, is_choice_based}]
  const [newCustomTag, setNewCustomTag] = useState("");
  const [savingTags, setSavingTags] = useState(false);
  const [tagMsg, setTagMsg] = useState(null);
  const [tagError, setTagError] = useState(null);

  // Sync tagConfigs when activeRun changes
  useEffect(() => {
    if (!activeRun) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setTagConfigs([]);
      return;
    }
    const existing = (activeRun.choice_tag_configs || []).map(c => ({
      tag: c.tag,
      numeric_value: c.numeric_value,
      is_choice_based: c.is_choice_based,
    }));
    setTagConfigs(existing);
    setTagMsg(null);
    setTagError(null);

    // Fetch catalog tags for this semester
    let cancelled = false;
    getSubjectTags(activeRun.semester)
      .then(data => {
        if (!cancelled) setAvailableTags(data.tags || []);
      })
      .catch(() => {
        if (!cancelled) setAvailableTags([]);
      });

    return () => { cancelled = true; };
  }, [activeRun]);

  async function handleCreateRun(e) {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    setCreateSuccess(null);

    try {
      const run = await createRun(Number(newSemester), []);
      await refreshRuns();
      setActiveRunId(run.id);
      setCreateSuccess(`Created Run #${run.id} for Semester ${run.semester}!`);
    } catch (err) {
      setCreateError(apiErrorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  function toggleChoiceBased(tag) {
    setTagConfigs(prev => {
      const idx = prev.findIndex(c => c.tag === tag);
      if (idx >= 0) {
        const item = prev[idx];
        const nextIsChoice = !item.is_choice_based;
        const updated = [...prev];
        updated[idx] = {
          ...item,
          is_choice_based: nextIsChoice,
          numeric_value: nextIsChoice ? (item.numeric_value || getNextNumericValue(prev)) : item.numeric_value,
        };
        return updated;
      } else {
        return [...prev, { tag, numeric_value: getNextNumericValue(prev), is_choice_based: true }];
      }
    });
    setTagMsg(null);
  }

  function getNextNumericValue(configs) {
    const used = configs.filter(c => c.is_choice_based).map(c => c.numeric_value).filter(Boolean);
    let next = 1;
    while (used.includes(next)) next++;
    return next;
  }

  function updateNumericValue(tag, val) {
    const num = parseInt(val, 10) || 0;
    setTagConfigs(prev => prev.map(c => c.tag === tag ? { ...c, numeric_value: num } : c));
    setTagMsg(null);
  }

  function addCustomTag(e) {
    e.preventDefault();
    const tag = newCustomTag.trim().toUpperCase();
    if (!tag) return;
    if (tagConfigs.some(c => c.tag === tag)) {
      setTagError(`Tag '${tag}' already exists in configuration.`);
      return;
    }
    const nextVal = getNextNumericValue(tagConfigs);
    setTagConfigs(prev => [...prev, { tag, numeric_value: nextVal, is_choice_based: true }]);
    setNewCustomTag("");
    setTagError(null);
  }

  function removeTagConfig(tag) {
    setTagConfigs(prev => prev.filter(c => c.tag !== tag));
    setTagMsg(null);
  }

  async function handleSaveTags() {
    if (!activeRun) return;
    setSavingTags(true);
    setTagMsg(null);
    setTagError(null);

    // Client-side validation: unique numeric values for active choice tags
    const active = tagConfigs.filter(c => c.is_choice_based);
    const seenValues = new Set();
    for (const c of active) {
      if (!c.numeric_value || c.numeric_value <= 0) {
        setTagError(`Choice-based tag '${c.tag}' must have a positive numeric value.`);
        setSavingTags(false);
        return;
      }
      if (seenValues.has(c.numeric_value)) {
        setTagError(`Duplicate numeric value ${c.numeric_value} used for multiple choice tags.`);
        setSavingTags(false);
        return;
      }
      seenValues.add(c.numeric_value);
    }

    try {
      await setRunChoiceTags(activeRun.id, tagConfigs);
      await refreshRuns();
      setTagMsg("Choice-tag configuration saved for this run!");
    } catch (err) {
      setTagError(apiErrorMessage(err));
    } finally {
      setSavingTags(false);
    }
  }

  // Combine tags found in catalog with configured tags
  const allKnownTags = Array.from(new Set([
    ...availableTags,
    ...tagConfigs.map(c => c.tag),
  ])).sort();

  return (
    <div>
      <PageHeader
        title="Runs & Semesters"
        sub="The timetable solver executes for one semester run at a time. Choice tags are configured strictly per-run."
      />

      <InfoBox title="How do runs work?">
        Each <strong>Generation Run</strong> corresponds to a single semester (e.g. Semester 3).
        Runs isolate student cohorts and choice-tag mappings: <strong>numeric choice columns in the student CSV
        (choice_1, choice_2...)</strong> are dynamically bound to the specific tags you mark as choice-based for this run.
      </InfoBox>

      {/* Grid: Runs list & Create run */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 16, marginBottom: 20 }}>
        {/* Existing Runs */}
        <Card>
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>Existing Generation Runs</span>
            <span style={{ fontSize: 12, color: "#888", fontWeight: 400 }}>{runs.length} run{runs.length !== 1 ? "s" : ""}</span>
          </div>

          {runs.length === 0 ? (
            <div style={{ color: "#888", fontSize: 13, padding: "12px 0" }}>
              No runs created yet. Create your first run on the right.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {runs.map(r => {
                const isActive = r.id === activeRunId;
                const activeChoices = (r.choice_tag_configs || []).filter(c => c.is_choice_based);
                return (
                  <div
                    key={r.id}
                    style={{
                      padding: "12px 14px",
                      borderRadius: 8,
                      border: isActive ? "2px solid #185FA5" : "1px solid #e0ddd8",
                      background: isActive ? "#F4F8FC" : "#fff",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontWeight: 700, fontSize: 14, color: "#222" }}>Run #{r.id}</span>
                        <span style={{ fontSize: 13, fontWeight: 500, color: "#555" }}>Semester {r.semester}</span>
                        <Badge color={r.status === "PUBLISHED" ? "green" : r.status === "CREATED" ? "amber" : "blue"}>
                          {r.status}
                        </Badge>
                        {isActive && (
                          <span style={{ background: "#185FA5", color: "#fff", fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4 }}>
                            ACTIVE
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: "#777", marginTop: 4 }}>
                        {activeChoices.length === 0
                          ? "No choice tags configured (core only)"
                          : `Choice tags: ${activeChoices.map(c => `${c.tag} (= ${c.numeric_value})`).join(", ")}`}
                      </div>
                    </div>

                    {!isActive && (
                      <button
                        onClick={() => setActiveRunId(r.id)}
                        style={{
                          padding: "5px 12px",
                          background: "#fff",
                          border: "1px solid #185FA5",
                          color: "#185FA5",
                          borderRadius: 6,
                          fontSize: 12,
                          fontWeight: 500,
                          cursor: "pointer",
                        }}
                      >
                        Select
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        {/* Create Run Form */}
        <Card>
          <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 12 }}>
            Start a New Run
          </div>

          {createError && (
            <div style={{ background: "#FCEBEB", border: "1px solid #F7C1C1", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#791F1F", marginBottom: 12 }}>
              ✕ {createError}
            </div>
          )}
          {createSuccess && (
            <div style={{ background: "#EAF3DE", border: "1px solid #C0DD97", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#27500A", marginBottom: 12 }}>
              ✓ {createSuccess}
            </div>
          )}

          <form onSubmit={handleCreateRun}>
            <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#444", marginBottom: 6 }}>
              Select Semester
            </label>
            <select
              value={newSemester}
              onChange={e => setNewSemester(Number(e.target.value))}
              style={{
                width: "100%",
                padding: "8px 10px",
                border: "1px solid #ccc",
                borderRadius: 6,
                fontSize: 14,
                marginBottom: 12,
                background: "#fff",
              }}
            >
              <optgroup label="Odd Semesters">
                {ODD_SEMESTERS.map(s => (
                  <option key={s} value={s}>Semester {s}</option>
                ))}
              </optgroup>
              <optgroup label="Even Semesters">
                {EVEN_SEMESTERS.map(s => (
                  <option key={s} value={s}>Semester {s}</option>
                ))}
              </optgroup>
            </select>

            <p style={{ fontSize: 11, color: "#888", marginBottom: 16, lineHeight: 1.5 }}>
              Creating a run prepares the scheduling workspace for this semester.
              You will be able to configure choice tags, import students, and generate sections.
            </p>

            <button
              type="submit"
              disabled={creating}
              style={{
                padding: "8px 18px",
                background: creating ? "#aaa" : "#185FA5",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                fontSize: 13,
                fontWeight: 600,
                cursor: creating ? "not-allowed" : "pointer",
              }}
            >
              {creating ? "Creating…" : "+ Create Run"}
            </button>
          </form>
        </Card>
      </div>

      {/* Choice Tag Configuration for the Active Run */}
      {activeRun ? (
        <Card>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15 }}>
                Choice-Tag Configuration for Run #{activeRun.id} (Semester {activeRun.semester})
              </div>
              <div style={{ fontSize: 12, color: "#666", marginTop: 2 }}>
                Configure which subject tags represent choice electives for this semester. Any number of tags is supported.
              </div>
            </div>

            <button
              onClick={handleSaveTags}
              disabled={savingTags}
              style={{
                padding: "8px 20px",
                background: savingTags ? "#aaa" : "#1D9E75",
                color: "#fff",
                border: "none",
                borderRadius: 6,
                fontSize: 13,
                fontWeight: 600,
                cursor: savingTags ? "not-allowed" : "pointer",
                boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
              }}
            >
              {savingTags ? "Saving…" : "Save Configuration"}
            </button>
          </div>

          {tagError && (
            <div style={{ background: "#FCEBEB", border: "1px solid #F7C1C1", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#791F1F", marginBottom: 12 }}>
              ✕ {tagError}
            </div>
          )}
          {tagMsg && (
            <div style={{ background: "#EAF3DE", border: "1px solid #C0DD97", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#27500A", marginBottom: 12 }}>
              ✓ {tagMsg}
            </div>
          )}

          <div style={{ background: "#f9f8f5", border: "1px solid #e5e3dc", borderRadius: 8, padding: "12px 16px", marginBottom: 16, fontSize: 12, color: "#555", lineHeight: 1.6 }}>
            💡 <strong>How Choice Mappings Work in Student CSV:</strong>
            <br />
            If you mark <strong>PE1</strong> (value = 1) and <strong>MDM</strong> (value = 2) as choice-based,
            the student CSV for this run requires columns <code style={{ background: "#f1efe8", padding: "1px 4px", borderRadius: 3 }}>choice_1</code> and <code style={{ background: "#f1efe8", padding: "1px 4px", borderRadius: 3 }}>choice_2</code>.
            A student putting <strong>1</strong> in <code style={{ background: "#f1efe8", padding: "1px 4px", borderRadius: 3 }}>choice_1</code> chooses PE1 as their first preference.
          </div>

          {/* Table of tags */}
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, marginBottom: 16 }}>
            <thead>
              <tr style={{ background: "#f9f8f5", borderBottom: "1.5px solid #e0ddd8" }}>
                <th style={{ textAlign: "left", padding: "8px 12px", color: "#555", fontWeight: 600 }}>Tag Name</th>
                <th style={{ textAlign: "left", padding: "8px 12px", color: "#555", fontWeight: 600 }}>Catalog Presence</th>
                <th style={{ textAlign: "center", padding: "8px 12px", color: "#555", fontWeight: 600 }}>Is Choice-Based?</th>
                <th style={{ textAlign: "left", padding: "8px 12px", color: "#555", fontWeight: 600 }}>Numeric Value</th>
                <th style={{ textAlign: "right", padding: "8px 12px", color: "#555", fontWeight: 600 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {allKnownTags.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ padding: "16px", textAlign: "center", color: "#888" }}>
                    No tags discovered in catalog yet. You can upload subjects or add custom tags below.
                  </td>
                </tr>
              ) : (
                allKnownTags.map(tag => {
                  const cfg = tagConfigs.find(c => c.tag === tag);
                  const isChoice = cfg?.is_choice_based || false;
                  const numVal = cfg?.numeric_value ?? "";
                  const inCatalog = availableTags.includes(tag);

                  return (
                    <tr key={tag} style={{ borderBottom: "1px solid #f0efeb" }}>
                      <td style={{ padding: "10px 12px", fontWeight: 600 }}>
                        <code style={{ background: "#E6F1FB", color: "#0C447C", padding: "2px 6px", borderRadius: 4 }}>
                          {tag}
                        </code>
                      </td>
                      <td style={{ padding: "10px 12px" }}>
                        {inCatalog ? (
                          <span style={{ color: "#27500A", fontSize: 11 }}>✓ In Sem {activeRun.semester} catalog</span>
                        ) : (
                          <span style={{ color: "#BA7517", fontSize: 11 }}>⚠ Not in catalog yet</span>
                        )}
                      </td>
                      <td style={{ padding: "10px 12px", textAlign: "center" }}>
                        <input
                          type="checkbox"
                          checked={isChoice}
                          onChange={() => toggleChoiceBased(tag)}
                          style={{ cursor: "pointer", width: 16, height: 16 }}
                        />
                      </td>
                      <td style={{ padding: "10px 12px" }}>
                        {isChoice ? (
                          <input
                            type="number"
                            min="1"
                            value={numVal}
                            onChange={e => updateNumericValue(tag, e.target.value)}
                            style={{
                              width: 80,
                              padding: "4px 8px",
                              border: "1px solid #ccc",
                              borderRadius: 4,
                              fontSize: 13,
                              fontWeight: 600,
                            }}
                          />
                        ) : (
                          <span style={{ color: "#aaa", fontSize: 12 }}>—</span>
                        )}
                      </td>
                      <td style={{ padding: "10px 12px", textAlign: "right" }}>
                        {cfg && (
                          <button
                            onClick={() => removeTagConfig(tag)}
                            title="Remove tag configuration"
                            style={{
                              background: "transparent",
                              border: "none",
                              color: "#791F1F",
                              cursor: "pointer",
                              fontSize: 12,
                            }}
                          >
                            ✕ Remove
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>

          {/* Add custom tag */}
          <form onSubmit={addCustomTag} style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 500, color: "#666" }}>Add Custom Tag:</span>
            <input
              type="text"
              value={newCustomTag}
              onChange={e => setNewCustomTag(e.target.value)}
              placeholder="e.g. HONORS or OPEN_ELEC"
              style={{
                padding: "6px 10px",
                border: "1px solid #ccc",
                borderRadius: 6,
                fontSize: 13,
                width: 200,
              }}
            />
            <button
              type="submit"
              style={{
                padding: "6px 14px",
                background: "#f1efe8",
                border: "1px solid #d1cfc7",
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                color: "#333",
                cursor: "pointer",
              }}
            >
              + Add Tag
            </button>
          </form>
        </Card>
      ) : (
        <Card>
          <div style={{ color: "#888", fontSize: 13, textAlign: "center", padding: "20px 0" }}>
            Select or create an active run above to configure choice tags.
          </div>
        </Card>
      )}
    </div>
  );
}
