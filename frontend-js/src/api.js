const originalFetch = window.fetch;
window.fetch = async (...args) => {
  const response = await originalFetch(...args);
  if (response.status === 429) {
    throw new Error("Rate limit exceeded (429). Please wait 30 seconds.");
  }
  return response;
};

export const createGoalApi = (baseUrl) => {
  const BASE_URL = (
    baseUrl || import.meta.env.VITE_API_BASE || ""
  ).replace(/\/$/, "");
  const API_URL = `${BASE_URL}/api/v1/goals`;

  let token = null;

  const getHeaders = () => {
    const headers = { "Content-Type": "application/json" };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  };

  return {
    setToken(newToken) {
      token = newToken;
    },

    async getMe() {
      const response = await fetch(`${BASE_URL}/api/v1/me/`, {
        headers: getHeaders(),
      });
      if (!response.ok) throw new Error("Failed to fetch user context");
      return await response.json();
    },

    async getUsersMap() {
      const response = await fetch(`${BASE_URL}/api/v1/users/map`, {
        headers: getHeaders(),
      });
      if (!response.ok) throw new Error("Failed to fetch users map");
      return await response.json();
    },

    async getSignals({ stream, event_type, source, goal_id, limit = 50, offset = 0 } = {}) {
      const params = new URLSearchParams();
      if (stream)     params.set("stream", stream);
      if (event_type) params.set("event_type", event_type);
      if (source)     params.set("source", source);
      if (goal_id)    params.set("goal_id", goal_id);
      params.set("limit", limit);
      params.set("offset", offset);
      const response = await fetch(`${BASE_URL}/api/v1/signals/?${params}`, {
        headers: getHeaders(),
      });
      if (!response.ok) throw new Error("Failed to fetch signals");
      return await response.json();
    },

    async getAllSignals({ stream, event_type, source, goal_id, limit = 50, offset = 0 } = {}) {
      const params = new URLSearchParams();
      if (stream)     params.set("stream", stream);
      if (event_type) params.set("event_type", event_type);
      if (source)     params.set("source", source);
      if (goal_id)    params.set("goal_id", goal_id);
      params.set("limit", limit);
      params.set("offset", offset);
      params.set("all", "true");
      const response = await fetch(`${BASE_URL}/api/v1/signals/?${params}`, {
        headers: getHeaders(),
      });
      if (!response.ok) throw new Error("Failed to fetch all signals");
      return await response.json();
    },

    async syncGithubEvents(goalId, repoName) {
      const response = await fetch(`${BASE_URL}/api/v1/signals/sync-github/${goalId}?repo_name=${encodeURIComponent(repoName)}`, {
        method: "POST",
        headers: getHeaders(),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to sync GitHub events");
      }
      return await response.json();
    },

    async ingestSignal(signal) {
      const response = await fetch(`${BASE_URL}/api/v1/signals/`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify(signal),
      });
      if (!response.ok) throw new Error("Failed to ingest signal");
      return await response.json();
    },

    async getGoals() {
      const response = await fetch(`${API_URL}/`, {
        headers: getHeaders(),
      });
      if (!response.ok) throw new Error("Failed to fetch goals from the server");
      return await response.json();
    },

    async getAllGoals() {
      const response = await fetch(`${API_URL}/?all=true`, {
        headers: getHeaders(),
      });
      if (!response.ok) throw new Error("Failed to fetch all goals");
      return await response.json();
    },

    async createGoal(goal) {
      const response = await fetch(`${API_URL}/`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify(goal),
      });
      if (!response.ok) throw new Error("Failed to create goal on the server");
      return await response.json();
    },

    async updateGoal(id, goalUpdate) {
      const response = await fetch(`${API_URL}/${id}`, {
        method: "PATCH",
        headers: getHeaders(),
        body: JSON.stringify(goalUpdate),
      });
      if (!response.ok) throw new Error("Failed to update goal on the server");
      return await response.json();
    },

    async deleteGoal(id) {
      const response = await fetch(`${API_URL}/${id}`, {
        method: "DELETE",
        headers: getHeaders(),
      });
      if (!response.ok) throw new Error("Failed to delete goal on the server");
    },

    async exchangeGithubToken(code, userId) {
      const response = await fetch(`${BASE_URL}/api/v1/github/exchange-token`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({ code, user_id: userId }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to exchange GitHub authorization code");
      }
      return await response.json();
    },

    async getGithubRepositories(userId) {
      const response = await fetch(`${BASE_URL}/api/v1/github/user-repositories/${userId}`, {
        headers: getHeaders(),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to fetch GitHub repositories");
      }
      return await response.json();
    },

    async validatePublicRepo(owner, repo) {
      const response = await fetch(`${BASE_URL}/api/v1/github/validate-public-repo/${owner}/${repo}`, {
        headers: getHeaders(),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to validate repository");
      }
      return await response.json();
    },

    async trackGithubRepository(userId, repoOwner, repoName) {
      const response = await fetch(`${BASE_URL}/api/v1/github/track-repo`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({
          user_id: userId,
          repo_owner: repoOwner,
          repo_name: repoName,
        }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to track GitHub repository");
      }
      return await response.json();
    },

    async disconnectGithubRepository(userId, repoOwner, repoName) {
      const response = await fetch(`${BASE_URL}/api/v1/github/disconnect-repo`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({
          user_id: userId,
          repo_owner: repoOwner,
          repo_name: repoName,
        }),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to disconnect GitHub repository");
      }
      return await response.json();
    },

    async disconnectGithubAccount(userId) {
      const response = await fetch(`${BASE_URL}/api/v1/github/disconnect-account/${userId}`, {
        method: "POST",
        headers: getHeaders(),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to disconnect GitHub account");
      }
      return await response.json();
    },

    async getRecommendations(userId) {
      const response = await fetch(`${BASE_URL}/api/v1/recommendations/${userId}`, {
        headers: getHeaders(),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to fetch recommendations");
      }
      return await response.json();
    },

    async getRecommendationsByGoal(userId, goalId) {
      const response = await fetch(`${BASE_URL}/api/v1/recommendations/${userId}/by-goal/${goalId}`, {
        method: "POST",
        headers: getHeaders(),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to fetch per-goal recommendations");
      }
      return await response.json();
    },

    async runRecommendationPipeline(userId) {
      const response = await fetch(`${BASE_URL}/api/v1/recommendations/${userId}/run`, {
        method: "POST",
        headers: getHeaders(),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to run recommendation pipeline");
      }
      return await response.json();
    },

    async submitRecommendationFeedback(userId, feedback) {
      const response = await fetch(`${BASE_URL}/api/v1/recommendations/${userId}/feedback`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify(feedback),
      });
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to submit recommendation feedback");
      }
      return await response.json();
    },

  };

};

export const goalApi = createGoalApi();
