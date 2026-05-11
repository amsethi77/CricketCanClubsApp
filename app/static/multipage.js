(function () {
const TOKEN_KEY = "cricketClubAppAuthToken";
const CLUB_KEY = "cricketClubAppPrimaryClubId";
const SESSION_KEY = "cricketClubAppSessionState";
const USER_BADGE_ID = "userIdentityBadge";
const CLUB_BADGE_ID = "currentClubBadge";
const BOTTOM_NAV_ID = "bottomAppNav";
const ASSISTANT_FAB_ID = "assistantFloatingButton";
const SHARED_HEADER_URL = "/assets/shared_header.html?v=20260509a";
const SESSION_ACTIVITY_DEBOUNCE_MS = 1200;
const SESSION_TOUCH_INTERVAL_MS = 60000;
const SHARED_NAV_ITEMS = [
  { href: "/dashboard", label: "Home" },
  { href: "/clubs", label: "Clubs" },
  { href: "/dashboard/widgets/scoring", label: "Scoring" },
  { href: "/dashboard/widgets/schedule", label: "Fixtures" },
  { href: "/player-availability", label: "Availability" },
  { href: "/dashboard/widgets/archive", label: "Archives" },
  { href: "/dashboard/widgets/performance", label: "Performances" },
  { href: "/profile", label: "Profile" },
  { href: "/dashboard/widgets/assistant", label: "AI Assistant" },
  { href: "/admin-center", label: "Admin Center", adminOnly: true },
];

let sessionTouchTimer = null;
let sessionTouchInFlight = false;
let sessionLastTouchAt = 0;
let sessionMonitorStarted = false;
let sharedHeaderTemplate = null;
let sharedHeaderTemplateInFlight = null;

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
    window.sessionStorage.setItem(CLUB_KEY, clubId);
  } else {
    window.sessionStorage.removeItem(CLUB_KEY);
  }
}

function getPrimaryClubId() {
  return window.sessionStorage.getItem(CLUB_KEY) || "";
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
  const trimmed = text.trim();
  const contentType = String(response.headers.get("content-type") || "").toLowerCase();
  let data = null;
  if (trimmed && (contentType.includes("json") || trimmed.startsWith("{") || trimmed.startsWith("["))) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    const detail = data && typeof data === "object" ? (data.detail || data.message) : "";
    throw new Error(detail || trimmed || "Request failed.");
  }
  if (data !== null) {
    return data;
  }
  if (!trimmed) {
    return {};
  }
  throw new Error("Unexpected non-JSON response from the server.");
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

async function loadSharedHeaderTemplate() {
  if (sharedHeaderTemplate) {
    return sharedHeaderTemplate;
  }
  if (sharedHeaderTemplateInFlight) {
    return sharedHeaderTemplateInFlight;
  }
  sharedHeaderTemplateInFlight = fetch(SHARED_HEADER_URL, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) {
        throw new Error("Shared header could not be loaded.");
      }
      return response.text();
    })
    .then((html) => {
      sharedHeaderTemplate = html;
      sharedHeaderTemplateInFlight = null;
      return html;
    })
    .catch((error) => {
      sharedHeaderTemplateInFlight = null;
      throw error;
    });
  return sharedHeaderTemplateInFlight;
}

