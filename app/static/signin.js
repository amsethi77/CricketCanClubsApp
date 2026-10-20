const { postJson, setAuthToken, setPrimaryClubId } = window.CricketClubAppPages;

const form = document.getElementById("signinForm");
const identifierInput = document.getElementById("signinIdentifier");
const passwordInput = document.getElementById("signinPassword");
const playerNameInput = document.getElementById("signinPlayerName");
const statusBanner = document.getElementById("signinStatus");

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
  const show = Boolean(message) && (tone === "error" || tone === "warning");
  statusBanner.hidden = !show;
  statusBanner.textContent = show ? message : "";
  statusBanner.className = `status-banner ${tone}`;
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
    // ?next=/some/page brings people back to where they were (same site only).
    const next = new URLSearchParams(window.location.search).get("next") || "";
    // Otherwise: Clubs, so people pick their club first (Amit, Oct 19). README "First page".
    window.location.href = /^\/(?![\/\\])/.test(next) ? next : "/clubs";
  } catch (error) {
    debug("Sign-in failed.", { error: error?.message || error });
    // Not found by mobile/email alone: show the player name box so they can add their name and try again.
    const quick = document.getElementById("signinQuick");
    if (quick && !passwordInput.value && !playerNameInput.value.trim()) {
      setStatus("We couldn't find you yet. Add your name as your club saved it, then tap Sign in again.", "warning");
      playerNameInput.focus();
      return;
    }
    setStatus(error.message, "error");
  }
});
