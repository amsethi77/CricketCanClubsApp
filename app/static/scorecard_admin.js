/*
 * /admin/scorecards (site admin): uploads waiting for review with the reasons from the smart checks,
 * Approve / Reject, and the duplicate report with "Hide ticked duplicates".
 * APIs: GET /api/admin/scorecards/checks, POST /api/admin/scorecards/{id}/decision,
 *       POST /api/admin/scorecards/duplicates/hide.
 * README: "Scorecard uploads: checks, review and duplicates".
 */
(() => {
  const waitingEl = document.getElementById("scaWaiting");
  const dupsEl = document.getElementById("scaDups");
  const msgEl = document.getElementById("scaMsg");
  const waitBadge = document.getElementById("scaWaitBadge");
  const dupBadge = document.getElementById("scaDupBadge");
  const token = () => {
    try {
      return localStorage.getItem("cricketClubAppAuthToken") || "";
    } catch (error) {
      return "";
    }
  };
  const esc = (v) =>
    String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");

  async function api(method, url, body) {
    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json", "X-Auth-Token": token() },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    return data;
  }

  function waitingItem(item) {
    const flags = item.flags.length
      ? `<ul class="sc-check-list">${item.flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>`
      : `<p>No problems found. Waiting for the scorer to publish.</p>`;
    return `
      <article class="sca-item">
        ${item.photo_url ? `<a href="${esc(item.photo_url)}" target="_blank" rel="noopener"><img src="${esc(item.photo_url)}" alt="Scorecard photo" loading="lazy" /></a>` : "<span></span>"}
        <div>
          <h3>${esc(item.title || item.file_name)}</h3>
          <p>${esc([item.date, item.club_name, item.uploaded_by ? `by ${item.uploaded_by}` : "", item.status].filter(Boolean).join(" · "))}</p>
          ${flags}
          <div class="sc-check-actions">
            <a class="sc-btn" href="/scorecards/${encodeURIComponent(item.id)}?preview=1">Open digital scorecard</a>
            <button type="button" class="sc-btn primary" data-decide="approve" data-id="${esc(item.id)}">Approve</button>
            <button type="button" class="sc-btn" data-decide="reject" data-id="${esc(item.id)}">Reject</button>
          </div>
        </div>
      </article>`;
  }

  function dupLine(item, keep) {
    const label = `${esc(item.file_name)} <small>(${esc([item.status, (item.created_at || "").slice(0, 10), item.title].filter(Boolean).join(" · "))})</small>`;
    return keep
      ? `<label><span class="sc-tag">Keep</span> ${label}</label>`
      : `<label><input type="checkbox" data-dup="${esc(item.id)}" checked /> ${label}</label>`;
  }

  let lastData = null;
  let aiGroups = [];

  function render(data) {
    lastData = data;
    const groups = [...data.duplicate_groups, ...aiGroups];
    waitBadge.textContent = String(data.waiting.length);
    dupBadge.textContent = `${groups.length} group${groups.length === 1 ? "" : "s"}`;
    waitingEl.innerHTML = data.waiting.length ? data.waiting.map(waitingItem).join("") : `<div class="live-empty">Nothing waiting. 🎉</div>`;
    // "Ask AI" finds duplicates the simple checks miss (same game read slightly differently). README: "AI duplicate check".
    const aiButton = data.llm
      ? `<button type="button" class="sc-btn" data-ai-scan>🤖 Ask AI to find more duplicates</button>`
      : `<span class="sca-ai-off">Add GEMINI_API_KEY to .env to let AI find more duplicates.</span>`;
    dupsEl.innerHTML = groups.length
      ? groups
          .map(
            (group) => `
        <div class="sca-group">
          <div class="sca-reasons">${group.reasons.map((r) => `<span class="sc-tag">${esc(r)}</span>`).join("")}</div>
          ${dupLine(group.keep, true)}
          ${group.duplicates.map((item) => dupLine(item, false)).join("")}
        </div>`
          )
          .join("") + `<div class="sc-check-actions"><button type="button" class="sc-btn primary" data-hide-dups>Hide ticked duplicates</button>${aiButton}</div>`
      : `<div class="live-empty">No duplicate scorecards found.</div><div class="sc-check-actions">${aiButton}</div>`;
  }

  async function load() {
    try {
      render(await api("GET", "/api/admin/scorecards/checks"));
    } catch (error) {
      waitingEl.innerHTML = `<div class="live-empty">${esc(error.message)}</div>`;
      dupsEl.innerHTML = "";
    }
  }

  document.addEventListener("click", async (event) => {
    const decide = event.target.closest("[data-decide]");
    if (decide) {
      const note = decide.dataset.decide === "reject" ? window.prompt("Why is it rejected? (the uploader sees this)") : "";
      if (note === null) return;
      decide.disabled = true;
      try {
        const data = await api("POST", `/api/admin/scorecards/${encodeURIComponent(decide.dataset.id)}/decision`, { decision: decide.dataset.decide, note });
        msgEl.textContent = data.message;
      } catch (error) {
        msgEl.textContent = error.message;
      }
      load();
      return;
    }
    const scan = event.target.closest("[data-ai-scan]");
    if (scan) {
      scan.disabled = true;
      scan.textContent = "🤖 Asking the AI… (up to a minute)";
      try {
        const data = await api("POST", "/api/admin/scorecards/duplicates/ai-scan");
        aiGroups = data.groups || [];
        msgEl.textContent = data.message;
      } catch (error) {
        msgEl.textContent = error.message;
      }
      if (lastData) render(lastData);
      return;
    }
    if (event.target.closest("[data-hide-dups]")) {
      const ids = Array.from(dupsEl.querySelectorAll("[data-dup]:checked")).map((box) => box.dataset.dup);
      if (!ids.length) return;
      try {
        const data = await api("POST", "/api/admin/scorecards/duplicates/hide", { ids });
        msgEl.textContent = data.message;
        aiGroups = [];
      } catch (error) {
        msgEl.textContent = error.message;
      }
      load();
    }
  });

  load();
})();
