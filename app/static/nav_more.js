/*
 * "More" menu for the public header (phone only).
 * Phone: LIVE, Fixtures, Rankings stay in the row, "More" sits at the right edge,
 *        and tapping it opens a dropdown with every other link
 *        (every link marked class="nav-overflow-item" in public_header.html).
 * Laptop: all links show in the row and "More" is hidden (handled in live.css).
 *
 * Clicks are handled at the document level, so this keeps working even if
 * public_header.js re-renders the header after this script runs.
 */
(() => {
  if (window.__navMoreLoaded) return;
  window.__navMoreLoaded = true;

  const BUTTON_SELECTOR = ".app-header .nav-more-toggle";
  let menu = null;
  let activeButton = null;

  function buildMenu(button) {
    const nav = button.closest(".top-nav");
    const panel = document.createElement("div");
    panel.id = "navMoreMenu";
    panel.className = "nav-more-menu";
    panel.setAttribute("role", "menu");

    const currentPath = window.location.pathname.replace(/\/+$/, "") || "/";
    (nav ? nav.querySelectorAll("a.nav-overflow-item") : []).forEach((link) => {
      const item = document.createElement("a");
      item.className = "nav-more-menu-item";
      item.href = link.getAttribute("href");
      item.setAttribute("role", "menuitem");
      if (currentPath === link.getAttribute("href")) item.setAttribute("aria-current", "page");
      const icon = link.querySelector(".nav-icon");
      const text = link.querySelector(".nav-text");
      item.innerHTML =
        `<span class="nav-more-menu-icon" aria-hidden="true">${icon ? icon.textContent : ""}</span>` +
        `<span>${text ? text.textContent : link.textContent.trim()}</span>`;
      panel.appendChild(item);
    });
    return panel;
  }

  function positionMenu() {
    if (!menu || !activeButton) return;
    const rect = activeButton.getBoundingClientRect();
    menu.style.top = `${rect.bottom + 8}px`;
    menu.style.right = `${Math.max(8, window.innerWidth - rect.right)}px`;
  }

  function closeMenu() {
    if (menu) menu.remove();
    if (activeButton) activeButton.setAttribute("aria-expanded", "false");
    menu = null;
    activeButton = null;
  }

  function openMenu(button) {
    closeMenu();
    activeButton = button;
    menu = buildMenu(button);
    document.body.appendChild(menu); // attached to <body> so nothing can clip it
    button.setAttribute("aria-expanded", "true");
    button.setAttribute("aria-haspopup", "menu");
    positionMenu();
  }

  // Capture phase so we run before any older handler on the button.
  document.addEventListener(
    "click",
    (event) => {
      const button = event.target.closest(BUTTON_SELECTOR);
      if (button) {
        event.preventDefault();
        event.stopImmediatePropagation();
        if (menu && activeButton === button) closeMenu();
        else openMenu(button);
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

  console.info("[nav_more] loaded");
})();