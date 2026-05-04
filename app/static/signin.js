const { getJson, postJson, setAuthToken, setPrimaryClubId } = window.CricketClubAppPages;

const form = document.getElementById("signinForm");
const identifierInput = document.getElementById("signinIdentifier");
const passwordInput = document.getElementById("signinPassword");
const playerNameInput = document.getElementById("signinPlayerName");
const statusBanner = document.getElementById("signinStatus");
const batsmenCount = document.getElementById("signinBatsmenCount");
const bowlersCount = document.getElementById("signinBowlersCount");
const clubsCount = document.getElementById("signinClubsCount");
const topBatsmen = document.getElementById("signinTopBatsmen");
const topBowlers = document.getElementById("signinTopBowlers");
const topClubs = document.getElementById("signinTopClubs");

function debug(...args) {
  if (typeof console !== "undefined" && console.debug) {
    console.debug("[Signin]", ...args);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setStatus(message, tone = "info") {
  statusBanner.hidden = !message;
  statusBanner.textContent = message || "";
  statusBanner.className = `status-banner ${tone}`;
}

function formatNumber(value, digits = 0) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "0";
  if (digits > 0) return number.toFixed(digits).replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1");
  return String(Math.round(number));
}

function renderLeaderItems(container, rows, renderRow, emptyLabel) {
  if (!container) return;
  if (!rows || !rows.length) {
    container.innerHTML = `<div class="signin-empty">${escapeHtml(emptyLabel)}</div>`;
    return;
  }
  container.innerHTML = rows.map(renderRow).join("");
}

function renderBatsmen(rows) {
  renderLeaderItems(
    topBatsmen,
    rows,
    (row, index) => `
      <div class="signin-leader-row">
        <span class="signin-rank">${index + 1}</span>
        <div class="signin-leader-copy">
          <strong>${escapeHtml(row.player_name || "Player")}</strong>
          <small>${formatNumber(row.runs)} runs · ${formatNumber(row.batting_average, 1)} avg · ${formatNumber(row.matches)} matches</small>
        </div>
      </div>
    `,
    "No batting leaders yet.",
  );
}

function renderBowlers(rows) {
  renderLeaderItems(
    topBowlers,
    rows,
    (row, index) => `
      <div class="signin-leader-row">
        <span class="signin-rank">${index + 1}</span>
        <div class="signin-leader-copy">
          <strong>${escapeHtml(row.player_name || "Player")}</strong>
          <small>${formatNumber(row.wickets)} wickets · ${formatNumber(row.wickets_per_match, 1)} wickets/match · ${formatNumber(row.matches)} matches</small>
        </div>
      </div>
    `,
    "No bowling leaders yet.",
  );
}

function renderClubs(rows) {
  if (!topClubs) return;
  if (!rows || !rows.length) {
    topClubs.innerHTML = '<div class="signin-empty">No club results yet.</div>';
    return;
  }
  topClubs.innerHTML = rows
    .map(
      (row, index) => `
        <div class="signin-club-row">
          <div class="signin-club-head">
            <span class="signin-rank">${index + 1}</span>
            <div class="signin-leader-copy">
              <strong>${escapeHtml(row.club_name || "Club")}</strong>
              <small>${formatNumber(row.matches_won)} won · ${formatNumber(row.matches_played)} played</small>
            </div>
          </div>
          <span class="signin-widget-pill">${formatNumber((Number(row.win_rate || 0) * 100), 0)}%</span>
        </div>
      `,
    )
    .join("");
}

async function loadLeagueLeaders() {
  try {
    debug("Loading sign-in leaders.");
    setStatus("Loading league leaders...", "info");
    const data = await getJson("/api/public/signin-stats");
    const batting = data.batting_leaders || [];
    const bowling = data.bowling_leaders || [];
    const clubs = data.club_leaders || [];
    batsmenCount.textContent = `${batting.length} shown`;
    bowlersCount.textContent = `${bowling.length} shown`;
    clubsCount.textContent = `${clubs.length} shown`;
    renderBatsmen(batting);
    renderBowlers(bowling);
    renderClubs(clubs);
    debug("Sign-in leaders loaded.", { batsmen: batting.length, bowlers: bowling.length, clubs: clubs.length });
    setStatus("League leaders loaded.", "success");
  } catch (error) {
    if (batsmenCount) batsmenCount.textContent = "Unavailable";
    if (bowlersCount) bowlersCount.textContent = "Unavailable";
    if (clubsCount) clubsCount.textContent = "Unavailable";
    renderBatsmen([]);
    renderBowlers([]);
    renderClubs([]);
    setStatus("League leaders could not be loaded right now.", "error");
    debug("Failed to load league leaders.", { error: error?.message || error });
    console.error("[Signin] Failed to load league leaders", error);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    debug("Sign-in submitted.", {
      hasIdentifier: Boolean(identifierInput.value.trim()),
      hasPassword: Boolean(passwordInput.value),
      hasPlayerName: Boolean(playerNameInput.value.trim()),
    });
    setStatus("Signing in...", "info");
    const data = await postJson("/api/auth/signin", {
      identifier: identifierInput.value.trim(),
      password: passwordInput.value,
      player_name: playerNameInput.value.trim(),
    });
    setAuthToken(data.token);
    setPrimaryClubId(data.user.current_club_id || data.user.primary_club_id || "");
    if (data.session) {
      window.sessionStorage.setItem("cricketClubAppSessionState", JSON.stringify(data.session));
    }
    debug("Sign-in completed.", {
      user: data.user?.display_name || data.user?.full_name || data.user?.mobile || "",
      clubId: data.user?.current_club_id || data.user?.primary_club_id || "",
    });
    window.location.href = "/clubs";
  } catch (error) {
    debug("Sign-in failed.", { error: error?.message || error });
    setStatus(error.message, "error");
  }
});

loadLeagueLeaders();
