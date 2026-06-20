import { useState, useEffect } from "react";
import { goalApi } from "../api";

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

export const GoalCard = ({ goal, onGoalUpdated, isAdminView, usersMap = {} }) => {
  const api = goalApi;
  const [isUpdating, setIsUpdating] = useState(false);
  const [showConfirmDelete, setShowConfirmDelete] = useState(false);

  const score = computeScore(goal);

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
        {goal.description || "No description provided."}
      </p>

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
