const { requireAuth, postJson, setPrimaryClubId, signOut, getJson } = window.CricketClubAppPages;

const greeting = document.getElementById("clubsGreeting");
const clubsList = document.getElementById("clubsList");
const selectedClubSummary = document.getElementById("selectedClubSummary");
const seasonSetupLink = document.getElementById("seasonSetupLink");
const playerAvailabilityLink = document.getElementById("playerAvailabilityLink");
const playerProfileLink = document.getElementById("playerProfileLink");
const signOutButton = document.getElementById("signOutButton");
const userIdentityBadge = document.getElementById("userIdentityBadge");
const clubSearchInput = document.getElementById("clubSearchInput");
const clubSearchButton = document.getElementById("clubSearchButton");
const clubSearchForm = document.getElementById("clubSearchForm");
const clubsSearchSummary = document.getElementById("clubsSearchSummary");
const statusBanner = document.getElementById("clubsStatus");
const clubsPlayerSnapshotTitle = document.getElementById("clubsPlayerSnapshotTitle");
const clubsPlayerSnapshotDetails = document.getElementById("clubsPlayerSnapshotDetails");
const clubsPlayerSnapshotTiles = document.getElementById("clubsPlayerSnapshotTiles");
const clubsPlayerYearRows = document.getElementById("clubsPlayerYearRows");
const clubsPlayerClubRows = document.getElementById("clubsPlayerClubRows");

let authData = null;
let dashboardData = null;
let playerOverviewData = null;
const clubDashboardCache = new Map();
let authSignature = "";

function getSelectedSeasonYear() {
  return String(window.localStorage.getItem("cricketClubAppSelectedSeasonYear") || "").trim();
}

function debug(...args) {
  if (typeof console !== "undefined" && console.debug) {
    console.debug("[Clubs]", ...args);
  }
}

async function loadClubDirectoryFallback() {
  try {
    const options = await getJson("/api/auth/options", false);
    return options?.clubs || [];
  } catch {
    return [];
  }
}

function currentMemberName() {
  const memberId = String(authData?.user?.member_id || "").trim();
  if (!memberId) {
    return "";
  }
  const members = dashboardData?.all_members || dashboardData?.members || [];
  const match = members.find((member) => String(member.id || "").trim() === memberId);
  return match?.name || "";
}

function isSuperadminUser(user) {
  const roles = [user?.effective_role, user?.role, ...(Array.isArray(user?.roles) ? user.roles : [])];
  return roles.some((role) => String(role || "").trim().toLowerCase() === "superadmin");
}

function memberKey(member) {
  return String(member?.name || member?.full_name || "").trim().toLowerCase();
}

function rowValue(row, key) {
  return Number(row?.[key] || 0) || 0;
}

function formatCell(value, decimals = 0) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  if (decimals) {
    return number.toFixed(decimals).replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1");
  }
  return String(Math.round(number));
}

function normalizedText(value) {
  return String(value || "").trim().toLowerCase();
}

function performanceMatchesMember(performanceName, member) {
  const target = normalizedText(performanceName);
  if (!target) return false;
  const hints = new Set(
    [
      member?.name,
      member?.full_name,
      authData?.user?.display_name,
      authData?.user?.full_name,
      authData?.user?.email,
      authData?.user?.mobile,
      ...(member?.aliases || []),
    ]
      .filter(Boolean)
      .map(normalizedText)
  );
  return hints.has(target);
}

function highestScoreFor(member, { year = null, clubId = null } = {}) {
  const fixtures = dashboardData?.all_fixtures || dashboardData?.fixtures || [];
  const archives = dashboardData?.all_archive_uploads || dashboardData?.archive_uploads || [];
  let highest = null;
  for (const fixture of fixtures) {
    if (year && normalizedText(fixture.season_year) !== normalizedText(year)) continue;
    if (clubId && normalizedText(fixture.club_id) !== normalizedText(clubId)) continue;
    for (const performance of fixture.performances || []) {
      if (!performanceMatchesMember(performance.player_name, member)) continue;
      const runs = Number(performance.runs || 0);
      highest = highest === null ? runs : Math.max(highest, runs);
    }
  }
  for (const archive of archives) {
    if (year && normalizedText(archive.archive_year) !== normalizedText(year)) continue;
    if (clubId && normalizedText(archive.club_id) !== normalizedText(clubId)) continue;
    const performances = (archive.suggested_performances || []).filter((performance) => performance && typeof performance === "object");
    if (!performances.length) {
      try {
        const template = archive.review_template_json ? JSON.parse(archive.review_template_json) : null;
        const innings = Array.isArray(template?.innings) ? template.innings : [];
        for (const inning of innings) {
          for (const batting of inning?.batting || []) {
            performances.push({
              player_name: batting?.player?.name || batting?.player_name || "",
              runs: batting?.runs || 0,
            });
          }
        }
      } catch {
        // Ignore malformed templates and keep the existing score lookup.
      }
    }
    for (const performance of performances) {
      if (!performanceMatchesMember(performance.player_name, member)) continue;
      const runs = Number(performance.runs || 0);
      highest = highest === null ? runs : Math.max(highest, runs);
    }
  }
  return highest;
}

