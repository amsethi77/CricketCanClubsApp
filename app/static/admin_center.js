let requireAuth;
let getJson;
let postJson;
let putJson;
let deleteJson;
let setPrimaryClubId;
let optionMarkup;

let statusBanner;
let clubForm;
let clubSelect;
let loadClubButton;
let clubStats;
let clubDetail;
let fixtureForm;
let fixtureIdInput;
let fixtureDateLabelInput;
let fixtureDateInput;
let fixtureOpponentInput;
let fixtureVenueInput;
let fixtureTypeInput;
let fixtureTimeInput;
let fixtureOversInput;
let fixtureYearInput;
let fixtureList;
let archiveSearchInput;
let refreshButton;
let archiveQueue;
let roleBadge;

let payload = null;
let auth = null;
let reviewQueue = [];
let selectedClubId = "";
let pendingDelete = { key: "", expiresAt: 0 };
let pendingDeleteTimer = null;
const adminDebugEnabled = ["localhost", "127.0.0.1", ""].includes(String(window.location.hostname || "").trim());

function adminDebug(...args) {
  if (adminDebugEnabled && typeof console !== "undefined" && console.debug) {
    console.debug("[AdminCenter]", ...args);
  }
}

function adminError(...args) {
  if (typeof console !== "undefined" && console.error) {
    console.error("[AdminCenter]", ...args);
  }
}

function setActionStatus(message, tone = "info") {
  setStatus(message, tone);
}

function bootstrapAdminCenter() {
  const pages = window.CricketClubAppPages;
  if (!pages) {
    adminDebug("Shared helpers not ready yet; retrying bootstrap.");
    return false;
  }
  ({
    requireAuth,
    getJson,
    postJson,
    putJson,
    deleteJson,
    setPrimaryClubId,
    optionMarkup,
  } = pages);

  statusBanner = document.getElementById("adminCenterStatus");
  clubForm = document.getElementById("adminClubForm");
  clubSelect = document.getElementById("adminClubSelect");
  loadClubButton = document.getElementById("adminLoadClubButton");
  clubStats = document.getElementById("adminClubStats");
  clubDetail = document.getElementById("adminClubDetail");
  fixtureForm = document.getElementById("adminFixtureForm");
  fixtureIdInput = document.getElementById("adminFixtureId");
  fixtureDateLabelInput = document.getElementById("adminFixtureDateLabel");
  fixtureDateInput = document.getElementById("adminFixtureDate");
  fixtureOpponentInput = document.getElementById("adminFixtureOpponent");
  fixtureVenueInput = document.getElementById("adminFixtureVenue");
  fixtureTypeInput = document.getElementById("adminFixtureType");
  fixtureTimeInput = document.getElementById("adminFixtureTime");
  fixtureOversInput = document.getElementById("adminFixtureOvers");
  fixtureYearInput = document.getElementById("adminSeasonYear");
  fixtureList = document.getElementById("adminFixtureList");
  archiveSearchInput = document.getElementById("adminArchiveSearch");
  refreshButton = document.getElementById("adminRefreshButton");
  archiveQueue = document.getElementById("adminReviewQueue");
  roleBadge = document.getElementById("adminRoleBadge");
  adminDebug("Bootstrap complete.", {
    hasClubForm: !!clubForm,
    hasClubSelect: !!clubSelect,
    hasArchiveQueue: !!archiveQueue,
  });
  return true;
}

function setStatus(message, tone = "info") {
  if (!statusBanner) return;
  statusBanner.hidden = !message;
  statusBanner.textContent = message || "";
  statusBanner.className = `status-banner ${tone}`;
}

