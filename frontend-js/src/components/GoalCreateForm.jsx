import { useState } from 'react';
import { goalApi } from '../api';
import "./GoalCreateForm.css";

export const GoalCreateForm = ({ onGoalCreated }) => {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState(5);
  const [smilePhase, setSmilePhase] = useState('reality-emulation');
  const [urgencyFlag, setUrgencyFlag] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [debugInfo, setDebugInfo] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim()) {
      setError('Goal title is required');
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setDebugInfo(null);

    const payload = {
      title: title.trim(),
      description: description.trim(),
      priority,
      smile_phase: smilePhase,
      urgency_flag: urgencyFlag,
    };

    console.log('[GoalCreate] Submitting payload:', payload);

    try {
      await goalApi.createGoal(payload);

      // success
      setTitle('');
      setDescription('');
      setPriority(5);
      setSmilePhase('reality-emulation');
      setUrgencyFlag(false);
      setDebugInfo(null);
      onGoalCreated?.();
    } catch (err) {
      console.error('[GoalCreate] Error:', err);
      setDebugInfo(err.message);
      setError(`Error: ${err.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="premium-card">
      <div style={{ marginBottom: "20px" }}>
        <h2 className="widget-title" style={{ fontSize: "1.2rem", fontWeight: "700" }}>Register Intent / Goal</h2>
      </div>

      <div>
        {error && (
          <div className="form-error-container">
            <strong>Error:</strong> {error}
            {debugInfo && (
              <pre className="form-error-debug">{debugInfo}</pre>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label" htmlFor="goal-title">Title</label>
            <input
              id="goal-title"
              type="text"
              className="form-input"
              placeholder="e.g. Master Docker deployment"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={isSubmitting}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="goal-desc">Description</label>
            <textarea
              id="goal-desc"
              className="form-textarea"
              placeholder="Describe the context or intent of this goal..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isSubmitting}
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="goal-priority">Priority Score (1-10)</label>
            <div className="priority-slider-container">
              <input
                id="goal-priority"
                type="range"
                min="1"
                max="10"
                className="priority-slider"
                value={priority}
                onChange={(e) => setPriority(parseInt(e.target.value))}
                disabled={isSubmitting}
              />
              <span className="priority-val">{priority}</span>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="goal-phase">Initial SMILE Phase</label>
            <select
              id="goal-phase"
              className="form-select"
              value={smilePhase}
              onChange={(e) => setSmilePhase(e.target.value)}
              disabled={isSubmitting}
            >
              <option value="reality-emulation">Reality Emulation (Phase 1)</option>
              <option value="concurrent-engineering">Concurrent Engineering (Phase 2)</option>
              <option value="collective-intelligence">Collective Intelligence (Phase 3)</option>
              <option value="contextual-intelligence">Contextual Intelligence (Phase 4)</option>
              <option value="continuous-intelligence">Continuous Intelligence (Phase 5)</option>
              <option value="perpetual-wisdom">Perpetual Wisdom (Phase 6)</option>
            </select>
          </div>

          <div className="form-group">
            <label className="urgency-toggle-label">
              <input
                type="checkbox"
                className="urgency-checkbox"
                checked={urgencyFlag}
                onChange={(e) => setUrgencyFlag(e.target.checked)}
                disabled={isSubmitting}
              />
              <span className="urgency-toggle-text">
                Mark as Urgent
                <span className="urgency-hint">Adds +0.2 to composite score</span>
              </span>
            </label>
          </div>

          <button type="submit" className="submit-btn" disabled={isSubmitting}>
            {isSubmitting ? 'Registering...' : 'Register Goal'}
          </button>
        </form>
      </div>
    </div>
  );
};