function renderTableRows(body, rows, emptyText) {
  if (!body) return;
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="21">${emptyText}</td></tr>`;
    return;
  }
  const gap = `<td class="pm-gap"></td>`;
  body.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${row.label}</td>
          <td class="pm-g-bat">${formatCell(row.matches)}</td>
          <td class="pm-g-bat">${formatCell(row.innings)}</td>
          <td class="pm-g-bat">${formatCell(row.not_outs)}</td>
          <td class="pm-g-bat">${formatCell(row.runs)}</td>
          <td class="pm-g-bat">${row.hs ?? "—"}</td>
          <td class="pm-g-bat">${formatCell(row.average, 2)}</td>
          <td class="pm-g-bat">${formatCell(row.balls)}</td>
          <td class="pm-g-bat">${formatCell(row.strike_rate, 2)}</td>
          <td class="pm-g-bat">${formatCell(row.scores_25_plus)}</td>
          <td class="pm-g-bat">${formatCell(row.fifties)}</td>
          <td class="pm-g-bat">${formatCell(row.hundreds)}</td>
          <td class="pm-g-bat">${formatCell(row.fours)}</td>
          <td class="pm-g-bat">${formatCell(row.sixes)}</td>
          ${gap}
          <td class="pm-g-bowl">${row.overs || "—"}</td>
          <td class="pm-g-bowl">${formatCell(row.wickets)}</td>
          <td class="pm-g-bowl">${formatCell(row.economy, 2)}</td>
          ${gap}
          <td class="pm-g-field">${formatCell(row.catches)}</td>
          <td class="pm-g-field">${formatCell(row.stumpings)}</td>
        </tr>
      `
    )
    .join("");
}

function snapshotTiles(stats, bowl) {
  const dash = (value) => (value === null || value === undefined || value === "" ? "—" : value);
  const matches = Number(stats.matches || 0);
  const catches = Number(stats.catches || 0);
  const tile = (group, title, pairs) =>
    `<div class="pm-stat-card pm-c-${group}"><h3>${title}</h3><dl>${pairs
      .map(([label, value]) => `<div><dt>${label}</dt><dd>${dash(value)}</dd></div>`)
      .join("")}</dl></div>`;
  return (
    tile("bat", "Batting", [
      ["Matches", matches],
      ["Runs", stats.runs],
      ["Highest", stats.highest_score],
      ["Average", formatCell(stats.batting_average, 2)],
      ["Strike rate", formatCell(stats.strike_rate, 2)],
    ]) +
    tile("bowl", "Bowling", [
      ["Innings", bowl.innings],
      ["Overs", bowl.overs],
      ["Wickets", bowl.wickets],
      ["Economy", formatCell(bowl.economy, 2)],
    ]) +
    tile("field", "Fielding", [
      ["Catches", catches],
      ["Per match", matches ? formatCell(catches / matches, 2) : "—"],
    ])
  );
}

