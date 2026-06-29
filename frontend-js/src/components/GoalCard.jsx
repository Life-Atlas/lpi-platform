import { useState, useEffect } from "react";
import { goalApi } from "../api";
import { useToast } from "./Toast";

const PHASE_SEQUENCE = [
  "reality-emulation",
  "concurrent-engineering",
  "collective-intelligence",
  "contextual-intelligence",
  "continuous-intelligence",
  "perpetual-wisdom",
];

const PHASE_LABELS = {
  "reality-emulation": "Reality Emulation",
  "concurrent-engineering": "Concurrent Engineering",
  "collective-intelligence": "Collective Intelligence",
  "contextual-intelligence": "Contextual Intelligence",
  "continuous-intelligence": "Continuous Intelligence",
  "perpetual-wisdom": "Perpetual Wisdom",
};

const PHASE_DESCRIPTIONS = {
  "reality-emulation": "Create a shared reality canvas — establishing where, when, and who. The foundation is a real-world planetary foundation in 3D+, understandable by all.",
  "concurrent-engineering": "Define the scope (as-is to to-be), invite stakeholders to innovate together, validate hypotheses virtually before committing resources.",
  "collective-intelligence": "Connect physical sensors, meet initial KPIs, create ontologies for shared understanding. The ontology factory becomes the foundation for AI factories.",
  "contextual-intelligence": "Connected everything — command & control, real-time decisions, uptime optimization, predictive analytics, root cause analysis.",
  "continuous-intelligence": "Leverage accumulated knowledge — prescriptive maintenance, AI-driven prognostics, universal event pipelines. Simulate everything.",
  "perpetual-wisdom": "Share impact across the planet. Up-cycle exploration, ecosystem enablement, circular strategies, open-source contribution.",
};

const PHASE_WEIGHTS = {
  "reality-emulation": 1,
  "concurrent-engineering": 2,
  "collective-intelligence": 3,
  "contextual-intelligence": 4,
  "continuous-intelligence": 5,
  "perpetual-wisdom": 6,
};

const computeScore = (goal) => {
  const phaseW = PHASE_WEIGHTS[goal.smile_phase] || 1;
  const urgency = goal.urgency_flag ? 1 : 0;
  return Math.round(((goal.priority * 0.5) + (phaseW * 0.3) + (urgency * 0.2)) * 100) / 100;
};

