/*
 * Zoom lock (Oct 2026, README "Screen size and zoom").
 * Keeps the app at its normal size on laptops/desktops:
 *  - blocks Ctrl/Cmd + "+" / "-" and Ctrl/Cmd + mouse wheel / trackpad pinch,
 *  - Ctrl/Cmd + 0 (reset to 100%) still works,
 *  - if the browser is already zoomed out (Chrome remembers zoom per site),
 *    shows a small note "Press Ctrl + 0" so the page goes back to normal size.
 * Phones are handled by the viewport meta (maximum-scale=1.0) and styles.css.
 * Loaded on every page with <script src="/assets/zoom_lock.js?v=...">.
 */
(() => {
  if (window.CCZoomLock) return;
  window.CCZoomLock = true;

  const ZOOM_KEYS = new Set(["+", "=", "-", "_"]);
  const ZOOM_CODES = new Set(["NumpadAdd", "NumpadSubtract", "Equal", "Minus"]);

  window.addEventListener(
    "keydown",
    (event) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      if (ZOOM_KEYS.has(event.key) || ZOOM_CODES.has(event.code)) event.preventDefault();
    },
    { capture: true }
  );

  // Ctrl + wheel, and laptop trackpad pinch (Chrome reports it as Ctrl + wheel).
  window.addEventListener(
    "wheel",
    (event) => {
      if (event.ctrlKey || event.metaKey) event.preventDefault();
    },
    { passive: false, capture: true }
  );

  // Safari trackpad pinch.
  ["gesturestart", "gesturechange", "gestureend"].forEach((name) =>
    document.addEventListener(name, (event) => event.preventDefault(), { passive: false })
  );

  // Already zoomed out? (inner width larger than the window means zoom below 100%.)
  const NOTE_ID = "ccZoomNote";
  function zoomedOutPercent() {
    if (!window.outerWidth || !window.innerWidth) return 0;
    const ratio = window.outerWidth / window.innerWidth;
    return ratio < 0.9 ? Math.round(ratio * 100) : 0;
  }
  function checkZoom() {
    const percent = zoomedOutPercent();
    let note = document.getElementById(NOTE_ID);
    if (!percent) {
      if (note) note.remove();
      return;
    }
    if (note || sessionStorageGet()) return;
    note = document.createElement("div");
    note.id = NOTE_ID;
    note.setAttribute("role", "status");
    note.style.cssText =
      "position:fixed;left:50%;top:12px;transform:translateX(-50%);z-index:4000;display:flex;gap:12px;align-items:center;" +
      "padding:10px 14px;border-radius:14px;background:#0f172a;color:#fff;font:600 15px/1.4 Roboto,system-ui,sans-serif;" +
      "box-shadow:0 12px 30px rgba(15,23,42,.3);max-width:calc(100vw - 32px)";
    note.innerHTML =
      '<span>Your browser is zoomed out (about ' + percent + '%). Press <b>Ctrl + 0</b> to see the app at normal size.</span>' +
      '<button type="button" style="border:0;border-radius:10px;padding:6px 10px;font-weight:800;cursor:pointer">OK</button>';
    note.querySelector("button").addEventListener("click", () => {
      note.remove();
      try {
        sessionStorage.setItem(NOTE_ID, "1");
      } catch (error) {
        /* ignore */
      }
    });
    (document.body || document.documentElement).appendChild(note);
  }
  function sessionStorageGet() {
    try {
      return sessionStorage.getItem(NOTE_ID);
    } catch (error) {
      return null;
    }
  }
  window.addEventListener("resize", checkZoom);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", checkZoom);
  else checkZoom();
})();
