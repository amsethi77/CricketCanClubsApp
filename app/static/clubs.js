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

if (clubsList?.dataset?.serverRendered === "true") {
  window.HeartlakeClubSearch = {
    refresh: () => window.location.reload(),
  };
} else {
  let authData = null;

  async function loadClubDirectoryFallback() {
    try {
      const options = await getJson("/api/auth/options", false);
      return options?.clubs || [];
    } catch {
      return [];
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
      if (!Array.isArray(authData.clubs) || !authData.clubs.length) {
        return loadClubDirectoryFallback().then((clubs) => {
          authData.clubs = clubs;
          greeting.textContent = `Signed in as ${data.user.display_name || data.user.email || data.user.mobile}`;
          renderClubs();
          refreshLinks();
        });
      }
      greeting.textContent = `Signed in as ${data.user.display_name || data.user.email || data.user.mobile}`;
      renderClubs();
      refreshLinks();
    })
    .catch((error) => setStatus(error.message, "error"));
}