function updatePlayerSnapshot() {
  if (!clubsPlayerSnapshotTitle || !clubsPlayerSnapshotDetails) {
    return;
  }
  if (clubsPlayerSnapshotTiles) clubsPlayerSnapshotTiles.innerHTML = "";
  const overview = playerOverviewData;
  const member =
    overview?.member ||
    (dashboardData?.all_members || dashboardData?.members || []).find((item) => String(item.id || "") === String(authData?.user?.member_id || ""));
  if (!member) {
    clubsPlayerSnapshotTitle.textContent = "No player selected";
    clubsPlayerSnapshotDetails.textContent = "Sign in with your player profile to see your totals here.";
    return;
  }
  const memberLabel = member?.full_name ? `${member.name} (${member.full_name})` : member?.name || "";
  clubsPlayerSnapshotTitle.textContent = memberLabel;
  if (!overview && !dashboardData) {
    clubsPlayerSnapshotDetails.textContent = "Loading totals from your clubs...";
    return;
  }
  const fallbackStats =
    (dashboardData?.member_summary_stats || []).find((item) => item.player_name === member.name) ||
    (dashboardData?.member_summary_stats || []).find((item) => String(item.player_name || "").trim().toLowerCase() === String(member.name || "").trim().toLowerCase()) ||
    dashboardData?.all_combined_player_stats?.find((item) => item.player_name === member.name) ||
    dashboardData?.all_combined_player_stats?.find((item) => String(item.player_name || "").trim().toLowerCase() === String(member.name || "").trim().toLowerCase()) ||
    {};
  const stats = overview?.summary_stats || fallbackStats;
  const gamesPlayed = Number(stats.matches || 0);
  const bowlSummary = overview?.bowling?.summary || {};
  clubsPlayerSnapshotTiles.innerHTML = snapshotTiles(stats, bowlSummary);
  const details = [`${gamesPlayed} games`];
  if (stats.last_game_date) {
    details.push(`Last: ${stats.last_game_date} vs ${stats.last_opponent || "TBD"}`);
  }
  if (stats.next_game_date) {
    details.push(`Next: ${stats.next_game_date} vs ${stats.next_opponent || "TBD"}`);
  }
  clubsPlayerSnapshotDetails.textContent = details.join(" · ");
}

async function loadClubDashboard(clubId) {
  if (!clubId) return null;
  const selectedYear = getSelectedSeasonYear();
  const cacheKey = `${clubId}::${selectedYear || "current"}`;
  if (clubDashboardCache.has(cacheKey)) {
    return clubDashboardCache.get(cacheKey);
  }
  debug("Loading club dashboard snapshot.", { clubId });
  const query = new URLSearchParams({ focus_club_id: clubId });
  if (selectedYear) {
    query.set("selected_season_year", selectedYear);
  }
  const dashboard = await getJson(`/api/dashboard?${query.toString()}`, true);
  clubDashboardCache.set(cacheKey, dashboard);
  return dashboard;
}

async function loadPlayerOverview() {
  try {
    debug("Loading player overview.");
    playerOverviewData = await getJson("/api/player/summary", true);
  } catch (error) {
    debug("Player overview load failed.", { error: error?.message || error });
    playerOverviewData = null;
  }
}