function renderRoleBadge() {
  if (!roleBadge) return;
  const role = String(
    auth?.user?.effective_role ||
      auth?.user?.role ||
      auth?.user?.roles?.[0] ||
      ""
  ).trim();
  const label = role ? role.replace(/_/g, " ") : "role unavailable";
  roleBadge.textContent = `Signed in as ${label}`;
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function confirmTypedDelete(message, expectedValue, button = null) {
  const expected = String(expectedValue || "").trim();
  const key = expected ? `delete:${expected.toLowerCase()}` : `delete:${String(message || "").toLowerCase()}`;
  const now = Date.now();
  if (pendingDelete.key === key && pendingDelete.expiresAt > now) {
    pendingDelete = { key: "", expiresAt: 0 };
    if (pendingDeleteTimer) {
      clearTimeout(pendingDeleteTimer);
      pendingDeleteTimer = null;
    }
    if (button) {
      button.textContent = button.dataset.originalLabel || button.textContent;
      button.classList.remove("armed-delete");
    }
    return true;
  }
  pendingDelete = { key, expiresAt: now + 5000 };
  if (pendingDeleteTimer) {
    clearTimeout(pendingDeleteTimer);
  }
  pendingDeleteTimer = window.setTimeout(() => {
    if (pendingDelete.key === key) {
      pendingDelete = { key: "", expiresAt: 0 };
      if (button) {
        button.textContent = button.dataset.originalLabel || button.textContent;
        button.classList.remove("armed-delete");
      }
      setStatus("Delete confirmation timed out.", "info");
    }
  }, 5000);
  if (button) {
    button.dataset.originalLabel = button.dataset.originalLabel || button.textContent;
    button.textContent = `Click again: ${button.dataset.originalLabel}`;
    button.classList.add("armed-delete");
  }
  setStatus(`${message} Click the same delete button again within 5 seconds to confirm.`, "warning");
  return false;
}

async function runArchiveAction(action, uploadId, button = null, reviewText = "") {
  const card = archiveQueue?.querySelector(`[data-admin-upload="${uploadId}"]`);
  if (!card) {
    const error = new Error("Archive card not found.");
    adminError("Archive action failed.", error);
    setStatus(error.message, "error");
    return false;
  }
  const textarea = card.querySelector(".admin-review-text");
  try {
    if (action === "extract") {
      adminDebug("Archive re-extract requested.", { uploadId });
      setActionStatus("Re-extracting archive...", "warning");
      await postJson(`/api/archive/${uploadId}/extract`, {}, true);
      setStatus("Scorecard re-extracted.", "success");
    } else if (action === "save") {
      const textValue = String(reviewText || textarea?.value || "").trim();
      if (!textValue) {
        setStatus("Paste the reviewed JSON before saving.", "error");
        return false;
      }
      adminDebug("Archive review save requested.", { uploadId, textLength: textValue.length });
      setActionStatus("Saving reviewed JSON...", "warning");
      await postJson(`/api/admin/archive/${uploadId}/review`, { text: textValue }, true);
      setStatus("Reviewed extraction saved.", "success");
    } else if (action === "approve") {
      const textValue = String(reviewText || textarea?.value || "").trim();
      if (!textValue) {
        setStatus("Paste the reviewed JSON before approving.", "error");
        return false;
      }
      adminDebug("Archive approve requested.", { uploadId, textLength: textValue.length });
      setActionStatus("Saving JSON and approving archive...", "warning");
      await postJson(`/api/admin/archive/${uploadId}/approve`, { text: textValue }, true);
      setStatus("Archive approved.", "success");
    } else if (action === "delete") {
      adminDebug("Archive delete requested.", { uploadId });
      if (!confirmTypedDelete("Delete this archive record?", uploadId, button)) return false;
      setActionStatus("Deleting archive record...", "warning");
      await deleteJson(`/api/admin/archive/${uploadId}`, true);
      setStatus("Archive deleted.", "success");
    } else {
      return false;
    }
    await refreshAll();
    return true;
  } catch (error) {
    adminError("Archive action failed.", error);
    setStatus(error.message, "error");
    return false;
  }
}

function clubId() {
  return selectedClubId || clubSelect?.value || auth?.user?.current_club_id || auth?.user?.primary_club_id || "";
}

function availableClubs(dashboard = payload) {
  const merged = [];
  const seen = new Set();
  for (const source of [auth?.clubs, dashboard?.clubs]) {
    if (!Array.isArray(source)) continue;
    for (const club of source) {
      const id = String(club?.id || "").trim();
      if (!id || seen.has(id)) continue;
      seen.add(id);
      merged.push(club);
    }
  }
  return merged;
}

function selectedClub() {
  const clubs = availableClubs();
  return clubs.find((club) => club.id === clubId()) || clubs[0] || null;
}

function focusedClub(dashboard = payload) {
  return dashboard?.focus_club || dashboard?.club || selectedClub() || {};
}

function renderedClubId() {
  return String(clubDetail?.querySelector("[data-admin-club]")?.dataset?.adminClub || selectedClubId || clubId() || "").trim();
}

async function deleteClubRosterItem(targetType, targetId) {
  const club = focusedClub(payload);
  const activeClubId = renderedClubId() || club.id || "";
  if (!club || !activeClubId) {
    const error = new Error("No club is currently loaded.");
    adminError("Club action blocked.", error);
    setStatus(error.message, "error");
    return;
  }
  if (targetType === "club") {
    const clubName = club.name || "this club";
    if (!confirmTypedDelete(`Delete ${clubName} and remove its club-only data?`, clubName)) {
      return;
    }
    try {
      setActionStatus(`Deleting ${clubName}...`, "warning");
      await deleteJson(`/api/admin/clubs/${encodeURIComponent(activeClubId)}`, true);
      setStatus(`${clubName} deleted.`, "success");
      await refreshAll();
    } catch (error) {
      adminError("Club delete failed.", error);
      setStatus(error.message, "error");
    }
    return;
  }
  const member = (payload?.members || payload?.all_members || []).find((item) => String(item.id || "") === String(targetId || ""));
  const memberName = member?.name || "this player";
  if (!confirmTypedDelete(`Remove ${memberName} from ${club.name || "this club"}?`, memberName)) {
    return;
  }
  try {
    setActionStatus(`Unlinking ${memberName} from ${club.name || "the club"}...`, "warning");
    await deleteJson(`/api/admin/clubs/${encodeURIComponent(activeClubId)}/members/${encodeURIComponent(targetId)}`, true);
    setStatus(`${memberName} removed from ${club.name || "the club"}.`, "success");
    await refreshAll();
  } catch (error) {
    adminError("Member unlink failed.", error);
    setStatus(error.message, "error");
  }
}

window.CricketClubAppAdminCenterDelete = deleteClubRosterItem;

function selectedClubKeys(dashboard = payload) {
  const club = dashboard?.club || dashboard?.focus_club || selectedClub() || {};
  const clubIdValue = String(club.id || club.club_id || "").trim().toLowerCase();
  const clubNameValue = String(club.name || "").trim().toLowerCase();
  const clubShortNameValue = String(club.short_name || "").trim().toLowerCase();
  return { clubIdValue, clubNameValue, clubShortNameValue };
}

function normalizeClubList(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || "").trim().toLowerCase()).filter(Boolean);
  }
  if (typeof value === "string") {
    const text = value.trim();
    if (!text) return [];
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        return parsed.map((item) => String(item || "").trim().toLowerCase()).filter(Boolean);
      }
    } catch {
      return text.split(/[,;|]/).map((item) => String(item || "").trim().toLowerCase()).filter(Boolean);
    }
  }
  return [];
}

