import { useState, useMemo, useEffect, useRef } from "react";
import "./SignalsView.css";

const STREAM_COLORS = {
  lpi: {
    bg: "rgba(139,92,246,0.15)",
    border: "rgba(139,92,246,0.4)",
    text: "#a78bfa",
    dot: "#8b5cf6",
  },
  boardy: {
    bg: "rgba(59,130,246,0.15)",
    border: "rgba(59,130,246,0.4)",
    text: "#60a5fa",
    dot: "#3b82f6",
  },
  datapro: {
    bg: "rgba(16,185,129,0.15)",
    border: "rgba(16,185,129,0.4)",
    text: "#34d399",
    dot: "#10b981",
  },
  github: {
    bg: "rgba(251,191,36,0.15)",
    border: "rgba(251,191,36,0.4)",
    text: "#fbbf24",
    dot: "#f59e0b",
  },
  default: {
    bg: "rgba(156,163,175,0.15)",
    border: "rgba(156,163,175,0.4)",
    text: "#9ca3af",
    dot: "#6b7280",
  },
};

const SOURCE_BADGES = {
  github_api: { label: "GitHub API", color: "#fbbf24" },
  manual: { label: "Manual", color: "#34d399" },
  simulated: { label: "Simulated", color: "#f87171" },
  api: { label: "API", color: "#60a5fa" },
};

function StreamBadge({ stream }) {
  const c = STREAM_COLORS[stream] || STREAM_COLORS.default;
  return (
    <span
      className="stream-badge"
      style={{
        background: c.bg,
        border: `1px solid ${c.border}`,
        color: c.text,
      }}
    >
      {stream}
    </span>
  );
}

function SourceBadge({ source }) {
  const b = SOURCE_BADGES[source] || SOURCE_BADGES.api;
  return (
    <span
      className="source-badge"
      style={{
        background: `${b.color}22`,
        border: `1px solid ${b.color}55`,
        color: b.color,
      }}
    >
      {b.label}
    </span>
  );
}

