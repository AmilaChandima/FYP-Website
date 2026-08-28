async function parse(response) {
  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.error || `Request failed (${response.status})`);
  }
  return payload;
}

export async function apiRequest(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body !== undefined && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, {
    ...options,
    headers,
    body: options.body !== undefined && !(options.body instanceof FormData) && typeof options.body !== "string"
      ? JSON.stringify(options.body)
      : options.body,
  });
  return parse(response);
}

export const databaseApi = {
  health: () => apiRequest("/api/database/status"),
  migrateLegacy: (payload) => apiRequest("/api/migration/import-local", { method: "POST", body: payload }),
  station: () => apiRequest("/api/station"),
  patchStation: (patch) => apiRequest("/api/station", { method: "PATCH", body: patch }),
  resetStation: () => apiRequest("/api/station/reset", { method: "POST" }),

  customers: () => apiRequest("/api/customers"),
  customer: (id) => apiRequest(`/api/customers/${encodeURIComponent(id)}`),
  signup: (payload) => apiRequest("/api/customers/signup", { method: "POST", body: payload }),
  login: (payload) => apiRequest("/api/customers/login", { method: "POST", body: payload }),
  updateCustomer: (id, payload) => apiRequest(`/api/customers/${encodeURIComponent(id)}`, { method: "PUT", body: payload }),

  bookings: ({ userId, date } = {}) => {
    const params = new URLSearchParams();
    if (userId) params.set("user_id", userId);
    if (date) params.set("date", date);
    const query = params.toString();
    return apiRequest(`/api/bookings${query ? `?${query}` : ""}`);
  },
  createBooking: (payload) => apiRequest("/api/bookings", { method: "POST", body: payload }),
  patchBooking: (id, patch) => apiRequest(`/api/bookings/${encodeURIComponent(id)}`, { method: "PATCH", body: patch }),
  applyOptimizerNotifications: (jobId, elasticNotifications) => apiRequest("/api/notifications/apply-optimizer", {
    method: "POST",
    body: { jobId, elasticNotifications },
  }),

  revenue: () => apiRequest("/api/admin/revenue"),
};
