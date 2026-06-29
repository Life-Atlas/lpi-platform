import { useState, useEffect, useRef } from "react";
import "./App.css";
import { goalApi } from "./api";
import { supabase } from "./supabaseClient";
import { LoginPage } from "./components/LoginPage";
import { GoalsList } from "./components/GoalsList";
import { GoalCreateModal } from "./components/GoalCreateModal";
import { UserProfile } from "./components/UserProfile";
import { SignalsView } from "./components/SignalsView";
import { GithubTracker } from "./components/GithubTracker";
import { RecommendationsView } from "./components/RecommendationsView";
import { useToast } from "./components/Toast";

const API_BASE = import.meta.env.VITE_API_BASE || "";

function App() {
  const { showToast } = useToast();
  const pendingIngestsRef = useRef(new Set());
  const [session, setSession] = useState(null);
  const [user, setUser] = useState(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [usersMap, setUsersMap] = useState({});
  const [goals, setGoals] = useState([]);
  const [signals, setSignals] = useState(null);
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("active");

  const [githubExchanging, setGithubExchanging] = useState(false);
  const [githubError, setGithubError] = useState(null);

  // Catch GitHub OAuth Redirect Callback Code
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    
    if (code && session?.user?.id) {
      const handleGithubExchange = async () => {
        setGithubExchanging(true);
        setGithubError(null);
        try {
          await goalApi.exchangeGithubToken(code, session.user.id);
          // Clean the query parameters from the URL
          const newUrl = window.location.origin + window.location.pathname;
          window.history.replaceState({}, document.title, newUrl);
          // Switch to github tracker tab
          setActiveTab("github");
          showToast("GitHub account linked successfully!", "success");
        } catch (err) {
          console.error("Failed to link GitHub account:", err);
          setGithubError(err.message || "Failed to link GitHub account.");
          showToast(err.message || "Failed to link GitHub account.", "error");
        } finally {
          setGithubExchanging(false);
        }
      };
      
      handleGithubExchange();
    }
  }, [session]);

  // Track Supabase Auth session changes
  useEffect(() => {
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      setSession(session);
      if (session) {
        goalApi.setToken(session.access_token);
        setUser(session.user.email);
        try {
          const meData = await goalApi.getMe();
          setIsAdmin(meData.is_admin);
        } catch (e) {
          console.error("Failed to fetch user role", e);
        }
      }
      setLoading(false);
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (_event, session) => {
      setSession(session);
      if (session) {
        goalApi.setToken(session.access_token);
        setUser(session.user.email);
        try {
          const meData = await goalApi.getMe();
          setIsAdmin(meData.is_admin);
        } catch (e) {
          console.error("Failed to fetch user role", e);
        }
      } else {
        goalApi.setToken(null);
        setUser(null);
        setIsAdmin(false);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const fetchGoals = async () => {
    if (!session) return;
    try {
      setLoading(true);
      if (isAdmin && activeTab === "admin") {
         const [data, uMap] = await Promise.all([
             goalApi.getAllGoals(),
             goalApi.getUsersMap().catch(() => ({}))
         ]);
         setGoals(data);
         setUsersMap(uMap);
      } else {
         const data = await goalApi.getGoals();
         setGoals(data);
         setUsersMap({});
      }
      setError(null);
    } catch (err) {
      setError(err.message || "Failed to load goals");
    } finally {
      setLoading(false);
    }
  };

  const fetchSignals = async () => {
    if (!session) return;
    try {
      setSignalsLoading(true);
      if (isAdmin && activeTab === "admin_signals") {
        const [data, uMap] = await Promise.all([
             goalApi.getAllSignals(),
             goalApi.getUsersMap().catch(() => ({}))
         ]);
         setSignals(data);
         setUsersMap(uMap);
      } else {
        const data = await goalApi.getSignals();
        setSignals(data);
        if (activeTab === "signals") setUsersMap({});
      }
    } catch (err) {
      console.error("Failed to fetch signals", err);
    } finally {
      setSignalsLoading(false);
    }
  };

  const handleIngestSignal = async (signalData) => {
    const eventId = signalData.payload?.github_event_id;
    if (eventId) {
      if (pendingIngestsRef.current.has(eventId)) {
        return false;
      }
      const alreadyExists = signals && signals.some(s => s.payload?.github_event_id === eventId);
      if (alreadyExists) {
        return false;
      }
      pendingIngestsRef.current.add(eventId);
    }
    try {
      await goalApi.ingestSignal(signalData);
      await fetchSignals();
      return true;
    } catch (err) {
      console.error("Ingest failed:", err);
      return false;
    } finally {
      if (eventId) {
        pendingIngestsRef.current.delete(eventId);
      }
    }
  };

  useEffect(() => {
    if (session) fetchGoals();
  }, [session, activeTab, isAdmin]);

  useEffect(() => {
    if (session && (activeTab === "signals" || activeTab === "admin_signals")) fetchSignals();
  }, [session, activeTab, isAdmin]);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    setGoals([]);
    setSignals(null);
    setModalOpen(false);
  };

  if (loading) {
    return (
      <div className="login-page app-loading-screen">
        <div className="spinner app-loading-spinner" />
      </div>
    );
  }

  if (!session) {
    return <LoginPage onAuthSuccess={(s) => setSession(s)} />;
  }

  return (
    <>
      <div className="bg-graphics" aria-hidden="true">
        <div className="bg-orb bg-orb-1" />
        <div className="bg-orb bg-orb-2" />
        <div className="bg-orb bg-orb-3" />
        <div className="bg-orb bg-orb-4" />
        <div className="bg-grid" />
      </div>

      <div className="navbar-row">
        <nav className="navbar-pill navbar-left">
          <span className="navbar-title">LPI Platform</span>
        </nav>

        <nav className="navbar-pill navbar-right">
          <div className="user-badge" onClick={() => setProfileOpen(true)} title="View profile">
            <span className="user-avatar">
              {session?.user?.id && localStorage.getItem(`lpi_${session.user.id}_avatar`)
                ? <img src={localStorage.getItem(`lpi_${session.user.id}_avatar`)} alt="avatar" className="app-avatar-img" />
                : user.charAt(0).toUpperCase()}
            </span>
            <span className="user-name">{user}</span>
          </div>

          <button
            className="create-goal-btn"
            onClick={() => setModalOpen(true)}
            id="open-create-goal-modal"
          >
            Create Goal
          </button>

          <button className="signout-btn" onClick={handleLogout} title="Sign out">
            ↩
          </button>
        </nav>
      </div>

      <div className="app-container">
        
        <UserProfile userName={user} goals={goals} userId={session?.user?.id} />

        <div className="dashboard-tabs">
          <button
            className={`tab-btn ${activeTab === "active" ? "active" : ""}`}
            onClick={() => setActiveTab("active")}
          >
            Active Goals
          </button>
          <button
            className={`tab-btn ${activeTab === "evolved" ? "active" : ""}`}
            onClick={() => setActiveTab("evolved")}
          >
            Evolved (Completed)
          </button>
          <button
            className={`tab-btn ${activeTab === "signals" ? "active tab-btn-signals-active" : ""}`}
            onClick={() => setActiveTab("signals")}
          >
            Signals
          </button>
          <button
            className={`tab-btn ${activeTab === "github" ? "active" : ""}`}
            onClick={() => setActiveTab("github")}
          >
            GitHub Connect
          </button>
          <button
            className={`tab-btn ${activeTab === "recommendations" ? "active" : ""}`}
            onClick={() => setActiveTab("recommendations")}
          >
            AI Recommendations
          </button>
          {isAdmin && (
            <>
              <button
                className={`tab-btn tab-btn-alert-color ${activeTab === "admin" ? "active" : ""}`}
                onClick={() => setActiveTab("admin")}
              >
                Admin View (Goals)
              </button>
              <button
                className={`tab-btn tab-btn-alert-color ${activeTab === "admin_signals" ? "active" : ""}`}
                onClick={() => setActiveTab("admin_signals")}
              >
                Admin View (Signals)
              </button>
            </>
          )}
        </div>

        {error ? (
          <div className="premium-card error-card">
            <div className="error-title">
              {error.includes("429") || error.toLowerCase().includes("rate limit")
                ? "Rate Limit Exceeded"
                : "Registry Connection Error"}
            </div>
            <p className="error-text">
              {error.includes("429") || error.toLowerCase().includes("rate limit")
                ? "You have made too many requests. Please wait 30 seconds without refreshing so that the lockout window resets."
                : "Failed to connect to the FastAPI backend. Make sure the server is running on port 8000."}
            </p>
            <button className="retry-btn" onClick={fetchGoals}>
              Attempt Reconnection
            </button>
          </div>
      ) : githubExchanging ? (
        <div className="premium-card github-loading">
          <div className="github-spinner"></div>
          <p>Exchanging GitHub authorization code...</p>
        </div>
      ) : activeTab === "github" ? (
        <GithubTracker userId={session?.user?.id} />
      ) : activeTab === "recommendations" ? (
        <RecommendationsView userId={session?.user?.id} onGoalCreated={fetchGoals} goals={goals} />
      ) : activeTab === "signals" || activeTab === "admin_signals" ? (
        <SignalsView
          userId={session?.user?.id}
          signals={signals || []}
          loading={signalsLoading || signals === null}
          onIngestSignal={handleIngestSignal}
          isAdminView={activeTab === "admin_signals"}
          usersMap={usersMap}
          goals={goals}
        />
      ) : (
        <GoalsList
          apiBase={API_BASE}
          isAdminView={activeTab === "admin"}
          usersMap={usersMap}
          userId={session?.user?.id}
          goals={activeTab === "admin"
            ? goals
            : activeTab === "active" 
              ? goals.filter(g => g.smile_phase !== "perpetual-wisdom")
              : goals.filter(g => g.smile_phase === "perpetual-wisdom")}
          onGoalUpdated={fetchGoals}
        />
      )}
      </div>

      <GoalCreateModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onGoalCreated={fetchGoals}
        apiBase={API_BASE}
        userId={user}
      />

      {profileOpen && (
        <>
          <div
            onClick={() => setProfileOpen(false)}
            className="profile-drawer-backdrop"
          />
          <div 
            className="profile-drawer"
            style={{
              transform: profileOpen ? "translateX(0)" : "translateX(100%)",
            }}
          >
            <div className="profile-drawer-header">
              <span className="profile-drawer-header-title">Profile</span>
              <button onClick={() => setProfileOpen(false)} className="profile-drawer-close-btn">×</button>
            </div>

            <div className="profile-drawer-body">
              <div className="profile-drawer-avatar-wrapper">
                {session?.user?.id && localStorage.getItem(`lpi_${session.user.id}_avatar`)
                  ? <img src={localStorage.getItem(`lpi_${session.user.id}_avatar`)} alt="avatar" className="app-avatar-img" />
                  : user.charAt(0).toUpperCase()}
              </div>
              <div className="profile-drawer-text-center">
                <div className="profile-drawer-name">{user}</div>
                {session?.user?.id && localStorage.getItem(`lpi_${session.user.id}_gender`) && (
                  <div className="profile-drawer-gender">{localStorage.getItem(`lpi_${session.user.id}_gender`)}</div>
                )}
                {session?.user?.id && localStorage.getItem(`lpi_${session.user.id}_dob`) && (
                  <div className="profile-drawer-dob">Born {localStorage.getItem(`lpi_${session.user.id}_dob`)}</div>
                )}
                {session?.user?.id && localStorage.getItem(`lpi_${session.user.id}_bio`) && (
                  <div className="profile-drawer-bio">{localStorage.getItem(`lpi_${session.user.id}_bio`)}</div>
                )}
              </div>
            </div>

            <div className="profile-drawer-stats">
              {[
                { label: "Active Goals", value: goals.filter(g => g.smile_phase !== "perpetual-wisdom").length, color: "#a78bfa" },
                { label: "Evolved Goals", value: goals.filter(g => g.smile_phase === "perpetual-wisdom").length, color: "#34d399" },
                { label: "Urgent Goals", value: goals.filter(g => g.urgency_flag).length, color: "#f87171" },
                { label: "Total Goals", value: goals.length, color: "#60a5fa" },
              ].map(({ label, value, color }) => (
                <div key={label} className="profile-drawer-stat-item">
                  <span className="profile-drawer-stat-label">{label}</span>
                  <span className="profile-drawer-stat-value" style={{ color }}>{value}</span>
                </div>
              ))}
            </div>

            <div className="profile-drawer-footer">
              <button onClick={() => { setProfileOpen(false); handleLogout(); }} className="profile-drawer-signout-btn">
                Sign Out
              </button>
            </div>
          </div>
        </>
      )}
    </>
  );
}

export default App;
