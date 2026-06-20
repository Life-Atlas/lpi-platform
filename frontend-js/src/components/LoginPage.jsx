/**
 * LoginPage Widget
 *
 * Full-screen landing/login page. Connected to Supabase Auth.
 * Swapped mock name login with real email/password JWT flow.
 */
import { useState } from "react";
import { supabase } from "../supabaseClient";
import "./LoginPage.css";

export const LoginPage = ({ onAuthSuccess }) => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSignUp, setIsSignUp] = useState(false);
  const [entering, setEntering] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) return;

    setEntering(true);
    setErrorMsg("");

    try {
      if (isSignUp) {
        const { data, error } = await supabase.auth.signUp({
          email: email.trim(),
          password: password.trim(),
        });
        if (error) throw error;
        
        if (data.session) {
          onAuthSuccess(data.session);
        } else {
          alert("Success! Check your inbox (Mailpit) for a verification link.");
          setIsSignUp(false);
        }
      } else {
        const { data, error } = await supabase.auth.signInWithPassword({
          email: email.trim(),
          password: password.trim(),
        });
        if (error) throw error;
        
        // Success: pass session back to App
        if (data.session) {
          onAuthSuccess(data.session);
        }
      }
    } catch (err) {
      setErrorMsg(err.message || "Authentication failed");
    } finally {
      setEntering(false);
    }
  };

  return (
    <div className="login-page">
      {/* Shared background graphics */}
      <div className="bg-graphics" aria-hidden="true">
        <div className="bg-orb bg-orb-1" />
        <div className="bg-orb bg-orb-2" />
        <div className="bg-orb bg-orb-3" />
        <div className="bg-orb bg-orb-4" />
        <div className="bg-grid" />
      </div>

      <div className={`login-container ${entering ? "login-exit" : ""}`}>
        {/* Branding */}
        <div className="login-eyebrow">Life Programmable Interface</div>
        <h1 className="login-title">LPI Goal Platform</h1>
        <p className="login-subtitle">
          Track intentions, score priorities, and evolve through SMILE phases.
        </p>

        {/* Login card */}
        <div className="login-card">
          <h2 className="login-card-title">
            {isSignUp ? "Create Account" : "Welcome back"}
          </h2>
          <p className="login-card-desc">
            {isSignUp
              ? "Register to start mapping your goals"
              : "Enter credentials to access the registry"}
          </p>

          {errorMsg && (
            <div className="login-error-container">
              {errorMsg}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="login-email">
                Email
              </label>
              <input
                id="login-email"
                type="email"
                className="form-input"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoFocus
                disabled={entering}
                required
              />
            </div>

            <div className="form-group login-form-group-spacing">
              <label className="form-label" htmlFor="login-password">
                Password
              </label>
              <input
                id="login-password"
                type="password"
                className="form-input"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={entering}
                required
              />
            </div>

            <button
              type="submit"
              className="login-btn login-submit-spacing"
              disabled={entering}
            >
              {entering ? (
                <span className="login-btn-loading">
                  <span className="spinner" /> Processing…
                </span>
              ) : isSignUp ? (
                "Create Account"
              ) : (
                "Enter Platform"
              )}
            </button>
          </form>

          <div className="login-toggle-container">
            <button
              onClick={() => setIsSignUp(!isSignUp)}
              className="login-toggle-btn"
              disabled={entering}
            >
              {isSignUp
                ? "Already have an account? Sign In"
                : "New to the platform? Sign Up"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
