/*
 * Site tools for every page. Loaded automatically by public_header.js (public pages)
 * and multipage.js (signed-in pages).
 *
 * Laptop / tablet:
 *   - Search icon in the navbar: the search box opens right next to it, results drop down below.
 *   - Moon / sun button: dark / light mode (saved in localStorage "cricketClubAppTheme").
 *
 * Phone (<= 640px), Cricinfo-style:
 *   - Left:  ☰ opens a "Menu" drawer with a search box and every page.
 *   - Right: ⚙️ opens a "Settings" sheet: Change Mode, plus Sign In / Register
 *            (or your account and Sign out when signed in).
 *   - Bottom: tab bar with the first five pages.
 */
(() => {
  if (window.CCSiteTools) return;

  const THEME_KEY = "cricketClubAppTheme";
  const svg = (body, size = 20) =>
    `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  const ICONS = {
    moon: svg('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>'),
    sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
    search: svg('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
    close: svg('<path d="M6 6l12 12M18 6 6 18"/>'),
    menu: svg('<path d="M4 7h16M4 12h16M4 17h16"/>', 24),
    gear: svg('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>', 24),
    signout: svg('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>'),
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  const isPhone = () => window.matchMedia("(max-width: 640px)").matches;
  const currentPath = () => (window.location.pathname || "/").replace(/\/+$/, "") || "/";

  // ======================================================================
  // Theme
  // ======================================================================
  function getTheme() {
    try {
      return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
    } catch {
      return "light";
    }
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    const dark = theme === "dark";
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      if (button.dataset.themeIcon === theme) return; // already up to date
      button.dataset.themeIcon = theme;
      button.innerHTML = dark ? ICONS.sun : ICONS.moon;
      button.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
      button.setAttribute("title", dark ? "Light mode" : "Dark mode");
    });
    document.querySelectorAll("[data-theme-row]").forEach((row) => {
      row.innerHTML = `<span class="sheet-row-icon">${dark ? ICONS.moon : ICONS.sun}</span><span>Change Mode: ${dark ? "Dark" : "Light"}</span>`;
    });
  }

  function toggleTheme() {
    const next = getTheme() === "dark" ? "light" : "dark";
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      /* private mode: theme still changes for this page */
    }
    applyTheme(next);
  }

  // Used by the older "More" menus.
  function themeMenuLabel() {
    return getTheme() === "dark" ? { icon: "☀️", text: "Light mode" } : { icon: "🌙", text: "Dark mode" };
  }

  applyTheme(getTheme());

  // ======================================================================
  // Search (shared by the laptop search box and the phone menu drawer)
  // ======================================================================

  function section(title, items) {
    if (!items.length) return "";
    return `<div class="site-search-group"><p class="site-search-group-title">${title}</p>${items.join("")}</div>`;
  }

  function resultItem(href, icon, title, meta) {
    return `
      <a class="site-search-item" href="${href}">
        <span class="site-search-item-icon" aria-hidden="true">${icon}</span>
        <span class="site-search-item-body"><strong>${escapeHtml(title)}</strong><small>${escapeHtml(meta)}</small></span>
      </a>`;
  }

  // Wires an <input> to a results container. onQuery(hasQuery) lets the caller swap views.
  function attachSearch(input, results, onQuery = () => {}) {
    let timer = null;
    let lastQuery = null;

    async function run() {
      const query = input.value.trim();
      if (query === lastQuery) return;
      lastQuery = query;
      onQuery(query.length >= 2);
      if (query.length < 2) {
        results.innerHTML = "";
        return;
      }
      results.innerHTML = `<p class="site-search-hint">Searching…</p>`;
      try {
        const response = await fetch(`/api/public/search?q=${encodeURIComponent(query)}`, { headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("Search failed");
        const data = await response.json();
        if (input.value.trim() !== query) return; // a newer search is running
        const players = (data.players || []).map((p) =>
          resultItem("/rankings", "👤", p.name, `${(p.clubs || []).join(", ") || "Player"} · ${p.runs} runs · ${p.wickets} wkts · ${p.matches} matches`)
        );
        const clubs = (data.clubs || []).map((c) =>
          resultItem(`/clubs?q=${encodeURIComponent(c.name || "")}`, "🏏", c.name, [c.city, c.country].filter(Boolean).join(", ") || c.season || "Club")
        );
        const matches = (data.matches || []).map((m) =>
          resultItem(`/live/${encodeURIComponent(m.id)}`, "📅", m.title, `${m.date_label} · ${m.status}${m.score ? ` · ${m.score}` : ""}`)
        );
        const html = section("Players", players) + section("Teams", clubs) + section("Matches", matches);
        results.innerHTML = html || `<p class="site-search-hint">No players, teams or matches found for “${escapeHtml(query)}”.</p>`;
      } catch (error) {
        console.warn("[Search]", error);
        results.innerHTML = `<p class="site-search-hint">Search isn't available right now.</p>`;
      }
    }

    input.addEventListener("input", () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(run, 200);
    });
    return {
      reset() {
        input.value = "";
        lastQuery = null;
        onQuery(false);
        results.innerHTML = "";
      },
    };
  }

  // ---------- Laptop / tablet: search box opens next to the icon ----------
  let openInline = null; // { header, box, dropdown, search }

  function openInlineSearch(header) {
    closeInlineSearch();
    const tools = header.querySelector(".site-tools");
    if (!tools) return;
    let box = tools.querySelector(".site-search-inline");
    let dropdown = tools.querySelector(".site-search-dropdown");
    if (!box) {
      box = document.createElement("div");
      box.className = "site-search-inline";
      box.innerHTML = `
        <span class="site-search-bar-icon">${ICONS.search}</span>
        <input type="search" class="site-search-input" placeholder="Search Players, Teams or Series" autocomplete="off" aria-label="Search players, teams or series" />
        <button type="button" class="site-search-close" aria-label="Close search">${ICONS.close}</button>`;
      dropdown = document.createElement("div");
      dropdown.className = "site-search-results site-search-dropdown";
      dropdown.setAttribute("aria-live", "polite");
      tools.prepend(dropdown);
      tools.prepend(box);
      box._search = attachSearch(box.querySelector("input"), dropdown);
      box.querySelector(".site-search-close").addEventListener("click", (event) => {
        event.stopPropagation();
        closeInlineSearch();
      });
    }
    header.classList.add("search-open");
    box.hidden = false;
    dropdown.hidden = false;
    fitInlineSearch(header, box, dropdown);
    if (!box.querySelector("input").value) dropdown.innerHTML = "";
    tools.querySelector("[data-search-toggle]")?.setAttribute("aria-expanded", "true");
    box.querySelector("input").focus();
    openInline = { header, box, dropdown };
  }

  // Make the search box fill only the free space between the last nav link and the icons.
  // If there isn't enough room (e.g. the signed-in navbar), only the links the box would
  // cover step aside while searching; the rest stay visible.
  function fitInlineSearch(header, box, dropdown) {
    header.querySelectorAll(".search-hidden-link").forEach((el) => el.classList.remove("search-hidden-link"));
    const tools = header.querySelector(".site-tools");
    const toolsLeft = tools.getBoundingClientRect().left;
    const links = Array.from(header.querySelectorAll(".top-nav > a, .top-nav > .nav-more-toggle")).filter(
      (el) => getComputedStyle(el).display !== "none"
    );
    const navRight = links.length ? Math.max(...links.map((el) => el.getBoundingClientRect().right)) : header.getBoundingClientRect().left;
    const free = Math.floor(toolsLeft - navRight - 20);
    let width = Math.min(free, 460);
    if (free < 200) {
      width = Math.min(360, Math.floor(toolsLeft - header.getBoundingClientRect().left - 120));
      const boxLeft = toolsLeft - 8 - width;
      links.forEach((el) => {
        if (el.getBoundingClientRect().right > boxLeft - 8) el.classList.add("search-hidden-link");
      });
    }
    box.style.width = `${width}px`;
    dropdown.style.width = `${Math.max(width, 320)}px`;
    // Short placeholder when the box is narrow, so it isn't cut off
    box.querySelector("input").placeholder = width < 330 ? "Search" : "Search Players, Teams or Series";
  }

  function closeInlineSearch() {
    if (!openInline) return;
    const { header, box, dropdown } = openInline;
    header.classList.remove("search-open");
    header.querySelectorAll(".search-hidden-link").forEach((el) => el.classList.remove("search-hidden-link"));
    box.hidden = true;
    dropdown.hidden = true;
    header.querySelector("[data-search-toggle]")?.setAttribute("aria-expanded", "false");
    openInline = null;
  }

  // ======================================================================
  // Phone: Menu drawer, Settings sheet, bottom tab bar
  // ======================================================================
  let backdrop = null;
  let drawer = null;
  let sheet = null;
  let drawerSearch = null;

  // All the page links from whichever navbar is on this page.
  function navLinks() {
    const header = document.querySelector(".app-header");
    if (!header) return [];
    return Array.from(header.querySelectorAll(".top-nav > a"))
      .filter((link) => !link.hidden)
      .map((link) => {
        const href = link.getAttribute("href") || "#";
        const icon = link.querySelector(".nav-icon")?.textContent?.trim() || "•";
        const label = link.querySelector(".nav-text")?.textContent?.trim() || link.textContent.trim();
        const path = currentPath();
        const clean = href.replace(/\/+$/, "") || "/";
        const active =
          link.getAttribute("aria-current") === "page" ||
          link.classList.contains("is-active") ||
          (clean !== "#" && (clean === "/dashboard" ? path === clean : path === clean || path.startsWith(`${clean}/`)));
        const account = ["/signin", "/register"].includes(clean);
        return { href, icon, label, active, account, disabled: link.classList.contains("is-disabled") };
      });
  }

  function isSignedInPage() {
    return Boolean(document.querySelector(".shared-topbar-host .app-header"));
  }

  function ensureBackdrop() {
    if (backdrop) return backdrop;
    backdrop = document.createElement("div");
    backdrop.className = "mobile-backdrop";
    backdrop.hidden = true;
    backdrop.addEventListener("click", closePanels);
    document.body.appendChild(backdrop);
    return backdrop;
  }

  function renderDrawerLinks() {
    const list = drawer.querySelector(".mobile-drawer-links");
    const items = navLinks().filter((link) => !link.account).map(
      (link) => `
        <a class="mobile-drawer-link${link.active ? " is-active" : ""}${link.disabled ? " is-disabled" : ""}" href="${escapeHtml(link.href)}">
          <span class="mobile-drawer-icon" aria-hidden="true">${escapeHtml(link.icon)}</span>
          <span>${escapeHtml(link.label)}</span>
        </a>`
    );
    list.innerHTML = items.join("");
  }

  function openDrawer() {
    closePanels();
    ensureBackdrop();
    if (!drawer) {
      drawer = document.createElement("aside");
      drawer.className = "mobile-drawer";
      drawer.setAttribute("role", "dialog");
      drawer.setAttribute("aria-label", "Menu");
      drawer.innerHTML = `
        <div class="mobile-panel-head">
          <strong>Menu</strong>
          <button type="button" class="mobile-panel-close" aria-label="Close menu">${ICONS.close}</button>
        </div>
        <label class="mobile-drawer-search">
          <span class="site-search-bar-icon">${ICONS.search}</span>
          <input type="search" class="site-search-input" placeholder="Search Players, Teams or Series" autocomplete="off" aria-label="Search players, teams or series" />
        </label>
        <nav class="mobile-drawer-links" aria-label="All pages"></nav>
        <div class="site-search-results mobile-drawer-results" hidden aria-live="polite"></div>`;
      document.body.appendChild(drawer);
      drawer.querySelector(".mobile-panel-close").addEventListener("click", closePanels);
      const links = drawer.querySelector(".mobile-drawer-links");
      const results = drawer.querySelector(".mobile-drawer-results");
      // While searching, the results replace the page list.
      drawerSearch = attachSearch(drawer.querySelector("input"), results, (hasQuery) => {
        links.hidden = hasQuery;
        results.hidden = !hasQuery;
      });
    }
    drawerSearch.reset();
    renderDrawerLinks();
    backdrop.hidden = false;
    drawer.classList.add("is-open");
    document.body.classList.add("mobile-panel-open");
  }

  function openSettings() {
    closePanels();
    ensureBackdrop();
    if (!sheet) {
      sheet = document.createElement("div");
      sheet.className = "mobile-sheet";
      sheet.setAttribute("role", "dialog");
      sheet.setAttribute("aria-label", "Settings");
      sheet.innerHTML = `
        <div class="mobile-panel-head">
          <strong>Settings</strong>
          <button type="button" class="mobile-panel-close" aria-label="Close settings">${ICONS.close}</button>
        </div>
        <button type="button" class="mobile-sheet-row" data-theme-row></button>
        <div class="mobile-sheet-account"></div>`;
      document.body.appendChild(sheet);
      sheet.querySelector(".mobile-panel-close").addEventListener("click", closePanels);
      sheet.querySelector("[data-theme-row]").addEventListener("click", toggleTheme);
    }
    renderSettingsAccount();
    applyTheme(getTheme()); // fills in the "Change Mode" row
    backdrop.hidden = false;
    sheet.classList.add("is-open");
    document.body.classList.add("mobile-panel-open");
  }

  // Settings sheet, bottom part: Sign In / Register (public) or your account + Sign out (signed in).
  function renderSettingsAccount() {
    const box = sheet.querySelector(".mobile-sheet-account");
    if (isSignedInPage()) {
      const userBadge = document.getElementById("userIdentityBadge");
      const clubBadge = document.getElementById("currentClubBadge");
      const name = (userBadge?.title || "").trim();
      const role = (userBadge?.querySelector(".user-chip-copy > span")?.textContent || "").trim();
      const club = (clubBadge?.title || "").trim();
      box.innerHTML = `
        ${name ? `<div class="mobile-sheet-user"><strong>${escapeHtml(name)}</strong><small>${escapeHtml([role, club].filter(Boolean).join(" · "))}</small></div>` : ""}
        <button type="button" class="mobile-sheet-row" data-drawer-signout>
          <span class="sheet-row-icon">${ICONS.signout}</span><span>Sign out</span>
        </button>`;
      return;
    }
    const accountLinks = navLinks().filter((link) => link.account);
    box.innerHTML = accountLinks
      .map(
        (link) => `
        <a class="mobile-sheet-row${link.active ? " is-active" : ""}" href="${escapeHtml(link.href)}">
          <span class="sheet-row-icon sheet-row-emoji" aria-hidden="true">${escapeHtml(link.icon)}</span><span>${escapeHtml(link.label)}</span>
        </a>`
      )
      .join("");
  }

  function closePanels() {
    drawer?.classList.remove("is-open");
    sheet?.classList.remove("is-open");
    if (backdrop) backdrop.hidden = true;
    document.body.classList.remove("mobile-panel-open");
  }

  // Bottom tab bar: the first five pages of the navbar.
  let tabbarSignature = "";
  function renderTabbar() {
    const links = navLinks().filter((link) => !link.account).slice(0, 5);
    if (!links.length) return;
    const signature = links.map((l) => `${l.href}|${l.label}|${l.active}|${l.disabled}`).join(";");
    let bar = document.querySelector(".mobile-tabbar");
    if (bar && signature === tabbarSignature) return;
    tabbarSignature = signature;
    if (!bar) {
      bar = document.createElement("nav");
      bar.className = "mobile-tabbar";
      bar.setAttribute("aria-label", "Main");
      document.body.appendChild(bar);
      document.body.classList.add("has-mobile-tabbar");
    }
    bar.style.setProperty("--tab-count", String(links.length));
    bar.innerHTML = links
      .map(
        (link) => `
        <a class="mobile-tab${link.active ? " is-active" : ""}${link.disabled ? " is-disabled" : ""}" href="${escapeHtml(link.href)}"${link.active ? ' aria-current="page"' : ""}>
          <span class="mobile-tab-icon" aria-hidden="true">${escapeHtml(link.icon)}</span>
          <span class="mobile-tab-label">${escapeHtml(link.label)}</span>
        </a>`
      )
      .join("");
  }

  // ======================================================================
  // Add the buttons to whichever navbar is on the page
  // ======================================================================
  function addNavbarTools() {
    let added = false;
    document.querySelectorAll(".app-header").forEach((header) => {
      if (header.querySelector(".site-tools")) return;
      added = true;

      // Laptop / tablet: search + theme buttons
      const tools = document.createElement("div");
      tools.className = "site-tools";
      tools.innerHTML = `
        <button type="button" class="site-tool-button" data-search-toggle aria-label="Search" title="Search" aria-expanded="false">${ICONS.search}</button>
        <button type="button" class="site-tool-button site-theme-button" data-theme-toggle></button>`;
      const right = header.querySelector(".header-right");
      if (right) header.insertBefore(tools, right);
      else header.appendChild(tools);

      // Phone: ☰ on the left, ⚙️ on the right
      const menuButton = document.createElement("button");
      menuButton.type = "button";
      menuButton.className = "mobile-icon-button mobile-menu-button";
      menuButton.setAttribute("aria-label", "Open menu");
      menuButton.innerHTML = ICONS.menu;
      header.prepend(menuButton);

      const settingsButton = document.createElement("button");
      settingsButton.type = "button";
      settingsButton.className = "mobile-icon-button mobile-settings-button";
      settingsButton.setAttribute("aria-label", "Settings");
      settingsButton.innerHTML = ICONS.gear;
      header.appendChild(settingsButton);
    });
    if (added) applyTheme(getTheme());
    renderTabbar();
  }

  // ======================================================================
  // Events
  // ======================================================================
  document.addEventListener(
    "click",
    (event) => {
      const target = event.target;
      if (target.closest("[data-theme-toggle]")) {
        event.preventDefault();
        toggleTheme();
        return;
      }
      const searchButton = target.closest("[data-search-toggle]");
      if (searchButton) {
        event.preventDefault();
        const header = searchButton.closest(".app-header");
        if (openInline && openInline.header === header) closeInlineSearch();
        else if (header) openInlineSearch(header);
        return;
      }
      if (target.closest(".mobile-menu-button")) {
        event.preventDefault();
        openDrawer();
        return;
      }
      if (target.closest(".mobile-settings-button")) {
        event.preventDefault();
        openSettings();
        return;
      }
      if (target.closest("[data-drawer-signout]")) {
        event.preventDefault();
        closePanels();
        if (window.CricketClubAppPages?.signOut) window.CricketClubAppPages.signOut();
        else window.location.href = "/signout";
        return;
      }
      if (target.closest(".mobile-drawer-link.is-disabled, .mobile-tab.is-disabled")) {
        event.preventDefault();
        return;
      }
      if (target.closest(".mobile-drawer a, .mobile-drawer-results a, .mobile-sheet a")) {
        closePanels();
        return;
      }
      if (openInline && !target.closest(".site-search-inline, .site-search-dropdown")) closeInlineSearch();
    },
    true
  );

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeInlineSearch();
      closePanels();
    }
    // "/" opens search (like many sites), unless typing in a field
    if (event.key === "/" && !event.target.closest("input, textarea, select, [contenteditable]")) {
      event.preventDefault();
      if (isPhone()) {
        openDrawer();
        drawer?.querySelector("input")?.focus();
      } else {
        const header = document.querySelector(".app-header");
        if (header) openInlineSearch(header);
      }
    }
  });

  window.addEventListener("resize", () => {
    if (isPhone()) closeInlineSearch();
    else {
      closePanels();
      if (openInline) fitInlineSearch(openInline.header, openInline.box, openInline.dropdown);
    }
  });

  // The navbars are injected after page load and can be re-rendered, so keep watching for them.
  const observer = new MutationObserver(() => addNavbarTools());
  const start = () => {
    addNavbarTools();
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["aria-current", "href", "hidden"] });
  };
  if (document.body) start();
  else document.addEventListener("DOMContentLoaded", start);

  window.CCSiteTools = {
    toggleTheme,
    getTheme,
    themeMenuLabel,
    openSearch: () => {
      const header = document.querySelector(".app-header");
      if (isPhone()) openDrawer();
      else if (header) openInlineSearch(header);
    },
  };
})();
