const { postJson, setAuthToken, setPrimaryClubId } = window.HeartlakePages;

const form = document.getElementById("signinForm");
const identifierInput = document.getElementById("signinIdentifier");
const passwordInput = document.getElementById("signinPassword");
const playerNameInput = document.getElementById("signinPlayerName");
const statusBanner = document.getElementById("signinStatus");

function setStatus(message, tone = "info") {
  statusBanner.hidden = !message;
  statusBanner.textContent = message || "";
  statusBanner.className = `status-banner ${tone}`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = await postJson("/api/auth/signin", {
      identifier: identifierInput.value.trim(),
      password: passwordInput.value,
      player_name: playerNameInput.value.trim(),
    });
    setAuthToken(data.token);
    setPrimaryClubId(data.user.current_club_id || data.user.primary_club_id || "");
    window.location.href = "/clubs";
  } catch (error) {
    setStatus(error.message, "error");
  }
});