function clubMatchesSelection(club, selected) {
  if (!club || !selected) return false;
  const clubIdValue = String(selected.id || selected.club_id || "").trim().toLowerCase();
  const clubNameValue = String(selected.name || "").trim().toLowerCase();
  const clubShortNameValue = String(selected.short_name || "").trim().toLowerCase();
  const targetId = String(club.club_id || club.id || "").trim().toLowerCase();
  const targetName = String(club.club_name || club.name || "").trim().toLowerCase();
  const targetShortName = String(club.short_name || "").trim().toLowerCase();
  return (
    (clubIdValue && targetId === clubIdValue) ||
    (clubNameValue && (targetName === clubNameValue || targetShortName === clubNameValue)) ||
    (clubShortNameValue && (targetName === clubShortNameValue || targetShortName === clubShortNameValue))
  );
}

function memberMatchesClub(member, club) {
  if (!member || !club) return false;
  if (clubMatchesSelection(member, club)) {
    return true;
  }
  const memberships = Array.isArray(member.club_memberships)
    ? member.club_memberships
    : Array.isArray(member.team_memberships)
      ? member.team_memberships
      : [];
  return memberships.some((membership) => clubMatchesSelection(membership, club));
}

function filterMembersForClub(dashboard, club) {
  const source = Array.isArray(dashboard?.all_members) && dashboard.all_members.length
    ? dashboard.all_members
    : Array.isArray(dashboard?.members)
      ? dashboard.members
      : [];
  return source.filter((member) => memberMatchesClub(member, club));
}

