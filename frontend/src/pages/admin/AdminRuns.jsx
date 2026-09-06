import { useState } from "react";
import { initializeCycle } from "../../api/cycle";
import { apiErrorMessage } from "../../api/client";
import { Card, PageHeader, Badge, InfoBox } from "../../components/ui";
import CycleBanner from "../../components/CycleBanner";

export default function AdminRuns({
  cycleStatus,
  refreshCycle,
  setPage,
}) {
  const [initializing, setInitializing] = useState(false);
  const [initMsg, setInitMsg] = useState(null);
  const [initErr, setInitErr] = useState(null);

  const currentRun = cycleStatus?.current_run;
  const activeSemesters = cycleStatus?.active_semesters || [];
  const tagsDetail = cycleStatus?.tags_detail || [];
  const choiceTags = tagsDetail.filter(t => t.is_choice_based);

  const handleInitCycle = async () => {
    setInitializing(true);
    setInitMsg(null);
    setInitErr(null);
    try {
      const res = await initializeCycle();
      setInitMsg(`Department cycle synchronized! Run #${res.current_run?.id} covers semester(s): ${res.current_run?.semesters?.join(", ")}`);
      if (refreshCycle) refreshCycle();
    } catch (e) {
      setInitErr(apiErrorMessage(e));
    } finally {
      setInitializing(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Department Solver Cycle"
        sub="Department-wide academic scheduling cycle covering all active semesters together."
      />

      <CycleBanner
        cycleStatus={cycleStatus}
        onInitializeCycle={handleInitCycle}
        onNavigate={setPage}
      />

      <InfoBox title="Unified Department Scheduling Cycle">
        PWSSAP operates on a unified department-level cycle. Rather than managing individual semester runs separately, all active semesters are solved together in one global timetable run to prevent cross-semester faculty clashes and balance teaching loads.
      </InfoBox>

      {initMsg && (
        <div style={{ background: "#EAF3DE", border: "1px solid #C0DD97", borderRadius: 6, padding: "10px 14px", fontSize: 13, color: "#27500A", marginBottom: 16 }}>
          ✓ {initMsg}
        </div>
      )}
      {initErr && (
        <div style={{ background: "#FCEBEB", border: "1px solid #F7C1C1", borderRadius: 6, padding: "10px 14px", fontSize: 13, color: "#791F1F", marginBottom: 16 }}>
          ✕ {initErr}
        </div>
      )}

      {/* Main Cycle Status Card */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16, color: "#0f172a" }}>
              Active Cycle Generation Run
            </div>
            <div style={{ fontSize: 12, color: "#64748b" }}>
              The department timetable solver executes against this generation cycle.
            </div>
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <button
              onClick={handleInitCycle}
              disabled={initializing || activeSemesters.length === 0}
              style={{
                background: "#185FA5",
                color: "#ffffff",
                border: "none",
                borderRadius: 6,
                padding: "7px 16px",
                fontSize: 12,
                fontWeight: 600,
                cursor: initializing || activeSemesters.length === 0 ? "not-allowed" : "pointer",
              }}
            >
              {initializing ? "Initializing…" : currentRun ? "Re-sync Cycle Run" : "Initialize Cycle Run"}
            </button>
            {setPage && (
              <button
                onClick={() => setPage("admin-solver")}
                style={{
                  background: "#1D9E75",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: 6,
                  padding: "7px 16px",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Go to Solver →
              </button>
            )}
          </div>
        </div>

        {currentRun ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12, background: "#f8fafc", padding: 16, borderRadius: 8, border: "1px solid #e2e8f0" }}>
            <div>
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", fontWeight: 600 }}>Run ID</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: "#1e293b", marginTop: 2 }}>#{currentRun.id}</div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", fontWeight: 600 }}>Status</div>
              <div style={{ marginTop: 2 }}>
                <Badge color={currentRun.status === "PUBLISHED" ? "green" : "amber"}>
                  {currentRun.status}
                </Badge>
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", fontWeight: 600 }}>Semesters Covered</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: "#1e293b", marginTop: 2 }}>
                {currentRun.semesters?.length > 0 ? currentRun.semesters.join(", ") : currentRun.semester || "All Active"}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", fontWeight: 600 }}>Student Lock-Ins</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: "#1e293b", marginTop: 2 }}>
                {cycleStatus?.lock_in_complete_count ?? 0} / {cycleStatus?.lock_in_total_students ?? 0} complete
              </div>
            </div>
          </div>
        ) : (
          <div style={{ padding: "24px 0", textAlign: "center", color: "#64748b" }}>
            {activeSemesters.length === 0 ? (
              <div>
                <p>No subjects found in catalog. Upload subject data first to activate semesters.</p>
                {setPage && (
                  <button
                    onClick={() => setPage("admin-subjects")}
                    style={{ background: "#f1f5f9", border: "1px solid #cbd5e1", padding: "6px 14px", borderRadius: 6, cursor: "pointer", fontSize: 12, fontWeight: 500 }}
                  >
                    Go to Subjects Catalog →
                  </button>
                )}
              </div>
            ) : (
              <div>
                <p>Active semesters detected: <strong>{activeSemesters.join(", ")}</strong>.</p>
                <p style={{ fontSize: 12 }}>Click &quot;Initialize Cycle Run&quot; above to prepare the generation cycle for the solver.</p>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Cycle Electives & Choice Tags Summary */}
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: "#0f172a" }}>
              Elective Choice Tags ({choiceTags.length})
            </div>
            <div style={{ fontSize: 12, color: "#64748b" }}>
              Subject tags configured as student choice electives.
            </div>
          </div>
          {setPage && (
            <button
              onClick={() => setPage("admin-subjects")}
              style={{ background: "transparent", border: "1px solid #cbd5e1", borderRadius: 6, padding: "5px 12px", fontSize: 12, cursor: "pointer", fontWeight: 500, color: "#185FA5" }}
            >
              Configure in Subjects →
            </button>
          )}
        </div>

        {choiceTags.length === 0 ? (
          <div style={{ padding: "16px 0", color: "#64748b", fontSize: 13, fontStyle: "italic" }}>
            No elective choice tags configured yet. Go to Subjects Catalog to mark tags (e.g. professional_elective_1) as electives.
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 10 }}>
            {choiceTags.map(t => (
              <div key={t.tag} style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 14px" }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: "#1e293b" }}>{t.tag}</div>
                <div style={{ fontSize: 11, color: "#64748b", marginTop: 4 }}>
                  {t.subtags?.length > 0 ? (
                    <span>Subtags: <strong>{t.subtags.join(", ")}</strong></span>
                  ) : (
                    <span>No subtags defined in catalog</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
