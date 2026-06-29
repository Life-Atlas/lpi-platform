import { useState, useEffect } from "react";
import { goalApi } from "../api";
import "./RecommendationsView.css";
import { useToast } from "./Toast";

export const RecommendationsView = ({ userId, onGoalCreated, goals = [] }) => {
  const { showToast } = useToast();
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [runningPipeline, setRunningPipeline] = useState(false);
  const [expandedCard, setExpandedCard] = useState(null);
  const [feedbackStatus, setFeedbackStatus] = useState({}); // { recommendationId: "accepted" | "dismissed" }
  const [error, setError] = useState(null);

  const fetchRecommendations = async () => {
    if (!userId) return;
    try {
      setLoading(true);
      setError(null);
      const data = await goalApi.getRecommendations(userId);
      // Filter out already feedback-treated ones
      setRecommendations(data || []);
    } catch (err) {
      console.error("Failed to load recommendations:", err);
      setError("Unable to load recommendations.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRecommendations();
  }, [userId]);

  const handleRunPipeline = async () => {
    if (!userId) return;
    try {
      setRunningPipeline(true);
      setError(null);
      const data = await goalApi.runRecommendationPipeline(userId);
      setRecommendations(data || []);
    } catch (err) {
      console.error("Failed to run pipeline:", err);
      setError("Pipeline execution failed. Please try again.");
    } finally {
      setRunningPipeline(false);
    }
  };

  const handleFeedback = async (rec, status) => {
    if (!userId) return;
    setFeedbackStatus((prev) => ({ ...prev, [rec.id]: status }));

    try {
      // 1. Submit feedback to backend
      await goalApi.submitRecommendationFeedback(userId, {
        recommendation_id: rec.id,
        action: rec.action,
        smile_phase: rec.smile_phase,
        status: status, // "accepted" | "dismissed"
      });

      // 2. If accepted, update the existing goal's phase!
      if (status === "accepted" && rec.source_goals && rec.source_goals.length > 0) {
        const goalId = rec.source_goals[0];
        // Find existing goal in our state to fetch its details
        const existingGoal = goals.find((g) => g.id === goalId);
        if (existingGoal) {
          await goalApi.updateGoal(goalId, {
            smile_phase: rec.smile_phase || "reality-emulation",
          });
          if (onGoalCreated) {
            onGoalCreated(); // Re-fetch goals to update the UI
          }
        }
      }

      // 3. Slide card away by removing it after animation finishes
      setTimeout(() => {
        setRecommendations((prev) => prev.filter((r) => r.id !== rec.id));
      }, 400);

    } catch (err) {
      console.error("Feedback failed:", err);
      // Revert status on failure
      setFeedbackStatus((prev) => {
        const next = { ...prev };
        delete next[rec.id];
        return next;
      });
      showToast(err.message || "Failed to record feedback.", "error");
    }
  };

  if (!userId) {
    return (
      <div className="premium-card recommendations-container">
        <div className="empty-state">
          <h3>Authentication Required</h3>
          <p>Please log in to view personalized AI recommendations.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="premium-card recommendations-container">
      <div className="recommendations-header-row">
        <div>
          <h2 className="widget-title" style={{ fontSize: "1.25rem", fontWeight: "700" }}>
            AI Recommendation Engine
          </h2>
          <p className="recommendations-subtitle">
            S.M.I.L.E.-grounded next actions generated dynamically based on your goal metrics and activity signals.
          </p>
        </div>
      </div>

      {error && <div className="recommendations-error-banner">{error}</div>}

      {runningPipeline ? (
        <div className="pipeline-loading-card">
          <div className="pipeline-loading-graphic">
            <div className="ring ring-outer"></div>
            <div className="ring ring-middle"></div>
            <div className="ring ring-inner"></div>
            <div className="sparkles">✨</div>
          </div>
          <h3>AI Orchestration Engine is Reasoning...</h3>
          <p>
            Running LangGraph multi-agent pipeline to analyze active paths, cross-reference signals, and generate optimized action items.
          </p>
        </div>
      ) : loading ? (
        <div className="recommendations-loading">
          <div className="recommendations-spinner"></div>
          <p>Analyzing recommendation history...</p>
        </div>
      ) : recommendations.length === 0 ? (
        <div className="empty-state recommendations-empty">
          <div className="empty-icon">💡</div>
          <h3>No Recommendations Available</h3>
          <p style={{ marginBottom: "20px" }}>
            To get recommendations, add repositories to your goals and sync signals.
          </p>
        </div>
      ) : (
        <div className="recommendations-grid">
          {recommendations
            .filter((rec) => goals.some((g) => rec.source_goals && rec.source_goals.includes(g.id)))
            .map((rec) => {
              const isSlideOut = feedbackStatus[rec.id];
              const isExpanded = expandedCard === rec.id;
              const associatedGoal = goals.find(
                (g) => rec.source_goals && rec.source_goals.includes(g.id)
              );

            return (
              <div
                key={rec.id}
                className={`rec-card ${isSlideOut ? `slide-out-${isSlideOut}` : ""}`}
              >
                <div className="rec-card-header">
                  <div className="rec-badge-row">
                    <span className={`smile-phase-badge ${rec.smile_phase || "conceptual-clarity"}`}>
                      {rec.smile_phase ? rec.smile_phase.replace("-", " ") : "conceptual clarity"}
                    </span>
                    <span className="priority-score-badge">
                      🔥 Priority: {Number(rec.priority || 3.0).toFixed(2)}
                    </span>
                  </div>
                  <h3 className="rec-title">{rec.action}</h3>
                  <p className="rec-description">{rec.description}</p>
                  
                  {/* Goal and Phase Metadata */}
                  <div className="rec-metadata-list">
                    <div className="rec-metadata-item">
                      <span className="rec-metadata-label">Goal Name:</span>
                      <span className="rec-metadata-value text-highlight">
                        {associatedGoal ? associatedGoal.title : "General / Cold Start"}
                      </span>
                    </div>
                    <div className="rec-metadata-item">
                      <span className="rec-metadata-label">Current Phase:</span>
                      <span className="rec-metadata-value" style={{ textTransform: "capitalize" }}>
                        {associatedGoal ? associatedGoal.smile_phase.replace("-", " ") : "None"}
                      </span>
                    </div>
                    <div className="rec-metadata-item">
                      <span className="rec-metadata-label">Next Phase:</span>
                      <span className="rec-metadata-value text-accent" style={{ textTransform: "capitalize" }}>
                        {rec.smile_phase ? rec.smile_phase.replace("-", " ") : "conceptual clarity"}
                      </span>
                    </div>
                  </div>
                </div>

                {rec.reasoning && (
                  <div className="rec-reasoning-section">
                    <button
                      className="rec-reasoning-toggle"
                      onClick={() => setExpandedCard(isExpanded ? null : rec.id)}
                    >
                      <span>💡 AI Explanation</span>
                      <span className={`arrow ${isExpanded ? "open" : ""}`}>▶</span>
                    </button>
                    {isExpanded && (
                      <div className="rec-reasoning-content">
                        <p>{rec.reasoning}</p>
                      </div>
                    )}
                  </div>
                )}

                <div className="rec-actions-footer">
                  <button
                    className="rec-btn accept-btn"
                    onClick={() => handleFeedback(rec, "accepted")}
                    disabled={!!isSlideOut}
                  >
                    ✓ Accept Recommendation
                  </button>
                  <button
                    className="rec-btn dismiss-btn"
                    onClick={() => handleFeedback(rec, "dismissed")}
                    disabled={!!isSlideOut}
                  >
                    ✕ Dismiss
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
