const { requireAuth, postJson, getJson, optionMarkup, setPrimaryClubId } = window.HeartlakePages;

const title = document.getElementById("playerProfileTitle");
const summary = document.getElementById("playerProfileSummary");
const statusBanner = document.getElementById("playerProfileStatus");
const form = document.getElementById("playerProfileForm");
const memberships = document.getElementById("playerMemberships");
const primaryClubSelect = document.getElementById("profilePrimaryClub");
const clubSearchInput = document.getElementById("profileClubSearch");
const clubSelect = document.getElementById("profileClubSelect");
const clubSwitchButton = document.getElementById("profileClubSwitch");
const genderSelect = document.getElementById("profileGender");

let payload = null;

function setStatus(message, tone = "info") {
  statusBanner.hidden = !message;
  statusBanner.textContent = message || "";
  statusBanner.className = `status-banner ${tone}`;
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
  summary.textContent = `Selected club: ${payload.club.name}`;
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
  renderMemberships();
}

async function loadProfile() {
  payload = await getJson("/api/player/profile-data", true);
  fillForm();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
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
    setStatus("Player profile saved.", "success");
  } catch (error) {
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
    const selected = await postJson("/api/auth/select-club", { club_id: clubSelect.value }, true);
    setPrimaryClubId(selected.user.current_club_id || selected.user.primary_club_id || "");
    await loadProfile();
    setStatus(`${selected.club.name} selected.`, "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

requireAuth()
  .then(async (auth) => {
    if (!auth) return;
    await loadProfile();
  })
  .catch((error) => setStatus(error.message, "error"));
