// Dark / light mode + navbar search (site_tools.js). Apply the saved theme right away to avoid a flash.
(function loadSiteTools() {
  try {
    if (localStorage.getItem("cricketClubAppTheme") === "dark") document.documentElement.setAttribute("data-theme", "dark");
  } catch (e) { /* ignore */ }
  if (document.querySelector('script[src^="/assets/site_tools.js"]')) return;
  const script = document.createElement("script");
  script.src = "/assets/site_tools.js";
  document.head.appendChild(script);
})();

(function () {
const TOKEN_KEY = "cricketClubAppAuthToken";
const CLUB_KEY = "cricketClubAppPrimaryClubId";
const SESSION_KEY = "cricketClubAppSessionState";
const USER_BADGE_ID = "userIdentityBadge";
const CLUB_BADGE_ID = "currentClubBadge";
const BOTTOM_NAV_ID = "bottomAppNav";
const ASSISTANT_FAB_ID = "assistantFloatingButton";
const SHARED_HEADER_URL = "/assets/shared_header.html?v=20260511k";
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
  { href: "/dashboard/widgets/assistant", label: "Assistant" },
  { href: "/admin-center", label: "Admin", adminOnly: true },
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
  window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(data.session || null));
  renderSharedTopbar(data.user || null);
  renderSharedBottomNav(data.user || null);
  syncActiveNavState();
  syncUserBadge(data.user || null);
  syncClubBadge(data.user?.current_club_name || data.user?.primary_club_name || "");
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
  badge.title = clean;
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
      <strong>${initials}</strong>
      <span>${clean}</span>
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
  const initials = formatInitials(name);
  badge.title = name;
  badge.innerHTML = `
    <span class="user-chip-mark" aria-hidden="true">${initials}</span>
    <span class="user-chip-copy">
      <small>User</small>
      <strong>${initials}</strong>
      <span>${role}</span>
    </span>
  `;
  renderAccountButton();
}

function renderSharedBottomNav(user = null) {
  const shell = document.querySelector(".page-shell");
  if (!shell) {
    return null;
  }
  const currentPath = String(window.location.pathname || "/dashboard").replace(/\/+$/, "") || "/dashboard";
  const currentRole = String(user?.effective_role || user?.role || "").trim();
  const isAdmin = currentRole === "superadmin";
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
    { href: "/player-availability", label: "Availability", icon: "✅" },
    { href: "/dashboard/widgets/archive", label: "Archives", icon: "🗂️" },
    { href: "/dashboard/widgets/performance", label: "Performances", icon: "📊" },
    { href: "/profile", label: "Profile", icon: "👤" },
    { href: "/dashboard/widgets/assistant", label: "Assistant", icon: "🤖" },
    { href: "/admin-center", label: "Admin", icon: "⚙️", adminOnly: true },
  ].filter((item) => !item.adminOnly || isAdmin);
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
    fab.setAttribute("aria-label", "Open Assistant");
    shell.appendChild(fab);
  }
  // No floating button on the Assistant page itself.
  fab.hidden = currentPath === "/dashboard/widgets/assistant";
  return nav;
}

let signedInMenuUser = null;
let signedInMoreMenuReady = false;

// Show the Admin link only to the superadmin (the header loads after the page's
// own admin check, so it needs its own pass).
function syncHeaderAdminLinks(user) {
  const role = String(user?.effective_role || user?.role || "").trim();
  const isAdmin = role === "superadmin";
  document.querySelectorAll(".shared-topbar-host [data-admin-only]").forEach((node) => {
    node.hidden = !isAdmin;
  });
  scheduleSignedInNavFit();
}

