const { requireAuth, postJson, setPrimaryClubId, signOut, getPrimaryClubId, getJson } = window.HeartlakePages;

const greeting = document.getElementById("clubsGreeting");
const clubsList = document.getElementById("clubsList");
const selectedClubSummary = document.getElementById("selectedClubSummary");
const seasonSetupLink = document.getElementById("seasonSetupLink");
const playerAvailabilityLink = document.getElementById("playerAvailabilityLink");
const playerProfileLink = document.getElementById("playerProfileLink");
const dashboardLink = document.getElementById("dashboardLink");
const signOutButton = document.getElementById("signOutButton");
const clubSearchInput = document.getElementById("clubSearchInput");
const clubSearchButton = document.getElementById("clubSearchButton");
const clubSearchForm = document.getElementById("clubSearchForm");
const clubsSearchSummary = document.getElementById("clubsSearchSummary");
const statusBanner = document.getElementById("clubsStatus");
const clubsPlayerSnapshotTitle = document.getElementById("clubsPlayerSnapshotTitle");
const clubsPlayerSnapshotDetails = document.getElementById("clubsPlayerSnapshotDetails");
const clubsPlayerYearRows = document.getElementById("clubsPlayerYearRows");
const clubsPlayerClubRows = document.getElementById("clubsPlayerClubRows");

let authData = null;
let dashboardData = null;
const clubDashboardCache = new Map();

async function loadClubDirectoryFallback() {
  try {
    const options = await getJson("/api/auth/options", false);
    return options?.clubs || [];
  } catch {
    return [];
  }
}

function currentMemberName() {
  const authName = String(authData?.user?.display_name || "").trim();
  const authEmail = String(authData?.user?.email || "").trim().toLowerCase();
  const authMobile = String(authData?.user?.mobile || "").trim().toLowerCase();
  const members = dashboardData?.all_members || dashboardData?.members || [];
  const memberId = authData?.user?.member_id || "";
  const viewerHints = new Set([authName.toLowerCase(), authEmail, authMobile].filter(Boolean));
  const match = members.find((member) => {
    if (member.id === memberId) return true;
    if (viewerHints.has(String(member.name || "").trim().toLowerCase())) return true;
    if (viewerHints.has(String(member.full_name || "").trim().toLowerCase())) return true;
    if (viewerHints.has(String(member.phone || "").trim().toLowerCase())) return true;
    if (viewerHints.has(String(member.email || "").trim().toLowerCase())) return true;
    return (member.aliases || []).some((alias) => viewerHints.has(String(alias || "").trim().toLowerCase()));
  });
  return match?.name || authName || "";
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
    for (const performance of archive.suggested_performances || []) {
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
    body.innerHTML = `<tr><td colspan="16">${emptyText}</td></tr>`;
    return;
  }
  body.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${row.label}</td>
          <td>${formatCell(row.matches)}</td>
          <td>${formatCell(row.innings)}</td>
          <td>${formatCell(row.not_outs)}</td>
          <td>${formatCell(row.runs)}</td>
          <td>${row.hs ?? "—"}</td>
          <td>${formatCell(row.average, 2)}</td>
          <td>${formatCell(row.balls)}</td>
          <td>${formatCell(row.strike_rate, 2)}</td>
          <td>${formatCell(row.scores_25_plus)}</td>
          <td>${formatCell(row.fifties)}</td>
          <td>${formatCell(row.hundreds)}</td>
          <td>${formatCell(row.fours)}</td>
          <td>${formatCell(row.sixes)}</td>
          <td>${formatCell(row.catches)}</td>
          <td>${formatCell(row.stumpings)}</td>
        </tr>
      `
    )
    .join("");
}

function updatePlayerSnapshot() {
  if (!clubsPlayerSnapshotTitle || !clubsPlayerSnapshotDetails) {
    return;
  }
  const memberName = currentMemberName();
  const authName = String(authData?.user?.display_name || "").trim();
  if (!memberName) {
    clubsPlayerSnapshotTitle.textContent = "No player selected";
    clubsPlayerSnapshotDetails.textContent = "Sign in with your player profile to see your totals here.";
    return;
  }
  const members = dashboardData?.all_members || dashboardData?.members || [];
  const member = members.find((item) => {
    if (String(item.id || "") === String(authData?.user?.member_id || "")) return true;
    if (String(item.name || "").trim().toLowerCase() === memberName.toLowerCase()) return true;
    if (String(item.full_name || "").trim().toLowerCase() === memberName.toLowerCase()) return true;
    if (String(item.phone || "").trim().toLowerCase() === String(authData?.user?.mobile || "").trim().toLowerCase()) return true;
    if (String(item.email || "").trim().toLowerCase() === String(authData?.user?.email || "").trim().toLowerCase()) return true;
    return (item.aliases || []).some((alias) => String(alias || "").trim().toLowerCase() === memberName.toLowerCase());
  });
  const memberLabel = member?.full_name ? `${member.name} (${member.full_name})` : member?.name || authName || memberName;
  clubsPlayerSnapshotTitle.textContent = memberLabel;
  if (!dashboardData) {
    clubsPlayerSnapshotDetails.textContent = "Loading totals from your clubs...";
    return;
  }
  const stats =
    (dashboardData.member_summary_stats || []).find((item) => item.player_name === (member?.name || memberName)) ||
    (dashboardData.member_summary_stats || []).find((item) => String(item.player_name || "").trim().toLowerCase() === memberName.trim().toLowerCase()) ||
    dashboardData.all_combined_player_stats?.find((item) => item.player_name === (member?.name || memberName)) ||
    dashboardData.all_combined_player_stats?.find((item) => String(item.player_name || "").trim().toLowerCase() === memberName.trim().toLowerCase()) ||
    { runs: 0, wickets: 0, catches: 0 };
  const gamesPlayed = Math.max(Number(stats.matches || 0), Number(stats.games_played || 0));
  const highestScore = stats.highest_score === null || stats.highest_score === undefined ? "—" : stats.highest_score;
  const battingAverage = Number(stats.batting_average || 0);
  const strikeRate = Number(stats.strike_rate || 0);
  const details = [
    `${stats.runs || 0} runs`,
    `HS: ${highestScore}`,
    `Avg: ${Number.isFinite(battingAverage) ? battingAverage.toFixed(2).replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1") : "0"}`,
    `SR: ${Number.isFinite(strikeRate) ? strikeRate.toFixed(2).replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1") : "0"}`,
    `25+: ${stats.scores_25_plus || 0}`,
    `50+: ${stats.scores_50_plus || 0}`,
    `100+: ${stats.scores_100_plus || 0}`,
    `${stats.wickets || 0} wickets`,
    `${stats.catches || 0} catches`,
    `${gamesPlayed} games`,
  ];
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
  if (clubDashboardCache.has(clubId)) {
    return clubDashboardCache.get(clubId);
  }
  const dashboard = await getJson(`/api/dashboard?focus_club_id=${encodeURIComponent(clubId)}`, true);
  clubDashboardCache.set(clubId, dashboard);
  return dashboard;
}

