import { useState, useEffect } from "react";
import { goalApi } from "../api";
import "./GithubTracker.css";
import { useToast } from "./Toast";

export const GithubTracker = ({ userId }) => {
  const { showToast } = useToast();
  const [isConnected, setIsConnected] = useState(false);
  const [repos, setRepos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [trackingStatus, setTrackingStatus] = useState({}); // { repoFullName: "success" | "error" | "loading" }
  const [customRepo, setCustomRepo] = useState("");
  const [customLoading, setCustomLoading] = useState(false);
  const [customDisconnectLoading, setCustomDisconnectLoading] = useState(false);

  const clientId = import.meta.env.VITE_GITHUB_CLIENT_ID;

  const fetchRepositories = async () => {
    if (!userId) return;
    try {
      setLoading(true);
      setError(null);
      const data = await goalApi.getGithubRepositories(userId);
      setRepos(data.repositories || []);
      setIsConnected(true);
    } catch (err) {
      console.warn("Failed to fetch GitHub repos (likely not connected yet):", err.message);
      setIsConnected(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRepositories();
    if (userId) {
      const activeList = JSON.parse(localStorage.getItem(`tracked_repos_${userId}`) || "[]");
      const initialStatus = {};
      activeList.forEach((name) => {
        initialStatus[name] = "success";
      });
      setTrackingStatus(initialStatus);
    } else {
      setTrackingStatus({});
    }
  }, [userId]);

  const handleDisconnectAccount = async () => {
    if (!userId) return;
    try {
      setLoading(true);
      await goalApi.disconnectGithubAccount(userId);
      setIsConnected(false);
      setRepos([]);
      setTrackingStatus({});
      localStorage.removeItem(`tracked_repos_${userId}`);
      showToast("Successfully disconnected GitHub account.", "success");
    } catch (err) {
      console.error("Failed to disconnect account:", err);
      showToast(err.message || "Failed to disconnect GitHub account.", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = () => {
    if (!clientId) {
      setError("VITE_GITHUB_CLIENT_ID is not configured in the environment.");
      return;
    }
    const redirectUri = window.location.origin;
    const scope = "repo,admin:repo_hook";
    const githubUrl = `https://github.com/login/oauth/authorize?client_id=${clientId}&scope=${scope}&redirect_uri=${redirectUri}&prompt=select_account`;
    window.location.href = githubUrl;
  };

  const handleTrackRepo = async (repo) => {
    if (!userId) return;
    setActionLoading(repo.full_name);
    setTrackingStatus((prev) => ({ ...prev, [repo.full_name]: "loading" }));
    try {
      const response = await goalApi.trackGithubRepository(userId, repo.owner, repo.name);
      setTrackingStatus((prev) => ({ ...prev, [repo.full_name]: "success" }));
      
      const storageKey = `tracked_repos_${userId}`;
      const activeList = JSON.parse(localStorage.getItem(storageKey) || "[]");
      if (!activeList.includes(repo.full_name)) {
        activeList.push(repo.full_name);
        localStorage.setItem(storageKey, JSON.stringify(activeList));
      }
    } catch (err) {
      console.error("Failed to track repository:", err);
      setTrackingStatus((prev) => ({ ...prev, [repo.full_name]: "error" }));
      setTimeout(() => {
        showToast(err.message || "Failed to set up tracking webhook.", "error");
      }, 50);
    } finally {
      setActionLoading(null);
    }
  };

  const handleTrackCustomRepo = async () => {
    if (!userId || !customRepo.trim()) return;
    const parts = customRepo.trim().split("/");
    if (parts.length !== 2) {
      showToast("Please enter in owner/repo format (e.g. facebook/react)", "error");
      return;
    }
    const [owner, name] = parts;
    const fullName = `${owner}/${name}`;
    setCustomLoading(true);
    try {
      // Step 1: Validate repository is public using our validate-public-repo endpoint
      await goalApi.validatePublicRepo(owner, name);
      
      // Step 2: Track it
      await goalApi.trackGithubRepository(userId, owner, name);
      
      // Step 3: Add to tracked repos in localStorage and trackingStatus state
      const storageKey = `tracked_repos_${userId}`;
      const activeList = JSON.parse(localStorage.getItem(storageKey) || "[]");
      if (!activeList.includes(fullName)) {
        activeList.push(fullName);
        localStorage.setItem(storageKey, JSON.stringify(activeList));
      }
      setTrackingStatus((prev) => ({ ...prev, [fullName]: "success" }));
      
      showToast(`Successfully tracked and synced signals for ${fullName}!`, "success");
      setCustomRepo("");
      fetchRepositories();
    } catch (err) {
      console.error(err);
      showToast(err.message || "Failed to track custom repository.", "error");
    } finally {
      setCustomLoading(false);
    }
  };

  const handleDisconnectCustomRepo = async () => {
    if (!userId || !customRepo.trim()) return;
    const parts = customRepo.trim().split("/");
    if (parts.length !== 2) {
      showToast("Please enter in owner/repo format (e.g. facebook/react)", "error");
      return;
    }
    const [owner, name] = parts;
    const fullName = `${owner}/${name}`;
    setCustomDisconnectLoading(true);
    try {
      await goalApi.disconnectGithubRepository(userId, owner, name);
      
      setTrackingStatus((prev) => {
        const next = { ...prev };
        delete next[fullName];
        return next;
      });
      
      const storageKey = `tracked_repos_${userId}`;
      const activeList = JSON.parse(localStorage.getItem(storageKey) || "[]");
      const filteredList = activeList.filter((name) => name !== fullName);
      localStorage.setItem(storageKey, JSON.stringify(filteredList));
      
      showToast(`Successfully disconnected from ${fullName}.`, "success");
      setCustomRepo("");
      fetchRepositories();
    } catch (err) {
      console.error(err);
      showToast(err.message || "Failed to disconnect custom repository.", "error");
    } finally {
      setCustomDisconnectLoading(false);
    }
  };

  const handleUntrackRepo = async (repo) => {
    if (!userId) return;
    setActionLoading(repo.full_name);
    setTrackingStatus((prev) => ({ ...prev, [repo.full_name]: "loading" }));
    try {
      await goalApi.disconnectGithubRepository(userId, repo.owner, repo.name);
      setTrackingStatus((prev) => {
        const next = { ...prev };
        delete next[repo.full_name];
        return next;
      });
      
      const storageKey = `tracked_repos_${userId}`;
      const activeList = JSON.parse(localStorage.getItem(storageKey) || "[]");
      const filteredList = activeList.filter((name) => name !== repo.full_name);
      localStorage.setItem(storageKey, JSON.stringify(filteredList));
      showToast(`Successfully disconnected from ${repo.name}.`, "success");
    } catch (err) {
      console.error("Failed to disconnect repository:", err);
      showToast(err.message || "Failed to disconnect repository.", "error");
      setTrackingStatus((prev) => ({ ...prev, [repo.full_name]: "success" }));
    } finally {
      setActionLoading(null);
    }
  };

  const filteredRepos = repos.filter((repo) =>
    repo.full_name.toLowerCase().includes(searchTerm.toLowerCase()) &&
    repo.permissions?.admin === true
  );


  if (!userId) {
    return (
      <div className="premium-card github-container">
        <div className="empty-state">
          <h3>Authentication Required</h3>
          <p>Please log in to integrate your GitHub workspace.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="premium-card github-container">
      <div className="github-header-row">
        <div>
          <h2 className="widget-title" style={{ fontSize: "1.25rem", fontWeight: "700" }}>
            GitHub Activity Signals
          </h2>
          <p className="github-subtitle">
            Link your GitHub account to automatically ingest push & pull request events as LPI Activity Signals.
          </p>
        </div>
        {isConnected && (
          <div style={{ display: "flex", gap: "12px", alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" }}>
            {Object.keys(trackingStatus).filter(k => trackingStatus[k] === "success").length > 0 && (
              <div className="connection-badge tracked-repo" style={{ background: "rgba(139, 92, 246, 0.1)", color: "#a78bfa", border: "1px solid rgba(139, 92, 246, 0.2)", textTransform: "none", letterSpacing: "normal" }}>
                Active: {Object.keys(trackingStatus).filter(k => trackingStatus[k] === "success").join(", ")}
              </div>
            )}
            <div className="connection-badge connected">
              <span className="dot"></span> Connected
            </div>
            <button
              className="github-track-btn tracking untrack-btn"
              onClick={handleDisconnectAccount}
              style={{
                background: "rgba(239, 68, 68, 0.15)",
                borderColor: "#ef4444",
                color: "#ef4444",
                padding: "4px 10px",
                fontSize: "0.75rem",
                borderRadius: "30px",
                margin: 0
              }}
            >
              Disconnect Account
            </button>
          </div>
        )}
      </div>


      {error && <div className="github-error-banner">{error}</div>}

      {loading ? (
        <div className="github-loading">
          <div className="github-spinner"></div>
          <p>Loading GitHub integration...</p>
        </div>
      ) : !isConnected ? (
        <div className="github-connect-flow">
          <div className="github-auth-card">
            <div className="github-large-icon">🐙</div>
            <h3>Connect Your GitHub Account</h3>
            <p>
              Grant the platform secure access to list your repositories and configure webhooks to feed your activity signals timeline.
            </p>
            <button className="github-auth-btn" onClick={handleConnect}>
              Authorize with GitHub
            </button>
          </div>
        </div>
      ) : (
        <div className="github-repos-dashboard">
          {/* Custom Repository Tracking Panel */}
          <div style={{ display: "flex", gap: "10px", marginBottom: "20px", background: "rgba(255, 255, 255, 0.03)", padding: "15px", borderRadius: "10px", border: "1px solid rgba(255, 255, 255, 0.08)", alignItems: "center" }}>
            <div style={{ flex: 1 }}>
              <input
                type="text"
                placeholder="Track any public repository (e.g. facebook/react)"
                className="github-search-input"
                style={{ width: "100%", margin: 0, padding: "8px 12px" }}
                value={customRepo}
                onChange={(e) => setCustomRepo(e.target.value)}
              />
            </div>
            <button
              className="github-track-btn"
              style={{ margin: 0, padding: "8px 20px", height: "auto", fontSize: "0.85rem" }}
              onClick={handleTrackCustomRepo}
              disabled={customLoading}
            >
              {customLoading ? (
                <>
                  <span className="button-spinner"></span> Syncing...
                </>
              ) : (
                "🔗 Track Custom Repo"
              )}
            </button>
            <button
              className="github-track-btn untrack-btn"
              style={{ 
                margin: 0, 
                padding: "8px 20px", 
                height: "auto", 
                fontSize: "0.85rem",
                background: "rgba(239, 68, 68, 0.15)",
                borderColor: "#ef4444",
                color: "#ef4444"
              }}
              onClick={handleDisconnectCustomRepo}
              disabled={customDisconnectLoading}
            >
              {customDisconnectLoading ? (
                <>
                  <span className="button-spinner"></span> Disconnecting...
                </>
              ) : (
                "✕ Disconnect Custom Repo"
              )}
            </button>
          </div>

          <div className="github-toolbar">
            <input
              type="text"
              placeholder="Search repositories..."
              className="github-search-input"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            <button className="github-refresh-btn" onClick={fetchRepositories} title="Refresh repositories">
              ⟳ Refresh
            </button>
          </div>

          <div className="github-repo-list">
            {filteredRepos.length === 0 ? (
              <div className="empty-state">
                <p>No repositories found.</p>
              </div>
            ) : (
              filteredRepos.map((repo) => {
                const status = trackingStatus[repo.full_name];
                return (
                  <div key={repo.id} className="github-repo-card">
                    <div className="github-repo-info">
                      <h4 className="github-repo-name">
                        <a href={repo.html_url} target="_blank" rel="noopener noreferrer">
                          {repo.full_name}
                        </a>
                      </h4>
                      <div className="github-repo-badges">
                        {repo.private ? (
                          <span className="repo-badge private">Private</span>
                        ) : (
                          <span className="repo-badge public">Public</span>
                        )}
                      </div>
                    </div>

                    {status === "success" ? (
                      <button
                        className="github-track-btn tracking untrack-btn"
                        onClick={() => handleUntrackRepo(repo)}
                        disabled={actionLoading === repo.full_name}
                        style={{ background: "rgba(239, 68, 68, 0.15)", borderColor: "#ef4444", color: "#ef4444" }}
                      >
                        Disconnect
                      </button>
                    ) : (
                      <button
                        className="github-track-btn"
                        onClick={() => handleTrackRepo(repo)}
                        disabled={actionLoading === repo.full_name}
                      >
                        {actionLoading === repo.full_name ? (
                          <>
                            <span className="button-spinner"></span> Creating Webhook...
                          </>
                        ) : (
                          "🔗 Track Repository"
                        )}
                      </button>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};