async function renderPlayerBreakdowns() {
  const overview = playerOverviewData;
  const member =
    overview?.member ||
    (dashboardData?.all_members || dashboardData?.members || []).find((item) => String(item.id || "") === String(authData?.user?.member_id || ""));
  if (!member) {
    renderTableRows(clubsPlayerYearRows, [], "Sign in with your player profile to see the yearly breakdown.");
    renderTableRows(clubsPlayerClubRows, [], "Sign in with your player profile to see the club breakdown.");
    return;
  }

  const yearRows = [];
  // Nov 4 2026: the player's own totals (all clubs) come first; the dashboard's rows only cover the current club
  // (2024 showed HS 24 with 0 matches because the Heartlake-only row won)
  const mergedYearStats = [...(overview?.year_stats || []), ...(dashboardData?.member_year_stats || [])];
  const yearStatsByKey = new Map();
  for (const row of mergedYearStats) {
    const key = `${String(row.season_year || "").trim().toLowerCase()}|${String(row.player_name || "").trim().toLowerCase()}`;
    if (!yearStatsByKey.has(key)) {
      yearStatsByKey.set(key, row);
    }
  }
  const yearStats = Array.from(yearStatsByKey.values());
  const rankingYears = [...new Set(yearStats.map((item) => item.season_year).filter(Boolean))];
  // Nov 11 2026 (Amit: Clubs player snapshot should show bowling and fielding): bowling comes from the scorecards
  // (/api/player/summary bowling block), matched by season and by club name.
  const bowlingByYear = new Map((overview?.bowling?.years || []).map((row) => [String(row.season_year), row]));
  const bowlingByClub = new Map((overview?.bowling?.clubs || []).map((row) => [String(row.club_name || "").trim().toLowerCase(), row]));
  for (const year of rankingYears) {
    const row = { runs: 0, wickets: 0, catches: 0, matches: 0, batting_innings: 0, outs: 0, batting_average: 0, strike_rate: 0, fours: 0, sixes: 0, highest_score: null };
    const match = yearStats.find((item) => item.season_year === String(year) && (item.player_name === member.name || performanceMatchesMember(item.player_name, member))) || row;
    const yearRow = match;
    yearRows.push({
      label: year,
      matches: rowValue(yearRow, "matches"),
      innings: rowValue(yearRow, "batting_innings"),
      not_outs: Math.max(0, rowValue(yearRow, "batting_innings") - rowValue(yearRow, "outs")),
      runs: rowValue(yearRow, "runs"),
      hs: rowValue(yearRow, "matches") ? rowValue(yearRow, "highest_score") || highestScoreFor(member, { year }) || "—" : "—",
      average: Number(yearRow.batting_average || 0) || 0,
      balls: rowValue(yearRow, "balls"),
      strike_rate: Number(yearRow.strike_rate || 0) || 0,
      scores_25_plus: rowValue(yearRow, "scores_25_plus"),
      hundreds: rowValue(yearRow, "scores_100_plus") || rowValue(yearRow, "centuries"),
      fifties: rowValue(yearRow, "scores_50_plus") || rowValue(yearRow, "fifties"),
      fours: rowValue(yearRow, "fours"),
      sixes: rowValue(yearRow, "sixes"),
      catches: rowValue(yearRow, "catches"),
      stumpings: rowValue(yearRow, "stumpings"),
      overs: bowlingByYear.get(String(year))?.overs || "",
      wickets: bowlingByYear.get(String(year))?.wickets ?? null,
      economy: bowlingByYear.get(String(year))?.economy ?? null,
    });
  }
  renderTableRows(clubsPlayerYearRows, yearRows, "No yearly breakdown available yet.");

  const clubRows = [];
  const memberships = (member.club_memberships || [])
    .filter((club) => String(club.club_id || "").trim())
    .map((club) => ({ club_id: String(club.club_id || "").trim(), club_name: String(club.club_name || "").trim() || club.club_id }));
  const mergedClubStats = [...(overview?.club_stats || []), ...(dashboardData?.member_club_stats || [])];
  const clubStatsByKey = new Map();
  for (const row of mergedClubStats) {
    const key = `${String(row.club_id || "").trim().toLowerCase()}|${String(row.player_name || "").trim().toLowerCase()}`;
    if (!clubStatsByKey.has(key)) {
      clubStatsByKey.set(key, row);
    }
  }
  const clubStats = Array.from(clubStatsByKey.values());
  // Nov 4 2026 (Amit: "club wise shows only Coca Cola with zeros"): every club the player belongs to OR has
  // stats for, matched by any of their names / aliases (not only the exact profile name)
  const isMe = (name) => String(name || "").trim() === member.name || performanceMatchesMember(name, member);
  for (const row of clubStats) {
    const id = String(row.club_id || "").trim();
    if (id && isMe(row.player_name) && !memberships.some((club) => club.club_id === id)) {
      memberships.push({ club_id: id, club_name: String(row.club_name || "").trim() || id });
    }
  }
  // Nov 4 2026 (Amit: "3 clubs to select but stats show 4 with 0,0"): Club Wise lists the same clubs as the
  // club picker (my_clubs) plus any club that has real stats; a stale membership with no club and no games is hidden.
  const pickerIds = new Set((authData?.clubs || []).map((club) => String(club.club_id || club.id || "").trim()).filter(Boolean));
  for (let index = memberships.length - 1; index >= 0; index -= 1) {
    const id = memberships[index].club_id;
    const hasGames = clubStats.some((item) => String(item.club_id || "").trim() === id && isMe(item.player_name) && Number(item.matches || 0) > 0);
    if (pickerIds.size && !pickerIds.has(id) && !hasGames) memberships.splice(index, 1);
  }
  for (const club of memberships) {
    const row = clubStats.find((item) => item.club_id === club.club_id && isMe(item.player_name)) || {
      runs: 0,
      wickets: 0,
      catches: 0,
      matches: 0,
      batting_innings: 0,
      outs: 0,
      batting_average: 0,
      strike_rate: 0,
      fours: 0,
      sixes: 0,
      highest_score: null,
    };
    const aggregate = {
      matches: rowValue(row, "matches"),
      innings: rowValue(row, "batting_innings"),
      not_outs: Math.max(0, rowValue(row, "batting_innings") - rowValue(row, "outs")),
      runs: rowValue(row, "runs"),
      hs: rowValue(row, "matches") ? rowValue(row, "highest_score") || highestScoreFor(member, { clubId: club.club_id }) || "—" : "—",
      average: Number(row.batting_average || 0) || 0,
      balls: rowValue(row, "balls"),
      strike_rate: Number(row.strike_rate || 0) || 0,
      scores_25_plus: rowValue(row, "scores_25_plus"),
      hundreds: rowValue(row, "scores_100_plus") || rowValue(row, "centuries"),
      fifties: rowValue(row, "scores_50_plus") || rowValue(row, "fifties"),
      fours: rowValue(row, "fours"),
      sixes: rowValue(row, "sixes"),
      catches: rowValue(row, "catches"),
      stumpings: rowValue(row, "stumpings"),
      overs: bowlingByClub.get(String(club.club_name || "").trim().toLowerCase())?.overs || "",
      wickets: bowlingByClub.get(String(club.club_name || "").trim().toLowerCase())?.wickets ?? null,
      economy: bowlingByClub.get(String(club.club_name || "").trim().toLowerCase())?.economy ?? null,
    };
    clubRows.push({
      label: club.club_name,
      ...aggregate,
    });
  }
  renderTableRows(clubsPlayerClubRows, clubRows, "No club breakdown available yet.");
}

