const { requireAuth, postJson, getJson, optionMarkup, setPrimaryClubId, getPrimaryClubId } = window.CricketClubAppPages;

const title = document.getElementById("playerProfileTitle");
const summary = document.getElementById("playerProfileSummary");
const statusBanner = document.getElementById("playerProfileStatus");
const form = document.getElementById("playerProfileForm");
const memberships = document.getElementById("playerMemberships");
const snapshot = document.getElementById("playerProfileSnapshot");
const matchHistory = document.getElementById("playerMatchHistory");
const primaryClubSelect = document.getElementById("profilePrimaryClub");
const clubSearchInput = document.getElementById("profileClubSearch");
const clubSelect = document.getElementById("profileClubSelect");
const clubSwitchButton = document.getElementById("profileClubSwitch");
const genderSelect = document.getElementById("profileGender");

let payload = null;

function debug(...args) {
  if (typeof console !== "undefined" && console.debug) {
    console.debug("[PlayerProfile]", ...args);
  }
}

function setStatus(message, tone = "info") {
  statusBanner.hidden = !message;
  statusBanner.textContent = message || "";
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
  const teamsLabel = (member.team_memberships || [])
    .map((item) => item.team_name || item)
    .filter(Boolean)
    .join(", ") || "No teams stored";
  snapshot.innerHTML = [
    summaryCard("Full Name", member.full_name || member.name || "Player"),
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

function renderClubOptions() {
  const clubs = payload?.clubs || [];
  const query = clubSearchInput.value.trim().toLowerCase();
  const selectedClubId = payload?.club?.id || "";
  const visibleClubs = clubs.filter((club) => {
    if (!query) return true;
    return [club.name, club.short_name, club.season].some((value) => String(value || "").toLowerCase().includes(query));
  });
  clubSelect.innerHTML = optionMarkup(visibleClubs, "id", (club) => `${club.name} · ${club.season || "Season TBD"}`);
  clubSelect.value = visibleClubs.some((club) => club.id === selectedClubId)
    ? selectedClubId
    : visibleClubs[0]?.id || "";
}

function fillForm() {
  const member = payload?.member;
  if (!member) return;
  title.textContent = `${member.full_name || member.name} profile`;
  summary.textContent = `Selected club: ${payload.club.name} · ${member.role || "Player"} · ${member.phone || "No mobile stored"}`;
  document.getElementById("profileFullName").value = member.full_name || "";
  genderSelect.value = member.gender || "";
  document.getElementById("profileAge").value = member.age || "";
  document.getElementById("profilePhone").value = member.phone || "";
  document.getElementById("profileEmail").value = member.email || "";
  document.getElementById("profileRole").value = member.role || "";
  document.getElementById("profileBattingStyle").value = member.batting_style || "";
  document.getElementById("profileBowlingStyle").value = member.bowling_style || "";
  document.getElementById("profileAliases").value = (member.aliases || []).join(", ");
  document.getElementById("profileTeams").value = (member.team_memberships || [])
    .filter((item) => (item.team_type || "") !== "club")
    .map((item) => item.team_name || item)
    .join(", ");
  document.getElementById("profileNotes").value = member.notes || "";
  primaryClubSelect.innerHTML = optionMarkup(payload.clubs || [], "id", (club) => club.name);
  primaryClubSelect.value = payload.club.id || payload.user.current_club_id || payload.user.primary_club_id || "";
  renderClubOptions();
  renderSnapshot();
  renderMatchHistory();
  renderMemberships();
}

async function loadProfile() {
  debug("Loading player profile.");
  setStatus("Loading player profile...", "info");
  payload = await getJson("/api/player/profile-data", true);
  fillForm();
  debug("Player profile loaded.", {
    clubId: payload.club?.id || "",
    member: payload.member?.name || "",
    summaryRuns: payload.summary_stats?.runs || 0,
  });
  setStatus(`Loaded ${payload.member?.full_name || payload.member?.name || "player"} profile.`, "success");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    debug("Saving player profile.", {
      player: document.getElementById("profileFullName").value.trim(),
      clubId: primaryClubSelect.value || "",
    });
    payload = await postJson(
      "/api/player/profile",
      {
        full_name: document.getElementById("profileFullName").value.trim(),
        gender: genderSelect.value,
        age: Number(document.getElementById("profileAge").value || 0),
        phone: document.getElementById("profilePhone").value.trim(),
        email: document.getElementById("profileEmail").value.trim(),
        role: document.getElementById("profileRole").value.trim(),
        batting_style: document.getElementById("profileBattingStyle").value.trim(),
        bowling_style: document.getElementById("profileBowlingStyle").value.trim(),
        aliases: document.getElementById("profileAliases").value.trim(),
        team_memberships: document.getElementById("profileTeams").value.trim(),
        notes: document.getElementById("profileNotes").value.trim(),
        primary_club_id: primaryClubSelect.value,
      },
      true
    );
    fillForm();
    debug("Player profile saved.", {
      player: payload?.member?.name || document.getElementById("profileFullName").value.trim(),
      clubId: payload?.club?.id || primaryClubSelect.value || "",
    });
    setStatus("Player profile saved.", "success");
  } catch (error) {
    debug("Player profile save failed.", { error: error?.message || error });
    setStatus(error.message, "error");
  }
});

clubSearchInput.addEventListener("input", renderClubOptions);

clubSwitchButton.addEventListener("click", async () => {
  if (!clubSelect.value) {
    setStatus("Choose a club first.", "error");
    return;
  }
  try {
    debug("Club switch requested.", { clubId: clubSelect.value || "" });
    const selected = await postJson("/api/auth/select-club", { club_id: clubSelect.value }, true);
    setPrimaryClubId(selected.user.current_club_id || selected.user.primary_club_id || "");
    await loadProfile();
    debug("Club switch completed.", { clubId: selected.club?.id || "", clubName: selected.club?.name || "" });
    setStatus(`${selected.club.name} selected.`, "success");
  } catch (error) {
    debug("Club switch failed.", { error: error?.message || error });
    setStatus(error.message, "error");
  }
});

requireAuth()
  .then(async (auth) => {
    if (!auth) return;
    const clubId = auth.user.current_club_id || auth.user.primary_club_id || getPrimaryClubId() || "";
    setPrimaryClubId(clubId);
    await loadProfile();
  })
  .catch((error) => setStatus(error.message, "error"));
