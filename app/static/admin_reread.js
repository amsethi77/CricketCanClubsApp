/*
 * Admin Center: "Clean up and re-read all with AI" (README "Clean up and re-read all scorecards").
 * Site admins only. POST /api/admin/scorecards/reread-all starts it in the background;
 * GET the same address every few seconds shows the progress here.
 */
(() => {
  const card = document.getElementById("adminRereadCard");
  if (!card) return;
  const button = document.getElementById("adminRereadButton");
  const cleanup = document.getElementById("adminRereadCleanup");
  const skip = document.getElementById("adminRereadSkip");
  const status = document.getElementById("adminRereadStatus");
  const TOKEN_KEY = "cricketClubAppAuthToken";
  let timer = null;

  const token = () => {
    try {
      return localStorage.getItem(TOKEN_KEY) || "";
    } catch (error) {
      return "";
    }
  };
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);

  async function call(method, body) {
    const response = await fetch("/api/admin/scorecards/reread-all", {
      method,
      headers: { "X-Auth-Token": token(), "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Something went wrong.");
    return data;
  }

  function show(job) {
    if (!job || (!job.running && !job.message)) {
      status.hidden = true;
      return;
    }
    const total = Number(job.total || 0);
    const number = Number(job.number || 0);
    const percent = total ? Math.round((number / total) * 100) : 0;
    const recent = (job.done || []).slice(-5).reverse().map((line) => `<li>${esc(line)}</li>`).join("");
    status.hidden = false;
    status.className = `status-banner ${job.running ? "info" : /error|Stopped/.test(job.message || "") ? "warning" : "success"}`;
    status.innerHTML = `
      <strong>${job.running ? "⏳ " : ""}${esc(job.message || "")}</strong>
      ${total ? `<div style="height:8px;border-radius:99px;background:#e2e8f0;margin:8px 0;overflow:hidden"><span style="display:block;height:100%;width:${percent}%;background:#e11d48"></span></div><small>${number} of ${total} photos</small>` : ""}
      ${recent ? `<ul style="margin:6px 0 0;padding-left:18px">${recent}</ul>` : ""}
      ${!job.running && job.report_path ? `<p style="margin:6px 0 0">Report saved on this computer: <code>${esc(job.report_path)}</code>. Tap “Refresh queue” to see the cards.</p>` : ""}`;
    button.disabled = Boolean(job.running);
    button.textContent = job.running ? "Reading…" : "🤖 Re-read all scorecards";
  }

  async function poll() {
    try {
      const data = await call("GET");
      show(data.job);
      if (data.job && data.job.running) {
        timer = setTimeout(poll, 3000);
      } else if (timer) {
        timer = null;
        document.getElementById("adminRefreshButton")?.click();
      }
    } catch (error) {
      timer = null;
    }
  }

  button.addEventListener("click", async () => {
    const what = cleanup.checked
      ? "Clean up the uploads (delete uploads without a photo on this computer and extra copies) and read every photo again with AI?\n\nA backup of the database is made first."
      : "Read every scorecard photo again with AI? A backup of the database is made first.";
    if (!window.confirm(what)) return;
    button.disabled = true;
    try {
      const data = await call("POST", { cleanup: cleanup.checked, skip_done: skip.checked });
      show(data.job);
      timer = setTimeout(poll, 2000);
    } catch (error) {
      status.hidden = false;
      status.className = "status-banner error";
      status.textContent = error.message;
      button.disabled = false;
    }
  });

  // Only site admins can use it: the status call answers 401/403 for everyone else, and the card stays hidden.
  call("GET")
    .then((data) => {
      card.hidden = false;
      show(data.job);
      if (data.job && data.job.running) timer = setTimeout(poll, 3000);
    })
    .catch(() => {});
})();