function fixtureMatchesClub(fixture, club) {
  if (!fixture || !club) return false;
  const clubIdValue = String(club.id || club.club_id || "").trim().toLowerCase();
  const clubNameValue = String(club.name || "").trim().toLowerCase();
  const clubShortNameValue = String(club.short_name || "").trim().toLowerCase();
  const fixtureClubId = String(fixture.club_id || "").trim().toLowerCase();
  const fixtureClubName = String(fixture.club_name || fixture.details?.club_name || "").trim().toLowerCase();
  return (
    (clubIdValue && fixtureClubId === clubIdValue) ||
    (clubNameValue && (fixtureClubName === clubNameValue || fixtureClubName === clubShortNameValue)) ||
    (clubShortNameValue && fixtureClubName === clubShortNameValue)
  );
}

function filterFixturesForClub(dashboard, club) {
  const source = Array.isArray(dashboard?.all_fixtures) && dashboard.all_fixtures.length
    ? dashboard.all_fixtures
    : Array.isArray(dashboard?.fixtures)
      ? dashboard.fixtures
      : [];
  return source.filter((fixture) => fixtureMatchesClub(fixture, club));
}

function archiveMatchesClub(upload, club) {
  if (!upload || !club) return false;
  const clubIdValue = String(club.id || club.club_id || "").trim().toLowerCase();
  const clubNameValue = String(club.name || "").trim().toLowerCase();
  const clubShortNameValue = String(club.short_name || "").trim().toLowerCase();
  const resolvedClubIds = normalizeClubList(upload.resolved_club_ids || upload.club_ids || upload.club_id || "");
  const resolvedClubNames = normalizeClubList(upload.resolved_club_names || upload.club_names || upload.club_name || "");
  return (
    (clubIdValue && resolvedClubIds.includes(clubIdValue)) ||
    (clubNameValue && (resolvedClubNames.includes(clubNameValue) || resolvedClubNames.includes(clubShortNameValue))) ||
    (clubShortNameValue && resolvedClubNames.includes(clubShortNameValue))
  );
}

function filterArchivesForClub(dashboard, club) {
  const source = Array.isArray(dashboard?.all_archive_uploads) && dashboard.all_archive_uploads.length
    ? dashboard.all_archive_uploads
    : Array.isArray(dashboard?.archive_uploads)
      ? dashboard.archive_uploads
      : [];
  return source.filter((upload) => archiveMatchesClub(upload, club));
}

function archiveBelongsToSelectedClub(upload, dashboard = payload) {
  const { clubIdValue, clubNameValue, clubShortNameValue } = selectedClubKeys(dashboard);
  if (!clubIdValue && !clubNameValue && !clubShortNameValue) {
    return true;
  }
  const resolvedClubId = String(upload.resolved_club_id || upload.club_id || "").trim().toLowerCase();
  const resolvedClubName = String(upload.resolved_club_name || upload.club_name || "").trim().toLowerCase();
  const resolvedClubIds = normalizeClubList(upload.resolved_club_ids || upload.club_ids || resolvedClubId);
  const resolvedClubNames = normalizeClubList(upload.resolved_club_names || upload.club_names || resolvedClubName);
  if (clubIdValue && resolvedClubIds.includes(clubIdValue)) {
    return true;
  }
  return clubNameValue
    ? resolvedClubNames.includes(clubNameValue) || resolvedClubNames.includes(clubShortNameValue)
    : clubShortNameValue
      ? resolvedClubNames.includes(clubShortNameValue)
      : false;
}

