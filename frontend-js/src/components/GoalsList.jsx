import { useEffect, useState } from "react";
import { goalApi } from "../api";
import { GoalCard } from "./GoalCard";

export const GoalsList = ({ goals: goalsProp, onGoalUpdated, apiBase, isAdminView, usersMap = {}, userId }) => {
  const isControlled = goalsProp !== undefined;
  const [goals, setGoals] = useState(isControlled ? goalsProp : []);
  const [loading, setLoading] = useState(!isControlled);
  const [error, setError] = useState(null);

  const fetchGoals = async () => {
    if (isControlled) return;
    try {
      setLoading(true);
      const data = await goalApi.getGoals();
      setGoals(data);
      setError(null);
    } catch (err) {
      setError(err.message || "Failed to load goals");
    } finally {
      setLoading(false);
    }
  };

  // Sync when parent-controlled goals change
  useEffect(() => {
    if (isControlled) setGoals(goalsProp);
  }, [goalsProp]);

  // Standalone: fetch on mount
  useEffect(() => {
    if (!isControlled) fetchGoals();
  }, []);

  const handleGoalUpdated = () => {
    fetchGoals();
    onGoalUpdated?.();
  };

  return (
    <div className="premium-card">
      <div style={{ display: "flex", justifyContent: "between", alignItems: "center", marginBottom: "20px" }}>
        <h2 className="widget-title" style={{ fontSize: "1.2rem", fontWeight: "700" }}>Goals ({goals.length})</h2>
      </div>

      <div>
        {loading ? (
          <div className="goals-grid">
            <div className="goal-card skeleton-card shadow-pulse" />
            <div className="goal-card skeleton-card shadow-pulse" />
          </div>
        ) : error ? (
          <div className="empty-state">
            <p style={{ color: "var(--accent-red)" }}>{error}</p>
            <button className="retry-btn" onClick={fetchGoals}>Retry</button>
          </div>
        ) : goals.length === 0 ? (
          <div className="empty-state">
            <h3>No goals registered</h3>
            <p>
              Register your first intent or goal using the creation form to
              track its priority score and SMILE phase progress.
            </p>
          </div>
        ) : (
          <div className="goals-grid">
            {goals.map((goal) => (
              <GoalCard
                key={goal.id}
                goal={goal}
                onGoalUpdated={handleGoalUpdated}
                apiBase={apiBase}
                isAdminView={isAdminView}
                usersMap={usersMap}
                userId={userId}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
