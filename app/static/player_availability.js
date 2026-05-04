const { requireAuth, postJson, getJson, getPrimaryClubId, setPrimaryClubId, optionMarkup } = window.CricketClubAppPages;

const heading = document.getElementById("availabilityPageTitle");
const summary = document.getElementById("availabilityPageSummary");
const fixturesList = document.getElementById("playerFixtures");
const statusBanner = document.getElementById("playerAvailabilityStatus");
const clubSearchInput = document.getElementById("availabilityClubSearch");
const clubSelect = document.getElementById("availabilityClubSelect");
const clubSwitchButton = document.getElementById("availabilityClubSwitch");

let payload = null;

function debug(...args) {
  if (typeof console !== "undefined" && console.debug) {
    console.debug("[Availability]", ...args);
  }
}

function setStatus(message, tone = "info") {
  const show = Boolean(message) && (tone === "error" || tone === "warning");
  statusBanner.hidden = !show;
  statusBanner.textContent = show ? message : "";
  statusBanner.className = `status-banner ${tone}`;
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

function renderFixtures() {
  if (!payload?.member) {
    fixturesList.innerHTML = `<p class="empty-state">This account is not linked to a player profile yet.</p>`;
    renderClubOptions();
    return;
  }
  const outlook = payload?.season_outlook || {};
  renderClubOptions();
  fixturesList.innerHTML = (payload.fixtures || [])
    .map((fixture) => {
      const currentStatus = fixture.availability_statuses?.[payload.member.name] || "no response";
      const currentNote = fixture.availability_notes?.[payload.member.name] || "";
      return `
        <article class="detail-card">
          <strong>${fixture.date_label} vs ${fixture.opponent}</strong>
          <p>${fixture.details?.venue || "Venue TBD"} · ${fixture.details?.scheduled_time || "Time TBD"}</p>
          <small>${fixture.date || "Date TBD"}</small>
          <small>Current status: ${currentStatus}${currentNote ? ` · ${currentNote}` : ""}</small>
          <form class="inline-actions" data-fixture-form="${fixture.id}">
            <select name="status">
              <option value="available" ${currentStatus === "available" ? "selected" : ""}>Available</option>
              <option value="maybe" ${currentStatus === "maybe" ? "selected" : ""}>Maybe</option>
              <option value="unavailable" ${currentStatus === "unavailable" ? "selected" : ""}>Unavailable</option>
            </select>
            <input type="text" name="note" value="${currentNote}" placeholder="Optional note" />
            <button class="secondary-button" type="submit">Save</button>
          </form>
        </article>
      `;
    })
    .join("") || `<p class="empty-state">No fixtures are stored yet for this club.</p>`;
}

async function loadAvailability() {
  debug("Loading availability page.");
  setStatus("Loading availability...", "info");
  payload = await getJson("/api/player/availability-data", true);
  heading.textContent = `${payload.club.name} player availability`;
  summary.textContent = payload.member
    ? `${payload.member.full_name || payload.member.name} can update availability for ${payload.fixtures.length} fixture(s) in ${payload.selected_year || "the selected season"}.`
    : "Link this account to a player profile to update availability.";
  renderFixtures();
  debug("Availability page loaded.", {
    clubId: payload.club?.id || "",
    fixtures: payload.fixtures?.length || 0,
    member: payload.member?.name || "",
  });
  setStatus(`Loaded ${payload.club.name} availability.`, "success");
}

fixturesList.addEventListener("submit", async (event) => {
  const form = event.target.closest("[data-fixture-form]");
  if (!form) return;
  event.preventDefault();
  try {
    debug("Saving availability.", {
      fixtureId: form.dataset.fixtureForm,
      playerName: payload?.member?.name || "",
      clubId: payload?.club?.id || "",
    });
    payload = await postJson(
      "/api/player/availability",
      {
        fixture_id: form.dataset.fixtureForm,
        status: form.elements.status.value,
        note: form.elements.note.value.trim(),
        club_id: payload?.club?.id || "",
      },
      true
    );
    renderFixtures();
    debug("Availability saved.", {
      fixtureId: form.dataset.fixtureForm,
      playerName: payload?.member?.name || "",
    });
    setStatus("Availability saved.", "success");
  } catch (error) {
    debug("Availability save failed.", { error: error?.message || error });
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
    await loadAvailability();
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
    await loadAvailability();
  })
  .catch((error) => setStatus(error.message, "error"));