async function loadDashboardSnapshot() {
  try {
    if (!authData?.user) {
      dashboardData = null;
      playerOverviewData = null;
      return;
    }
    const clubId = authData?.user?.current_club_id || authData?.user?.primary_club_id || "";
    debug("Loading dashboard snapshot.", { clubId });
    dashboardData = await getJson(`/api/dashboard${clubId ? `?focus_club_id=${encodeURIComponent(clubId)}` : ""}`, true);
    await loadPlayerOverview();
    updatePlayerSnapshot();
    await renderPlayerBreakdowns();
    debug("Dashboard snapshot loaded.", { clubId, members: dashboardData?.members?.length || 0 });
    setStatus("", "info");
  } catch {
    await loadPlayerOverview();
    updatePlayerSnapshot();
    await renderPlayerBreakdowns();
    setStatus("Club dashboard could not be loaded right now.", "error");
  }
}

function setStatus(message, tone = "info") {
  const show = Boolean(message) && (tone === "error" || tone === "warning");
  statusBanner.hidden = !show;
  statusBanner.textContent = show ? message : "";
  statusBanner.className = `status-banner ${tone}`;
}

function currentClub() {
  const clubId = authData?.user?.current_club_id || authData?.user?.primary_club_id || "";
  return (authData?.clubs || []).find((club) => club.id === clubId) || authData?.clubs?.[0] || null;
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
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("").slice(0, 2);
}

function syncUserBadge(user) {
  if (!userIdentityBadge) return;
  if (!user) {
    userIdentityBadge.hidden = true;
    userIdentityBadge.innerHTML = "";
    return;
  }
  userIdentityBadge.hidden = false;
  const name = String(user.display_name || user.full_name || user.mobile || "Signed in").trim();
  const role = formatRoleLabel(user.effective_role || user.role || "player");
  userIdentityBadge.innerHTML = `
    <span class="user-chip-mark" aria-hidden="true">${formatInitials(name)}</span>
    <span class="user-chip-copy">
      <strong>${name}</strong>
      <span>${role}</span>
    </span>
  `;
}

function refreshLinks() {
  const club = currentClub();
  const query = club ? `?focus_club_id=${encodeURIComponent(club.id)}` : "";
  seasonSetupLink.href = `/season-setup${query}`;
  playerAvailabilityLink.href = `/player-availability${query}`;
  playerProfileLink.href = `/profile${query}`;
  selectedClubSummary.textContent = club
    ? `Current club: ${club.name} · ${club.season || "Season TBD"}`
    : "Choose a club to continue.";
}

