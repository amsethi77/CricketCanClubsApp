const { requireAuth, postJson, getPrimaryClubId, setPrimaryClubId } = window.HeartlakePages;

const title = document.getElementById("seasonSetupTitle");
const summary = document.getElementById("seasonSetupSummary");
const form = document.getElementById("seasonSetupForm");
const fixturesList = document.getElementById("seasonFixtures");
const seasonFilter = document.getElementById("seasonFilter");
const statusBanner = document.getElementById("seasonStatus");
const seasonYearInput = document.getElementById("seasonYear");

const MIN_SEASON_YEAR = 2026;

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
  const years = Array.from(
    new Set(
      [...(payload?.season_years || []), String(seasonYearInput.value || "")].filter((year) => {
        const value = Number(year);
        return Number.isFinite(value) && value >= MIN_SEASON_YEAR;
      })
    )
  ).sort();
  if (!years.length) {
    years.push(String(MIN_SEASON_YEAR));
  }
  seasonFilter.innerHTML = years.map((year) => `<option value="${year}">${year} Season</option>`).join("");
  const selectedYear = String(payload?.selected_year || years[years.length - 1] || MIN_SEASON_YEAR);
  seasonFilter.value = years.includes(selectedYear) ? selectedYear : (years[years.length - 1] || "");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const clubId = getPrimaryClubId() || payload?.club?.id || "";
    const submittedYear = String(seasonYearInput.value || MIN_SEASON_YEAR);
    if (Number(submittedYear) < MIN_SEASON_YEAR) {
      setStatus(`Season setup is only available for ${MIN_SEASON_YEAR} and later.`, "error");
      return;
    }
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
    seasonYearInput.value = submittedYear;
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
    const permissions = auth.user.permissions || [];
    if (!permissions.includes("manage_fixtures") && !permissions.includes("manage_club")) {
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
    seasonYearInput.value = Number(payload.selected_year || MIN_SEASON_YEAR);
    renderSeasonFilter();
    renderFixtures();
  })
  .catch((error) => setStatus(error.message, "error"));