async function renderPlayerBreakdowns() {
  const memberName = currentMemberName();
  const member = (dashboardData?.all_members || dashboardData?.members || []).find((item) => {
    const target = memberName.trim().toLowerCase();
    if (!target) return false;
    if (memberKey(item) === target) return true;
    if (normalizedText(item.phone) && normalizedText(item.phone) === normalizedText(authData?.user?.mobile)) return true;
    if (normalizedText(item.email) && normalizedText(item.email) === normalizedText(authData?.user?.email)) return true;
    return (item.aliases || []).some((alias) => normalizedText(alias) === target);
  });
  if (!memberName || !member) {
    renderTableRows(clubsPlayerYearRows, [], "Sign in with your player profile to see the yearly breakdown.");
    renderTableRows(clubsPlayerClubRows, [], "Sign in with your player profile to see the club breakdown.");
    return;
  }

  const yearRows = [];
  const rankingYears = dashboardData?.ranking_years || dashboardData?.season_years || [];
  const yearStats = dashboardData?.member_year_stats || [];
  for (const year of rankingYears) {
    const row =
      yearStats.find((item) => item.season_year === String(year) && item.player_name === member.name) ||
      yearStats.find((item) => item.season_year === String(year) && String(item.player_name || "").trim().toLowerCase() === memberName.trim().toLowerCase()) ||
      { runs: 0, wickets: 0, catches: 0, matches: 0, batting_innings: 0, outs: 0, batting_average: 0, strike_rate: 0, fours: 0, sixes: 0, highest_score: null };
    yearRows.push({
      label: year,
      matches: rowValue(row, "matches"),
      innings: rowValue(row, "batting_innings"),
      not_outs: Math.max(0, rowValue(row, "batting_innings") - rowValue(row, "outs")),
      runs: rowValue(row, "runs"),
      hs: rowValue(row, "highest_score") || highestScoreFor(member, { year }) || "—",
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
    });
  }
  renderTableRows(clubsPlayerYearRows, yearRows, "No yearly breakdown available yet.");

  const clubRows = [];
  const memberships = (member.club_memberships || [])
    .filter((club) => String(club.club_id || "").trim())
    .map((club) => ({ club_id: String(club.club_id || "").trim(), club_name: String(club.club_name || "").trim() || club.club_id }));
  const clubStats = dashboardData?.member_club_stats || [];
  for (const club of memberships) {
    const row =
      clubStats.find((item) => item.club_id === club.club_id && item.player_name === member.name) ||
      clubStats.find((item) => item.club_id === club.club_id && String(item.player_name || "").trim().toLowerCase() === memberName.trim().toLowerCase()) ||
      { runs: 0, wickets: 0, catches: 0, matches: 0, batting_innings: 0, outs: 0, batting_average: 0, strike_rate: 0, fours: 0, sixes: 0, highest_score: null };
    const aggregate = {
      matches: rowValue(row, "matches"),
      innings: rowValue(row, "batting_innings"),
      not_outs: Math.max(0, rowValue(row, "batting_innings") - rowValue(row, "outs")),
      runs: rowValue(row, "runs"),
      hs: rowValue(row, "highest_score") || highestScoreFor(member, { clubId: club.club_id }) || "—",
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
    const clubId = getPrimaryClubId() || authData?.user?.current_club_id || authData?.user?.primary_club_id || "";
    dashboardData = await getJson(`/api/dashboard${clubId ? `?focus_club_id=${encodeURIComponent(clubId)}` : ""}`, true);
    updatePlayerSnapshot();
    await renderPlayerBreakdowns();
  } catch {
    updatePlayerSnapshot();
    await renderPlayerBreakdowns();
  }
}

function setStatus(message, tone = "info") {
  statusBanner.hidden = !message;
  statusBanner.textContent = message || "";
  statusBanner.className = `status-banner ${tone}`;
}

function currentClub() {
  const clubId = getPrimaryClubId() || authData?.user?.current_club_id || authData?.user?.primary_club_id || "";
  return (authData?.clubs || []).find((club) => club.id === clubId) || authData?.clubs?.[0] || null;
}

function refreshLinks() {
  const club = currentClub();
  const query = club ? `?focus_club_id=${encodeURIComponent(club.id)}` : "";
  dashboardLink.href = `/dashboard${query}`;
  seasonSetupLink.href = `/season-setup${query}`;
  playerAvailabilityLink.href = `/player-availability${query}`;
  playerProfileLink.href = `/player-profile${query}`;
  selectedClubSummary.textContent = club
    ? `Current club: ${club.name} · ${club.season || "Season TBD"}`
    : "Choose a club to continue.";
}

function renderClubs() {
  const selectedId = currentClub()?.id || "";
  const query = clubSearchInput.value.trim().toLowerCase();
  const visibleClubs = (authData?.clubs || [])
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
        <article class="detail-card ${club.id === selectedId ? "active-card" : ""}">
          <strong>${club.name}</strong>
          <p>${club.season || "Season TBD"}</p>
          <small>${club.short_name || ""}</small>
          <div class="inline-actions">
            <button class="secondary-button" type="button" data-club-select="${club.id}">Select club</button>
          </div>
        </article>
      `
    )
    .join("") || `<p class="empty-state">No clubs match that search.</p>`;
}

  clubsList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-club-select]");
    if (!button) return;
    try {
      const data = await postJson("/api/auth/select-club", { club_id: button.dataset.clubSelect }, true);
      authData.user = data.user;
      setPrimaryClubId(data.user.current_club_id || data.user.primary_club_id || "");
      renderClubs();
      refreshLinks();
      setStatus(`${data.club.name} selected.`, "success");
    } catch (error) {
      setStatus(error.message, "error");
    }
  });

  signOutButton?.addEventListener("click", signOut);
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
      const signedInName = data.user.display_name || data.user.full_name || data.user.email || data.user.mobile || "Signed in";
      if (greeting) {
        greeting.textContent = `Welcome, ${signedInName}`;
      }
      if (!Array.isArray(authData.clubs) || !authData.clubs.length) {
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

window.HeartlakeClubSearch = {
  refresh: () => window.location.reload(),
};