// "More" dropdown for the signed-in navbar (tablet / phone).
// Uses one document-level listener, so it keeps working if the header is re-rendered.
function setupSignedInMoreMenu() {
  if (signedInMoreMenuReady) return;
  signedInMoreMenuReady = true;

  let menu = null;
  let activeButton = null;

  function closeMenu() {
    if (menu) menu.remove();
    if (activeButton) activeButton.setAttribute("aria-expanded", "false");
    menu = null;
    activeButton = null;
  }

  function positionMenu() {
    if (!menu || !activeButton) return;
    const rect = activeButton.getBoundingClientRect();
    menu.style.top = `${rect.bottom + 8}px`;
    menu.style.right = `${Math.max(8, window.innerWidth - rect.right)}px`;
  }

  function openMenu(button) {
    const nav = button.closest(".top-nav");
    if (!nav) return;
    closeMenu();
    activeButton = button;
    menu = document.createElement("div");
    menu.className = "signed-in-more-menu";
    menu.setAttribute("role", "menu");

    // Laptop / tablet: the links that didn't fit in the row. Phone: every link after the first three.
    const allLinks = Array.from(nav.querySelectorAll(":scope > a")).filter((link) => !link.hidden);
    const overflowed = allLinks.filter((link) => link.classList.contains("is-overflowed") && !link.matches(".nav-account-item, .nav-fab-item"));
    const links = overflowed.length ? overflowed : allLinks.slice(3);
    links.forEach((link) => {
      const item = document.createElement("a");
      item.href = link.getAttribute("href") || "#";
      item.setAttribute("role", "menuitem");
      if (link.getAttribute("aria-current") === "page") item.setAttribute("aria-current", "page");
      const icon = link.querySelector(".nav-icon");
      const text = link.querySelector(".nav-text");
      item.innerHTML =
        `<span class="menu-icon" aria-hidden="true">${escapeHtml(icon ? icon.textContent : "")}</span>` +
        `<span>${escapeHtml(text ? text.textContent : link.textContent.trim())}</span>`;
      menu.appendChild(item);
    });

    // On phones the club / user / sign-out buttons are hidden, so add them here.
    if (window.matchMedia("(max-width: 640px)").matches) {
      const user = signedInMenuUser || {};
      const name = String(user.display_name || user.full_name || user.mobile || "Signed in").trim();
      const role = formatRoleLabel(user.effective_role || user.role || "player");
      const club = String(user.current_club_name || user.primary_club_name || "").trim();
      menu.insertAdjacentHTML(
        "beforeend",
        `<div class="menu-divider" role="separator"></div>
         <div class="menu-account">
           <strong>${escapeHtml(name)}</strong>
           <small>${escapeHtml(role)}${club ? ` · ${escapeHtml(club)}` : ""}</small>
         </div>
         <a href="/signout" role="menuitem" data-menu-signout><span class="menu-icon" aria-hidden="true">🚪</span><span>Sign out</span></a>`
      );
    }

    // Dark / light mode (the toggle button is hidden in the phone navbar)
    if (window.CCSiteTools && window.matchMedia("(max-width: 640px)").matches) {
      const label = window.CCSiteTools.themeMenuLabel();
      menu.insertAdjacentHTML(
        "beforeend",
        `<a href="#" role="menuitem" data-menu-theme><span class="menu-icon" aria-hidden="true">${label.icon}</span><span>${label.text}</span></a>`
      );
    }

    document.body.appendChild(menu);
    button.setAttribute("aria-expanded", "true");
    button.setAttribute("aria-haspopup", "menu");
    positionMenu();
  }

  // Capture phase: runs before any older click handler on the More button.
  document.addEventListener(
    "click",
    (event) => {
      const button = event.target.closest(".shared-topbar-host .nav-more-toggle");
      if (button) {
        event.preventDefault();
        event.stopPropagation();
        if (menu && activeButton === button) closeMenu();
        else openMenu(button);
        return;
      }
      if (menu && event.target.closest("[data-menu-theme]")) {
        event.preventDefault();
        closeMenu();
        if (window.CCSiteTools) window.CCSiteTools.toggleTheme();
        return;
      }
      if (menu && event.target.closest("[data-menu-signout]")) {
        event.preventDefault();
        closeMenu();
        signOut();
        return;
      }
      if (menu && !menu.contains(event.target)) closeMenu();
    },
    true
  );

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menu) {
      const button = activeButton;
      closeMenu();
      if (button) button.focus();
    }
  });
  window.addEventListener("resize", closeMenu);
  window.addEventListener("scroll", positionMenu, { passive: true });
}

