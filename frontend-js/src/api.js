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

    async getSignals({ stream, event_type, source, limit = 50, offset = 0 } = {}) {
      const params = new URLSearchParams();
      if (stream)     params.set("stream", stream);
      if (event_type) params.set("event_type", event_type);
      if (source)     params.set("source", source);
      params.set("limit", limit);
      params.set("offset", offset);
      const response = await fetch(`${BASE_URL}/api/v1/signals/?${params}`, {
        headers: getHeaders(),
      });
      if (!response.ok) throw new Error("Failed to fetch signals");
      return await response.json();
    },

    async getAllSignals({ stream, event_type, source, limit = 50, offset = 0 } = {}) {
      const params = new URLSearchParams();
      if (stream)     params.set("stream", stream);
      if (event_type) params.set("event_type", event_type);
      if (source)     params.set("source", source);
      params.set("limit", limit);
      params.set("offset", offset);
      params.set("all", "true");
      const response = await fetch(`${BASE_URL}/api/v1/signals/?${params}`, {
        headers: getHeaders(),
      });
      if (!response.ok) throw new Error("Failed to fetch all signals");
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
  };
};

export const goalApi = createGoalApi();
