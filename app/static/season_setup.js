const { requireAuth, postJson, getPrimaryClubId, setPrimaryClubId } = window.CricketClubAppPages;

const title = document.getElementById("seasonSetupTitle");
const summary = document.getElementById("seasonSetupSummary");
const form = document.getElementById("seasonSetupForm");
const fixturesList = document.getElementById("seasonFixtures");
const seasonFilter = document.getElementById("seasonFilter");
const statusBanner = document.getElementById("seasonStatus");
const seasonYearInput = document.getElementById("seasonYear");
const editingFixtureIdInput = document.getElementById("editingFixtureId");
const fixtureSubmitButton = document.getElementById("fixtureSubmitButton");
const fixtureCancelEditButton = document.getElementById("fixtureCancelEditButton");

const MIN_SEASON_YEAR = 2026;

let payload = null;

function debug(...args) {
  if (typeof console !== "undefined" && console.debug) {
    console.debug("[SeasonSetup]", ...args);
  }
}

function setStatus(message, tone = "info") {
  const show = Boolean(message) && (tone === "error" || tone === "warning");
  statusBanner.hidden = !show;
  statusBanner.textContent = show ? message : "";
  statusBanner.className = `status-banner ${tone}`;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function isPastFixture(fixture) {
  const fixtureDate = String(fixture?.date || "").trim();
  if (!fixtureDate) return false;
  return fixtureDate < todayIso();
}

function resetEditMode() {
  if (editingFixtureIdInput) {
    editingFixtureIdInput.value = "";
  }
  if (fixtureSubmitButton) {
    fixtureSubmitButton.textContent = "Add fixture";
  }
  if (fixtureCancelEditButton) {
    fixtureCancelEditButton.hidden = true;
  }
}

function enterEditMode(fixture) {
  if (!fixture || isPastFixture(fixture)) {
    setStatus("Past fixtures cannot be edited.", "error");
    return;
  }
  editingFixtureIdInput.value = fixture.id || "";
  seasonYearInput.value = String(fixture.season_year || fixture.date?.slice(0, 4) || payload?.selected_year || MIN_SEASON_YEAR);
  document.getElementById("fixtureDate").value = fixture.date || "";
  document.getElementById("fixtureDateLabel").value = fixture.date_label || "";
  document.getElementById("fixtureOpponent").value = fixture.opponent || "";
  document.getElementById("fixtureVenue").value = fixture.details?.venue || "";
  document.getElementById("fixtureType").value = fixture.details?.match_type || "";
  document.getElementById("fixtureTime").value = fixture.details?.scheduled_time || "";
  document.getElementById("fixtureOvers").value = fixture.details?.overs || "";
  if (fixtureSubmitButton) {
    fixtureSubmitButton.textContent = "Update fixture";
  }
  if (fixtureCancelEditButton) {
    fixtureCancelEditButton.hidden = false;
  }
  setStatus("", "info");
}

function renderFixtures() {
  const selectedYear = String(seasonFilter.value || payload?.selected_year || seasonYearInput.value || "");
  const fixtures = (payload?.fixtures || []).filter((fixture) => {
    if (!selectedYear) return true;
    return String(fixture.season_year || String(fixture.date || "").slice(0, 4)) === selectedYear;
  });
  fixturesList.innerHTML = fixtures
    .map(
      (fixture) => {
        const locked = isPastFixture(fixture);
        return `
        <article class="detail-card">
          <strong>${fixture.date_label} vs ${fixture.opponent}</strong>
          <p>${fixture.details?.venue || "Venue TBD"} · ${fixture.details?.scheduled_time || "Time TBD"}</p>
          <small>${fixture.season || `${fixture.season_year || ""} Season`} · ${fixture.status}</small>
          <div class="inline-actions">
            <button class="secondary-button" type="button" data-fixture-edit="${fixture.id}" ${locked ? "disabled" : ""}>${locked ? "Locked" : "Edit"}</button>
          </div>
        </article>
      `;
      }
    )
    .join("") || `<p class="empty-state">No fixtures created yet for this club.</p>`;
}

function renderSeasonFilter() {
  const currentYear = String(new Date().getFullYear());
  const years = Array.from(
    new Set(
      [...(payload?.season_years || []), currentYear, String(seasonYearInput.value || ""), String(payload?.selected_year || "")].filter((year) => {
        const value = Number(year);
        return Number.isFinite(value) && value >= MIN_SEASON_YEAR;
      })
    )
  ).sort((left, right) => Number(right) - Number(left));
  if (!years.length) {
    years.push(String(MIN_SEASON_YEAR));
  }
  seasonFilter.innerHTML = years.map((year) => `<option value="${year}">${year} Season</option>`).join("");
  const selectedYear = String(payload?.selected_year || seasonYearInput.value || years[0] || MIN_SEASON_YEAR);
  seasonFilter.value = years.includes(selectedYear) ? selectedYear : (years[0] || String(MIN_SEASON_YEAR));
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const clubId = payload?.club?.id || getPrimaryClubId() || "";
    const submittedYear = String(seasonYearInput.value || MIN_SEASON_YEAR);
    if (Number(submittedYear) < MIN_SEASON_YEAR) {
      setStatus(`Season setup is only available for ${MIN_SEASON_YEAR} and later.`, "error");
      return;
    }
    const fixturePayload = {
      club_id: clubId,
      season_year: Number(submittedYear),
      date: document.getElementById("fixtureDate").value,
      date_label: document.getElementById("fixtureDateLabel").value.trim(),
      opponent: document.getElementById("fixtureOpponent").value.trim(),
      venue: document.getElementById("fixtureVenue").value.trim(),
      match_type: document.getElementById("fixtureType").value.trim(),
      scheduled_time: document.getElementById("fixtureTime").value.trim(),
      overs: document.getElementById("fixtureOvers").value.trim(),
    };
    const editingFixtureId = String(editingFixtureIdInput?.value || "").trim();
    const isEditing = Boolean(editingFixtureId);
    debug(isEditing ? "Fixture update requested." : "Fixture create requested.", { clubId, seasonYear: submittedYear, opponent: fixturePayload.opponent, fixtureId: editingFixtureId });
    setStatus(`Saving ${submittedYear} fixture for ${payload?.club?.name || "selected club"}...`, "info");
    const result = await postJson(
      isEditing
        ? `/api/admin/clubs/${encodeURIComponent(clubId)}/fixtures/${encodeURIComponent(editingFixtureId)}`
        : "/api/season-setup/fixtures",
      fixturePayload,
      true
    );
    payload = result;
    setPrimaryClubId(result.club.id);
    title.textContent = `${result.club.name} season setup`;
    summary.textContent = `Club default season ${result.club.season || "TBD"} · ${result.fixtures.length} fixture(s) stored`;
    form.reset();
    resetEditMode();
    payload.selected_year = submittedYear;
    seasonYearInput.value = submittedYear;
    renderSeasonFilter();
    renderFixtures();
    const savedCount = Array.isArray(result.fixtures) ? result.fixtures.length : 0;
    debug(isEditing ? "Fixture update completed." : "Fixture create completed.", { clubId: result.club?.id || "", seasonYear: submittedYear, savedCount });
    setStatus("", "info");
  } catch (error) {
    debug("Fixture create failed.", { error: error?.message || error });
    setStatus(error.message, "error");
  }
});

