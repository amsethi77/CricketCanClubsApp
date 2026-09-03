(() => {
  const liveMatchesEl = document.getElementById("liveMatches");
  const liveMatchesCountEl = document.getElementById("liveMatchesCount");
  const liveHeroFeatureEl = document.getElementById("liveHeroFeature");

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function scoreline(match) {
    const left = match?.heartlake_score || "--";
    const right = match?.opponent_score || "--";
    return `${left} · ${right}`;
  }

  function renderBalls(match) {
    const balls = Array.isArray(match?.recent_balls) ? match.recent_balls : [];
    if (!balls.length) {
      return `<div class="live-empty">No recent balls yet.</div>`;
    }
    return `<div class="live-recent-balls">${balls.slice(-6).map((ball) => {
      const value = String(ball || "0").toUpperCase();
      const cls = value === "4" ? "is-four" : value === "6" ? "is-six" : value === "W" ? "is-wicket" : value === "WD" || value === "NB" ? "is-extra" : "";
      return `<span class="live-recent-ball ${cls}">${escapeHtml(value)}</span>`;
    }).join("")}</div>`;
  }

  function renderLiveCard(match) {
    return `
      <a class="live-card" href="/live/${encodeURIComponent(match.id)}">
        <div class="live-card-head">
          <div>
            <div class="live-pill"><span class="live-dot"></span><span>${escapeHtml(String(match.status || "Live").toUpperCase())}</span></div>
            <h4>${escapeHtml(match.club_name || "Club")} vs ${escapeHtml(match.opponent || "Opponent")}</h4>
            <p>${escapeHtml(match.date_label || match.date || "Date TBD")} · ${escapeHtml(match.venue || "Venue TBD")} · ${escapeHtml(match.match_type || "Friendly")}</p>
          </div>
          <div class="live-score">${escapeHtml(scoreline(match))}</div>
        </div>
        <p>${escapeHtml(match.live_summary || match.result || "Live scorecard")}</p>
        <p>${escapeHtml(match.scheduled_time || "Time TBD")} · ${escapeHtml(match.overs || "")}</p>
        ${renderBalls(match)}
      </a>
    `;
  }

  function renderHero(match) {
    if (!liveHeroFeatureEl) {
      return;
    }
    if (!match || !match.id) {
      liveHeroFeatureEl.innerHTML = `
        <div class="live-feature-card">
          <div class="live-pill"><span class="live-dot"></span><span>NO LIVE MATCHES</span></div>
          <h2 style="margin:14px 0 8px;font-family:'Source Serif 4',serif;font-size:clamp(1.8rem,4vw,3rem);">Check back for the next live scorecard.</h2>
          <p>Fixtures are available on the fixtures page.</p>
          <div class="live-cta-row" style="margin-top:16px;">
            <a class="live-action secondary" href="/fixtures">View Fixtures</a>
          </div>
        </div>
      `;
      return;
    }
    liveHeroFeatureEl.innerHTML = `
      <div class="live-feature-card">
        <div class="live-pill"><span class="live-dot"></span><span>${escapeHtml(String(match.status || "LIVE").toUpperCase())}</span></div>
        <h2 style="margin:14px 0 8px;font-family:'Source Serif 4',serif;font-size:clamp(1.8rem,4vw,3rem);">${escapeHtml(match.club_name || "Club")} vs ${escapeHtml(match.opponent || "Opponent")}</h2>
        <p>${escapeHtml(match.date_label || match.date || "Date TBD")} · ${escapeHtml(match.venue || "Venue TBD")} · ${escapeHtml(match.match_type || "Friendly")}</p>
        <div class="live-score" style="margin-top:16px;">${escapeHtml(scoreline(match))}</div>
        <p style="margin-top:10px;">${escapeHtml(match.live_summary || match.result || "Live scorecard")}</p>
        ${renderBalls(match)}
        <div class="live-cta-row" style="margin-top:16px;">
          <a class="live-action secondary" href="/live/${encodeURIComponent(match.id)}">Open Scorecard</a>
        </div>
      </div>
    `;
  }

  async function loadLivePage() {
    try {
      const response = await fetch("/api/public/live-page", { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error("Unable to load live landing page.");
      }
      const data = await response.json();
      const liveMatches = Array.isArray(data.live_matches) ? data.live_matches : [];
      renderHero(data.hero || liveMatches[0] || {});
      if (liveMatchesEl) {
        liveMatchesEl.innerHTML = liveMatches.length
          ? liveMatches.map((match) => renderLiveCard(match)).join("")
          : `<div class="live-empty">No live matches yet today.</div>`;
      }
      if (liveMatchesCountEl) {
        liveMatchesCountEl.textContent = `${liveMatches.length} live`;
      }
    } catch (error) {
      console.error("[Live Landing]", error);
      renderHero({});
      if (liveMatchesEl) liveMatchesEl.innerHTML = `<div class="live-empty">Live matches could not be loaded right now.</div>`;
      if (liveMatchesCountEl) liveMatchesCountEl.textContent = "Unavailable";
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadLivePage);
  } else {
    loadLivePage();
  }
})();