function TimelineSignalCard({ signal, isAdminView, usersMap }) {
  const [expanded, setExpanded] = useState(false);
  const displayTime = useMemo(() => {
    if (signal.payload && signal.payload.created_at) {
      // Use the actual event time
      const date = new Date(signal.payload.created_at);
      if (!isNaN(date.getTime())) {
        return date.toLocaleString([], {
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        });
      }
    }
    // Fallback to ingestion time formatted with date and time
    const date = new Date(signal.timestamp);
    return date.toLocaleString([], {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }, [signal.payload, signal.timestamp]);

  const c = STREAM_COLORS[signal.stream] || STREAM_COLORS.default;

  return (
    <div className="timeline-card-wrapper">
      {/* Timeline Node */}
      <div
        className="timeline-card-dot"
        style={{
          background: c.dot,
          boxShadow: `0 0 8px ${c.dot}88`,
        }}
      />

      {/* Card Content */}
      <div
        className="timeline-card-content"
        style={{
          "--hover-border": c.border,
        }}
      >
        <div className="timeline-card-header">
          <div className="timeline-card-header-left">
            <span className="timeline-card-time">{displayTime}</span>
            <StreamBadge stream={signal.stream} />
            <span className="timeline-card-title">{signal.event_type}</span>
            <SourceBadge source={signal.source} />
          </div>
          {isAdminView && (
            <div className="timeline-card-owner">
              <span>👤</span>
              <span className="timeline-card-owner-id">
                {usersMap[signal.user_id]?.name
                  ? `${usersMap[signal.user_id].name} `
                  : ""}
                {usersMap[signal.user_id]?.email
                  ? `(${usersMap[signal.user_id].email})`
                  : signal.user_id}
              </span>
            </div>
          )}
        </div>

        {Object.keys(signal.payload || {}).length > 0 && (
          <div className="timeline-card-payload-wrapper">
            <button
              onClick={() => setExpanded(!expanded)}
              className="timeline-card-payload-toggle"
              style={{
                "--hover-text-color": c.text,
              }}
            >
              <span
                className={`timeline-card-payload-arrow ${expanded ? "expanded" : ""}`}
              >
                ▶
              </span>
              {expanded ? "Hide payload data" : "View payload data"}
            </button>

            {expanded && (
              <div className="timeline-card-payload-container">
                <pre className="timeline-card-payload-pre">
                  {JSON.stringify(signal.payload, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export function SignalsView({
  signals = [],
  loading,
  onIngestSignal,
  isAdminView,
  usersMap = {},
}) {
  const [filterStream, setFilterStream] = useState("");
  const [filterSource, setFilterSource] = useState("");

  const streams = [...new Set(signals.map((s) => s.stream))];
  const sources = [...new Set(signals.map((s) => s.source))];

  // Auto-sync logic
  const signalsRef = useRef(signals);
  const localIngestedIdsRef = useRef(new Set());

  useEffect(() => {
    signalsRef.current = signals;
  }, [signals]);

  useEffect(() => {
    let active = true;

    const formatToIST = (utcString) => {
      try {
        const date = new Date(utcString);
        if (isNaN(date.getTime())) return utcString;
        const istDate = new Date(date.getTime() + 5.5 * 60 * 60 * 1000);
        return istDate.toISOString().slice(0, 19) + "+05:30";
      } catch {
        return utcString;
      }
    };

    const autoSync = async () => {
      if (loading) return;
      try {
        const repoName = "Jahanvi3005/demo4";
        const response = await fetch(
          `https://api.github.com/repos/${repoName}/events`,
        );
        if (!active || !response.ok) return;
        const events = await response.json();
        if (!active) return;
        const recentEvents = events.slice(0, 20);

        for (const ev of recentEvents) {
          if (!active) return;
          const alreadyExists =
            (signalsRef.current || []).some(
              (s) => s.payload && s.payload.github_event_id === ev.id,
            ) || localIngestedIdsRef.current.has(ev.id);
          if (alreadyExists) continue;

          if (onIngestSignal) {
            const eventPayload = {
              github_event_id: ev.id,
              repo: ev.repo.name,
              actor: ev.actor.login,
              created_at: formatToIST(ev.created_at),
            };

            if (ev.payload?.action) {
              eventPayload.action = ev.payload.action;
            }

            if (ev.type === "CreateEvent") {
              eventPayload.ref_type = ev.payload?.ref_type || null;
              eventPayload.ref = ev.payload?.ref || null;
            } else if (ev.type === "PushEvent") {
              eventPayload.ref = ev.payload?.ref || null;
              eventPayload.commit_count = ev.payload?.commits?.length || 0;
              if (ev.payload?.commits && ev.payload.commits.length > 0) {
                eventPayload.latest_commit_message =
                  ev.payload.commits[0].message;
              }
            } else if (ev.type === "PullRequestEvent") {
              eventPayload.action = ev.payload?.action || null;
              eventPayload.pr_title = ev.payload?.pull_request?.title || null;
              eventPayload.pr_number = ev.payload?.pull_request?.number || null;
            }

            localIngestedIdsRef.current.add(ev.id);
            await onIngestSignal({
              stream: "github",
              event_type: ev.type,
              source: "github_api",
              payload: eventPayload,
            });
          }
        }
      } catch (err) {
        if (active) {
          console.error("Auto-sync failed:", err);
        }
      }
    };

    autoSync();
    const interval = setInterval(() => {
      if (active) {
        autoSync();
      }
    }, 30000); // Poll every 30 seconds

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [loading]); // eslint-disable-line react-hooks/exhaustive-deps

  // Apply filters and sort by time descending
  const filtered = useMemo(() => {
    const getSignalTime = (s) => {
      if (s.payload && s.payload.created_at) {
        const d = new Date(s.payload.created_at);
        if (!isNaN(d.getTime())) return d.getTime();
      }
      return new Date(s.timestamp).getTime();
    };

    return signals
      .filter((s) => {
        // Only display github signals belonging to the current demo repo (Jahanvi3005/demo4)
        if (s.stream === "github") {
          const repoName = s.payload?.repo ? s.payload.repo.toLowerCase() : "";
          if (repoName && repoName !== "jahanvi3005/demo4") {
            return false;
          }
        }
        if (filterStream && s.stream !== filterStream) return false;
        if (filterSource && s.source !== filterSource) return false;
        return true;
      })
      .sort((a, b) => getSignalTime(b) - getSignalTime(a));
  }, [signals, filterStream, filterSource]);

  // Group by date
  const groupedSignals = useMemo(() => {
    const groups = {};
    filtered.forEach((signal) => {
      let targetDate = new Date(signal.timestamp);
      if (signal.payload && signal.payload.created_at) {
        const payloadDate = new Date(signal.payload.created_at);
        if (!isNaN(payloadDate.getTime())) {
          targetDate = payloadDate;
        }
      }
      const dateStr = targetDate.toLocaleDateString(undefined, {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
      });
      if (!groups[dateStr]) groups[dateStr] = [];
      groups[dateStr].push(signal);
    });
    return groups;
  }, [filtered]);

  return (
    <div className="signals-view-container">
      {/* Filters Toolbar */}
      <div className="signals-view-toolbar">
        <div className="signals-view-toolbar-row">
          <h3 className="signals-view-title">Signal History</h3>

          <div className="signals-view-filters">
            <div className="signals-view-filter-group">
              <span className="signals-view-filter-label">Stream:</span>
              <select
                value={filterStream}
                onChange={(e) => setFilterStream(e.target.value)}
                className="signals-view-select"
              >
                <option value="">All Streams</option>
                {streams.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>

            <div className="signals-view-filter-group">
              <span className="signals-view-filter-label">Source:</span>
              <select
                value={filterSource}
                onChange={(e) => setFilterSource(e.target.value)}
                className="signals-view-select"
              >
                <option value="">All Sources</option>
                {sources.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Timeline Implementation */}
        <div className="signals-view-timeline-area">
          {/* Loading State */}
          {loading ? (
            <div className="signals-view-loading">
              <div className="spinner signals-view-spinner" />
              <span className="signals-view-loading-text">
                Loading signal history...
              </span>
            </div>
          ) : filtered.length === 0 ? (
            /* Empty State */
            <div className="signals-view-empty">
              <div className="signals-view-empty-icon">📡</div>
              <div className="signals-view-empty-title">No signals found</div>
              <div className="signals-view-empty-desc">
                {signals.length === 0
                  ? "Your activity timeline is empty. Log your first signal above to start tracking your progress."
                  : "No signals match your current filters. Try adjusting the stream or source drop-downs."}
              </div>
              {(filterStream || filterSource) && (
                <button
                  onClick={() => {
                    setFilterStream("");
                    setFilterSource("");
                  }}
                  className="signals-view-clear-btn"
                >
                  Clear Filters
                </button>
              )}
            </div>
          ) : (
            /* The Timeline */
            <div className="signals-timeline">
              {/* The Spine (Vertical Line) */}
              <div className="signals-timeline-spine" />

              <div className="signals-timeline-groups">
                {Object.entries(groupedSignals).map(([date, dateSignals]) => (
                  <div key={date} className="signals-timeline-group">
                    {/* Date Header */}
                    <div className="signals-timeline-group-header">
                      <div className="signals-timeline-group-dot" />
                      <div className="signals-timeline-group-date">{date}</div>
                    </div>

                    {/* Signals for this Date */}
                    <div className="signals-timeline-group-cards">
                      {dateSignals.map((signal) => (
                        <TimelineSignalCard
                          key={signal.id}
                          signal={signal}
                          isAdminView={isAdminView}
                          usersMap={usersMap}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
