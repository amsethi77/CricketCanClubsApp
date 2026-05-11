const { requireAuth, postJson, getJson } = window.CricketClubAppPages;

const fixturesList = document.getElementById("playerFixtures");
const statusBanner = document.getElementById("playerAvailabilityStatus");
const selectedFixtureId = new URLSearchParams(window.location.search).get("fixture_id") || "";

let payload = null;

function statusLabel(value) {
  if (value === "available") return "Available";
  if (value === "maybe") return "Maybe";
  if (value === "unavailable") return "Not available";
  return "No response";
}

function normalizeStatus(value) {
  if (value === "available" || value === "maybe" || value === "unavailable") return value;
  return "no response";
}

function patchLocalAvailability(fixtureId, status) {
  if (!payload?.fixtures) return;
  const fixture = payload.fixtures.find((item) => String(item.id) === String(fixtureId));
  if (!fixture) return;
  fixture.availability_statuses = fixture.availability_statuses || {};
  fixture.availability_statuses[payload.member.name] = normalizeStatus(status);
}

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

function renderFixtures() {
  if (!payload?.member) {
    fixturesList.innerHTML = `<p class="empty-state">This account is not linked to a player profile yet.</p>`;
    return;
  }
  fixturesList.innerHTML = (payload.fixtures || [])
    .map((fixture) => {
      const currentStatus = fixture.availability_statuses?.[payload.member.name] || "no response";
      const selectedStatus = normalizeStatus(currentStatus);
      const highlighted = selectedFixtureId && String(fixture.id) === String(selectedFixtureId);
      return `
        <article class="detail-card availability-card ${highlighted ? "active-card" : ""}" data-fixture-availability="${fixture.id}">
          <strong>${fixture.date_label} vs ${fixture.opponent}</strong>
          <p>${fixture.details?.venue || "Venue TBD"} · ${fixture.details?.scheduled_time || "Time TBD"}</p>
          <small>${fixture.date || "Date TBD"}</small>
          <small class="availability-current-status">Current status: <span class="status-pill ${selectedStatus === "available" ? "yes" : selectedStatus === "maybe" ? "maybe" : selectedStatus === "unavailable" ? "no" : "neutral"}">${statusLabel(selectedStatus)}</span></small>
          <div class="availability-slider" role="group" aria-label="Availability selection">
            <form class="inline-actions" data-fixture-form="${fixture.id}">
              <div class="availability-quick-actions">
                <button class="status-toggle available ${selectedStatus === "available" ? "is-selected" : ""}" type="button" data-set-availability="available" aria-pressed="${selectedStatus === "available"}">Available</button>
                <button class="status-toggle maybe ${selectedStatus === "maybe" ? "is-selected" : ""}" type="button" data-set-availability="maybe" aria-pressed="${selectedStatus === "maybe"}">Maybe</button>
                <button class="status-toggle unavailable ${selectedStatus === "unavailable" ? "is-selected" : ""}" type="button" data-set-availability="unavailable" aria-pressed="${selectedStatus === "unavailable"}">Not available</button>
              </div>
            </form>
          </div>
        </article>
      `;
    })
    .join("") || `<p class="empty-state">No fixtures are stored yet for this club.</p>`;
}

async function loadAvailability() {
  debug("Loading availability page.");
  setStatus("Loading availability...", "info");
  payload = await getJson("/api/player/availability-data", true);
  renderFixtures();
  debug("Availability page loaded.", {
    clubId: payload.club?.id || "",
    fixtures: payload.fixtures?.length || 0,
    member: payload.member?.name || "",
  });
  setStatus(`Loaded ${payload.club.name} availability.`, "success");
  if (selectedFixtureId) {
    const highlightedCard = fixturesList.querySelector(`[data-fixture-availability="${CSS.escape(selectedFixtureId)}"]`);
    highlightedCard?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

fixturesList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-set-availability]");
  if (!button) return;
  const form = button.closest("[data-fixture-form]");
  if (!form) return;
  const previousStatus = payload?.fixtures?.find((item) => String(item.id) === String(form.dataset.fixtureForm))?.availability_statuses?.[payload?.member?.name || ""] || "no response";
  try {
    button.disabled = true;
    patchLocalAvailability(form.dataset.fixtureForm, button.dataset.setAvailability);
    renderFixtures();
    setStatus(`Selected ${statusLabel(button.dataset.setAvailability)} for this fixture. Saving...`, "info");
    debug("Saving availability.", {
      fixtureId: form.dataset.fixtureForm,
      playerName: payload?.member?.name || "",
      clubId: payload?.club?.id || "",
      status: button.dataset.setAvailability,
    });
    payload = await postJson(
      "/api/player/availability",
      {
        fixture_id: form.dataset.fixtureForm,
        status: button.dataset.setAvailability,
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
    patchLocalAvailability(form.dataset.fixtureForm, previousStatus);
    renderFixtures();
    debug("Availability save failed.", { error: error?.message || error });
    setStatus(error.message, "error");
  } finally {
    button.disabled = false;
  }
});

requireAuth()
  .then(async (auth) => {
    if (!auth) return;
    await loadAvailability();
  })
  .catch((error) => setStatus(error.message, "error"));
