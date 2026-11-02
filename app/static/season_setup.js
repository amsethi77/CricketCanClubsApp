const { requireAuth, postJson, deleteJson, setPrimaryClubId } = window.CricketClubAppPages;

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
let canManageFixtures = false;

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

function isCompletedFixture(fixture) {
  const status = String(fixture?.status || "").trim().toLowerCase();
  const results = [fixture?.result, fixture?.scorecard?.result].map((value) => String(value || "").trim().toLowerCase());
  if (
    ["complete", "completed", "finished", "final"].includes(status) ||
    results.some((result) => result && !["tbd", "to be determined", "pending", "not recorded", "in progress", "ongoing"].includes(result))
  ) {
    return true;
  }
  const innings = fixture?.scorebook?.innings || [];
  const completedInnings = innings.map((inning) => String(inning?.status || "").trim().toLowerCase());
  return completedInnings.length >= 2 && completedInnings.every((inningsStatus) => ["complete", "completed", "finished"].includes(inningsStatus));
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
        const completed = isCompletedFixture(fixture);
        const canDelete = Boolean(fixture.can_delete_incomplete) && !completed;
        return `
        <article class="detail-card">
          <strong>${fixture.date_label} vs ${fixture.opponent}</strong>
          <p>${fixture.details?.venue || "Venue TBD"} · ${fixture.details?.scheduled_time || "Time TBD"}</p>
          <small>${fixture.season || `${fixture.season_year || ""} Season`} · ${fixture.status}</small>
          <div class="inline-actions">
            ${canManageFixtures ? `<button class="secondary-button" type="button" data-fixture-edit="${fixture.id}" ${locked ? "disabled" : ""}>${locked ? "Locked" : "Edit"}</button>` : ""}
            ${canDelete ? `<button class="secondary-button" type="button" data-fixture-delete="${fixture.id}">Delete incomplete game</button>` : completed ? `<span>Completed game — kept in scorecards</span>` : ""}
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
      [
        ...(payload?.season_years || []),
        currentYear,
        String(seasonYearInput.value || ""),
        String(payload?.selected_year || ""),
      ].filter((year) => /^20\d{2}$/.test(String(year || "").trim()))
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
    const clubId = payload?.club?.id || "";
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
    setStatus(
      isEditing
        ? `Updated ${fixturePayload.date_label || fixturePayload.date} for ${fixturePayload.opponent || "selected club"}.`
        : `Created ${fixturePayload.date_label || fixturePayload.date} for ${fixturePayload.opponent || "selected club"}.`,
      "success"
    );
  } catch (error) {
    debug("Fixture create failed.", { error: error?.message || error });
    setStatus(error.message, "error");
  }
});

seasonFilter.addEventListener("change", renderFixtures);
fixturesList.addEventListener("click", (event) => {
  const deleteButton = event.target.closest("[data-fixture-delete]");
  if (deleteButton) {
    const fixture = (payload?.fixtures || []).find((item) => item.id === deleteButton.dataset.fixtureDelete);
    if (!fixture || !fixture.can_delete_incomplete || isCompletedFixture(fixture)) {
      setStatus("Only a club captain, club admin, or superadmin can delete an incomplete game in their club.", "error");
      return;
    }
    if (!window.confirm(`Delete incomplete game ${fixture.date_label || fixture.date} vs ${fixture.opponent}?`)) return;
    deleteJson(
      `/api/admin/clubs/${encodeURIComponent(payload.club.id)}/fixtures/${encodeURIComponent(fixture.id)}`,
      true
    )
      .then((result) => {
        payload = result;
        form.reset();
        resetEditMode();
        renderSeasonFilter();
        renderFixtures();
        summary.textContent = `Club default season ${result.club.season || "TBD"} · ${result.fixtures.length} fixture(s) stored`;
        setStatus("Incomplete game deleted.", "success");
      })
      .catch((error) => setStatus(error.message, "error"));
    return;
  }
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
    canManageFixtures = permissions.includes("manage_fixtures") || permissions.includes("manage_club");
    const canViewAndDelete = canManageFixtures || permissions.includes("score_matches");
    if (!canViewAndDelete) {
      form.hidden = true;
      setStatus("Only club captains, club admins, or superadmins can manage incomplete fixtures.", "error");
      return;
    }
    form.hidden = !canManageFixtures;
    const clubId = auth.user.current_club_id || auth.user.primary_club_id || "";
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