export const GoalCard = ({ goal, onGoalUpdated, isAdminView, usersMap = {}, userId }) => {
  const api = goalApi;
  const { showToast } = useToast();
  const [isUpdating, setIsUpdating] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isGettingRec, setIsGettingRec] = useState(false);
  const [recommendation, setRecommendation] = useState(null);
  const [showRecCard, setShowRecCard] = useState(false);
  const [showConfirmDelete, setShowConfirmDelete] = useState(false);

  const score = computeScore(goal);

  const rawDescription = goal.description || "";
  const githubRepoMatch = rawDescription.match(/\[github_repo:\s*([a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+)\]/) || rawDescription.match(/\b([a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+)\b/);
  
  const githubRepo = githubRepoMatch ? githubRepoMatch[1] : null;

  const cleanDescription = rawDescription.replace(/\[github_repo:\s*([a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+)\]/, "").trim();

  const handleSyncSignals = async () => {
    if (!githubRepo) return;
    setIsSyncing(true);
    try {
      const res = await api.syncGithubEvents(goal.id, githubRepo);
      showToast(`Successfully synced ${res.ingested_high_value || 0} signals from ${githubRepo}!`, "success");
    } catch (err) {
      console.error("Failed to sync GitHub events:", err);
      showToast(err.message || "Failed to sync signals.", "error");
    } finally {
      setIsSyncing(false);
    }
  };



  const handleGetRecommendation = async () => {
    if (!userId) return;
    setIsGettingRec(true);
    setRecommendation(null);
    try {
      const recs = await api.getRecommendationsByGoal(userId, goal.id);
      if (recs && recs.length > 0) {
        setRecommendation(recs[0]);
        setShowRecCard(true);
        showToast("AI reasoning completed! Recommendation generated.", "success");
      } else {
        showToast("No recommendations generated. Try syncing more signals first!", "info");
      }
    } catch (err) {
      console.error("Failed to generate per-goal recommendation:", err);
      showToast(err.message || "Failed to generate recommendation.", "error");
    } finally {
      setIsGettingRec(false);
    }
  };

  const handleRecFeedback = async (actionStatus) => {
    if (!userId || !recommendation) return;
    try {
      await api.submitRecommendationFeedback(userId, {
        recommendation_id: recommendation.id,
        action: recommendation.action,
        smile_phase: recommendation.smile_phase,
        status: actionStatus,
      });

      if (actionStatus === "accepted") {
        await api.updateGoal(goal.id, { smile_phase: recommendation.smile_phase });
        onGoalUpdated?.();
        showToast(`Goal phase successfully advanced to ${PHASE_LABELS[recommendation.smile_phase]}!`, "success");
      } else {
        showToast("Recommendation dismissed.", "info");
      }
      setRecommendation(null);
      setShowRecCard(false);
    } catch (err) {
      console.error("Failed to record feedback:", err);
      showToast(err.message || "Failed to submit feedback.", "error");
    }
  };

  const getScoreClass = (s) => {
    if (s >= 4.5) return "priority-high";
    if (s >= 3.0) return "priority-med";
    return "priority-low";
  };

  const getScoreLabel = (s) => {
    if (s >= 4.5) return `High (${s})`;
    if (s >= 3.0) return `Medium (${s})`;
    return `Low (${s})`;
  };

  const currentIdx = PHASE_SEQUENCE.indexOf(goal.smile_phase);
  const nextPhase = currentIdx < PHASE_SEQUENCE.length - 1 ? PHASE_SEQUENCE[currentIdx + 1] : null;
  const prevPhase = currentIdx > 0 ? PHASE_SEQUENCE[currentIdx - 1] : null;
  const firstPhase = PHASE_SEQUENCE[0];

  const handleTransition = async () => {
    if (!nextPhase) return;
    setIsUpdating(true);
    try {
      await api.updateGoal(goal.id, { smile_phase: nextPhase });
      onGoalUpdated?.();
    } catch (err) {
      console.error("Failed to transition phase:", err);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleStepBack = async () => {
    if (!prevPhase) return;
    setIsUpdating(true);
    try {
      await api.updateGoal(goal.id, { smile_phase: prevPhase });
      onGoalUpdated?.();
    } catch (err) {
      console.error("Failed to step back phase:", err);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleLoopback = async () => {
    setIsUpdating(true);
    try {
      await api.updateGoal(goal.id, { smile_phase: firstPhase });
      onGoalUpdated?.();
    } catch (err) {
      console.error("Failed to loop back to reality-emulation:", err);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDelete = () => {
    setShowConfirmDelete(true);
  };

  const confirmDelete = async () => {
    setShowConfirmDelete(false);
    setIsUpdating(true);
    try {
      await api.deleteGoal(goal.id);
      onGoalUpdated?.();
    } catch (err) {
      console.error("Failed to delete goal:", err);
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div className={`goal-card border-phase-${goal.smile_phase}`}>
      <div className="goal-header">
        <h3 className="goal-title">{goal.title}</h3>
        <div className="badges-container">
          <span className={`priority-badge ${getScoreClass(score)}`}>
            Score: {getScoreLabel(score)}
          </span>
          {goal.urgency_flag && (
            <span className="urgency-badge">Urgent</span>
          )}
        </div>
      </div>

      {isAdminView && (
        <div style={{ fontSize: "0.85rem", color: "#a78bfa", marginBottom: "12px", display: "flex", alignItems: "center", gap: "6px" }}>
          <span>👤</span>
          <span style={{ wordBreak: "break-all" }}>
            <strong>Owner:</strong> {usersMap[goal.user_id]?.name ? `${usersMap[goal.user_id].name} ` : ""}
            {usersMap[goal.user_id]?.email ? `(${usersMap[goal.user_id].email})` : goal.user_id}
          </span>
        </div>
      )}

      <p className="goal-desc">
        {cleanDescription || "No description provided."}
      </p>

      {githubRepo && (
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "rgba(255, 255, 255, 0.03)",
          border: "1px solid rgba(255, 255, 255, 0.06)",
          borderRadius: "10px",
          padding: "10px 14px",
          margin: "14px 0",
          fontSize: "0.85rem",
          boxShadow: "inset 0 1px 0 rgba(255, 255, 255, 0.05)",
          flexWrap: "wrap",
          gap: "10px"
        }}>
          <span style={{ display: "flex", alignItems: "center", gap: "8px", color: "rgba(255, 255, 255, 0.85)" }}>
            <span style={{ fontSize: "1.1rem" }}>📁</span>
            <span>
              <strong>GitHub:</strong> <a href={`https://github.com/${githubRepo}`} target="_blank" rel="noopener noreferrer" style={{ color: "#fbbf24", textDecoration: "none", fontWeight: "600" }}>{githubRepo}</a>
            </span>
          </span>
          <div style={{ display: "flex", gap: "10px" }}>
            <button
              onClick={handleSyncSignals}
              disabled={isSyncing}
              style={{
                background: "linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)",
                border: "1px solid rgba(255,255,255,0.15)",
                color: "#e2e8f0",
                borderRadius: "8px",
                padding: "6px 12px",
                cursor: isSyncing ? "not-allowed" : "pointer",
                fontSize: "0.8rem",
                fontWeight: "600",
                display: "flex",
                alignItems: "center",
                gap: "6px",
                transition: "all 0.2s ease"
              }}
            >
              {isSyncing ? (
                <>
                  <span className="button-spinner" />
                  <span>Syncing...</span>
                </>
              ) : (
                <>
                  <span>🔄</span>
                  <span>Sync Signals</span>
                </>
              )}
            </button>
            <button
              onClick={handleGetRecommendation}
              disabled={isGettingRec}
              style={{
                background: "linear-gradient(135deg, rgba(139, 92, 246, 0.3) 0%, rgba(109, 40, 217, 0.3) 100%)",
                border: "1px solid rgba(139, 92, 246, 0.6)",
                color: "#c4b5fd",
                borderRadius: "8px",
                padding: "6px 12px",
                cursor: isGettingRec ? "not-allowed" : "pointer",
                fontSize: "0.8rem",
                fontWeight: "600",
                display: "flex",
                alignItems: "center",
                gap: "6px",
                boxShadow: "0 2px 8px rgba(139, 92, 246, 0.15)",
                transition: "all 0.2s ease"
              }}
              onMouseOver={(e) => { if (!isGettingRec) e.currentTarget.style.border = "1px solid #8b5cf6"; }}
              onMouseOut={(e) => { if (!isGettingRec) e.currentTarget.style.border = "1px solid rgba(139, 92, 246, 0.6)"; }}
            >
              {isGettingRec ? (
                <>
                  <span className="button-spinner" />
                  <span>AI Reasoning...</span>
                </>
              ) : (
                <>
                  <span>✨</span>
                  <span>Get AI Recommendation</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {showRecCard && recommendation && (
        <div style={{
          background: "rgba(139, 92, 246, 0.04)",
          border: "1px solid rgba(139, 92, 246, 0.2)",
          borderRadius: "12px",
          padding: "16px",
          margin: "16px 0",
          display: "flex",
          flexDirection: "column",
          gap: "12px",
          boxShadow: "0 4px 20px rgba(0, 0, 0, 0.2)",
          backdropFilter: "blur(5px)"
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{
              background: "rgba(139, 92, 246, 0.15)",
              color: "#a78bfa",
              border: "1px solid rgba(139, 92, 246, 0.3)",
              padding: "4px 8px",
              borderRadius: "8px",
              fontSize: "0.7rem",
              fontWeight: "700",
              textTransform: "uppercase"
            }}>
              💡 AI Phase Advancement Card
            </span>
            <span style={{ fontSize: "0.75rem", color: "#fbbf24", fontWeight: "600" }}>
              🔥 Priority Score: {Number(recommendation.priority || 3.0).toFixed(2)}
            </span>
          </div>
          
          <h4 style={{ color: "#fff", margin: 0, fontSize: "0.95rem", fontWeight: "700", lineHeight: 1.4 }}>
            {recommendation.action}
          </h4>

          {recommendation.reasoning && (
            <div style={{
              background: "rgba(0, 0, 0, 0.2)",
              border: "1px solid rgba(255, 255, 255, 0.03)",
              borderRadius: "8px",
              padding: "10px 12px",
              fontSize: "0.8rem",
              color: "rgba(255, 255, 255, 0.7)",
              lineHeight: 1.5
            }}>
              <strong>Reasoning:</strong> {recommendation.reasoning}
            </div>
          )}

          <div style={{ display: "flex", gap: "10px", marginTop: "4px" }}>
            <button
              onClick={() => handleRecFeedback("accepted")}
              style={{
                flex: 1,
                background: "#10b981",
                border: "none",
                color: "#fff",
                borderRadius: "6px",
                padding: "8px",
                cursor: "pointer",
                fontSize: "0.8rem",
                fontWeight: "600"
              }}
            >
              ✓ Accept Recommendation
            </button>
            <button
              onClick={() => handleRecFeedback("dismissed")}
              style={{
                background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.1)",
                color: "#ccc",
                borderRadius: "6px",
                padding: "8px 12px",
                cursor: "pointer",
                fontSize: "0.8rem",
                fontWeight: "600"
              }}
            >
              ✕ Dismiss
            </button>
          </div>
        </div>
      )}

      <div className="smile-stepper">
        {PHASE_SEQUENCE.map((phase, idx) => {
          const isCompleted = idx < currentIdx;
          const isActive = idx === currentIdx;
          return (
            <div
              key={phase}
              className={`step ${isCompleted ? "completed" : ""} ${isActive ? "active" : ""}`}
            >
              <div className="step-circle">{isCompleted ? "✓" : idx + 1}</div>
              <span className="step-label">{PHASE_LABELS[phase]}</span>
            </div>
          );
        })}
      </div>

      <div className="phase-instruction">
        <span className="instruction-tag">Active Stage:</span>
        <span className="instruction-text">
          {PHASE_DESCRIPTIONS[goal.smile_phase]}
        </span>
      </div>

      <div className="score-breakdown">
        <span className="score-detail">
          Priority {goal.priority} × 0.5 = {Math.round(goal.priority * 0.5 * 100) / 100}
        </span>
        <span className="score-detail">
          Phase ({PHASE_LABELS[goal.smile_phase]}) × 0.3 = {Math.round(PHASE_WEIGHTS[goal.smile_phase] * 0.3 * 100) / 100}
        </span>
        <span className="score-detail">
          Urgency × 0.2 = {goal.urgency_flag ? "0.20" : "0.00"}
        </span>
      </div>

      <div className="action-panel">
        <div style={{ display: "flex", gap: "10px" }}>
          {nextPhase ? (
            <button
              onClick={handleTransition}
              disabled={isUpdating}
              className="transition-btn advance-btn"
              title={`Transition to ${nextPhase}`}
            >
              Advance to {PHASE_LABELS[nextPhase]}
            </button>
          ) : (
            <span className="fully-evolved-badge">GOAL FULLY EVOLVED</span>
          )}

          {prevPhase && (
            <button
              onClick={handleStepBack}
              disabled={isUpdating}
              className="transition-btn back-btn"
              title={`Step back to ${prevPhase}`}
            >
              Back to {PHASE_LABELS[prevPhase]}
            </button>
          )}

          {currentIdx > 1 && (
            <button
              onClick={handleLoopback}
              disabled={isUpdating}
              className="transition-btn resense-btn"
              title="Restart SMILE cycle (Re-emulate Reality)"
              >
              Re-emulate Reality
            </button>
          )}
        </div>

        <button
          onClick={handleDelete}
          disabled={isUpdating}
          className="delete-btn"
          title="Delete goal"
        >
          {isUpdating ? "Deleting..." : "Delete"}
        </button>
      </div>

      {showConfirmDelete && (
        <>
          <div onClick={() => setShowConfirmDelete(false)} style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 9998, backdropFilter: "blur(4px)"
          }} />
          <div style={{
            position: "fixed", top: "50%", left: "50%", transform: "translate(-50%, -50%)",
            background: "var(--surface, #1a1a2e)", borderRadius: "16px", padding: "32px",
            width: "360px", zIndex: 9999, boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
            border: "1px solid rgba(255,255,255,0.1)", textAlign: "center"
          }}>
            <div style={{
              width: "48px", height: "48px", borderRadius: "50%", background: "rgba(255, 107, 107, 0.15)",
              color: "#ff6b6b", display: "flex", alignItems: "center", justifyContent: "center",
              margin: "0 auto 16px", fontSize: "1.5rem"
            }}>
              ⚠️
            </div>
            <h3 style={{ color: "#fff", margin: "0 0 12px", fontSize: "1.1rem", fontWeight: 600 }}>
              Delete Goal?
            </h3>
            <p style={{ color: "var(--text-secondary, #aaa)", fontSize: "0.9rem", lineHeight: 1.5, marginBottom: "24px" }}>
              Are you sure you want to delete the goal <strong>"{goal.title}"</strong>? This action cannot be undone.
            </p>
            <div style={{ display: "flex", gap: "12px" }}>
              <button onClick={() => setShowConfirmDelete(false)} style={{
                flex: 1, padding: "10px", borderRadius: "8px",
                background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.1)",
                color: "#fff", cursor: "pointer", fontWeight: 500
              }}>Cancel</button>
              <button onClick={confirmDelete} style={{
                flex: 1, padding: "10px", borderRadius: "8px",
                background: "#ff6b6b", border: "none",
                color: "#fff", cursor: "pointer", fontWeight: 600
              }}>Delete Goal</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