// ---------------------------------------------------------------------------
// Laptop / tablet navbar: show as many links as fit; only the rest go into More.
// ---------------------------------------------------------------------------
let signedInNavFitFrame = 0;

function fitSignedInNav() {
  const nav = document.querySelector(".shared-topbar-host .top-nav");
  if (!nav) return;
  // Profile / Admin live in the account menu and Assistant is the floating button,
  // so on laptop they are not part of the row.
  const links = Array.from(nav.querySelectorAll(":scope > a")).filter(
    (link) => !link.hidden && !link.matches(".nav-account-item, .nav-fab-item")
  );
  const more = nav.querySelector(".nav-more-toggle");
  links.forEach((link) => link.classList.remove("is-overflowed"));
  nav.classList.remove("has-overflow", "more-current");
  if (window.matchMedia("(max-width: 640px)").matches) return;

  const gap = parseFloat(getComputedStyle(nav).columnGap || getComputedStyle(nav).gap) || 8;
  const available = nav.clientWidth;
  const widths = links.map((link) => link.getBoundingClientRect().width);
  const total = widths.reduce((sum, width) => sum + width, 0) + gap * Math.max(0, links.length - 1);
  if (total <= available + 1) return;

  // Room for the More button too.
  const moreWidth = 64 + gap;
  let used = 0;
  let fits = 0;
  for (let index = 0; index < links.length; index += 1) {
    const next = used + (index ? gap : 0) + widths[index];
    if (next + moreWidth > available) break;
    used = next;
    fits += 1;
  }
  links.slice(Math.max(1, fits)).forEach((link) => link.classList.add("is-overflowed"));
  nav.classList.add("has-overflow");
  if (nav.querySelector(':scope > a.is-overflowed[aria-current="page"]')) nav.classList.add("more-current");
  if (more) more.setAttribute("aria-label", "More menu");
}

function scheduleSignedInNavFit() {
  if (signedInNavFitFrame) cancelAnimationFrame(signedInNavFitFrame);
  signedInNavFitFrame = requestAnimationFrame(() => {
    signedInNavFitFrame = 0;
    fitSignedInNav();
  });
}

window.addEventListener("resize", scheduleSignedInNavFit);
if (document.fonts && document.fonts.ready) document.fonts.ready.then(scheduleSignedInNavFit).catch(() => {});

// ---------------------------------------------------------------------------
// Account button (laptop / tablet): one avatar that opens your name, club,
// Profile, Clubs and Sign out. Replaces the separate club / user / door icons.
// ---------------------------------------------------------------------------
let signedInAccountMenuReady = false;

function isAdminUser() {
  const role = String(signedInMenuUser?.effective_role || signedInMenuUser?.role || "").trim();
  if (role) return role === "superadmin";
  const adminLink = document.querySelector('.shared-topbar-host .top-nav a[href="/admin-center"]');
  return Boolean(adminLink && !adminLink.hidden);
}

function accountDetails() {
  const user = signedInMenuUser || {};
  const userBadge = document.getElementById(USER_BADGE_ID);
  const clubBadge = document.getElementById(CLUB_BADGE_ID);
  const name = String(user.display_name || user.full_name || userBadge?.title || user.mobile || "Signed in").trim();
  const role = user.effective_role || user.role
    ? formatRoleLabel(user.effective_role || user.role)
    : String(userBadge?.querySelector(".user-chip-copy > span")?.textContent || "").trim();
  const club = String(user.current_club_name || user.primary_club_name || clubBadge?.title || "").trim();
  return { name, role, club, initials: formatInitials(name) };
}

function renderAccountButton() {
  const actions = document.querySelector(".shared-topbar-host .topbar-actions");
  if (!actions) return;
  let button = actions.querySelector(".account-button");
  if (!button) {
    button = document.createElement("button");
    button.type = "button";
    button.className = "account-button";
    button.setAttribute("aria-haspopup", "menu");
    button.setAttribute("aria-expanded", "false");
    actions.appendChild(button);
  }
  const details = accountDetails();
  const label = `Account: ${details.name}${details.club ? `, ${details.club}` : ""}`;
  const html = `<span class="account-button-mark" aria-hidden="true">${escapeHtml(details.initials)}</span><span class="account-button-caret" aria-hidden="true">▾</span>`;
  if (button.innerHTML !== html) button.innerHTML = html;
  button.setAttribute("aria-label", label);
  button.title = label;
  setupAccountMenu();
}

