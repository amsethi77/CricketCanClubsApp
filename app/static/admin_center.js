const { requireAuth, getJson, postJson, putJson, deleteJson, setPrimaryClubId, optionMarkup } = window.HeartlakePages;

const statusBanner = document.getElementById("adminCenterStatus");
const clubSelect = document.getElementById("adminClubSelect");
const loadClubButton = document.getElementById("adminLoadClubButton");
const clubStats = document.getElementById("adminClubStats");
const clubDetail = document.getElementById("adminClubDetail");
const fixtureForm = document.getElementById("adminFixtureForm");
const fixtureIdInput = document.getElementById("adminFixtureId");
const fixtureDateLabelInput = document.getElementById("adminFixtureDateLabel");
const fixtureDateInput = document.getElementById("adminFixtureDate");
const fixtureOpponentInput = document.getElementById("adminFixtureOpponent");
const fixtureVenueInput = document.getElementById("adminFixtureVenue");
const fixtureTypeInput = document.getElementById("adminFixtureType");
const fixtureTimeInput = document.getElementById("adminFixtureTime");
const fixtureOversInput = document.getElementById("adminFixtureOvers");
const fixtureYearInput = document.getElementById("adminSeasonYear");
const fixtureList = document.getElementById("adminFixtureList");
const archiveSearchInput = document.getElementById("adminArchiveSearch");
const refreshButton = document.getElementById("adminRefreshButton");
const archiveQueue = document.getElementById("adminReviewQueue");

let payload = null;
let auth = null;
let reviewQueue = [];

