const TOKEN_KEY = "heartlakeAuthToken";
const CLUB_KEY = "heartlakePrimaryClubId";

function getAuthToken() {
  return window.localStorage.getItem(TOKEN_KEY) || "";
}

function setAuthToken(token) {
  if (token) {
    window.localStorage.setItem(TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

function setPrimaryClubId(clubId) {
  if (clubId) {
    window.localStorage.setItem(CLUB_KEY, clubId);
  } else {
    window.localStorage.removeItem(CLUB_KEY);
  }
}

function getPrimaryClubId() {
  return window.localStorage.getItem(CLUB_KEY) || "";
}

function authHeaders(extra = {}) {
  const headers = { ...extra };
  const token = getAuthToken();
  if (token) {
    headers["X-Auth-Token"] = token;
  }
  return headers;
}

async function apiJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.detail || data.message || "Request failed.");
  }
  return data;
}

async function getJson(url, authenticated = false) {
  return apiJson(url, {
    headers: authenticated ? authHeaders() : undefined,
  });
}

async function postJson(url, payload, authenticated = false) {
  return apiJson(url, {
    method: "POST",
    headers: authenticated ? authHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function authMe() {
  return getJson("/api/auth/me", true);
}

async function requireAuth() {
  try {
    return await authMe();
  } catch {
    setAuthToken("");
    window.location.href = "/signin";
    return null;
  }
}

function signOut() {
  setAuthToken("");
  setPrimaryClubId("");
  window.location.href = "/signin";
}

function optionMarkup(items, valueKey, labelFn) {
  return (items || [])
    .map((item) => `<option value="${item[valueKey]}">${labelFn(item)}</option>`)
    .join("");
}

window.HeartlakePages = {
  getAuthToken,
  setAuthToken,
  getPrimaryClubId,
  setPrimaryClubId,
  getJson,
  postJson,
  authMe,
  requireAuth,
  signOut,
  optionMarkup,
};