function setupAccountMenu() {
  if (signedInAccountMenuReady) return;
  signedInAccountMenuReady = true;
  let menu = null;
  let button = null;

  function close() {
    if (menu) menu.remove();
    if (button) button.setAttribute("aria-expanded", "false");
    menu = null;
    button = null;
  }

  function open(trigger) {
    close();
    button = trigger;
    const details = accountDetails();
    menu = document.createElement("div");
    menu.className = "signed-in-more-menu signed-in-account-menu";
    menu.setAttribute("role", "menu");
    const path = window.location.pathname.replace(/\/+$/, "");
    const current = (href) => (path === href ? ' aria-current="page"' : "");
    menu.innerHTML = `
      <div class="menu-account menu-account-head">
        <span class="menu-account-mark" aria-hidden="true">${escapeHtml(details.initials)}</span>
        <span>
          <strong>${escapeHtml(details.name)}</strong>
          <small>${escapeHtml(details.role || "")}</small>
        </span>
      </div>
      ${details.club ? `<div class="menu-account-club"><small>Current club</small><strong>${escapeHtml(details.club)}</strong></div>` : ""}
      <div class="menu-divider" role="separator"></div>
      <a href="/profile" role="menuitem"${current("/profile")}><span class="menu-icon" aria-hidden="true">👤</span><span>My profile</span></a>
      <a href="/clubs" role="menuitem"${current("/clubs")}><span class="menu-icon" aria-hidden="true">🏏</span><span>My clubs / switch club</span></a>
      ${isAdminUser() ? `<a href="/admin-center" role="menuitem"${current("/admin-center")}><span class="menu-icon" aria-hidden="true">⚙️</span><span>Admin center</span></a>` : ""}
      <div class="menu-divider" role="separator"></div>
      <a href="/signout" role="menuitem" data-account-signout><span class="menu-icon" aria-hidden="true">🚪</span><span>Sign out</span></a>`;
    document.body.appendChild(menu);
    const rect = trigger.getBoundingClientRect();
    menu.style.top = `${rect.bottom + 8}px`;
    menu.style.right = `${Math.max(8, window.innerWidth - rect.right)}px`;
    trigger.setAttribute("aria-expanded", "true");
  }

  document.addEventListener(
    "click",
    (event) => {
      const trigger = event.target.closest(".shared-topbar-host .account-button");
      if (trigger) {
        event.preventDefault();
        event.stopPropagation();
        if (menu && button === trigger) close();
        else open(trigger);
        return;
      }
      if (menu && event.target.closest("[data-account-signout]")) {
        event.preventDefault();
        close();
        signOut();
        return;
      }
      if (menu && !menu.contains(event.target)) close();
    },
    true
  );
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menu) {
      const trigger = button;
      close();
      if (trigger) trigger.focus();
    }
  });
  window.addEventListener("resize", close);
  window.addEventListener("scroll", close, { passive: true });
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
  // Holder styling + More menu for the signed-in navbar (see styles.css).
  topbar.classList.add("shared-topbar-host");
  setupSignedInMoreMenu();
  if (user) {
    signedInMenuUser = user;
    syncHeaderAdminLinks(user);
  }
  if (user) {
    syncUserBadge(user);
  }
  syncClubBadge(user?.current_club_name || user?.primary_club_name || "");
  if (user) {
    renderSharedBottomNav(user);
  }
  renderAccountButton();
  scheduleSignedInNavFit();
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
      // On public pages (Sign In, Register, Live...) just forget the old login quietly:
      // redirecting from here made the page reload.
      if (!document.querySelector(".page-topbar")) {
        setAuthToken("");
        return null;
      }
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
  renderSharedBottomNav,
  renderSharedPageIntro,
  syncClubBadge,
  syncAdminOnlyElements,
};

})();