function setStatus(message, tone = "info") {
  if (!statusBanner) return;
  statusBanner.hidden = !message;
  statusBanner.textContent = message || "";
  statusBanner.className = `status-banner ${tone}`;
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function clubId() {
  return clubSelect?.value || auth?.user?.current_club_id || auth?.user?.primary_club_id || "";
}

function availableClubs(dashboard = payload) {
  const authClubs = Array.isArray(auth?.clubs) ? auth.clubs : [];
  if (authClubs.length) {
    return authClubs;
  }
  return Array.isArray(dashboard?.clubs) ? dashboard.clubs : [];
}

function selectedClub() {
  const clubs = availableClubs();
  return clubs.find((club) => club.id === clubId()) || clubs[0] || null;
}

function selectedClubKeys(dashboard = payload) {
  const club = dashboard?.club || dashboard?.focus_club || selectedClub() || {};
  const clubIdValue = String(club.id || club.club_id || "").trim().toLowerCase();
  const clubNameValue = String(club.name || "").trim().toLowerCase();
  const clubShortNameValue = String(club.short_name || "").trim().toLowerCase();
  return { clubIdValue, clubNameValue, clubShortNameValue };
}

function archiveBelongsToSelectedClub(upload, dashboard = payload) {
  const { clubIdValue, clubNameValue, clubShortNameValue } = selectedClubKeys(dashboard);
  if (!clubIdValue && !clubNameValue && !clubShortNameValue) {
    return true;
  }
  const resolvedClubId = String(upload.resolved_club_id || upload.club_id || "").trim().toLowerCase();
  const resolvedClubName = String(upload.resolved_club_name || upload.club_name || "").trim().toLowerCase();
  if (clubIdValue) {
    return resolvedClubId === clubIdValue;
  }
  return (
    (clubNameValue && (resolvedClubName === clubNameValue || resolvedClubName === clubShortNameValue)) ||
    (clubShortNameValue && resolvedClubName === clubShortNameValue)
  );
}

function renderClubSelect(dashboard = payload) {
  const clubs = availableClubs(dashboard);
  const current = clubId() || clubs[0]?.id || "";
  clubSelect.innerHTML = optionMarkup(clubs, "id", (club) => `${club.name} · ${club.season || "Season TBD"}`);
  clubSelect.value = current;
}

function renderClubStats(dashboard) {
  const summary = dashboard?.summary || {};
  const club = dashboard?.club || {};
  clubStats.innerHTML = `
    <article class="summary-card"><span>Selected club</span><strong>${escapeHtml(club.name || "TBD")}</strong></article>
    <article class="summary-card"><span>Members</span><strong>${summary.member_count || 0}</strong></article>
    <article class="summary-card"><span>Teams</span><strong>${summary.team_count || 0}</strong></article>
    <article class="summary-card"><span>Fixtures</span><strong>${summary.fixture_count || 0}</strong></article>
    <article class="summary-card"><span>Archives</span><strong>${summary.archive_count || 0}</strong></article>
    <article class="summary-card"><span>Top Batter</span><strong>${escapeHtml(summary.top_batter || "TBD")}</strong><p>${summary.top_batter_runs || 0} runs</p></article>
  `;
}

function renderClubDetail(dashboard) {
  const club = dashboard?.club || {};
  const members = dashboard?.members || [];
  const teams = dashboard?.teams || [];
  clubDetail.innerHTML = `
    <article class="detail-card">
      <strong>${escapeHtml(club.name || "Selected club")}</strong>
      <p>${escapeHtml(club.short_name || "")} · ${escapeHtml(club.season || "Season TBD")}</p>
      <small>${members.length} players · ${teams.length} teams</small>
    </article>
  `;
}

function populateFixtureForm(fixture = null) {
  fixtureIdInput.value = fixture?.id || "";
  fixtureDateLabelInput.value = fixture?.date_label || "";
  fixtureDateInput.value = fixture?.date || "";
  fixtureOpponentInput.value = fixture?.opponent || "";
  fixtureVenueInput.value = fixture?.details?.venue || "";
  fixtureTypeInput.value = fixture?.details?.match_type || "";
  fixtureTimeInput.value = fixture?.details?.scheduled_time || "";
  fixtureOversInput.value = fixture?.details?.overs || "";
  fixtureYearInput.value = Number(fixture?.season_year || fixture?.date?.slice?.(0, 4) || new Date().getFullYear());
}

function renderFixtures(dashboard) {
  const fixtures = dashboard?.fixtures || [];
  fixtureList.innerHTML = fixtures.length
    ? fixtures
        .map(
          (fixture) => `
            <article class="detail-card">
              <strong>${escapeHtml(fixture.date_label || fixture.date || "Fixture")}</strong>
              <p>${escapeHtml(fixture.opponent || "Opponent TBD")} · ${escapeHtml(fixture.status || "Scheduled")}</p>
              <small>${escapeHtml(fixture.season || fixture.season_year || "")} · ${escapeHtml(fixture.details?.venue || "Venue TBD")}</small>
              <small>Created by ${escapeHtml(fixture.created_by_user_id ?? "TBD")} · Created ${escapeHtml(fixture.created_at || "TBD")} · Updated ${escapeHtml(fixture.updated_at || "TBD")}</small>
              <div class="inline-actions">
                <button class="secondary-button" type="button" data-fixture-load="${fixture.id}">Edit</button>
                <button class="secondary-button" type="button" data-fixture-delete="${fixture.id}">Delete</button>
              </div>
            </article>
          `
        )
        .join("")
    : `<p class="empty-state">No fixtures created for this club yet.</p>`;
}

function renderArchives(dashboard, uploadsOverride = null) {
  const query = String(archiveSearchInput?.value || "").trim().toLowerCase();
  const sourceUploads = Array.isArray(uploadsOverride) ? uploadsOverride : (dashboard?.archive_uploads || []);
  const uploads = sourceUploads.filter((upload) => {
    if (!archiveBelongsToSelectedClub(upload, dashboard)) {
      return false;
    }
    if (!query) return true;
    return [
      upload.file_name,
      upload.club_name,
      upload.season,
      upload.archive_date,
      upload.archive_year,
      upload.status,
      upload.extracted_summary,
    ].some((value) => String(value || "").toLowerCase().includes(query));
  });

  if (!uploads.length) {
    archiveQueue.innerHTML = `<p class="empty-state">No archives match this club or search.</p>`;
    return;
  }

  const groups = uploads.reduce((acc, upload) => {
    const clubKey = upload.resolved_club_id || upload.club_id || "";
    const clubName = upload.resolved_club_name || upload.club_name || "Unassigned";
    const key = `${clubKey}::${clubName}`;
    if (!acc[key]) {
      acc[key] = { clubKey, clubName, uploads: [] };
    }
    acc[key].uploads.push(upload);
    return acc;
  }, {});

  const orderedGroups = Object.values(groups).sort((a, b) => {
    const left = String(a.clubName || "").toLowerCase();
    const right = String(b.clubName || "").toLowerCase();
    return left.localeCompare(right);
  });

  archiveQueue.innerHTML = orderedGroups
    .map(
      (group) => `
        <section class="admin-review-group">
          <div class="panel-head compact-head">
            <div>
              <p class="section-kicker">Club review queue</p>
              <h3>${escapeHtml(group.clubName || "Unassigned")} · ${group.uploads.length}</h3>
            </div>
          </div>
          <div class="archive-list">
            ${group.uploads
              .map((upload) => {
                const reviewText = JSON.stringify(
                  {
                    meta: {
                      source: upload.ocr_engine || "manual-review",
                      confidence: upload.confidence || "review",
                      status: upload.status || "Pending review",
                    },
                    archive: {
                      id: upload.id,
                      file_name: upload.file_name,
                      season: upload.season,
                      club_name: upload.club_name || upload.resolved_club_name || "Unassigned",
                      archive_date: upload.archive_date,
                      archive_year: upload.archive_year,
                    },
                    draft_scorecard: upload.draft_scorecard || {},
                    suggested_performances: upload.suggested_performances || [],
                    raw_extracted_text: upload.raw_extracted_text || "",
                  },
                  null,
                  2
                );
                return `
                  <article class="detail-card" data-admin-upload="${upload.id}">
                    <strong>${escapeHtml(upload.file_name)}</strong>
                    <p>${escapeHtml(upload.club_name || upload.resolved_club_name || "Club TBD")} · ${escapeHtml(upload.season || "Season TBD")}</p>
                    <small>${escapeHtml(upload.archive_date || "Date TBD")} · ${escapeHtml(upload.status || "Pending review")}</small>
                    <p>${escapeHtml(upload.extracted_summary || "Review the extracted draft before approving.")}</p>
                    <label class="stack-label">
                      Reviewed extraction JSON
                      <textarea class="admin-review-text" rows="10" spellcheck="false">${escapeHtml(reviewText)}</textarea>
                    </label>
                    <div class="inline-actions">
                      <button class="secondary-button" type="button" data-action="extract">Re-extract</button>
                      <button class="secondary-button" type="button" data-action="save">Save review</button>
                      <button class="primary-button" type="button" data-action="approve">Approve</button>
                      <button class="secondary-button" type="button" data-action="delete">Delete</button>
                    </div>
                  </article>
                `;
              })
              .join("")}
          </div>
        </section>
      `
    )
    .join("");
}

async function loadClubView(targetClubId = "", uploadsOverride = null) {
  const requestedClubId = targetClubId || clubId() || auth?.user?.current_club_id || auth?.user?.primary_club_id || "";
  payload = requestedClubId
    ? await getJson(`/api/dashboard?focus_club_id=${encodeURIComponent(requestedClubId)}`, true)
    : await getJson("/api/dashboard", true);
  const clubs = availableClubs(payload);
  const resolvedClubId = requestedClubId || payload?.focus_club?.id || payload?.club?.id || clubs[0]?.id || "";
  const club = clubs.find((item) => item.id === resolvedClubId) || payload?.focus_club || payload?.club || { id: resolvedClubId, name: "Selected club" };
  if (!club?.id) {
    setStatus("No club selected.", "error");
    return;
  }
  setPrimaryClubId(club.id);
  clubSelect.value = club.id;
  if (!Array.isArray(auth?.clubs) || !auth.clubs.length) {
    auth = {
      ...auth,
      clubs: clubs,
    };
  }
  renderClubStats(payload);
  renderClubDetail(payload);
  renderFixtures(payload);
  renderArchives(payload, uploadsOverride);
  renderClubSelect(payload);
  populateFixtureForm();
  setStatus(`Loaded ${payload.club?.name || club.name}.`, "success");
}

async function loadReviewQueue() {
  const data = await getJson("/api/admin/review-queue", true);
  reviewQueue = data?.queue || [];
  return reviewQueue;
}

async function refreshAll() {
  auth = await getJson("/api/auth/me", true);
  const targetClubId = clubId() || auth.user.current_club_id || auth.user.primary_club_id || "";
  const queue = await loadReviewQueue();
  await loadClubView(targetClubId, queue);
}

fixtureForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const club = selectedClub();
  if (!club) return;
  const body = {
    club_id: club.id,
    season_year: Number(fixtureYearInput.value || new Date().getFullYear()),
    date: fixtureDateInput.value,
    date_label: fixtureDateLabelInput.value.trim(),
    opponent: fixtureOpponentInput.value.trim(),
    venue: fixtureVenueInput.value.trim(),
    match_type: fixtureTypeInput.value.trim(),
    scheduled_time: fixtureTimeInput.value.trim(),
    overs: fixtureOversInput.value.trim(),
  };
  try {
    if (fixtureIdInput.value) {
      await putJson(`/api/admin/clubs/${encodeURIComponent(club.id)}/fixtures/${encodeURIComponent(fixtureIdInput.value)}`, body, true);
      setStatus("Fixture updated.", "success");
    } else {
      await postJson("/api/season-setup/fixtures", body, true);
      setStatus("Fixture created.", "success");
    }
    await refreshAll();
  } catch (error) {
    setStatus(error.message, "error");
  }
});

