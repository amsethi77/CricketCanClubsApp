const { getJson, postJson, setAuthToken, setPrimaryClubId, optionMarkup } = window.HeartlakePages;

const form = document.getElementById("registerForm");
const roleSelect = document.getElementById("registerRole");
const clubSelect = document.getElementById("registerClub");
const memberSelect = document.getElementById("registerMember");
const memberRow = document.getElementById("registerMemberRow");
const statusBanner = document.getElementById("registerStatus");

function setStatus(message, tone = "info") {
  statusBanner.hidden = !message;
  statusBanner.textContent = message || "";
  statusBanner.className = `status-banner ${tone}`;
}

function syncRoleVisibility() {
  memberRow.hidden = roleSelect.value !== "player";
}

async function loadOptions() {
  const data = await getJson("/api/auth/options");
  clubSelect.innerHTML = optionMarkup(data.clubs, "id", (club) => `${club.name} · ${club.season || "Season TBD"}`);
  memberSelect.innerHTML = `<option value="">Not linked yet</option>${optionMarkup(
    data.members,
    "name",
    (member) => `${member.full_name || member.name} · ${member.team_name || "No team"}`
  )}`;
}

roleSelect.addEventListener("change", syncRoleVisibility);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    display_name: document.getElementById("registerDisplayName").value.trim(),
    mobile: document.getElementById("registerMobile").value.trim(),
    email: document.getElementById("registerEmail").value.trim(),
    password: document.getElementById("registerPassword").value,
    role: roleSelect.value,
    primary_club_id: clubSelect.value,
    member_name: memberSelect.value,
  };
  try {
    const data = await postJson("/api/auth/register", payload);
    setAuthToken(data.token);
    setPrimaryClubId(data.user.current_club_id || data.user.primary_club_id || "");
    window.location.href = "/clubs";
  } catch (error) {
    setStatus(error.message, "error");
  }
});

loadOptions().then(syncRoleVisibility).catch((error) => setStatus(error.message, "error"));
