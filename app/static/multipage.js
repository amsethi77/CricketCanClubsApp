(function () {
const TOKEN_KEY = "cricketClubAppAuthToken";
const CLUB_KEY = "cricketClubAppPrimaryClubId";
const SESSION_KEY = "cricketClubAppSessionState";
const USER_BADGE_ID = "userIdentityBadge";
const SESSION_ACTIVITY_DEBOUNCE_MS = 1200;
const SESSION_TOUCH_INTERVAL_MS = 60000;
const SHARED_NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/clubs", label: "Clubs" },
  { href: "/season-setup", label: "Season Fixtures" },
  { href: "/player-availability", label: "Availability" },
  { href: "/player-profile", label: "Profile" },
  { href: "/admin-center", label: "Admin center", adminOnly: true },
];

let sessionTouchTimer = null;
let sessionTouchInFlight = false;
let sessionLastTouchAt = 0;
let sessionMonitorStarted = false;

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

async function sharedGetJson(url, authenticated = false) {
  return apiJson(url, {
    headers: authenticated ? authHeaders() : undefined,
  });
}

async function sharedPostJson(url, payload, authenticated = false) {
  return apiJson(url, {
    method: "POST",
    headers: authenticated ? authHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function putJson(url, payload, authenticated = false) {
  return apiJson(url, {
    method: "PUT",
    headers: authenticated ? authHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function deleteJson(url, authenticated = false) {
  return apiJson(url, {
    method: "DELETE",
    headers: authenticated ? authHeaders() : undefined,
  });
}

async function authMe() {
  const data = await sharedGetJson("/api/auth/me", true);
  renderSharedTopbar(data.user || null);
  syncUserBadge(data.user || null);
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(data.session || null));
  return data;
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
  Promise.resolve(
    sharedPostJson("/api/auth/signout", {}, true).catch(() => null)
  ).finally(() => {
    setAuthToken("");
    setPrimaryClubId("");
    window.sessionStorage.removeItem(SESSION_KEY);
    const badge = document.getElementById(USER_BADGE_ID);
    if (badge) {
      badge.remove();
    }
    window.location.href = "/signin";
  });
}

function formatRoleLabel(role) {
  const normalized = String(role || "").trim().replaceAll("_", " ");
  if (!normalized) return "Player";
  return normalized.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatInitials(name) {
  const parts = String(name || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return "CC";
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("")
    .slice(0, 2);
}

function ensureUserBadge() {
  const topbarActions = document.querySelector(".topbar-actions");
  if (!topbarActions) {
    return null;
  }
  let badge = document.getElementById(USER_BADGE_ID);
  if (!badge) {
    badge = document.createElement("div");
    badge.id = USER_BADGE_ID;
    badge.className = "user-chip";
    badge.setAttribute("aria-live", "polite");
    topbarActions.insertAdjacentElement("afterbegin", badge);
  }
  return badge;
}

function syncUserBadge(user) {
  if (!user) {
    const existing = document.getElementById(USER_BADGE_ID);
    if (existing) {
      existing.hidden = true;
      existing.innerHTML = "";
    }
    return;
  }
  const badge = ensureUserBadge();
  if (!badge) return;
  badge.hidden = false;
  badge.classList.remove("is-muted");
  const name = String(user.display_name || user.full_name || user.mobile || "Signed in").trim();
  const role = formatRoleLabel(user.effective_role || user.role || "player");
  badge.innerHTML = `
    <span class="user-chip-mark" aria-hidden="true">${formatInitials(name)}</span>
    <span class="user-chip-copy">
      <strong>${name}</strong>
      <span>${role}</span>
    </span>
  `;
}

function renderSharedTopbar(user = null) {
  const topbar = document.querySelector(".page-topbar");
  if (!topbar) {
    return null;
  }
  if (topbar.dataset.sharedTopbarRendered !== "true") {
    const currentPath = String(window.location.pathname || "/dashboard").replace(/\/+$/, "") || "/dashboard";
    const navHtml = SHARED_NAV_ITEMS.map((item) => {
      const isCurrent = currentPath === item.href || currentPath.startsWith(`${item.href}/`);
      const currentAttr = isCurrent ? ' aria-current="page"' : "";
      const adminAttrs = item.adminOnly ? ' data-admin-only hidden' : "";
      return `<a href="${item.href}"${currentAttr}${adminAttrs}>${item.label}</a>`;
    }).join("");
    topbar.innerHTML = `
      <nav class="top-nav">
        ${navHtml}
      </nav>
      <div class="topbar-actions">
        <div id="${USER_BADGE_ID}" class="user-chip" aria-live="polite" hidden></div>
        <button id="signOutButton" class="secondary-button" type="button">Sign out</button>
      </div>
    `;
    topbar.dataset.sharedTopbarRendered = "true";
    const signOutButton = document.getElementById("signOutButton");
    if (signOutButton) {
      signOutButton.addEventListener("click", signOut);
    }
  }
  if (user) {
    syncUserBadge(user);
  }
  return topbar;
}

async function touchSessionIfNeeded(force = false) {
  const token = getAuthToken();
  if (!token) {
    return null;
  }
  const now = Date.now();
  if (!force && sessionLastTouchAt && now - sessionLastTouchAt < SESSION_TOUCH_INTERVAL_MS) {
    return null;
  }
  if (sessionTouchInFlight) {
    return null;
  }
  sessionTouchInFlight = true;
  try {
    const auth = await authMe();
    sessionLastTouchAt = Date.now();
    return auth;
  } catch (error) {
    const message = String(error?.message || "").toLowerCase();
    if (message.includes("session expired") || message.includes("sign in first")) {
      signOut();
      return null;
    }
    throw error;
  } finally {
    sessionTouchInFlight = false;
  }
}

function scheduleSessionTouch() {
  if (sessionTouchTimer) {
    window.clearTimeout(sessionTouchTimer);
  }
  sessionTouchTimer = window.setTimeout(() => {
    touchSessionIfNeeded(true).catch(() => {});
  }, SESSION_ACTIVITY_DEBOUNCE_MS);
}

function startSessionMonitor() {
  if (sessionMonitorStarted) {
    return;
  }
  sessionMonitorStarted = true;
  const activityEvents = ["click", "pointerdown", "keydown", "input", "change", "submit", "touchstart"];
  activityEvents.forEach((eventName) => {
    document.addEventListener(eventName, scheduleSessionTouch, true);
  });
  window.addEventListener("focus", () => {
    touchSessionIfNeeded().catch(() => {});
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      touchSessionIfNeeded().catch(() => {});
    }
  });
  window.setInterval(() => {
    if (getAuthToken()) {
      try {
        const stored = JSON.parse(window.sessionStorage.getItem(SESSION_KEY) || "null");
        if (!stored) {
          window.sessionStorage.removeItem(SESSION_KEY);
        }
      } catch {
        window.sessionStorage.removeItem(SESSION_KEY);
      }
    }
  }, 30000);
  if (getAuthToken()) {
    touchSessionIfNeeded(true).catch(() => {});
  }
}

function optionMarkup(items, valueKey, labelFn) {
  return (items || [])
    .map((item) => `<option value="${item[valueKey]}">${labelFn(item)}</option>`)
    .join("");
}

async function syncAdminOnlyElements() {
  const nodes = document.querySelectorAll("[data-admin-only]");
  if (!nodes.length) {
    return;
  }
  try {
    const auth = await authMe();
    const role = String(auth?.user?.effective_role || auth?.user?.role || "").trim();
    const isAdmin = role === "superadmin";
    nodes.forEach((node) => {
      if (isAdmin) {
        node.hidden = false;
        node.removeAttribute("aria-hidden");
      } else {
        node.remove();
      }
    });
  } catch {
    nodes.forEach((node) => {
      node.remove();
    });
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", syncAdminOnlyElements);
} else {
  syncAdminOnlyElements();
}

renderSharedTopbar();
startSessionMonitor();

window.CricketClubAppPages = {
  getAuthToken,
  setAuthToken,
  getPrimaryClubId,
  setPrimaryClubId,
  getJson: sharedGetJson,
  postJson: sharedPostJson,
  putJson,
  deleteJson,
  authMe,
  requireAuth,
  signOut,
  optionMarkup,
  renderSharedTopbar,
  syncAdminOnlyElements,
};

})();