seasonFilter.addEventListener("change", renderFixtures);
fixturesList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-fixture-edit]");
  if (!button) return;
  const fixture = (payload?.fixtures || []).find((item) => item.id === button.dataset.fixtureEdit);
  if (!fixture) {
    setStatus("Fixture not found.", "error");
    return;
  }
  enterEditMode(fixture);
});

fixtureCancelEditButton?.addEventListener("click", () => {
  form.reset();
  resetEditMode();
  const fallbackYear = String(payload?.selected_year || MIN_SEASON_YEAR);
  seasonYearInput.value = fallbackYear;
  renderSeasonFilter();
  renderFixtures();
});

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
    const clubId = auth.user.current_club_id || auth.user.primary_club_id || getPrimaryClubId() || "";
    setPrimaryClubId(clubId);
    debug("Loading season setup data.", { clubId });
    setStatus("Loading season setup...", "info");
    payload = await window.CricketClubAppPages.getJson(`/api/season-setup/data${clubId ? `?club_id=${encodeURIComponent(clubId)}` : ""}`, true);
    setPrimaryClubId(payload.club.id || clubId);
    title.textContent = `${payload.club.name} season setup`;
    summary.textContent = `Club default season ${payload.club.season || "TBD"} · ${payload.fixtures.length} fixture(s) stored`;
    const activeYear = String(payload.selected_year || seasonYearInput.value || MIN_SEASON_YEAR);
    seasonYearInput.value = activeYear;
    resetEditMode();
    renderSeasonFilter();
    renderFixtures();
    debug("Season setup loaded.", { clubId: payload.club?.id || "", fixtures: payload.fixtures?.length || 0, selectedYear: payload.selected_year || "" });
    setStatus("", "info");
  })
  .catch((error) => setStatus(error.message, "error"));
