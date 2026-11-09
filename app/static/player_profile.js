const { requireAuth, postJson, getJson } = window.CricketClubAppPages;

const title = document.getElementById("playerProfileTitle");
const summary = document.getElementById("playerProfileSummary");
const statusBanner = document.getElementById("playerProfileStatus");
const form = document.getElementById("playerProfileForm");
const memberships = document.getElementById("playerMemberships");
const snapshot = document.getElementById("playerProfileSnapshot");
const matchHistory = document.getElementById("playerMatchHistory");
const genderSelect = document.getElementById("profileGender");

let payload = null;

function debug(...args) {
  if (typeof console !== "undefined" && console.debug) {
    console.debug("[PlayerProfile]", ...args);
  }
}

function setStatus(message, tone = "info") {
  const show = Boolean(message) && (tone === "error" || tone === "warning");
  statusBanner.hidden = !show;
  statusBanner.textContent = show ? message : "";
  statusBanner.className = `status-banner ${tone}`;
}

function formatValue(value, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function summaryCard(label, value, note = "") {
  return `
    <article class="summary-card">
      <span>${label}</span>
      <strong>${formatValue(value)}</strong>
      ${note ? `<p>${note}</p>` : ""}
    </article>
  `;
}

function renderMemberships() {
  const member = payload?.member;
  if (!member) {
    memberships.innerHTML = `<p class="empty-state">This account is not linked to a player profile yet.</p>`;
    return;
  }
  const clubMemberships = member.club_memberships || [];
  memberships.innerHTML =
    clubMemberships
      .map(
        (club) => `
          <article class="detail-card">
            <strong>${club.club_name}</strong>
            <p>${(club.teams || []).filter((team) => team && team !== club.club_name).join(", ") || "No teams listed"}</p>
          </article>
        `
      )
      .join("") || `<p class="empty-state">No club memberships found yet.</p>`;
}

function renderSnapshot() {
  const member = payload?.member;
  if (!member) {
    snapshot.innerHTML = `<p class="empty-state">No player profile is linked to this account yet.</p>`;
    return;
  }
  const stats = payload?.summary_stats || {};
  const clubsLabel = (member.club_memberships || []).map((club) => club.club_name).filter(Boolean).join(", ") || "No clubs stored";
  const teamsLabel = [...new Set((member.team_memberships || []).map((item) => item.display_name || item.team_name || item).filter((v) => typeof v === "string" && v))].join(", ") || "No teams stored";
  snapshot.innerHTML = [
    summaryCard("Player ID", member.player_id || "Pending"),
    summaryCard("Full Name", member.full_name || member.name || "Player"),
    summaryCard("Date of Birth", member.date_of_birth || "Not provided"),
    summaryCard("Mobile", member.phone || "No mobile stored"),
    summaryCard("Email", member.email || "No email stored"),
    summaryCard("Age", member.age || "TBD"),
    summaryCard("Role", member.role || "Player"),
    summaryCard("Primary Club", payload?.club?.name || "Unassigned"),
    summaryCard("Clubs", clubsLabel),
    summaryCard("Teams", teamsLabel),
    summaryCard(
      "Season Runs",
      stats.runs || 0,
      `${stats.matches || 0} matches · Avg ${stats.batting_average ?? 0} · SR ${stats.strike_rate ?? 0}`
    ),
    summaryCard(
      "Season Wickets",
      stats.wickets || 0,
      `${stats.catches || 0} catches · HS ${stats.highest_score ?? "—"}`
    ),
    summaryCard(
      "Aliases",
      (member.aliases || []).join(", ") || "No aliases stored",
      "Alias matching keeps duplicate spellings tied to the same player."
    ),
    summaryCard(
      "Notes",
      member.notes || "No extra notes stored",
      member.gender ? `Gender: ${member.gender}` : "No gender recorded"
    ),
  ].join("");
}

function renderMatchHistory() {
  const rows = payload?.recent_history || [];
  if (!rows.length) {
    matchHistory.innerHTML = `<tr><td colspan="9" class="empty-state">No match history found yet for this player.</td></tr>`;
    return;
  }
  matchHistory.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${formatValue(row.date)}</td>
          <td>${formatValue(row.source)}</td>
          <td>${formatValue(row.club_name)}</td>
          <td>${formatValue(row.opponent)}</td>
          <td>${formatValue(row.runs, "0")}</td>
          <td>${formatValue(row.balls, "0")}</td>
          <td>${formatValue(row.wickets, "0")}</td>
          <td>${formatValue(row.catches, "0")}</td>
          <td>${formatValue(row.result || row.status || "—")}</td>
        </tr>
      `
    )
    .join("");
}

function fillForm() {
  const member = payload?.member;
  if (!member) return;
  title.textContent = `${member.full_name || member.name} profile`;
  title.hidden = false;
  summary.textContent = `Selected club: ${payload?.club?.name || "Selected club"} · ${member.role || "Player"} · ${member.phone || "No mobile stored"}`;
  summary.hidden = false;
  document.getElementById("profileFullName").value = member.full_name || "";
  document.getElementById("profilePlayerId").value = member.player_id || "";
  document.getElementById("profileDateOfBirth").value = member.date_of_birth || "";
  genderSelect.value = member.gender || "";
  document.getElementById("profileAge").value = member.age || "";
  document.getElementById("profilePhone").value = member.phone || "";
  document.getElementById("profileEmail").value = member.email || "";
  document.getElementById("profileRole").value = member.role || "";
  document.getElementById("profileBattingStyle").value = member.batting_style || "";
  document.getElementById("profileBowlingStyle").value = member.bowling_style || "";
  document.getElementById("profileAliases").value = (member.aliases || []).join(", ");
  // Nov 4 2026: show every club the player belongs to (it used to hide club links and show only typed names)
  document.getElementById("profileTeams").value = [...new Set((member.club_memberships || []).map((club) => club.club_name).filter(Boolean))].join(", ");
  document.getElementById("profileNotes").value = member.notes || "";
  renderSnapshot();
  renderMatchHistory();
  renderMemberships();
}

async function loadProfile(auth = null) {
  debug("Loading player profile.");
  setStatus("Loading player profile...", "info");
  title.textContent = "Loading player profile...";
  title.hidden = false;
  summary.textContent = "Loading selected club and player data...";
  summary.hidden = false;
  if (!auth) return;
  try {
    payload = await getJson("/api/player/summary", true);
    fillForm();
    debug("Player profile loaded.", {
      clubId: payload.club?.id || "",
      member: payload.member?.name || "",
      summaryRuns: payload.summary_stats?.runs || 0,
    });
    setStatus(`Loaded ${payload.member?.full_name || payload.member?.name || "player"} profile.`, "success");
  } catch (error) {
    debug("Player profile load failed.", { error: error?.message || error });
    setStatus(error.message || "Player profile could not be loaded.", "error");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    debug("Saving player profile.", {
      player: document.getElementById("profileFullName").value.trim(),
      clubId: payload?.club?.id || "",
    });
    payload = await postJson(
      "/api/player/profile",
      {
        full_name: document.getElementById("profileFullName").value.trim(),
        gender: genderSelect.value,
        age: Number(document.getElementById("profileAge").value || 0),
        date_of_birth: document.getElementById("profileDateOfBirth").value || "",
        phone: document.getElementById("profilePhone").value.trim(),
        email: document.getElementById("profileEmail").value.trim(),
        role: document.getElementById("profileRole").value.trim(),
        batting_style: document.getElementById("profileBattingStyle").value.trim(),
        bowling_style: document.getElementById("profileBowlingStyle").value.trim(),
        aliases: document.getElementById("profileAliases").value.trim(),
        team_memberships: document.getElementById("profileTeams").value.trim(),
        notes: document.getElementById("profileNotes").value.trim(),
      },
      true
    );
    fillForm();
    debug("Player profile saved.", {
      player: payload?.member?.name || document.getElementById("profileFullName").value.trim(),
      clubId: payload?.club?.id || "",
    });
    setStatus("Player profile saved.", "success");
  } catch (error) {
    debug("Player profile save failed.", { error: error?.message || error });
    setStatus(error.message, "error");
  }
});

requireAuth()
  .then(async (auth) => {
    if (!auth) return;
    await loadProfile(auth);
  })
  .catch((error) => setStatus(error.message, "error"));


// Nov 7 2026 (Amit: "players in their profile page should be shown matching names and asked to merge"):
// GET /api/player/name-suggestions lists names on scorecards that look like this player; "This is me" calls
// POST /api/player/name-suggestions/claim, which adds the name to his aliases (and merges an unclaimed duplicate).
(function nameMatches() {
  const box = document.getElementById("playerNameMatches");
  if (!box) return;
  const list = box.querySelector("[data-name-list]");
  const msg = box.querySelector("[data-name-msg]");
  const token = () => {
    try {
      return localStorage.getItem("cricketClubAppAuthToken") || "";
    } catch (error) {
      return "";
    }
  };
  const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const hiddenKey = "cricketClubAppNotMeNames";
  const notMe = () => {
    try {
      return JSON.parse(localStorage.getItem(hiddenKey) || "[]");
    } catch (error) {
      return [];
    }
  };
  async function load() {
    if (!token()) return;
    const response = await fetch("/api/player/name-suggestions", { headers: { "X-Auth-Token": token() } }).catch(() => null);
    if (!response || !response.ok) return;
    const data = await response.json();
    const skip = new Set(notMe().map((n) => String(n).toLowerCase()));
    const items = (data.suggestions || []).filter((item) => !skip.has(String(item.name).toLowerCase()));
    if (!items.length) {
      box.hidden = true;
      return;
    }
    list.innerHTML = items
      .map(
        (item) => `<div class="detail-card" data-name="${esc(item.name)}">
          <strong>${esc(item.name)}</strong>
          <p class="lede">${item.cards.length} scorecard${item.cards.length === 1 ? "" : "s"}: ${item.cards
            .slice(0, 3)
            .map((c) => `<a href="/scorecards/${encodeURIComponent(c.id)}">${esc(c.date || "")} ${esc(c.title || "")}</a>${c.detail ? ` (${esc(c.detail)})` : ""}`)
            .join(" · ")}</p>
          <button type="button" class="primary-button" data-claim>This is me</button>
          <button type="button" class="secondary-button" data-not-me>Not me</button>
        </div>`
      )
      .join("");
    box.hidden = false;
  }
  list.addEventListener("click", async (event) => {
    const card = event.target.closest("[data-name]");
    if (!card) return;
    const name = card.dataset.name;
    if (event.target.closest("[data-not-me]")) {
      localStorage.setItem(hiddenKey, JSON.stringify([...notMe(), name]));
      card.remove();
      if (!list.children.length) box.hidden = true;
      return;
    }
    if (!event.target.closest("[data-claim]")) return;
    msg.textContent = "Saving…";
    const response = await fetch("/api/player/name-suggestions/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Auth-Token": token() },
      body: JSON.stringify({ name }),
    }).catch(() => null);
    const data = response ? await response.json().catch(() => ({})) : {};
    msg.textContent = response && response.ok ? data.message : data.detail || "Couldn't save it. Please try again.";
    if (response && response.ok) {
      card.remove();
      const aliases = document.getElementById("profileAliases");
      if (aliases && data.aliases) aliases.value = data.aliases.join(", ");
      if (!list.children.length) box.hidden = true;
    }
  });
  load();
})();