async function authMe() {
  syncDashboardWidgetAttribute();
  const data = await sharedGetJson("/api/auth/me", true);
  renderSharedTopbar(data.user || null);
  renderSharedBottomNav();
  syncActiveNavState();
  syncUserBadge(data.user || null);
  syncClubBadge(data.user?.current_club_name || data.user?.primary_club_name || "");
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
    const clubBadge = document.getElementById(CLUB_BADGE_ID);
    if (clubBadge) {
      clubBadge.remove();
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

function ensureClubBadge() {
  const topbarActions = document.querySelector(".topbar-actions");
  if (!topbarActions) {
    return null;
  }
  let badge = document.getElementById(CLUB_BADGE_ID);
  if (!badge) {
    badge = document.createElement("div");
    badge.id = CLUB_BADGE_ID;
    badge.className = "club-chip";
    badge.setAttribute("aria-live", "polite");
    topbarActions.insertAdjacentElement("afterbegin", badge);
  }
  return badge;
}

function syncClubBadge(clubName) {
  const clean = String(clubName || "").trim();
  const existing = document.getElementById(CLUB_BADGE_ID);
  if (!clean) {
    if (existing) {
      existing.hidden = true;
      existing.innerHTML = "";
    }
    return;
  }
  const badge = ensureClubBadge();
  if (!badge) return;
  badge.hidden = false;
  const initials = clean
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("")
    .slice(0, 2) || "CL";
  badge.innerHTML = `
    <span class="club-chip-mark" aria-hidden="true">${initials}</span>
    <span class="club-chip-copy">
      <small>Club</small>
      <strong>${clean}</strong>
    </span>
  `;
}

function inferDashboardWidgetFromPath(pathname) {
  const path = String(pathname || "/dashboard").replace(/\/+$/, "") || "/dashboard";
  if (path === "/dashboard") {
    return "overview";
  }
  const widgetMatch = path.match(/^\/dashboard\/widgets\/([^/?#]+)/);
  return widgetMatch ? widgetMatch[1] : "";
}

function syncDashboardWidgetAttribute() {
  if (!document.body) {
    return;
  }
  const widget = inferDashboardWidgetFromPath(window.location.pathname || "/dashboard");
  if (widget) {
    document.body.setAttribute("data-dashboard-widget", widget);
  }
}

function syncActiveNavState() {
  const currentPath = String(window.location.pathname || "/dashboard").replace(/\/+$/, "") || "/dashboard";
  const navLinks = document.querySelectorAll(".template-nav a, .top-nav a, .bottom-app-nav-item");
  navLinks.forEach((link) => {
    const href = String(link.getAttribute("href") || "").replace(/\/+$/, "") || "/";
    const isCurrent = href === "/dashboard"
      ? currentPath === href
      : currentPath === href || currentPath.startsWith(`${href}/`);
    if (isCurrent) {
      link.setAttribute("aria-current", "page");
      if (link.classList.contains("bottom-app-nav-item")) {
        link.classList.add("is-active");
      }
    } else {
      link.removeAttribute("aria-current");
      if (link.classList.contains("bottom-app-nav-item")) {
        link.classList.remove("is-active");
      }
    }
  });
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

function renderSharedBottomNav() {
  const shell = document.querySelector(".page-shell");
  if (!shell) {
    return null;
  }
  const currentPath = String(window.location.pathname || "/dashboard").replace(/\/+$/, "") || "/dashboard";
  let nav = document.getElementById(BOTTOM_NAV_ID);
  if (!nav) {
    nav = document.createElement("nav");
    nav.id = BOTTOM_NAV_ID;
    nav.className = "bottom-app-nav";
    shell.appendChild(nav);
  }
  const items = [
    { href: "/dashboard", label: "Home", icon: "🏠" },
    { href: "/clubs", label: "Clubs", icon: "🏏" },
    { href: "/dashboard/widgets/scoring", label: "Scoring", icon: "🏏" },
    { href: "/dashboard/widgets/schedule", label: "Fixtures", icon: "📅" },
    { href: "/dashboard/widgets/archive", label: "Archives", icon: "🗂️" },
    { href: "/dashboard/widgets/performance", label: "Performances", icon: "📊" },
    { href: "/profile", label: "Profile", icon: "👤" },
  ];
  nav.innerHTML = items
    .map((item) => {
      const isCurrent = currentPath === item.href || currentPath.startsWith(`${item.href}/`);
      const activeClass = isCurrent ? " is-active" : "";
      const currentAttr = isCurrent ? ' aria-current="page"' : "";
      return `
        <a class="bottom-app-nav-item${activeClass}" href="${item.href}"${currentAttr}>
          <span aria-hidden="true">${item.icon}</span>
          <span>${item.label}</span>
        </a>
      `;
    })
    .join("");

  let fab = document.getElementById(ASSISTANT_FAB_ID);
  if (!fab) {
    fab = document.createElement("a");
    fab.id = ASSISTANT_FAB_ID;
    fab.className = "assistant-fab";
    fab.href = "/dashboard/widgets/assistant";
    fab.innerHTML = `<span aria-hidden="true">🤖</span><strong>Assistant</strong>`;
    shell.appendChild(fab);
  }
  return nav;
}

async function renderSharedTopbar(user = null) {
  const topbar = document.querySelector(".page-topbar");
  if (!topbar) {
    return null;
  }
  if (topbar.dataset.sharedTopbarRendered !== "true") {
    topbar.innerHTML = await loadSharedHeaderTemplate();
    topbar.dataset.sharedTopbarRendered = "true";
    const signOutButton = document.getElementById("signOutButton");
    if (signOutButton) {
      signOutButton.addEventListener("click", signOut);
    }
  }
  if (user) {
    syncUserBadge(user);
  }
  syncClubBadge(user?.current_club_name || user?.primary_club_name || "");
  renderSharedBottomNav();
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderSharedPageIntro() {
  const cards = document.querySelectorAll("[data-shared-page-intro]");
  cards.forEach((card) => {
    if (card.dataset.sharedPageIntroRendered === "true") {
      return;
    }
    const kicker = escapeHtml(card.dataset.pageKicker || "");
    const title = escapeHtml(card.dataset.pageTitle || "");
    const summary = escapeHtml(card.dataset.pageSummary || "");
    const note = escapeHtml(card.dataset.pageNote || "");
    const noteMarkup = note ? `<div class="detail-card intro-note"><p class="lede">${note}</p></div>` : "";
    card.innerHTML = `
      <p class="section-kicker">${kicker}</p>
      <h1>${title}</h1>
      <p class="lede">${summary}</p>
      ${noteMarkup}
    `;
    card.dataset.sharedPageIntroRendered = "true";
  });
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

void renderSharedTopbar().then(() => {
  syncActiveNavState();
});
renderSharedPageIntro();
syncActiveNavState();
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
  renderSharedPageIntro,
  syncClubBadge,
  syncAdminOnlyElements,
};

})();
