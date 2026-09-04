// Empty in dev so requests stay relative and Vite proxies them to :8000.
// Set VITE_API_BASE_URL to the Render URL for the Vercel build.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const TOKEN_KEY = "cwyd_token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

async function request(path, { method = "GET", body, isForm = false } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (!isForm && body !== undefined) headers["Content-Type"] = "application/json";

  const resp = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: isForm ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `Request failed (${resp.status})`);
  return data;
}

export const signup = (email, password) =>
  request("/api/auth/signup", { method: "POST", body: { email, password } });

export const login = (email, password) =>
  request("/api/auth/login", { method: "POST", body: { email, password } });

// One-click demo sign-in. Takes no credentials: the backend issues a token
// for the shared demo account, so no password ships in this bundle.
export const demoSignin = () => request("/api/auth/demo", { method: "POST" });

// `demo` tells the login screen whether to offer that button.
export const fetchHealth = () => request("/api/health");

export const fetchMe = () => request("/api/auth/me");

export const listDatasets = () => request("/api/datasets");

export function uploadDataset(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/api/datasets", { method: "POST", body: form, isForm: true });
}

export const getStats = () => request("/api/stats");

export const askQuestion = (datasetId, question, fresh = false) =>
  request(`/api/datasets/${datasetId}/ask`, {
    method: "POST",
    body: { question, fresh },
  });
