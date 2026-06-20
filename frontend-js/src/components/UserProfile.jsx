import { useState, useRef, useEffect } from "react";
import { supabase } from "../supabaseClient";
import "./UserProfile.css";

export const UserProfile = ({ userName, goals = [], userId }) => {
  const activeGoals = goals.filter(g => g.smile_phase !== "perpetual-wisdom").length;
  const evolvedGoals = goals.filter(g => g.smile_phase === "perpetual-wisdom").length;
  const urgentGoals = goals.filter(g => g.urgency_flag).length;

  const [avatarSrc, setAvatarSrc] = useState(() => userId ? localStorage.getItem(`lpi_${userId}_avatar`) : null);
  const fileInputRef = useRef(null);

  const [editing, setEditing] = useState(false);
  const [displayName, setDisplayName] = useState(() => userId ? localStorage.getItem(`lpi_${userId}_name`) || "" : "");
  const [gender, setGender] = useState(() => userId ? localStorage.getItem(`lpi_${userId}_gender`) || "" : "");
  const [dob, setDob] = useState(() => userId ? localStorage.getItem(`lpi_${userId}_dob`) || "" : "");
  const [bio, setBio] = useState(() => userId ? localStorage.getItem(`lpi_${userId}_bio`) || "" : "");
  const [draft, setDraft] = useState({ name: "", gender: "", dob: "", bio: "" });

  // Sync state whenever the logged-in user ID changes
  useEffect(() => {
    if (userId) {
      // 1. Load from localStorage as a quick offline fallback
      setAvatarSrc(localStorage.getItem(`lpi_${userId}_avatar`) || null);
      setDisplayName(localStorage.getItem(`lpi_${userId}_name`) || "");
      setGender(localStorage.getItem(`lpi_${userId}_gender`) || "");
      setDob(localStorage.getItem(`lpi_${userId}_dob`) || "");
      setBio(localStorage.getItem(`lpi_${userId}_bio`) || "");

      // 2. Fetch fresh metadata from Supabase Auth online
      const fetchSupabaseMetadata = async () => {
        try {
          const { data: { user }, error } = await supabase.auth.getUser();
          if (error) throw error;
          if (user && user.user_metadata) {
            const meta = user.user_metadata;
            if (meta.display_name !== undefined) {
              setDisplayName(meta.display_name || "");
              localStorage.setItem(`lpi_${userId}_name`, meta.display_name || "");
            }
            if (meta.gender !== undefined) {
              setGender(meta.gender || "");
              localStorage.setItem(`lpi_${userId}_gender`, meta.gender || "");
            }
            if (meta.dob !== undefined) {
              setDob(meta.dob || "");
              localStorage.setItem(`lpi_${userId}_dob`, meta.dob || "");
            }
            if (meta.bio !== undefined) {
              setBio(meta.bio || "");
              localStorage.setItem(`lpi_${userId}_bio`, meta.bio || "");
            }
          }
        } catch (err) {
          console.error("Failed to fetch profile metadata from Supabase", err);
        }
      };
      fetchSupabaseMetadata();
    } else {
      setAvatarSrc(null);
      setDisplayName("");
      setGender("");
      setDob("");
      setBio("");
    }
  }, [userId]);

  const handleAvatarChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target.result;
      setAvatarSrc(dataUrl);
      if (userId) {
        localStorage.setItem(`lpi_${userId}_avatar`, dataUrl);
      }
    };
    reader.readAsDataURL(file);
  };

  const openEdit = () => {
    setDraft({ name: displayName, gender, dob, bio });
    setEditing(true);
  };

  const saveEdit = async () => {
    setDisplayName(draft.name);
    setGender(draft.gender);
    setDob(draft.dob);
    setBio(draft.bio);
    if (userId) {
      localStorage.setItem(`lpi_${userId}_name`, draft.name);
      localStorage.setItem(`lpi_${userId}_gender`, draft.gender);
      localStorage.setItem(`lpi_${userId}_dob`, draft.dob);
      localStorage.setItem(`lpi_${userId}_bio`, draft.bio);
    }
    setEditing(false);

    try {
      await supabase.auth.updateUser({
        data: {
          display_name: draft.name,
          gender: draft.gender,
          dob: draft.dob,
          bio: draft.bio
        }
      });
    } catch (err) {
      console.error("Failed to sync profile metadata to Supabase", err);
    }
  };

  const demographics = [gender, dob ? `Born ${dob}` : ""].filter(Boolean).join(" • ");

  return (
    <div className="user-profile-section">
      <div className="profile-banner">
        <div className="profile-banner-bg"></div>
        <div className="profile-info">
          <div className="profile-avatar-wrapper">
            <div className="profile-avatar">
              {avatarSrc ? (
                <img src={avatarSrc} alt="Profile" className="profile-avatar-img" />
              ) : (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                  <circle cx="12" cy="7" r="4"></circle>
                </svg>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="profile-file-input"
              onChange={handleAvatarChange}
            />
            <button className="avatar-upload-btn" title="Upload photo" onClick={() => fileInputRef.current?.click()}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="17 8 12 3 7 8"></polyline>
                <line x1="12" y1="3" x2="12" y2="15"></line>
              </svg>
            </button>
          </div>
          <div className="profile-text">
            <h1 className="profile-name">{displayName || userName}</h1>
            {demographics ? (
              <p className="profile-demographics">{demographics}</p>
            ) : (
              <p className="profile-demographics profile-demographics-empty">No details added yet</p>
            )}
            <button onClick={openEdit} className="profile-edit-btn">Edit Profile</button>
          </div>
        </div>
      </div>      {editing && (
        <>
          <div onClick={() => setEditing(false)} className="profile-modal-overlay" />
          <div className="profile-modal-container">
            <h3 className="profile-modal-title">Edit Profile</h3>
 
            <div className="profile-modal-fields">
              <div>
                <label className="profile-modal-label">Name</label>
                <input
                  type="text"
                  placeholder="Your display name"
                  value={draft.name}
                  onChange={e => setDraft(d => ({ ...d, name: e.target.value }))}
                  className="form-input"
                />
              </div>
              <div>
                <label className="profile-modal-label">Gender</label>
                <input
                  type="text"
                  placeholder="e.g. Female, Male, Non-binary"
                  value={draft.gender}
                  onChange={e => setDraft(d => ({ ...d, gender: e.target.value }))}
                  className="form-input"
                />
              </div>
              <div>
                <label className="profile-modal-label">Date of Birth</label>
                <input
                  type="date"
                  value={draft.dob}
                  onChange={e => setDraft(d => ({ ...d, dob: e.target.value }))}
                  className="form-input"
                />
              </div>
              <div>
                <label className="profile-modal-label">Bio</label>
                <textarea
                  placeholder="A short bio about yourself..."
                  value={draft.bio}
                  onChange={e => setDraft(d => ({ ...d, bio: e.target.value }))}
                  className="form-textarea"
                  rows={3}
                />
              </div>
            </div>
 
            <div className="profile-modal-actions">
              <button onClick={saveEdit} className="profile-modal-btn-save">Save</button>
              <button onClick={() => setEditing(false)} className="profile-modal-btn-cancel">Cancel</button>
            </div>
          </div>
        </>
      )}

      {/* Summary Card */}
      <div className="profile-summary-card">
        <h3 className="summary-title">Summary</h3>
        <p className="summary-text">
          {displayName || userName || "Jahanvi"}, welcome to your Life Programmable Interface. 
          You currently have <strong>{activeGoals}</strong> active goals and have successfully evolved <strong>{evolvedGoals}</strong> goals. 
          {urgentGoals > 0 && (
            <span> There are <strong>{urgentGoals}</strong> urgent goals that need your immediate attention.</span>
          )}
          {' '}Focus on progressing your priorities through the SMILE methodology to systematically achieve your objectives.
        </p>
      </div>
    </div>
  );
};