function blankTemplatePlayer(didNotBat = false) {
  if (didNotBat) {
    return {
      player: { name: null, normalized_name: null, member_id: null },
      runs: null,
      dismissal: { type: "did_not_bat" },
    };
  }
  return {
    player: { name: null, normalized_name: null, member_id: null },
    runs: null,
    balls: null,
    fours: null,
    sixes: null,
    strike_rate: null,
    dismissal: { type: null, fielder: null, bowler: null },
  };
}

function blankTemplateBowler() {
  return {
    player: { name: null, normalized_name: null },
    overs: null,
    runs_conceded: null,
    wickets: null,
    economy: null,
  };
}

function reviewTemplateForUpload(upload) {
  if (upload?.extraction_template && typeof upload.extraction_template === "object") {
    return upload.extraction_template;
  }
  const draft = upload?.draft_scorecard || {};
  return {
    meta: {
      source: upload?.ocr_engine || null,
      processed_by: upload?.ocr_pipeline || null,
      confidence: upload?.confidence || null,
      status: "template",
      created_at: upload?.created_at || null,
      updated_at: upload?.ocr_processed_at || upload?.updated_at || null,
    },
    match: {
      match_id: upload?.match_id || null,
      match_type: "club",
      format: upload?.match_format || null,
      date: upload?.archive_date || upload?.scorecard_date || upload?.photo_taken_at || null,
      venue: upload?.venue || null,
      teams: {
        team_1: null,
        team_2: null,
      },
      overs_limit: upload?.overs_limit || null,
    },
    innings: [
      {
        inning_number: 1,
        batting_team: null,
        bowling_team: null,
        summary: {
          runs: draft.heartlake_runs || null,
          wickets: draft.heartlake_wickets || null,
          overs: draft.heartlake_overs || null,
          balls: upload?.inning_1_balls || null,
        },
        batting: Array.from({ length: 10 }, () => blankTemplatePlayer()).concat([blankTemplatePlayer(true)]),
        bowling: [blankTemplateBowler()],
        extras: {
          wides: null,
          no_balls: null,
          byes: null,
          leg_byes: null,
          penalties: null,
          total: null,
        },
      },
      {
        inning_number: 2,
        batting_team: null,
        bowling_team: null,
        summary: {
          runs: draft.opponent_runs || null,
          wickets: draft.opponent_wickets || null,
          overs: draft.opponent_overs || null,
          balls: upload?.inning_2_balls || null,
        },
        batting: Array.from({ length: 10 }, () => blankTemplatePlayer()).concat([blankTemplatePlayer(true)]),
        bowling: [blankTemplateBowler()],
        extras: {
          wides: null,
          no_balls: null,
          byes: null,
          leg_byes: null,
          penalties: null,
          total: null,
        },
      },
    ],
    validation: {
      inning_1_total: draft.heartlake_runs || null,
      inning_2_total: draft.opponent_runs || null,
      expected_result: draft.result || null,
      is_consistent: null,
      notes: null,
    },
  };
}

function renderClubSelect(dashboard = payload) {
  const clubs = availableClubs(dashboard);
  adminDebug("Rendering club selector.", {
    clubCount: clubs.length,
    selectedClubId,
  });
  const current = selectedClubId || focusedClub(dashboard)?.id || clubId() || clubs[0]?.id || "";
  clubSelect.innerHTML = optionMarkup(clubs, "id", (club) => `${club.name} · ${club.season || "Season TBD"}`);
  clubSelect.value = current;
}

