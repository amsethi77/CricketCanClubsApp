(() => {
  const CONTAINER_IDS = ["signinLiveMatches", "registerLiveMatches", "publicLiveMatches"];
  const COUNT_IDS = ["signinLiveMatchesCount", "registerLiveMatchesCount"];

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function liveBadge(match) {
    const status = String(match?.status || "").trim().toLowerCase();
    if (status === "live" || status === "in progress" || status === "ongoing") {
      return '<span class="public-live-badge is-live">LIVE</span>';
    }
    return '<span class="public-live-badge is-today">TODAY</span>';
  }

  function scoreline(match) {
    const heartlake = match?.heartlake_score || "--";
    const opponent = match?.opponent_score || "--";
    return `${heartlake} · ${opponent}`;
  }

  function renderCard(match) {
    const scorecard = match?.scorecard || {};
    const liveSummary = String(match?.live_summary || scorecard.live_summary || "").trim();
    const scoreDetail = scorecard.result || match?.result || "TBD";
    return `
      <a class="public-live-card" href="/public/match/${encodeURIComponent(match.id)}">
        <div class="public-live-card-head">
          <div class="public-live-card-tags">
            ${liveBadge(match)}
            <span class="public-live-match-date">${escapeHtml(match.date_label || match.date || "Today")}</span>
          </div>
          <span class="public-live-score">${escapeHtml(scoreline(match))}</span>
        </div>
        <h4>${escapeHtml(match.club_name || "Club")} vs ${escapeHtml(match.opponent || "Opponent")}</h4>
        <p>${escapeHtml(match.venue || "Venue TBD")} · ${escapeHtml(match.match_type || "Friendly")} · ${escapeHtml(match.scheduled_time || "Time TBD")}</p>
        <small>${escapeHtml(scoreDetail)}</small>
        <small>${escapeHtml(liveSummary || "Tap to open the full read-only scorecard.")}</small>
      </a>
    `;
  }

  async function loadLiveMatches() {
    const containers = CONTAINER_IDS.map((id) => document.getElementById(id)).filter(Boolean);
    if (!containers.length) {
      return;
    }
    try {
      const response = await fetch("/api/public/live-matches", { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error("Unable to load public live matches.");
      }
      const data = await response.json();
      const matches = Array.isArray(data.matches) ? data.matches : [];
      containers.forEach((container) => {
        container.innerHTML = matches.length
          ? matches.map((match) => renderCard(match)).join("")
          : `<div class="public-live-empty">No live matches yet today. Check back later for the next live scorecard.</div>`;
      });
      COUNT_IDS.map((id) => document.getElementById(id)).filter(Boolean).forEach((countEl) => {
        countEl.textContent = `${matches.length} shown`;
      });
    } catch (error) {
      containers.forEach((container) => {
        container.innerHTML = `<div class="public-live-empty">Live matches could not be loaded right now.</div>`;
      });
      COUNT_IDS.map((id) => document.getElementById(id)).filter(Boolean).forEach((countEl) => {
        countEl.textContent = "Unavailable";
      });
      console.error("[Public Live]", error);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadLiveMatches);
  } else {
    loadLiveMatches();
  }
})();
