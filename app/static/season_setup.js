const { requireAuth, postJson, getPrimaryClubId, setPrimaryClubId } = window.HeartlakePages;

const title = document.getElementById("seasonSetupTitle");
const summary = document.getElementById("seasonSetupSummary");
const form = document.getElementById("seasonSetupForm");
const fixturesList = document.getElementById("seasonFixtures");
const seasonFilter = document.getElementById("seasonFilter");
const statusBanner = document.getElementById("seasonStatus");

let payload = null;

function setStatus(message, tone = "info") {
  statusBanner.hidden = !message;
  statusBanner.textContent = message || "";
  statusBanner.className = `status-banner ${tone}`;
}

function renderFixtures() {
  const selectedYear = String(seasonFilter.value || payload?.selected_year || "");
  const fixtures = (payload?.fixtures || []).filter((fixture) => {
    if (!selectedYear) return true;
    return String(fixture.season_year || String(fixture.date || "").slice(0, 4)) === selectedYear;
  });
  fixturesList.innerHTML = fixtures
    .map(
      (fixture) => `
        <article class="detail-card">
          <strong>${fixture.date_label} vs ${fixture.opponent}</strong>
          <p>${fixture.details?.venue || "Venue TBD"} · ${fixture.details?.scheduled_time || "Time TBD"}</p>
          <small>${fixture.season || `${fixture.season_year || ""} Season`} · ${fixture.status}</small>
        </article>
      `
    )
    .join("") || `<p class="empty-state">No fixtures created yet for this club.</p>`;
}

function renderSeasonFilter() {
  const years = Array.from(new Set([...(payload?.season_years || []), String(document.getElementById("seasonYear").value || "")].filter(Boolean))).sort();
  seasonFilter.innerHTML = years.map((year) => `<option value="${year}">${year} Season</option>`).join("");
  seasonFilter.value = String(payload?.selected_year || years[years.length - 1] || "");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const clubId = getPrimaryClubId() || payload?.club?.id || "";
    const submittedYear = String(document.getElementById("seasonYear").value);
    const result = await postJson(
      "/api/season-setup/fixtures",
      {
        club_id: clubId,
        season_year: Number(submittedYear),
        date: document.getElementById("fixtureDate").value,
        date_label: document.getElementById("fixtureDateLabel").value.trim(),
        opponent: document.getElementById("fixtureOpponent").value.trim(),
        venue: document.getElementById("fixtureVenue").value.trim(),
        match_type: document.getElementById("fixtureType").value.trim(),
        scheduled_time: document.getElementById("fixtureTime").value.trim(),
        overs: document.getElementById("fixtureOvers").value.trim(),
      },
      true
    );
    payload = result;
    setPrimaryClubId(result.club.id);
    title.textContent = `${result.club.name} season setup`;
    summary.textContent = `Club default season ${result.club.season || "TBD"} · ${result.fixtures.length} fixture(s) stored`;
    form.reset();
    payload.selected_year = submittedYear;
    document.getElementById("seasonYear").value = submittedYear;
    renderSeasonFilter();
    renderFixtures();
    setStatus("Fixture added.", "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
});

seasonFilter.addEventListener("change", renderFixtures);

requireAuth()
  .then(async (auth) => {
    if (!auth) return;
    if ((auth.user.role || "player") !== "club_admin") {
      setStatus("Only club administrators can set schedules.", "error");
      form.querySelectorAll("input, button").forEach((element) => {
        element.disabled = true;
      });
      return;
    }
    const clubId = getPrimaryClubId() || auth.user.current_club_id || auth.user.primary_club_id || "";
    setPrimaryClubId(clubId);
    payload = await window.HeartlakePages.getJson("/api/season-setup/data", true);
    title.textContent = `${payload.club.name} season setup`;
    summary.textContent = `Club default season ${payload.club.season || "TBD"} · ${payload.fixtures.length} fixture(s) stored`;
    document.getElementById("seasonYear").value = Number(payload.selected_year || String(payload.club.season || "").match(/20\d{2}/)?.[0] || new Date().getFullYear());
    renderSeasonFilter();
    renderFixtures();
  })
  .catch((error) => setStatus(error.message, "error"));