fixtureList?.addEventListener("click", async (event) => {
  const editButton = event.target.closest("[data-fixture-load]");
  const deleteButton = event.target.closest("[data-fixture-delete]");
  const club = selectedClub();
  if (editButton) {
    const fixture = payload?.fixtures?.find((item) => item.id === editButton.dataset.fixtureLoad);
    if (!fixture) return;
    populateFixtureForm(fixture);
    setStatus(`Loaded ${fixture.date_label || fixture.date || "fixture"} into the editor.`, "success");
  }
  if (deleteButton) {
    if (!window.confirm("Delete this fixture?")) {
      return;
    }
    try {
      await deleteJson(`/api/admin/clubs/${encodeURIComponent(club.id)}/fixtures/${encodeURIComponent(deleteButton.dataset.fixtureDelete)}`, true);
      populateFixtureForm();
      setStatus("Fixture deleted.", "success");
      await refreshAll();
    } catch (error) {
      setStatus(error.message, "error");
    }
  }
});

archiveQueue?.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const card = button.closest("[data-admin-upload]");
  if (!card) return;
  const uploadId = card.dataset.adminUpload;
  const textarea = card.querySelector(".admin-review-text");
  try {
    if (button.dataset.action === "extract") {
      await postJson(`/api/archive/${uploadId}/extract`, {}, true);
      setStatus("Scorecard re-extracted.", "success");
    } else if (button.dataset.action === "save") {
      await postJson(`/api/admin/archive/${uploadId}/review`, { text: textarea?.value || "" }, true);
      setStatus("Reviewed extraction saved.", "success");
    } else if (button.dataset.action === "approve") {
      await postJson(`/api/admin/archive/${uploadId}/approve`, {}, true);
      setStatus("Archive approved.", "success");
    } else if (button.dataset.action === "delete") {
      if (!window.confirm("Delete this archive record?")) {
        return;
      }
      await deleteJson(`/api/admin/archive/${uploadId}`, true);
      setStatus("Archive deleted.", "success");
    }
    await refreshAll();
  } catch (error) {
    setStatus(error.message, "error");
  }
});

clubSelect?.addEventListener("change", async () => {
  try {
    const queue = reviewQueue.length ? reviewQueue : await loadReviewQueue();
    await loadClubView(clubSelect.value, queue);
  } catch (error) {
    setStatus(error.message, "error");
  }
});

loadClubButton?.addEventListener("click", async () => {
  try {
    const queue = reviewQueue.length ? reviewQueue : await loadReviewQueue();
    await loadClubView(clubSelect.value, queue);
  } catch (error) {
    setStatus(error.message, "error");
  }
});

archiveSearchInput?.addEventListener("input", () => renderArchives(payload, reviewQueue));
refreshButton?.addEventListener("click", async () => {
  try {
    const queue = await loadReviewQueue();
    await loadClubView(clubSelect.value, queue);
  } catch (error) {
    setStatus(error.message, "error");
  }
});

requireAuth()
  .then(async (result) => {
    if (!result) return;
    try {
      await refreshAll();
    } catch (error) {
      setStatus(error.message, "error");
    }
  })
  .catch((error) => setStatus(error.message, "error"));
