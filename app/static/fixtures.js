(() => {
  const TOKEN_KEY = "cricketClubAppAuthToken";
  const CLUB_KEY = "cricketClubAppPrimaryClubId";
  const fixturesGroupsEl = document.getElementById("fixturesGroups");
  const fixturesHeroSummaryEl = document.getElementById("fixturesHeroSummary");
  const fixturesTotalCountEl = document.getElementById("fixturesTotalCount");
  const fixturesClubCountEl = document.getElementById("fixturesClubCount");
  const fixturesUpcomingCountEl = document.getElementById("fixturesUpcomingCount");
  const fixturesModeLabelEl = document.getElementById("fixturesModeLabel");
  const fixturesListHeadingEl = document.getElementById("fixturesListHeading");
  const fixturesListBadgeEl = document.getElementById("fixturesListBadge");

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function getAuthToken() {
    return window.localStorage.getItem(TOKEN_KEY) || "";
  }

  function getSelectedClubId() {
    return window.sessionStorage.getItem(CLUB_KEY) || "";
  }

  function scoreline(fixture) {
    const left = fixture?.heartlake_score || "--";
    const right = fixture?.opponent_score || "--";
    return `${left} · ${right}`;
  }

  function fixtureCard(fixture, modeLabel) {
    const link = fixture?.id ? `/live/${encodeURIComponent(fixture.id)}` : "#";
    return `
      <a class="live-card fixtures-card" href="${link}">
        <div class="live-card-head">
          <div>
            <div class="live-pill"><span class="live-dot"></span><span>${escapeHtml(String(fixture.status || "Scheduled").toUpperCase())}</span></div>
            <h4>${escapeHtml(fixture.club_name || "Club")} vs ${escapeHtml(fixture.opponent || "Opponent")}</h4>
            <p>${escapeHtml(fixture.date_label || fixture.date || "Date TBD")} · ${escapeHtml(fixture.venue || "Venue TBD")} · ${escapeHtml(fixture.match_type || "Friendly")}</p>
          </div>
          <div class="live-score">${escapeHtml(scoreline(fixture))}</div>
        </div>
        <p>${escapeHtml(fixture.scheduled_time || "Time TBD")} · ${escapeHtml(fixture.overs || "")}</p>
        <p class="fixtures-card-meta">${escapeHtml(modeLabel)}</p>
      </a>
    `;
  }

  function renderGroups(groups, modeLabel) {
    if (!fixturesGroupsEl) {
      return;
    }
    if (!groups.length) {
      fixturesGroupsEl.innerHTML = `<div class="live-empty">No fixtures available right now.</div>`;
      return;
    }
    fixturesGroupsEl.innerHTML = groups
      .map(
        (group) => `
          <section class="fixtures-group">
            <div class="fixtures-group-head">
              <div>
                <p class="section-kicker">${escapeHtml(group.group_label || "Fixtures")}</p>
                <h3>${escapeHtml(group.club_name || "Club fixtures")}</h3>
              </div>
              <span class="signin-widget-pill">${escapeHtml(String(group.count || (group.fixtures || []).length || 0))}</span>
            </div>
            <div class="fixtures-grid">
              ${(Array.isArray(group.fixtures) ? group.fixtures : []).map((fixture) => fixtureCard(fixture, modeLabel)).join("")}
            </div>
          </section>
        `
      )
      .join("");
  }

  async function loadPublicFixtures() {
    const token = getAuthToken();
    const selectedClubId = getSelectedClubId();
    try {
      if (token) {
        const response = await fetch("/api/dashboard", {
          headers: { Accept: "application/json", "X-Auth-Token": token },
        });
        if (response.ok) {
          const dashboard = await response.json();
          const fixtures = Array.isArray(dashboard.fixtures) ? dashboard.fixtures : [];
          const club = dashboard.focus_club || dashboard.club || {};
          const clubName = club.name || "Selected club";
          const readOnlyLabel = `Read-only club fixtures${selectedClubId ? ` · ${clubName}` : ""}`;
          if (fixturesHeroSummaryEl) {
            fixturesHeroSummaryEl.textContent = `Read-only fixtures for ${clubName}. Use this page to review upcoming games without editing.`;
          }
          if (fixturesTotalCountEl) fixturesTotalCountEl.textContent = String(fixtures.length || 0);
          if (fixturesClubCountEl) fixturesClubCountEl.textContent = "1";
          if (fixturesUpcomingCountEl) {
            fixturesUpcomingCountEl.textContent = String(fixtures.filter((fixture) => String(fixture.status || "").toLowerCase() !== "completed").length || 0);
          }
          if (fixturesModeLabelEl) fixturesModeLabelEl.textContent = "Read-only";
          if (fixturesListHeadingEl) fixturesListHeadingEl.textContent = `${clubName} fixtures`;
          if (fixturesListBadgeEl) fixturesListBadgeEl.textContent = readOnlyLabel;
          renderGroups([
            {
              club_name: clubName,
              group_label: "Your club",
              count: fixtures.length,
              fixtures,
            },
          ], "Club read-only mode");
          return;
        }
      }

      const response = await fetch("/api/public/fixtures-page", { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error("Unable to load public fixtures.");
      }
      const data = await response.json();
      const groups = Array.isArray(data.club_groups) ? data.club_groups : [];
      const totalFixtures = Array.isArray(data.fixtures) ? data.fixtures.length : 0;
      if (fixturesHeroSummaryEl) {
        fixturesHeroSummaryEl.textContent = data.hero?.summary || "Browse fixtures by club.";
      }
      if (fixturesTotalCountEl) fixturesTotalCountEl.textContent = String(data.hero?.total_fixtures || totalFixtures || 0);
      if (fixturesClubCountEl) fixturesClubCountEl.textContent = String(data.hero?.club_count || groups.length || 0);
      if (fixturesUpcomingCountEl) fixturesUpcomingCountEl.textContent = String(data.hero?.upcoming_count || 0);
      if (fixturesModeLabelEl) fixturesModeLabelEl.textContent = "Public";
      if (fixturesListHeadingEl) fixturesListHeadingEl.textContent = "All clubs";
      if (fixturesListBadgeEl) fixturesListBadgeEl.textContent = `${groups.length} clubs`;
      renderGroups(groups, "Public read-only mode");
    } catch (error) {
      console.error("[Fixtures]", error);
      if (fixturesGroupsEl) fixturesGroupsEl.innerHTML = `<div class="live-empty">Fixtures could not be loaded right now.</div>`;
      if (fixturesListBadgeEl) fixturesListBadgeEl.textContent = "Unavailable";
      if (fixturesModeLabelEl) fixturesModeLabelEl.textContent = "Unavailable";
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadPublicFixtures);
  } else {
    loadPublicFixtures();
  }
})();