function renderClubs() {
  const selectedId = currentClub()?.id || "";
  const query = clubSearchInput.value.trim().toLowerCase();
  const pool = query && isSuperadminUser(authData?.user) ? authData?.allClubs || authData?.clubs || [] : authData?.clubs || [];
  const visibleClubs = pool
    .slice()
    .sort((left, right) => {
      const leftScore = left.id === selectedId ? 0 : 1;
      const rightScore = right.id === selectedId ? 0 : 1;
      if (leftScore !== rightScore) return leftScore - rightScore;
      return String(left.name || "").localeCompare(String(right.name || ""));
    })
    .filter((club) => {
      if (!query) return true;
      return [club.name, club.short_name, club.season].some((value) => String(value || "").toLowerCase().includes(query));
    });
  clubsSearchSummary.textContent = query
    ? `${visibleClubs.length} club${visibleClubs.length === 1 ? "" : "s"} match your search.`
    : `${visibleClubs.length} club${visibleClubs.length === 1 ? "" : "s"} available.`;
  clubsList.innerHTML = visibleClubs
    .map(
      (club) => `
        <article class="club-tile ${club.id === selectedId ? "is-current" : ""}">
          ${club.id === selectedId ? `<span class="club-tile-badge">Current club</span>` : ""}
          <strong>${club.name}</strong>
          <p>${club.season || "Season TBD"}</p>
          <small>${club.short_name || ""}</small>
          <button class="secondary-button" type="button" data-club-select="${club.id}">Select club</button>
        </article>
      `
    )
    .join("") || `<p class="empty-state">No clubs match that search.</p>`;
}

  clubsList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-club-select]");
    if (!button) return;
    try {
      debug("Club select requested.", { clubId: button.dataset.clubSelect || "" });
      const data = await postJson("/api/auth/select-club", { club_id: button.dataset.clubSelect }, true);
      authData.user = data.user;
      setPrimaryClubId(data.user.current_club_id || data.user.primary_club_id || "");
      renderClubs();
      refreshLinks();
      const clubId = data.club?.id || data.user?.current_club_id || data.user?.primary_club_id || button.dataset.clubSelect || "";
      const dashboardUrl = "/dashboard";
      debug("Club select completed.", { clubId, clubName: data.club?.name || "" });
      window.setTimeout(() => {
        window.location.href = dashboardUrl;
      }, 100);
    } catch (error) {
      debug("Club select failed.", { error: error?.message || error });
      setStatus(error.message, "error");
    }
  });

  clubSearchInput.addEventListener("input", renderClubs);
  clubSearchInput.addEventListener("search", renderClubs);
  clubSearchButton?.addEventListener("click", renderClubs);
  clubSearchForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    renderClubs();
  });

  requireAuth()
    .then((data) => {
      if (!data) return;
      authData = data;
      // Nov 4 2026 (Amit): "My clubs" = every club you belong to / played for (Heartlake + Coca Cola + Amit CC),
      // not only the current one; a superadmin's search also finds every other club.
      authData.allClubs = authData.clubs || [];
      if (Array.isArray(authData.my_clubs) && authData.my_clubs.length) authData.clubs = authData.my_clubs;
      const nextAuthSignature = [
        authData?.user?.member_id || "",
        authData?.user?.viewer_member_name || "",
        authData?.user?.current_club_id || authData?.user?.primary_club_id || "",
      ].join("|");
      if (authSignature && authSignature !== nextAuthSignature) {
        clubDashboardCache.clear();
        dashboardData = null;
      }
      authSignature = nextAuthSignature;
      syncUserBadge(data.user || null);
      window.CricketClubAppPages.syncClubBadge(currentClub()?.name || "");
      const signedInName = data.user.display_name || data.user.full_name || data.user.email || data.user.mobile || "Signed in";
      if (greeting) {
        greeting.textContent = `Welcome, ${signedInName}`;
      }
      if (!Array.isArray(authData.clubs) || !authData.clubs.length) {
        if (isSuperadminUser(authData.user)) {
          renderClubs();
          refreshLinks();
          loadDashboardSnapshot();
          return;
        }
        return loadClubDirectoryFallback().then((clubs) => {
          authData.clubs = clubs;
          renderClubs();
          refreshLinks();
          loadDashboardSnapshot();
        });
      }
      renderClubs();
      refreshLinks();
      loadDashboardSnapshot();
    })
    .catch((error) => setStatus(error.message, "error"));

window.CricketClubAppClubSearch = {
  refresh: () => window.location.reload(),
};