function renderClubStats(dashboard) {
  const summary = dashboard?.summary || {};
  const club = focusedClub(dashboard);
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
  adminDebug("Rendering club detail.", {
    clubId: focusedClub(dashboard)?.id || "",
    memberCount: Array.isArray(dashboard?.members) ? dashboard.members.length : 0,
  });
  const club = focusedClub(dashboard);
  const members = Array.isArray(dashboard?.members) ? dashboard.members : [];
  const teams = Array.isArray(dashboard?.teams) ? dashboard.teams : [];
  const memberCards = members.length
    ? members
        .map(
          (member) => `
            <article class="detail-card admin-member-card" data-admin-member="${escapeHtml(member.id || "")}">
              <strong>${escapeHtml(member.name || "Player")}</strong>
              <p>${escapeHtml(member.full_name || "")}</p>
              <small>${escapeHtml(member.role || "player")} · ${escapeHtml(member.phone || "No mobile")}</small>
              <small>${escapeHtml(member.team_name || "")}</small>
              <form class="admin-delete-form" method="post" action="/api/admin/clubs/${encodeURIComponent(club.id || "")}/members/${encodeURIComponent(member.id || "")}/delete">
                <label class="stack-label">
                  Type the exact player name to confirm removal
                  <input name="confirmation" type="text" placeholder="${escapeHtml(member.name || "")}" autocomplete="off" required />
                </label>
                <button class="danger-button" type="submit">Remove from club</button>
              </form>
            </article>
          `
        )
        .join("")
    : `<p class="empty-state">No club members are linked to this club yet.</p>`;
  clubDetail.innerHTML = `
    <article class="detail-card admin-club-card" data-admin-club="${escapeHtml(club.id || "")}">
      <strong>${escapeHtml(club.name || "Selected club")}</strong>
      <p>${escapeHtml(club.short_name || "")} · ${escapeHtml(club.season || "Season TBD")}</p>
      <small>${members.length} players · ${teams.length} teams · ${escapeHtml(club.city || "City TBD")} · ${escapeHtml(club.country || "Country TBD")}</small>
      <form class="admin-delete-form" method="post" action="/api/admin/clubs/${encodeURIComponent(club.id || "")}/delete">
        <label class="stack-label">
          Type the exact club name to confirm deletion
          <input name="confirmation" type="text" placeholder="${escapeHtml(club.name || "")}" autocomplete="off" required />
        </label>
        <button class="danger-button" type="submit">Delete club</button>
      </form>
    </article>
    <article class="stack-card admin-roster-panel">
      <div class="panel-head compact-head">
        <div>
          <p class="section-kicker">Players</p>
          <h3>Club roster</h3>
        </div>
      </div>
      <div class="archive-list">
        ${memberCards}
      </div>
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

function renderArchives(dashboard) {
  adminDebug("Rendering archive queue.", {
    clubId: focusedClub(dashboard)?.id || "",
    sourceCount: Array.isArray(dashboard?.archive_uploads) ? dashboard.archive_uploads.length : 0,
    search: String(archiveSearchInput?.value || "").trim(),
  });
  const query = String(archiveSearchInput?.value || "").trim().toLowerCase();
  const sourceUploads = Array.isArray(dashboard?.archive_uploads) ? dashboard.archive_uploads : [];
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
    const clubKey = upload.resolved_club_id || normalizeClubList(upload.resolved_club_ids || upload.club_ids)[0] || upload.club_id || "";
    const clubName = upload.resolved_club_name || upload.club_name || normalizeClubList(upload.resolved_club_names || upload.club_names).join(" / ") || "Unassigned";
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
                const reviewText = JSON.stringify(reviewTemplateForUpload(upload), null, 2);
                return `
                  <article class="detail-card" data-admin-upload="${upload.id}">
                    <strong>${escapeHtml(upload.file_name)}</strong>
                    <p>${escapeHtml(upload.club_name || upload.resolved_club_name || "Club TBD")} · ${escapeHtml(upload.season || "Season TBD")}</p>
                    <small>${escapeHtml(upload.archive_date || "Date TBD")} · ${escapeHtml(upload.status || "Pending review")}</small>
                    <p>${escapeHtml(upload.extracted_summary || "Review the extracted draft before approving.")}</p>
                    <form class="admin-review-form" method="post" action="/api/admin/archive/${upload.id}/review-form">
                      <label class="stack-label">
                        Reviewed extraction JSON
                        <textarea class="admin-review-text" name="text" rows="10" spellcheck="false">${escapeHtml(reviewText)}</textarea>
                      </label>
                      <div class="inline-actions">
                        <button class="secondary-button" type="submit" data-action="save">Save review</button>
                        <button class="primary-button" type="submit" data-action="approve" formaction="/api/admin/archive/${upload.id}/approve-form">Approve</button>
                      </div>
                    </form>
                    <div class="inline-actions">
                      <button class="secondary-button" type="button" data-action="extract" onclick="return window.CricketClubAppAdminCenterArchiveAction(this, 'extract');">Re-extract</button>
                      <button class="secondary-button" type="button" data-action="delete" onclick="return window.CricketClubAppAdminCenterArchiveAction(this, 'delete');">Delete</button>
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
  adminDebug("Loading club view.", { targetClubId, selectedClubId });
  const requestedClubId = targetClubId || clubId() || auth?.user?.current_club_id || auth?.user?.primary_club_id || "";
  payload = requestedClubId
    ? await getJson(`/api/dashboard?focus_club_id=${encodeURIComponent(requestedClubId)}`, true)
    : await getJson("/api/dashboard", true);
  const clubs = availableClubs(payload);
  const resolvedClub = clubs.find((item) => item.id === requestedClubId)
    || payload?.focus_club
    || payload?.club
    || clubs[0]
    || { id: requestedClubId, name: "Selected club" };
  const resolvedClubId = resolvedClub?.id || requestedClubId || clubs[0]?.id || "";
  if (!resolvedClubId) {
    setStatus("No club selected.", "error");
    return;
  }
  const club = resolvedClub;
  selectedClubId = club.id || resolvedClubId;
  setPrimaryClubId(club.id);
  clubSelect.value = club.id;
  if (!Array.isArray(auth?.clubs) || !auth.clubs.length) {
    auth = {
      ...auth,
      clubs: clubs,
    };
  }
  payload = {
    ...payload,
    club,
    focus_club: club,
    members: filterMembersForClub(payload, club),
    teams: (Array.isArray(payload?.teams) ? payload.teams : []).filter((team) => clubMatchesSelection(team, club)),
    fixtures: filterFixturesForClub(payload, club),
    archive_uploads: filterArchivesForClub(payload, club),
  };
  renderClubStats(payload);
  renderClubDetail(payload);
  renderFixtures(payload);
  renderArchives(payload);
  renderClubSelect(payload);
  populateFixtureForm();
  setStatus(`Loaded ${payload.club?.name || club.name}.`, "success");
  adminDebug("Club view loaded.", {
    clubId: payload.club?.id || "",
    fixtureCount: Array.isArray(payload.fixtures) ? payload.fixtures.length : 0,
    archiveCount: Array.isArray(payload.archive_uploads) ? payload.archive_uploads.length : 0,
  });
}

async function loadReviewQueue() {
  adminDebug("Loading review queue.");
  const data = await getJson("/api/admin/review-queue", true);
  reviewQueue = data?.queue || [];
  adminDebug("Review queue loaded.", { count: reviewQueue.length });
  return reviewQueue;
}

async function refreshAll() {
  adminDebug("Refreshing admin center.");
  auth = await getJson("/api/auth/me", true);
  renderRoleBadge();
  const targetClubId = clubId() || auth?.user?.current_club_id || auth?.user?.primary_club_id || "";
  const queue = await loadReviewQueue();
  await loadClubView(targetClubId, queue);
  adminDebug("Refresh complete.", { targetClubId, queueCount: queue.length });
}

let adminCenterHandlersBound = false;

function bindAdminCenterHandlers() {
  if (adminCenterHandlersBound) return;
  adminCenterHandlersBound = true;

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
      setActionStatus(fixtureIdInput.value ? "Updating fixture..." : "Creating fixture...", "warning");
      adminDebug("Saving fixture.", { clubId: club.id, fixtureId: fixtureIdInput.value || "" });
      if (fixtureIdInput.value) {
        await putJson(`/api/admin/clubs/${encodeURIComponent(club.id)}/fixtures/${encodeURIComponent(fixtureIdInput.value)}`, body, true);
        setStatus("Fixture updated.", "success");
      } else {
        await postJson("/api/season-setup/fixtures", body, true);
        setStatus("Fixture created.", "success");
      }
      await refreshAll();
    } catch (error) {
      adminError("Fixture save failed.", error);
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
      adminDebug("Fixture loaded into editor.", { fixtureId: fixture.id, date: fixture.date_label || fixture.date || "" });
      populateFixtureForm(fixture);
      setStatus(`Loaded ${fixture.date_label || fixture.date || "fixture"} into the editor.`, "success");
    }
    if (deleteButton) {
      const fixture = payload?.fixtures?.find((item) => item.id === deleteButton.dataset.fixtureDelete);
      if (!confirmTypedDelete("Delete this fixture?", fixture?.date_label || fixture?.date || "fixture", deleteButton)) {
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

  archiveQueue?.addEventListener("submit", async (event) => {
    const form = event.target.closest("form.admin-review-form");
    if (!form) return;
    event.preventDefault();
    const button = event.submitter || form.querySelector("button[data-action='save']");
    const card = form.closest("[data-admin-upload]");
    if (!card) return;
    const uploadId = card.dataset.adminUpload;
    const action = String(button?.dataset?.action || "save").trim();
    const textValue = form.querySelector(".admin-review-text")?.value || "";
    await runArchiveAction(action, uploadId, button, textValue);
  });

  archiveQueue?.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    if (button.type === "submit") return;
    const card = button.closest("[data-admin-upload]");
    if (!card) return;
    const uploadId = card.dataset.adminUpload;
    await runArchiveAction(button.dataset.action, uploadId, button);
  });

  clubSelect?.addEventListener("change", async () => {
    try {
      selectedClubId = clubSelect.value;
      adminDebug("Club changed.", { selectedClubId });
      const queue = reviewQueue.length ? reviewQueue : await loadReviewQueue();
      await loadClubView(selectedClubId, queue);
    } catch (error) {
      adminError("Club change failed.", error);
      setStatus(error.message, "error");
    }
  });

  clubForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      selectedClubId = clubSelect.value || selectedClubId;
      adminDebug("Load club submitted.", { selectedClubId });
      const queue = reviewQueue.length ? reviewQueue : await loadReviewQueue();
      await loadClubView(selectedClubId, queue);
    } catch (error) {
      adminError("Load club failed.", error);
      setStatus(error.message, "error");
    }
  });

  archiveSearchInput?.addEventListener("input", () => {
    adminDebug("Archive search updated.", { value: archiveSearchInput.value });
    renderArchives(payload);
  });
  refreshButton?.addEventListener("click", async () => {
    try {
      adminDebug("Review queue refresh clicked.");
      setActionStatus("Refreshing review queue...", "warning");
      const queue = await loadReviewQueue();
      await loadClubView(selectedClubId || clubSelect.value);
      adminDebug("Review queue refreshed.", { count: queue.length });
    } catch (error) {
      adminError("Review queue refresh failed.", error);
      setStatus(error.message, "error");
    }
  });
}

async function startAdminCenter() {
  if (!bootstrapAdminCenter()) {
    adminDebug("Bootstrap deferred because shared helpers were not ready.");
    window.setTimeout(startAdminCenter, 25);
    return;
  }
  bindAdminCenterHandlers();
  try {
    adminDebug("Starting admin auth refresh.");
    const result = await requireAuth();
    if (!result) return;
    await refreshAll();
  } catch (error) {
    adminError("Admin center startup failed.", error);
    setStatus(error.message, "error");
  }
}

startAdminCenter();

renderRoleBadge();
window.CricketClubAppAdminCenterArchiveAction = async (button, action) => runArchiveAction(action, button?.closest?.("[data-admin-upload]")?.dataset?.adminUpload || "", button);
