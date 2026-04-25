function getCookieValue(name) {
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${name}=`));
  if (!match) return "";
  return decodeURIComponent(match.slice(name.length + 1));
}

const savedChatHistory = (() => {
  try {
    return JSON.parse(window.sessionStorage.getItem("heartlakeChatHistory") || "[]");
  } catch {
    return [];
  }
})();

const state = {
  dashboard: null,
  viewerAuth: null,
  isAdmin: false,
  canManageOtherAvailability: false,
  selectedMatchId: null,
  selectedPlayerName: null,
  selectedAvailabilityPlayerName: null,
  selectedTeamName: null,
  selectedFocusClubId: getCookieValue("heartlakePrimaryClubId") || window.localStorage.getItem("heartlakePrimaryClubId") || null,
  selectedSeasonYear: null,
  expandedLists: (() => {
    try {
      return JSON.parse(window.sessionStorage.getItem("heartlakeExpandedLists") || "{}");
    } catch {
      return {};
    }
  })(),
  chatHistory: Array.isArray(savedChatHistory) ? savedChatHistory : [],
  chatSessionId:
    window.sessionStorage.getItem("heartlakeChatSessionId") ||
    (window.crypto?.randomUUID ? window.crypto.randomUUID() : `chat-${Date.now()}`),
};

const ARCHIVE_SEASON_LABEL = "2025 Season";
const DEFAULT_LIST_LIMIT = 5;

let recognition = null;
let recognitionActive = false;
let statusTimer = null;

const elements = {
  statusBanner: document.getElementById("statusBanner"),
  seasonLabel: document.getElementById("seasonLabel"),
  nextMatchLabelTitle: document.getElementById("nextMatchLabelTitle"),
  nextMatchLabel: document.getElementById("nextMatchLabel"),
  availabilityLabel: document.getElementById("availabilityLabel"),
  seasonModeLabel: document.getElementById("seasonModeLabel"),
  llmLabel: document.getElementById("llmLabel"),
  viewerPlayerSnapshotLabel: document.getElementById("viewerPlayerSnapshotLabel"),
  viewerPlayerSnapshotTitle: document.getElementById("viewerPlayerSnapshotTitle"),
  viewerPlayerSnapshotDetails: document.getElementById("viewerPlayerSnapshotDetails"),
  heroEyebrow: document.getElementById("heroEyebrow"),
  focusClubBadge: document.getElementById("focusClubBadge"),
  activeMatchSelect: document.getElementById("activeMatchSelect"),
  whatsappLink: document.getElementById("whatsappLink"),
  viewerProfileForm: document.getElementById("viewerProfileForm"),
  viewerDisplayNameInput: document.getElementById("viewerDisplayNameInput"),
  viewerMobileInput: document.getElementById("viewerMobileInput"),
  viewerEmailInput: document.getElementById("viewerEmailInput"),
  primaryClubSelect: document.getElementById("primaryClubSelect"),
  clubSearchInput: document.getElementById("clubSearchInput"),
  clubSearchResults: document.getElementById("clubSearchResults"),
  landingPlayerSearchInput: document.getElementById("landingPlayerSearchInput"),
  landingPlayerResults: document.getElementById("landingPlayerResults"),
  landingEvents: document.getElementById("landingEvents"),
  landingMatches: document.getElementById("landingMatches"),
  landingClubStats: document.getElementById("landingClubStats"),
  clubDirectory: document.getElementById("clubDirectory"),
  followedPlayers: document.getElementById("followedPlayers"),
  focusClubSummary: document.getElementById("focusClubSummary"),
  matchCenterHeading: document.getElementById("matchCenterHeading"),
  selectedScorecardTitle: document.getElementById("selectedScorecardTitle"),
  selectedAvailabilityTitle: document.getElementById("selectedAvailabilityTitle"),
  summaryGrid: document.getElementById("summaryGrid"),
  selectedMatchSnapshot: document.getElementById("selectedMatchSnapshot"),
  selectedScorecard: document.getElementById("selectedScorecard"),
  selectedAvailability: document.getElementById("selectedAvailability"),
  selectedPerformances: document.getElementById("selectedPerformances"),
  selectedCommentary: document.getElementById("selectedCommentary"),
  detailsForm: document.getElementById("detailsForm"),
  captainInput: document.getElementById("captainInput"),
  venueInput: document.getElementById("venueInput"),
  matchTypeInput: document.getElementById("matchTypeInput"),
  scheduledTimeInput: document.getElementById("scheduledTimeInput"),
  oversInput: document.getElementById("oversInput"),
  tossWinnerInput: document.getElementById("tossWinnerInput"),
  tossDecisionInput: document.getElementById("tossDecisionInput"),
  weatherInput: document.getElementById("weatherInput"),
  umpiresInput: document.getElementById("umpiresInput"),
  scorerInput: document.getElementById("scorerInput"),
  whatsappThreadInput: document.getElementById("whatsappThreadInput"),
  matchStatusInput: document.getElementById("matchStatusInput"),
  matchNotesInput: document.getElementById("matchNotesInput"),
  scoreForm: document.getElementById("scoreForm"),
  heartlakeRunsInput: document.getElementById("heartlakeRunsInput"),
  heartlakeWicketsInput: document.getElementById("heartlakeWicketsInput"),
  heartlakeOversInput: document.getElementById("heartlakeOversInput"),
  opponentRunsInput: document.getElementById("opponentRunsInput"),
  opponentWicketsInput: document.getElementById("opponentWicketsInput"),
  opponentOversInput: document.getElementById("opponentOversInput"),
  resultInput: document.getElementById("resultInput"),
  liveSummaryInput: document.getElementById("liveSummaryInput"),
  scorebookInningsSelect: document.getElementById("scorebookInningsSelect"),
  scorebookSetupForm: document.getElementById("scorebookSetupForm"),
  scorebookBattingTeamInput: document.getElementById("scorebookBattingTeamInput"),
  scorebookBowlingTeamInput: document.getElementById("scorebookBowlingTeamInput"),
  scorebookOversLimitInput: document.getElementById("scorebookOversLimitInput"),
  scorebookTargetRunsInput: document.getElementById("scorebookTargetRunsInput"),
  scorebookStatusInput: document.getElementById("scorebookStatusInput"),
  scorebookBatters: document.getElementById("scorebookBatters"),
  scorebookBowlers: document.getElementById("scorebookBowlers"),
  scorebookBallForm: document.getElementById("scorebookBallForm"),
  scorebookOverNumberInput: document.getElementById("scorebookOverNumberInput"),
  scorebookBallNumberInput: document.getElementById("scorebookBallNumberInput"),
  scorebookStrikerInput: document.getElementById("scorebookStrikerInput"),
  scorebookNonStrikerInput: document.getElementById("scorebookNonStrikerInput"),
  scorebookBowlerInput: document.getElementById("scorebookBowlerInput"),
  scorebookRunsBatInput: document.getElementById("scorebookRunsBatInput"),
  scorebookExtrasTypeInput: document.getElementById("scorebookExtrasTypeInput"),
  scorebookExtrasRunsInput: document.getElementById("scorebookExtrasRunsInput"),
  scorebookWicketInput: document.getElementById("scorebookWicketInput"),
  scorebookWicketTypeInput: document.getElementById("scorebookWicketTypeInput"),
  scorebookWicketPlayerInput: document.getElementById("scorebookWicketPlayerInput"),
  scorebookFielderInput: document.getElementById("scorebookFielderInput"),
  scorebookBallCommentaryInput: document.getElementById("scorebookBallCommentaryInput"),
  scorebookSummary: document.getElementById("scorebookSummary"),
  scorebookRecentBalls: document.getElementById("scorebookRecentBalls"),
  availabilityForm: document.getElementById("availabilityForm"),
  availabilitySaveButton: document.getElementById("availabilitySaveButton"),
  availabilityPlayerSelect: document.getElementById("availabilityPlayerSelect"),
  availabilityStatusSelect: document.getElementById("availabilityStatusSelect"),
  availabilityNoteInput: document.getElementById("availabilityNoteInput"),
  availabilityFixturesEditor: document.getElementById("availabilityFixturesEditor"),
  availabilityMatrix: document.getElementById("availabilityMatrix"),
  performanceForm: document.getElementById("performanceForm"),
  performancePlayerSelect: document.getElementById("performancePlayerSelect"),
  performanceRunsInput: document.getElementById("performanceRunsInput"),
  performanceBallsInput: document.getElementById("performanceBallsInput"),
  performanceWicketsInput: document.getElementById("performanceWicketsInput"),
  performanceCatchesInput: document.getElementById("performanceCatchesInput"),
  performanceFoursInput: document.getElementById("performanceFoursInput"),
  performanceSixesInput: document.getElementById("performanceSixesInput"),
  performanceNotesInput: document.getElementById("performanceNotesInput"),
  playerLeaderboard: document.getElementById("playerLeaderboard"),
  rankingYearSelect: document.getElementById("rankingYearSelect"),
  playerProfileSelect: document.getElementById("playerProfileSelect"),
  playerSearchInput: document.getElementById("playerSearchInput"),
  playerIdentity: document.getElementById("playerIdentity"),
  playerEditForm: document.getElementById("playerEditForm"),
  editPlayerName: document.getElementById("editPlayerName"),
  editPlayerFullName: document.getElementById("editPlayerFullName"),
  editPlayerGender: document.getElementById("editPlayerGender"),
  editPlayerAliases: document.getElementById("editPlayerAliases"),
  editPlayerTeamName: document.getElementById("editPlayerTeamName"),
  editPlayerTeamMemberships: document.getElementById("editPlayerTeamMemberships"),
  editPlayerAge: document.getElementById("editPlayerAge"),
  editPlayerRole: document.getElementById("editPlayerRole"),
  editPlayerBattingStyle: document.getElementById("editPlayerBattingStyle"),
  editPlayerBowlingStyle: document.getElementById("editPlayerBowlingStyle"),
  editPlayerJerseyNumber: document.getElementById("editPlayerJerseyNumber"),
  editPlayerPhone: document.getElementById("editPlayerPhone"),
  editPlayerEmail: document.getElementById("editPlayerEmail"),
  editPlayerPictureUrl: document.getElementById("editPlayerPictureUrl"),
  editPlayerNotes: document.getElementById("editPlayerNotes"),
  playerSeasonSummary: document.getElementById("playerSeasonSummary"),
  playerCareerSnapshot: document.getElementById("playerCareerSnapshot"),
  playerPendingHistory: document.getElementById("playerPendingHistory"),
  playerMatchHistory: document.getElementById("playerMatchHistory"),
  teamProfileSelect: document.getElementById("teamProfileSelect"),
  teamSummary: document.getElementById("teamSummary"),
  teamRoster: document.getElementById("teamRoster"),
  teamPlayerScores: document.getElementById("teamPlayerScores"),
  commentaryForm: document.getElementById("commentaryForm"),
  commentaryMode: document.getElementById("commentaryMode"),
  commentaryText: document.getElementById("commentaryText"),
  startVoiceCommentary: document.getElementById("startVoiceCommentary"),
  stopVoiceCommentary: document.getElementById("stopVoiceCommentary"),
  memberList: document.getElementById("memberList"),
  memberForm: document.getElementById("memberForm"),
  memberTeamSelect: document.getElementById("memberTeamSelect"),
  memberTeamMemberships: document.getElementById("memberTeamMemberships"),
  scheduleBoard: document.getElementById("scheduleBoard"),
  visitingTeams: document.getElementById("visitingTeams"),
  uploadForm: document.getElementById("uploadForm"),
  resetScoresButton: document.getElementById("resetScoresButton"),
  uploadSeason: document.getElementById("uploadSeason"),
  uploadFile: document.getElementById("uploadFile"),
  archiveSearchInput: document.getElementById("archiveSearchInput"),
  archiveDateInput: document.getElementById("archiveDateInput"),
  archiveYearSelect: document.getElementById("archiveYearSelect"),
  archiveClearFilters: document.getElementById("archiveClearFilters"),
  archiveSearchSummary: document.getElementById("archiveSearchSummary"),
  archiveImportForm: document.getElementById("archiveImportForm"),
  archiveImportSelect: document.getElementById("archiveImportSelect"),
  archiveImportText: document.getElementById("archiveImportText"),
  archiveList: document.getElementById("archiveList"),
  duplicateList: document.getElementById("duplicateList"),
  archiveScorecards: document.getElementById("archiveScorecards"),
  archiveApplyForm: document.getElementById("archiveApplyForm"),
  archiveSelect: document.getElementById("archiveSelect"),
  archiveHeartlakeRunsInput: document.getElementById("archiveHeartlakeRunsInput"),
  archiveHeartlakeWicketsInput: document.getElementById("archiveHeartlakeWicketsInput"),
  archiveHeartlakeOversInput: document.getElementById("archiveHeartlakeOversInput"),
  archiveOpponentRunsInput: document.getElementById("archiveOpponentRunsInput"),
  archiveOpponentWicketsInput: document.getElementById("archiveOpponentWicketsInput"),
  archiveOpponentOversInput: document.getElementById("archiveOpponentOversInput"),
  archiveResultInput: document.getElementById("archiveResultInput"),
  archiveSourceNoteInput: document.getElementById("archiveSourceNoteInput"),
  chatMessages: document.getElementById("chatMessages"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
};

window.sessionStorage.setItem("heartlakeChatSessionId", state.chatSessionId);

async function getJson(url) {
  const token = window.localStorage.getItem("heartlakeAuthToken") || getCookieValue("heartlakeAuthToken") || "";
  const response = await fetch(url, {
    headers: token ? { "X-Auth-Token": token } : undefined,
  });
  if (!response.ok) throw new Error("Request failed");
  return response.json();
}

async function postJson(url, payload) {
  const token = window.localStorage.getItem("heartlakeAuthToken") || getCookieValue("heartlakeAuthToken") || "";
  const response = await fetch(url, {
    method: "POST",
    headers: token ? { "Content-Type": "application/json", "X-Auth-Token": token } : { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const message = await response.text();
    let parsed = null;
    try {
      parsed = JSON.parse(message);
    } catch {}
    throw new Error(parsed?.detail || parsed?.message || message || "Request failed");
  }
  return response.json();
}

function setStatus(message, tone = "info") {
  if (!message) {
    elements.statusBanner.hidden = true;
    elements.statusBanner.textContent = "";
    elements.statusBanner.className = "status-banner";
    return;
  }
  elements.statusBanner.hidden = false;
  elements.statusBanner.textContent = message;
  elements.statusBanner.className = `status-banner ${tone}`;
  window.clearTimeout(statusTimer);
  statusTimer = window.setTimeout(() => {
    elements.statusBanner.hidden = true;
  }, 5000);
}

function saveExpandedLists() {
  window.sessionStorage.setItem("heartlakeExpandedLists", JSON.stringify(state.expandedLists || {}));
}

function isListExpanded(key) {
  return Boolean(state.expandedLists?.[key]);
}

function setListExpanded(key, expanded) {
  state.expandedLists ||= {};
  if (expanded) {
    state.expandedLists[key] = true;
  } else {
    delete state.expandedLists[key];
  }
  saveExpandedLists();
}

function renderLimitedCollection(items, { key, renderItem, emptyMessage, limit = DEFAULT_LIST_LIMIT, wrapperClass = "" }) {
  if (!items.length) {
    return emptyMessage;
  }
  const expanded = isListExpanded(key);
  const shownItems = expanded ? items : items.slice(0, limit);
  const hiddenCount = Math.max(items.length - shownItems.length, 0);
  const body = shownItems.map(renderItem).join("");
  const wrappedBody = wrapperClass ? `<div class="${wrapperClass}">${body}</div>` : body;
  const toggle =
    items.length > limit
      ? `<div class="list-actions"><button class="secondary-button list-toggle-button" type="button" data-list-toggle="${key}">${expanded ? "Show less" : `Load ${hiddenCount} more`}</button></div>`
      : "";
  return `${wrappedBody}${toggle}`;
}

function statsByPlayer() {
  return Object.fromEntries((state.dashboard?.all_player_stats || state.dashboard?.player_stats || []).map((item) => [item.player_name, item]));
}

function combinedStatsByPlayer() {
  return Object.fromEntries((state.dashboard?.all_combined_player_stats || state.dashboard?.combined_player_stats || []).map((item) => [item.player_name, item]));
}

function displayPlayerName(member) {
  if (!member) return "";
  return member.full_name || member.name || "";
}

function focusClubName() {
  return state.dashboard?.focus_club?.name || state.dashboard?.club?.name || "Selected club";
}

function focusClubShortName() {
  return state.dashboard?.focus_club?.short_name || state.dashboard?.club?.short_name || focusClubName();
}

function clubScopedApi(path) {
  const focus = state.selectedFocusClubId || "";
  return focus ? `${path}?focus_club_id=${encodeURIComponent(focus)}` : path;
}

function isPlayerFollowed(playerName) {
  return Boolean(state.dashboard?.viewer_profile?.followed_player_names?.includes(playerName));
}

async function runAction(action, successMessage = "") {
  try {
    const result = await action();
    if (successMessage) {
      setStatus(successMessage, "success");
    }
    return result;
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Something went wrong.", "error");
    return null;
  }
}

function currentMatch() {
  return (
    state.dashboard.fixtures.find((match) => match.id === state.selectedMatchId) ||
    state.dashboard.fixtures[0] || {
      id: "",
      date_label: "No club match selected",
      opponent: "No fixture",
      status: "Scheduled",
      heartlake_captain: "",
      availability: [],
      availability_statuses: {},
      availability_notes: {},
      performances: [],
      commentary: [],
      details: {
        venue: "No fixture for the selected club yet.",
        match_type: "",
        scheduled_time: "",
        overs: "",
        toss_winner: "",
        toss_decision: "",
        weather: "",
        umpires: "",
        scorer: "",
        whatsapp_thread: "",
        notes: "",
      },
      scorecard: {
        heartlake_runs: "",
        heartlake_wickets: "",
        heartlake_overs: "",
        opponent_runs: "",
        opponent_wickets: "",
        opponent_overs: "",
        result: "No fixture yet",
        live_summary: "",
      },
      scorebook: { innings: [] },
    }
  );
}

function currentPlayer() {
  const members = state.dashboard.all_members || state.dashboard.members || [];
  const viewerMemberName = getViewerMemberNameFromAuth();
  return (
    members.find((member) => member.name === state.selectedPlayerName) ||
    members.find((member) => member.name === viewerMemberName) ||
    members[0] ||
    null
  );
}

function getViewerMemberNameFromAuth() {
  const members = state.dashboard?.all_members || state.dashboard?.members || [];
  const viewerMemberId = state.viewerAuth?.user?.member_id || "";
  if (!viewerMemberId) {
    return "";
  }
  const viewerMember = members.find((member) => member.id === viewerMemberId);
  return viewerMember?.name || "";
}

function viewerMemberName(dashboard) {
  const members = dashboard.all_members || dashboard.members || [];
  const viewerMemberId = state.viewerAuth?.user?.member_id || dashboard.user?.member_id || "";
  if (!viewerMemberId) {
    return "";
  }
  const viewerMember = members.find((member) => member.id === viewerMemberId);
  return viewerMember?.name || "";
}

function currentSignedInMemberName(dashboard = state.dashboard) {
  if (!dashboard) return "";
  const members = dashboard.all_members || dashboard.members || [];
  const viewerMemberId = state.viewerAuth?.user?.member_id || dashboard.user?.member_id || "";
  if (viewerMemberId) {
    const matchById = members.find((member) => String(member.id || "") === String(viewerMemberId));
    if (matchById?.name) return matchById.name;
  }
  const viewerName = viewerMemberName(dashboard);
  if (viewerName) return viewerName;
  const authName = String(state.viewerAuth?.user?.display_name || dashboard.user?.display_name || "").trim();
  return authName ? authName : members[0]?.name || "";
}

function canManageOtherAvailability() {
  const role = String(state.dashboard?.user?.effective_role || "").trim();
  return role === "captain" || role === "superadmin";
}

function currentAvailabilityPlayerName() {
  const selfName = currentSignedInMemberName();
  if (!state.canManageOtherAvailability) {
    return selfName;
  }
  return (
    state.selectedAvailabilityPlayerName ||
    elements.availabilityPlayerSelect.value ||
    state.selectedPlayerName ||
    selfName ||
    state.dashboard?.members?.[0]?.name ||
    ""
  );
}

function updateViewerPlayerSnapshot(dashboard) {
  if (!elements.viewerPlayerSnapshotLabel || !elements.viewerPlayerSnapshotTitle || !elements.viewerPlayerSnapshotDetails) {
    return;
  }
  const focusClub = dashboard.focus_club || dashboard.club || {};
  const summary = dashboard.summary || {};
  const yearLabel = state.selectedSeasonYear || String(new Date().getFullYear());
  elements.viewerPlayerSnapshotLabel.textContent = `Clubs Summary for ${yearLabel}`;
  elements.viewerPlayerSnapshotTitle.textContent = `${focusClub.name || "Club"} Clubs Summary`;
  elements.viewerPlayerSnapshotDetails.textContent = `Total Matches Played: ${summary.matches_played || 0} · Won: ${summary.matches_won || 0} · Lost: ${summary.matches_lost || 0} · NR: ${summary.matches_nr || 0}`;
}

function currentTeam() {
  return state.dashboard.teams.find((team) => team.name === state.selectedTeamName) || state.dashboard.teams[0] || null;
}

function currentScorebookInnings() {
  const match = currentMatch();
  const inningsNumber = Number(elements.scorebookInningsSelect.value || 1);
  const innings = match.scorebook?.innings || [];
  return innings.find((item) => Number(item.inning_number) === inningsNumber) || innings[0] || null;
}

function ensureScorebookSlotInputs() {
  if (!elements.scorebookBatters.children.length) {
    elements.scorebookBatters.innerHTML = Array.from({ length: 11 }, (_, index) => {
      const slot = index + 1;
      return `<label>Batter ${slot}<input type="text" data-batter-slot="${slot}" placeholder="Batter ${slot}" /></label>`;
    }).join("");
  }
  if (!elements.scorebookBowlers.children.length) {
    elements.scorebookBowlers.innerHTML = Array.from({ length: 11 }, (_, index) => {
      const slot = index + 1;
      return `<label>Bowler ${slot}<input type="text" data-bowler-slot="${slot}" placeholder="Bowler ${slot}" /></label>`;
    }).join("");
  }
}

function scorebookSummary(innings) {
  const balls = innings?.balls || [];
  let runs = 0;
  let wickets = 0;
  let legalBalls = 0;
  const batterMap = {};
  const bowlerMap = {};
  balls.forEach((ball) => {
    const runsBat = Number(ball.runs_bat || 0);
    const extrasRuns = Number(ball.extras_runs || 0);
    const striker = (ball.striker || "").trim();
    const bowler = (ball.bowler || "").trim();
    runs += runsBat + extrasRuns;
    if (!["wide", "no_ball"].includes((ball.extras_type || "none").toLowerCase())) {
      legalBalls += 1;
    }
    if (striker) {
      batterMap[striker] ||= { player_name: striker, runs: 0, balls: 0 };
      batterMap[striker].runs += runsBat;
      if (!["wide", "no_ball"].includes((ball.extras_type || "none").toLowerCase())) {
        batterMap[striker].balls += 1;
      }
    }
    if (bowler) {
      bowlerMap[bowler] ||= { player_name: bowler, legal_balls: 0, wickets: 0, runs: 0 };
      bowlerMap[bowler].runs += runsBat + extrasRuns;
      if (!["wide", "no_ball"].includes((ball.extras_type || "none").toLowerCase())) {
        bowlerMap[bowler].legal_balls += 1;
      }
      if (ball.wicket && !["run_out", "retired_hurt"].includes((ball.wicket_type || "").toLowerCase()) && (ball.wicket_player || "").trim()) {
        bowlerMap[bowler].wickets += 1;
      }
    }
    if (ball.wicket && (ball.wicket_player || "").trim()) {
      wickets += 1;
    }
  });
  return {
    runs,
    wickets,
    overs: `${Math.floor(legalBalls / 6)}.${legalBalls % 6}`,
    batters: Object.values(batterMap),
    bowlers: Object.values(bowlerMap).map((item) => ({
      ...item,
      overs: `${Math.floor(item.legal_balls / 6)}.${item.legal_balls % 6}`,
    })),
  };
}

function populateMatchSelects(fixtures) {
  const options = fixtures
    .map((match) => `<option value="${match.id}">${match.date_label} vs ${match.opponent}</option>`)
    .join("");
  elements.activeMatchSelect.innerHTML = options || `<option value="">No matches for this club yet</option>`;
  elements.activeMatchSelect.value = state.selectedMatchId || "";
  elements.activeMatchSelect.disabled = !fixtures.length;
}

function populatePlayerSelects(members, allMembers = members) {
  const options = members
    .map((member) => {
      const aliasText = (member.aliases || []).length ? ` · ${(member.aliases || []).join(", ")}` : "";
      return `<option value="${member.name}">${member.name}${aliasText}</option>`;
    })
    .join("");
  elements.availabilityPlayerSelect.innerHTML = options;
  elements.performancePlayerSelect.innerHTML = options;
  elements.playerProfileSelect.innerHTML = allMembers
    .map((member) => {
      const label = member.full_name ? `${member.name} (${member.full_name})` : member.name;
      return `<option value="${member.name}">${label}</option>`;
    })
    .join("");
  elements.playerProfileSelect.value = state.selectedPlayerName || allMembers[0]?.name || members[0]?.name || "";
  const currentName = currentSignedInMemberName();
  const availabilityChoice = state.canManageOtherAvailability
    ? (
        (state.selectedAvailabilityPlayerName && members.some((member) => member.name === state.selectedAvailabilityPlayerName)
          ? state.selectedAvailabilityPlayerName
          : state.selectedPlayerName && members.some((member) => member.name === state.selectedPlayerName)
            ? state.selectedPlayerName
            : members[0]?.name || "")
      )
    : currentName || state.selectedPlayerName || members[0]?.name || "";
  elements.availabilityPlayerSelect.hidden = !state.canManageOtherAvailability;
  elements.availabilityPlayerSelect.disabled = !state.canManageOtherAvailability;
  elements.availabilityPlayerSelect.value = availabilityChoice;
  state.selectedAvailabilityPlayerName = availabilityChoice || state.selectedAvailabilityPlayerName || null;
  elements.performancePlayerSelect.value = availabilityChoice || members[0]?.name || "";
}

function populateTeamSelect(teams) {
  const options = teams
    .map((team) => `<option value="${team.name}">${team.display_name || team.name}</option>`)
    .join("");
  elements.memberTeamSelect.innerHTML = options;
  elements.editPlayerTeamName.innerHTML = options;
  elements.teamProfileSelect.innerHTML = teams
    .map((team) => `<option value="${team.name}">${team.display_name || team.name}</option>`)
    .join("");
  elements.teamProfileSelect.value = state.selectedTeamName;
}

function syncPlayerEditForm(player) {
  if (!player || !elements.playerEditForm) {
    return;
  }
  elements.editPlayerName.value = player.name || "";
  elements.editPlayerFullName.value = player.full_name || "";
  if (elements.editPlayerGender) {
    elements.editPlayerGender.value = player.gender || "";
  }
  elements.editPlayerAliases.value = (player.aliases || []).join(", ");
  elements.editPlayerTeamName.value = player.team_name || "Heartlake";
  elements.editPlayerTeamMemberships.value = (player.team_memberships || [])
    .map((membership) => (typeof membership === "string" ? membership : membership.display_name || membership.team_name || ""))
    .filter(Boolean)
    .join(", ");
  elements.editPlayerAge.value = player.age || "";
  elements.editPlayerRole.value = player.role || "";
  elements.editPlayerBattingStyle.value = player.batting_style || "";
  elements.editPlayerBowlingStyle.value = player.bowling_style || "";
  elements.editPlayerJerseyNumber.value = player.jersey_number || "";
  elements.editPlayerPhone.value = player.phone || "";
  elements.editPlayerEmail.value = player.email || "";
  elements.editPlayerPictureUrl.value = player.picture_url || "";
  elements.editPlayerNotes.value = player.notes || "";
}

function playerMembershipSummary(player) {
  const teamNames = [...new Set(
    (player.team_memberships || [])
      .filter((membership) => typeof membership !== "object" || (membership.team_type || "") !== "club")
      .map((membership) => (typeof membership === "string" ? membership : membership.team_name || membership.display_name || ""))
      .filter(Boolean)
  )];
  const clubMemberships = [...new Map(
    (player.club_memberships || [])
      .filter((membership) => membership && membership.club_name)
      .map((membership) => [membership.club_name, {
        club_name: membership.club_name,
        club_id: membership.club_id || "",
        teams: [...new Set(membership.teams || [])],
      }])
  ).values()];
  return { teamNames, clubMemberships };
}

function clubRankForPlayer(clubRanking, playerName, key) {
  const list = clubRanking?.[key] || [];
  return list.find((item) => item.player_name === playerName) || null;
}

function populateArchiveSelect(uploads) {
  const options = uploads.length
    ? uploads
        .map((upload) => `<option value="${upload.id}">${upload.file_name} · ${upload.status}</option>`)
        .join("")
    : `<option value="">No uploaded scorecards yet</option>`;
  elements.archiveSelect.innerHTML = options;
  elements.archiveImportSelect.innerHTML = options;
}

function archivePlayers(upload) {
  return (upload.suggested_performances || []).map((entry) => entry.player_name).filter(Boolean);
}

function archiveDateLabel(upload) {
  return upload.archive_date || (upload.photo_taken_at || "").slice(0, 10) || "";
}

function archiveVariantLabel(upload) {
  const count = Number(upload.family_hidden_count || 0);
  if (!count) {
    return "";
  }
  return `${count} sibling file variant${count === 1 ? "" : "s"} folded into this scorecard family`;
}

function archiveReviewStatus(item) {
  const status = String(item?.status || "").trim().toLowerCase();
  if (status.includes("approved") || status.includes("applied")) {
    return "Approved";
  }
  if (status.includes("pending")) {
    return "Pending review";
  }
  if (status.includes("review")) {
    return "Pending review";
  }
  return item?.status || "Pending review";
}

function archiveFiltersActive() {
  return Boolean(
    elements.archiveSearchInput.value.trim() || elements.archiveDateInput.value || elements.archiveYearSelect.value
  );
}

function filteredArchiveUploads(uploads) {
  const query = elements.archiveSearchInput.value.trim().toLowerCase();
  const selectedDate = elements.archiveDateInput.value;
  const selectedYear = elements.archiveYearSelect.value;
  return uploads.filter((upload) => {
    const archiveDate = archiveDateLabel(upload);
    const archiveYear = upload.archive_year || (archiveDate ? archiveDate.slice(0, 4) : "");
    if (selectedDate && archiveDate !== selectedDate) {
      return false;
    }
    if (selectedYear && archiveYear !== selectedYear) {
      return false;
    }
    if (!query) {
      return true;
    }
    const linkedMatch = state.dashboard.fixtures.find((match) => match.id === upload.match_id);
    const haystack = [
      upload.file_name,
      upload.season,
      upload.status,
      upload.extracted_summary,
      upload.raw_extracted_text,
      upload.archive_date,
      upload.scorecard_date,
      upload.archive_date_source,
      ...(upload.family_hidden_files || []),
      linkedMatch?.date_label,
      linkedMatch?.opponent,
      ...archivePlayers(upload),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });
}

function populateArchiveYearSelect(uploads) {
  const years = [...new Set(uploads.map((upload) => upload.archive_year).filter(Boolean))].sort().reverse();
  const options = ['<option value="">All years</option>']
    .concat(years.map((year) => `<option value="${year}">${year}</option>`))
    .join("");
  const previous = elements.archiveYearSelect.value;
  elements.archiveYearSelect.innerHTML = options;
  if (years.includes(previous)) {
    elements.archiveYearSelect.value = previous;
  }
}

function renderArchiveSearchSummary(filteredCount, totalCount) {
  if (!archiveFiltersActive()) {
    elements.archiveSearchSummary.textContent = `Archive search is ready. You can retrieve old scorecards by player, exact date, or year across ${totalCount} files.`;
    return;
  }
  elements.archiveSearchSummary.textContent = `Showing ${filteredCount} of ${totalCount} archived scorecards for the current filters.`;
}

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = text;
  elements.chatMessages.appendChild(div);
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
  state.chatHistory.push({ role, text });
  state.chatHistory = state.chatHistory.slice(-12);
  window.sessionStorage.setItem("heartlakeChatHistory", JSON.stringify(state.chatHistory));
}

function restoreChatHistory() {
  elements.chatMessages.innerHTML = "";
  for (const entry of state.chatHistory) {
    const div = document.createElement("div");
    div.className = `message ${entry.role}`;
    div.textContent = entry.text;
    elements.chatMessages.appendChild(div);
  }
  elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function statusBadge(status) {
  const cls = status === "available" ? "yes" : status === "maybe" ? "maybe" : "no";
  return `<span class="status-pill ${cls}">${status}</span>`;
}

function renderSummary(summary) {
  elements.summaryGrid.innerHTML = `
    <article class="summary-card"><span>Clubs Summary</span><strong>${state.dashboard?.focus_club?.name || state.dashboard?.club?.name || "Club"}</strong><p>Total Matches Played: ${summary.matches_played || 0} · Won: ${summary.matches_won || 0} · Lost: ${summary.matches_lost || 0} · NR: ${summary.matches_nr || 0}</p></article>
    <article class="summary-card"><span>Fixtures</span><strong>${summary.fixture_count}</strong></article>
    <article class="summary-card"><span>Members</span><strong>${summary.member_count}</strong></article>
    <article class="summary-card"><span>Completed</span><strong>${summary.completed_matches}</strong></article>
    <article class="summary-card"><span>Live Matches</span><strong>${summary.live_matches}</strong></article>
    <article class="summary-card"><span>Captains Needed</span><strong>${summary.matches_without_captain}</strong></article>
    <article class="summary-card"><span>Archive Uploads</span><strong>${summary.archive_count}</strong></article>
    <article class="summary-card"><span>Duplicates</span><strong>${summary.duplicate_count || 0}</strong></article>
    <article class="summary-card"><span>Batting Leader</span><strong>${summary.batting_leader || "TBD"}</strong><p>${summary.batting_leader_runs || 0} runs</p></article>
    <article class="summary-card"><span>Wicket Leader</span><strong>${summary.wicket_leader || "TBD"}</strong><p>${summary.wicket_leader_count || 0} wickets</p></article>
    <article class="summary-card"><span>Fielding Leader</span><strong>${summary.fielding_leader || "TBD"}</strong><p>${summary.fielding_leader_count || 0} catches</p></article>
  `;
}

function populatePrimaryClubSelect(clubs) {
  elements.primaryClubSelect.innerHTML = (clubs || [])
    .map((club) => `<option value="${club.id}">${club.name}</option>`)
    .join("");
  const selectedId = state.selectedFocusClubId || state.dashboard?.viewer_profile?.primary_club_id || clubs?.[0]?.id || "";
  elements.primaryClubSelect.value = selectedId;
}

function renderLandingClubStats(stats) {
  elements.landingClubStats.innerHTML = `
    <article class="summary-card"><span>Members</span><strong>${stats.member_count || 0}</strong></article>
    <article class="summary-card"><span>Teams</span><strong>${stats.team_count || 0}</strong></article>
    <article class="summary-card"><span>Fixtures</span><strong>${stats.fixture_count || 0}</strong></article>
    <article class="summary-card"><span>Archives</span><strong>${stats.archive_count || 0}</strong></article>
    <article class="summary-card"><span>Top Batter</span><strong>${stats.top_batter || "TBD"}</strong><p>${stats.top_batter_runs || 0} runs</p></article>
  `;
}

function renderLandingEvents(items) {
  elements.landingEvents.innerHTML = renderLimitedCollection(items || [], {
    key: "landing-events",
    emptyMessage: `<p class="empty-state">No upcoming events stored for this club yet.</p>`,
    renderItem: (item) => `
      <article class="detail-card">
        <strong>${item.title}</strong>
        <small>${item.subtitle || "Schedule details coming soon."}</small>
      </article>
    `,
  });
}

function renderLandingMatches(items) {
  elements.landingMatches.innerHTML = renderLimitedCollection(items || [], {
    key: "landing-matches",
    emptyMessage: `<p class="empty-state">No scheduled matches yet for the focused club.</p>`,
    renderItem: (match) => `
      <article class="detail-card clickable-card" data-match="${match.id}">
        <strong>${match.date_label}</strong>
        <p>vs ${match.opponent}</p>
        <small>${match.details?.venue || "Venue TBD"} · ${match.status}</small>
      </article>
    `,
  });
}

function renderClubDirectory(cards) {
  if (!elements.clubDirectory) {
    return;
  }
  elements.clubDirectory.innerHTML = renderLimitedCollection(cards || [], {
    key: "club-directory",
    emptyMessage: `<p class="empty-state">No clubs stored yet.</p>`,
    renderItem: (club) => `
      <article class="detail-card clickable-card" data-club="${club.id}">
        <strong>${club.name}</strong>
        <p>${club.member_count} players · ${club.team_count} teams · ${club.fixture_count} fixtures</p>
        <small>${club.top_batter ? `${club.top_batter} leads with ${club.top_batter_runs} runs` : "No batting leader yet."}</small>
      </article>
    `,
  });
}

function renderFollowedPlayers(items) {
  if (!elements.followedPlayers) {
    return;
  }
  elements.followedPlayers.innerHTML = renderLimitedCollection(items || [], {
    key: "followed-players",
    emptyMessage: `<p class="empty-state">Follow players to pin their stats here.</p>`,
    renderItem: (item) => `
      <article class="detail-card clickable-card" data-player="${item.player_name}">
        <strong>${item.full_name || item.player_name}</strong>
        <p>${item.matches || 0} matches</p>
        <small>${item.runs || 0} runs · ${item.wickets || 0} wickets · ${item.catches || 0} catches</small>
      </article>
    `,
  });
}

function renderClubSearchResults() {
  if (!elements.clubSearchInput || !elements.clubSearchResults) {
    return;
  }
  const query = elements.clubSearchInput.value.trim().toLowerCase();
  const clubs = state.dashboard?.clubs || [];
  const filtered = !query
    ? clubs
    : clubs.filter((club) => {
        const haystack = `${club.name || ""} ${club.short_name || ""} ${club.city || ""}`.toLowerCase();
        return haystack.includes(query);
      });
  elements.clubSearchResults.innerHTML = renderLimitedCollection(filtered, {
    key: "club-search-results",
    emptyMessage: `<p class="empty-state">No clubs match that search.</p>`,
    renderItem: (club) => `
      <article class="detail-card clickable-card ${club.id === state.selectedFocusClubId ? "active-card" : ""}" data-club="${club.id}">
        <strong>${club.name}</strong>
        <p>${club.city || "City TBD"} · ${club.season || "Season TBD"}</p>
        <small>${club.short_name || ""}</small>
      </article>
    `,
  });
}

function renderLandingPlayerResults() {
  const query = elements.landingPlayerSearchInput.value.trim().toLowerCase();
  const statMap = combinedStatsByPlayer();
  const members = state.dashboard?.all_members || state.dashboard?.members || [];
  const filtered = !query
    ? []
    : members.filter((member) => {
        const haystack = `${member.name || ""} ${member.full_name || ""} ${(member.aliases || []).join(" ")}`.toLowerCase();
        return haystack.includes(query);
      });
  elements.landingPlayerResults.innerHTML = query
    ? renderLimitedCollection(filtered, {
        key: "landing-player-results",
        emptyMessage: `<p class="empty-state">No players match that search.</p>`,
        renderItem: (member) => {
          const stats = statMap[member.name] || { runs: 0, matches: 0, wickets: 0, catches: 0 };
          return `
            <article class="detail-card">
              <strong>${displayPlayerName(member)}</strong>
              <p>${stats.matches || 0} matches</p>
              <small>${stats.runs || 0} runs · ${stats.wickets || 0} wickets · ${stats.catches || 0} catches</small>
              <div class="inline-actions">
                <button class="secondary-button" type="button" data-player-jump="${member.name}">Open profile</button>
                <button class="secondary-button" type="button" data-follow-player="${member.name}" data-following="${isPlayerFollowed(member.name) ? "false" : "true"}">${isPlayerFollowed(member.name) ? "Unfollow" : "Follow"}</button>
              </div>
            </article>
          `;
        },
      })
    : `<p class="empty-state">Search for a player to view quick stats and follow them.</p>`;
}

function renderViewerProfile(dashboard) {
  const profile = dashboard.viewer_profile || {};
  const focusClub = dashboard.focus_club || dashboard.club || {};
  state.selectedFocusClubId = focusClub.id || profile.primary_club_id || state.selectedFocusClubId;
  if (state.selectedFocusClubId) {
    window.localStorage.setItem("heartlakePrimaryClubId", state.selectedFocusClubId);
    document.cookie = `heartlakePrimaryClubId=${encodeURIComponent(state.selectedFocusClubId)}; path=/; samesite=lax`;
  }
  elements.viewerDisplayNameInput.value = profile.display_name || "";
  elements.viewerMobileInput.value = profile.mobile || "";
  elements.viewerEmailInput.value = profile.email || "";
  document.title = `${focusClub.name || "Club"} Matchday Hub`;
  elements.heroEyebrow.textContent = `${focusClub.short_name || focusClub.name || "Club"} Matchday Hub`;
  elements.focusClubBadge.textContent = `Primary club: ${focusClub.name || dashboard.club.name || "Heartlake Cricket Club"}`;
  populatePrimaryClubSelect(dashboard.clubs || []);
  renderLandingPlayerResults();
  renderLandingEvents(dashboard.landing_upcoming_events || []);
  renderLandingMatches(dashboard.landing_upcoming_matches || []);
  renderLandingClubStats(dashboard.landing_club_stats || {});
}

function renderSelectedMatch(match) {
  const clubName = focusClubName();
  elements.matchCenterHeading.textContent = `${clubName} match center`;
  elements.selectedScorecardTitle.textContent = `${clubName} scorecard`;
  elements.selectedAvailabilityTitle.textContent = `${clubName} confirmed availability`;
  elements.selectedMatchSnapshot.innerHTML = `
    <article class="snapshot-card">
      <div>
        <p class="snapshot-label">${clubName} · ${match.date_label}</p>
        <h3>${clubName} vs ${match.opponent}</h3>
        <p>${match.details.venue} · ${match.details.match_type} · ${match.details.scheduled_time}</p>
      </div>
      <div class="snapshot-side">
        <span class="fixture-badge">${match.status}</span>
        <p>Captain: ${match.heartlake_captain || "Unassigned"}</p>
      </div>
    </article>
  `;

  elements.selectedScorecard.innerHTML = `
    <article class="detail-card">
      <strong>${focusClubShortName()}</strong>
      <p>${match.scorecard.heartlake_runs || "--"}/${match.scorecard.heartlake_wickets || "--"} in ${match.scorecard.heartlake_overs || "--"} overs</p>
    </article>
    <article class="detail-card">
      <strong>${match.opponent}</strong>
      <p>${match.scorecard.opponent_runs || "--"}/${match.scorecard.opponent_wickets || "--"} in ${match.scorecard.opponent_overs || "--"} overs</p>
    </article>
    <article class="detail-card wide">
      <strong>Result</strong>
      <p>${match.scorecard.result || "TBD"}</p>
      <small>${match.scorecard.live_summary || "No live summary yet."}</small>
    </article>
  `;

  const availabilityEntries = Object.entries(match.availability_statuses)
    .map(([player, status]) => {
      const note = match.availability_notes[player] ? ` · ${match.availability_notes[player]}` : "";
      return `<article class="detail-card"><strong>${player}</strong><p>${status}${note}</p></article>`;
    })
    .join("");
  elements.selectedAvailability.innerHTML = availabilityEntries || `<p class="empty-state">No availability set.</p>`;

  elements.selectedPerformances.innerHTML = renderLimitedCollection(match.performances || [], {
    key: `selected-performances-${match.id}`,
    emptyMessage: `<p class="empty-state">No player performances saved for this match yet.</p>`,
    renderItem: (item) => `
      <article class="detail-card">
        <strong>${item.player_name}</strong>
        <p>${item.runs} runs · ${item.wickets} wickets · ${item.catches} catches</p>
        <small>${item.notes || item.source}</small>
      </article>
    `,
  });

  const commentaryItems = (match.commentary || []).slice().reverse();
  elements.selectedCommentary.innerHTML = renderLimitedCollection(commentaryItems, {
    key: `selected-commentary-${match.id}`,
    emptyMessage: `<p class="empty-state">No commentary entries yet.</p>`,
    renderItem: (entry) => `
      <article class="detail-card">
        <strong>${entry.mode}</strong>
        <p>${entry.text}</p>
        <small>${entry.created_at}</small>
      </article>
    `,
  });
}

function renderFormValues(match) {
  const clubShort = focusClubShortName();
  elements.captainInput.placeholder = `${clubShort} captain`;
  elements.heartlakeRunsInput.placeholder = `${clubShort} runs`;
  elements.heartlakeWicketsInput.placeholder = `${clubShort} wickets`;
  elements.heartlakeOversInput.placeholder = `${clubShort} overs`;
  elements.archiveHeartlakeRunsInput.placeholder = `${clubShort} runs`;
  elements.archiveHeartlakeWicketsInput.placeholder = `${clubShort} wickets`;
  elements.archiveHeartlakeOversInput.placeholder = `${clubShort} overs`;
  elements.captainInput.value = match.heartlake_captain || "";
  elements.venueInput.value = match.details.venue || "";
  elements.matchTypeInput.value = match.details.match_type || "";
  elements.scheduledTimeInput.value = match.details.scheduled_time || "";
  elements.oversInput.value = match.details.overs || "";
  elements.tossWinnerInput.value = match.details.toss_winner || "";
  elements.tossDecisionInput.value = match.details.toss_decision || "";
  elements.weatherInput.value = match.details.weather || "";
  elements.umpiresInput.value = match.details.umpires || "";
  elements.scorerInput.value = match.details.scorer || "";
  elements.whatsappThreadInput.value = match.details.whatsapp_thread || "";
  elements.matchStatusInput.value = match.status || "Scheduled";
  elements.matchNotesInput.value = match.details.notes || "";
  elements.heartlakeRunsInput.value = match.scorecard.heartlake_runs || "";
  elements.heartlakeWicketsInput.value = match.scorecard.heartlake_wickets || "";
  elements.heartlakeOversInput.value = match.scorecard.heartlake_overs || "";
  elements.opponentRunsInput.value = match.scorecard.opponent_runs || "";
  elements.opponentWicketsInput.value = match.scorecard.opponent_wickets || "";
  elements.opponentOversInput.value = match.scorecard.opponent_overs || "";
  elements.resultInput.value = match.scorecard.result || "";
  elements.liveSummaryInput.value = match.scorecard.live_summary || "";
}

function renderScorebook(match) {
  ensureScorebookSlotInputs();
  const inningsList = match.scorebook?.innings || [];
  const inningsNumber = Number(elements.scorebookInningsSelect.value || 1);
  const innings =
    inningsList.find((item) => Number(item.inning_number) === inningsNumber) ||
    inningsList[0] || {
      inning_number: inningsNumber,
      batting_team: "Heartlake",
      bowling_team: match.opponent || "Opponent",
      overs_limit: Number(match.details?.overs || 20),
      status: "Not started",
      target_runs: null,
      batters: [],
      bowlers: [],
      balls: [],
    };

  elements.scorebookBattingTeamInput.value = innings.batting_team || "";
  elements.scorebookBowlingTeamInput.value = innings.bowling_team || "";
  elements.scorebookOversLimitInput.value = innings.overs_limit || Number(match.details?.overs || 20);
  elements.scorebookTargetRunsInput.value = innings.target_runs || "";
  elements.scorebookStatusInput.value = innings.status || "Not started";

  const batterMap = Object.fromEntries((innings.batters || []).map((item) => [Number(item.slot_number), item.player_name || ""]));
  const bowlerMap = Object.fromEntries((innings.bowlers || []).map((item) => [Number(item.slot_number), item.player_name || ""]));
  elements.scorebookBatters.querySelectorAll("[data-batter-slot]").forEach((input) => {
    input.value = batterMap[Number(input.dataset.batterSlot)] || "";
  });
  elements.scorebookBowlers.querySelectorAll("[data-bowler-slot]").forEach((input) => {
    input.value = bowlerMap[Number(input.dataset.bowlerSlot)] || "";
  });

  const summary = scorebookSummary(innings);
  elements.scorebookSummary.innerHTML = `
    <article class="summary-card"><span>Innings</span><strong>${innings.inning_number}</strong><p>${innings.batting_team || "Batting team"} vs ${innings.bowling_team || "Bowling team"}</p></article>
    <article class="summary-card"><span>Score</span><strong>${summary.runs}/${summary.wickets}</strong><p>${summary.overs} overs</p></article>
    <article class="summary-card"><span>Overs Limit</span><strong>${innings.overs_limit || 20}</strong><p>Status: ${innings.status || "Not started"}</p></article>
    <article class="summary-card"><span>Target</span><strong>${innings.target_runs || "--"}</strong><p>${(innings.balls || []).length} deliveries logged</p></article>
  `;

  const battingCards = summary.batters.length
    ? summary.batters
        .map((item) => `<article class="detail-card"><strong>${item.player_name}</strong><p>${item.runs} runs off ${item.balls}</p></article>`)
        .join("")
    : `<p class="empty-state">No batter entries recorded from deliveries yet.</p>`;
  const bowlingCards = summary.bowlers.length
    ? summary.bowlers
        .map((item) => `<article class="detail-card"><strong>${item.player_name}</strong><p>${item.overs} overs · ${item.runs} runs · ${item.wickets} wickets</p></article>`)
        .join("")
    : `<p class="empty-state">No bowler entries recorded from deliveries yet.</p>`;
  const recentBalls = (innings.balls || []).length
    ? innings.balls
        .slice()
        .reverse()
        .slice(0, 12)
        .map((ball) => {
          const extrasLabel =
            ball.extras_type && ball.extras_type !== "none" ? ` + ${ball.extras_runs} ${String(ball.extras_type).replace("_", " ")}` : "";
          const wicketLabel = ball.wicket
            ? ` · Wicket${ball.wicket_player ? `: ${ball.wicket_player}` : ""}${ball.fielder ? ` · Fielder: ${ball.fielder}` : ""}`
            : "";
          return `
            <article class="history-card scorebook-ball">
              <strong>${ball.over_number}.${ball.ball_number}</strong>
              <div>
                <p>${ball.striker || "Striker"} vs ${ball.bowler || "Bowler"} · ${ball.runs_bat} run(s)${extrasLabel}${wicketLabel}</p>
                <small>${ball.commentary || "No extra commentary for this ball."}</small>
              </div>
            </article>
          `;
        })
        .join("")
    : `<p class="empty-state">No deliveries logged for this innings yet.</p>`;
  elements.scorebookRecentBalls.innerHTML = `
    <div>
      <h3>Batting card</h3>
      <div class="detail-stack">${battingCards}</div>
    </div>
    <div>
      <h3>Bowling card</h3>
      <div class="detail-stack">${bowlingCards}</div>
    </div>
    <div>
      <h3>Recent balls</h3>
      <div class="player-history">${recentBalls}</div>
    </div>
  `;
}

function renderMembers(members) {
  const statMap = statsByPlayer();
  const pendingMap = Object.fromEntries((state.dashboard.player_pending_stats || []).map((item) => [item.player_name, item]));
  elements.memberList.innerHTML = renderLimitedCollection(members, {
    key: "member-list",
    emptyMessage: `<p class="empty-state">No team members yet.</p>`,
    renderItem: (member) => {
      const avatar = member.picture_url
        ? `<img class="avatar-image" src="${member.picture_url}" alt="${member.name}" />`
        : `<div class="avatar-fallback">${member.picture}</div>`;
      const displayName = member.full_name ? `${member.name} (${member.full_name})` : member.name;
      const aliases = (member.aliases || []).length ? `<small>Aliases: ${(member.aliases || []).join(", ")}</small>` : "";
      const stats = statMap[member.name] || { runs: 0, wickets: 0, catches: 0, matches: 0 };
      const pending = pendingMap[member.name] || { runs: 0, matches: 0 };
      const storedRuns = Number(stats.runs || 0) + Number(pending.runs || 0);
      return `
        <article class="member-card clickable-card" data-player="${member.name}">
          ${avatar}
          <div>
            <h3>${displayName}</h3>
            <p>${member.role} · Age ${member.age || "TBD"} · Jersey ${member.jersey_number || "--"}</p>
            <p>${member.batting_style || "Batting style TBD"} / ${member.bowling_style || "Bowling style TBD"}</p>
            <p class="member-stats">${storedRuns} stored runs · ${stats.wickets} wickets · ${stats.matches} applied matches</p>
            <small>${pending.runs ? `${stats.runs} confirmed + ${pending.runs} reviewed historical archive runs` : `${stats.runs} confirmed runs`}</small>
            <small>${member.phone || ""} ${member.email ? "· " + member.email : ""}</small>
            ${aliases}
            <small>${member.notes || ""}</small>
          </div>
        </article>
      `;
    },
  });
}

function renderSchedule(fixtures) {
  elements.scheduleBoard.innerHTML = renderLimitedCollection(fixtures, {
    key: "schedule-board",
    emptyMessage: `<p class="empty-state">No fixtures scheduled yet.</p>`,
    renderItem: (match) => `
      <article class="schedule-card clickable-card ${match.id === state.selectedMatchId ? "active-card" : ""}" data-match="${match.id}">
        <strong>${match.date_label}</strong>
        <p>vs ${match.opponent}</p>
        <p>${match.status} · ${match.availability.length} available</p>
        <p>${match.heartlake_score || "--"} / ${match.opponent_score || "--"}</p>
      </article>
    `,
  });
}

function renderVisitingTeams(teams) {
  elements.visitingTeams.innerHTML = renderLimitedCollection(teams, {
    key: "visiting-teams",
    emptyMessage: `<p class="empty-state">No visiting teams yet.</p>`,
    renderItem: (team) => `
      <article class="visiting-card">
        <strong>${team.name}</strong>
        <p>${team.fixture_count} fixtures</p>
        <small>Next: ${team.next_date}</small>
      </article>
    `,
  });
}

function renderAvailabilityMatrix(board, fixtures) {
  if (!state.canManageOtherAvailability) {
    elements.availabilityMatrix.hidden = true;
    elements.availabilityMatrix.innerHTML = "";
    return;
  }
  elements.availabilityMatrix.hidden = false;
  const activeClubId = state.selectedFocusClubId || state.dashboard?.focus_club?.id || state.dashboard?.club?.id || "";
  const scopedFixtures = activeClubId ? fixtures.filter((match) => (match.club_id || "") === activeClubId) : fixtures;
  const scopedBoard = board?.map((row) => ({
    ...row,
    by_match: activeClubId
      ? row.by_match.filter((item) => scopedFixtures.some((match) => match.id === item.match_id))
      : row.by_match,
  }));
  const head = scopedFixtures
    .map((match) => {
      const title = match.date || match.date_label || "Date TBD";
      return `<th title="${title}"><span class="stacked-head">${match.date_label || "Date TBD"}</span></th>`;
    })
    .join("");
  const rows = scopedBoard
    .map((row) => {
      const cells = row.by_match.map((item) => `<td>${statusBadge(item.status)}</td>`).join("");
      return `<tr><th>${row.player_name}</th>${cells}</tr>`;
    })
    .join("");
  elements.availabilityMatrix.innerHTML = `
    <table class="matrix-table">
      <thead>
        <tr><th>Player</th>${head}</tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderAvailabilityFixtureEditor(fixtures) {
  if (!elements.availabilityFixturesEditor) {
    return;
  }
  const activeClubId = state.selectedFocusClubId || state.dashboard?.focus_club?.id || state.dashboard?.club?.id || "";
  const scopedFixtures = activeClubId ? fixtures.filter((match) => (match.club_id || "") === activeClubId) : fixtures;
  const playerName = currentAvailabilityPlayerName();
  const cards = scopedFixtures.length
    ? scopedFixtures
        .map((fixture) => {
          const currentStatus = fixture.availability_statuses?.[playerName] || "no response";
          const currentNote = fixture.availability_notes?.[playerName] || "";
          return `
            <article class="detail-card" data-fixture-availability-card="${fixture.id}">
              <strong>${fixture.date_label} vs ${fixture.opponent}</strong>
              <p>${fixture.details?.venue || "Venue TBD"} · ${fixture.details?.scheduled_time || "Time TBD"}</p>
              <small>${state.canManageOtherAvailability ? (playerName ? `For ${playerName}` : "Choose a player above first") : `For ${playerName || "you"}`}</small>
              <small>Current status: ${currentStatus}${currentNote ? ` · ${currentNote}` : ""}</small>
              <form class="inline-actions" data-fixture-availability-form="${fixture.id}">
                <select name="status">
                  <option value="available" ${currentStatus === "available" ? "selected" : ""}>Available</option>
                  <option value="maybe" ${currentStatus === "maybe" ? "selected" : ""}>Maybe</option>
                  <option value="unavailable" ${currentStatus === "unavailable" ? "selected" : ""}>Unavailable</option>
                </select>
                <input type="text" name="note" value="${currentNote}" placeholder="Optional note" />
                <button class="secondary-button" type="submit">Save game</button>
              </form>
            </article>
          `;
        })
        .join("")
    : `<p class="empty-state">No fixtures are stored yet for this club.</p>`;
  elements.availabilityFixturesEditor.innerHTML = cards;
}

function formatMetric(value, decimals = 2) {
  const numeric = Number(value || 0);
  return Number.isFinite(numeric) ? numeric.toFixed(decimals).replace(/\.00$/, "") : "0";
}

function populateRankingYearSelect(dashboard) {
  const years = dashboard.season_years || dashboard.ranking_years || [];
  const defaultYear = dashboard.selected_season_year || dashboard.default_season_year || dashboard.default_ranking_year || years[0] || "";
  if (!state.selectedSeasonYear || !years.includes(state.selectedSeasonYear)) {
    state.selectedSeasonYear = defaultYear;
  }
  elements.rankingYearSelect.innerHTML = years
    .map((year) => `<option value="${year}">${year}</option>`)
    .join("");
  elements.rankingYearSelect.value = state.selectedSeasonYear || "";
}

function renderRankingSection(title, rows, renderer, emptyMessage) {
  const content = renderLimitedCollection(rows, {
    key: `ranking-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    emptyMessage: `<p class="empty-state">${emptyMessage}</p>`,
    wrapperClass: "leaderboard ranking-grid",
    renderItem: renderer,
  });
  return `
    <section class="ranking-section">
      <div class="panel-head compact-head">
        <div>
          <p class="section-kicker">Ranking</p>
          <h3>${title}</h3>
        </div>
      </div>
      ${content}
    </section>
  `;
}

function renderLeaderboard() {
  const selectedYear = state.selectedSeasonYear || state.dashboard.selected_season_year || state.dashboard.default_season_year || "";
  const battingRows = state.dashboard.batting_rankings || [];
  const bowlingRows = state.dashboard.bowling_rankings || [];
  const fieldingRows = state.dashboard.fielding_rankings || [];

  const battingSection = renderRankingSection(
    selectedYear ? `Batting Rankings · ${selectedYear}` : "Batting Rankings",
    battingRows,
    (item) => {
      return `
        <article class="leader-card clickable-card" data-player="${item.player_name}">
          <strong>#${item.rank} ${item.player_name}</strong>
          <p>${item.matches} stored matches · ${item.runs} stored runs</p>
          <p>${item.runs} stored runs · Avg ${formatMetric(item.batting_average)} · SR ${formatMetric(item.strike_rate)}</p>
          <small>${item.balls ? `${item.runs} off ${item.balls} balls` : "Strike rate waiting for ball data"}</small>
        </article>
      `;
    },
    selectedYear ? `No batting rankings yet for ${selectedYear}.` : "No batting rankings yet. Add or apply player batting scores first."
  );

  const bowlingSection = renderRankingSection(
    selectedYear ? `Bowling Rankings · ${selectedYear}` : "Bowling Rankings",
    bowlingRows,
    (item) => `
      <article class="leader-card clickable-card" data-player="${item.player_name}">
        <strong>#${item.rank} ${item.player_name}</strong>
        <p>${item.wickets} wickets in ${item.matches} stored matches</p>
        <p>${formatMetric(item.wickets_per_match)} wickets per match</p>
        <small>${item.runs} runs scored as batter · ${item.catches} catches</small>
      </article>
    `,
    selectedYear ? `No bowling rankings yet for ${selectedYear}.` : "No bowling rankings yet. Add wicket data from matches or applied archives first."
  );

  const fieldingSection = renderRankingSection(
    selectedYear ? `Fielding Rankings · ${selectedYear}` : "Fielding Rankings",
    fieldingRows,
    (item) => `
      <article class="leader-card clickable-card" data-player="${item.player_name}">
        <strong>#${item.rank} ${item.player_name}</strong>
        <p>${item.catches} catches in ${item.matches} stored matches</p>
        <p>${formatMetric(item.catches_per_match)} catches per match</p>
        <small>${item.wickets} wickets · ${item.runs} runs</small>
      </article>
    `,
    selectedYear ? `No fielding rankings yet for ${selectedYear}.` : "No fielding rankings yet. Add catches to player performances first."
  );

  elements.playerLeaderboard.innerHTML = `${battingSection}${bowlingSection}${fieldingSection}`;
}

function currentViewerProfilePayload(selectedSeasonYear = state.selectedSeasonYear || "") {
  return {
    display_name: elements.viewerDisplayNameInput.value.trim() || state.dashboard?.viewer_profile?.display_name || "",
    mobile: elements.viewerMobileInput.value.trim() || state.dashboard?.viewer_profile?.mobile || "",
    email: elements.viewerEmailInput.value.trim() || state.dashboard?.viewer_profile?.email || "",
    primary_club_id: elements.primaryClubSelect.value || state.dashboard?.viewer_profile?.primary_club_id || "",
    selected_season_year: selectedSeasonYear || state.dashboard?.selected_season_year || "",
  };
}

function setLiveSeasonMode(isLiveSeason, selectedYear) {
  const lockedMessage = `Viewing ${selectedYear} season. Live scheduling, scoring, availability, and commentary are disabled for historical seasons.`;
  const activeMessage = `Viewing ${selectedYear} season. Live scheduling, scoring, availability, and commentary are enabled.`;
  document.querySelectorAll("[data-live-only]").forEach((section) => {
    section.classList.toggle("live-locked", !isLiveSeason);
    section.dataset.liveMode = isLiveSeason ? "live" : "historical";
    const controls = section.querySelectorAll("input, select, textarea, button");
    controls.forEach((control) => {
      if (isLiveSeason) {
        control.disabled = false;
      } else if (!control.closest(".archive-toolbar") && !control.closest(".archive-list") && !control.closest(".archive-scorecards")) {
        control.disabled = true;
      }
    });
    let note = section.querySelector(".mode-note");
    if (!note) {
      note = document.createElement("p");
      note.className = "mode-note";
      section.querySelector(".panel-head")?.insertAdjacentElement("afterend", note);
    }
    note.textContent = isLiveSeason ? activeMessage : lockedMessage;
  });
}

function getArchiveOpponentName(archive, focusClubName) {
  const directOpponent = String(archive.draft_scorecard?.opponent || archive.opponent || "").trim();
  if (directOpponent) {
    return directOpponent;
  }

  const liveSummary = String(archive.draft_scorecard?.live_summary || archive.extracted_summary || archive.raw_extracted_text || "").trim();
  const match = /Batting team:\s*([^|]+)\|[^|]*\|?\s*Bowling team:\s*([^|]+)/i.exec(liveSummary);
  if (match) {
    const battingTeam = match[1].trim();
    const bowlingTeam = match[2].trim();
    const focus = String(focusClubName || "").trim();
    if (focus && battingTeam.toLowerCase() === focus.toLowerCase()) return bowlingTeam;
    if (focus && bowlingTeam.toLowerCase() === focus.toLowerCase()) return battingTeam;
    return bowlingTeam || battingTeam;
  }

  const filename = String(archive.file_name || "").trim();
  const fileMatch = /_(.+?)_vs_(.+?)(?:_|\.json|$)/i.exec(filename);
  if (fileMatch) {
    const teamA = fileMatch[1].replace(/[-_]/g, " ").trim();
    const teamB = fileMatch[2].replace(/[-_]/g, " ").trim();
    const focus = String(focusClubName || "").trim().toLowerCase();
    if (focus && teamA.toLowerCase().includes(focus)) return teamB;
    if (focus && teamB.toLowerCase().includes(focus)) return teamA;
    return teamB || teamA;
  }

  const clubName = String(archive.club_name || "").trim();
  if (clubName) {
    return clubName;
  }
  return "last match";
}

function getHistoricalSeasonSummary(dashboard) {
  const archives = Array.isArray(dashboard.archive_uploads) ? dashboard.archive_uploads : [];
  const archiveCount = archives.length;
  const latestArchive = archives
    .filter((archive) => archive.archive_date || archive.scorecard_date || archive.created_at)
    .sort((a, b) => {
      const aDate = new Date(a.archive_date || a.scorecard_date || a.created_at || "");
      const bDate = new Date(b.archive_date || b.scorecard_date || b.created_at || "");
      return bDate - aDate;
    })[0];
  if (!latestArchive) {
    return {
      headline: archiveCount ? `Historical season · ${archiveCount} archive${archiveCount === 1 ? "" : "s"}` : "Historical season view",
      details: archiveCount ? `${archiveCount} archived scorecard${archiveCount === 1 ? "" : "s"}` : "No archived match scorecards found for this season.",
    };
  }
  const focusClubName = dashboard.focus_club?.name || dashboard.club?.name || "";
  const opponent = getArchiveOpponentName(latestArchive, focusClubName);
  const result =
    latestArchive.draft_scorecard?.result ||
    latestArchive.extracted_summary ||
    latestArchive.draft_scorecard?.live_summary ||
    latestArchive.status ||
    "";
  const reducedResult = String(result).split("\n")[0].trim();
  return {
    headline: opponent ? `Last Match: vs ${opponent}` : "Last Match",
    details: reducedResult || `${archiveCount} archived scorecard${archiveCount === 1 ? "" : "s"}`,
  };
}

function getPlayerAvailabilitySummary(playerName) {
  return state.dashboard.availability_board.find((row) => row.player_name === playerName);
}

function getPlayerSeasonProfile(playerName) {
  const members = state.dashboard.all_members || state.dashboard.members || [];
  const player = members.find((member) => member.name === playerName);
  const combinedRecords = state.dashboard.all_combined_player_stats || state.dashboard.combined_player_stats || [];
  const combinedRecord = combinedRecords.find((item) => item.player_name === playerName) || {
    batting_average: 0,
    strike_rate: 0,
    batting_innings: 0,
    outs: 0,
  };
  const membershipSummary = playerMembershipSummary(player || {});
  const clubIdSet = new Set((membershipSummary.clubMemberships || []).map((club) => club.club_id).filter(Boolean));
  const clubNameSet = new Set((membershipSummary.clubMemberships || []).map((club) => club.club_name).filter(Boolean));
  const pendingRecords = state.dashboard.player_pending_stats || state.dashboard.all_player_pending_stats || [];
  const pending = pendingRecords.find((item) => item.player_name === playerName) || {
    player_name: playerName,
    runs: 0,
    wickets: 0,
    catches: 0,
    matches: 0,
    sources: [],
  };
  const allFixtures = state.dashboard.all_fixtures || state.dashboard.fixtures || [];
  const relevantFixtures = membershipSummary.clubMemberships.length
    ? allFixtures.filter((match) => {
        const matchClubId = match.club_id || match.details?.club_id || "";
        const matchClubName = match.club_name || match.details?.club_name || "";
        return (matchClubId && clubIdSet.has(matchClubId)) || (matchClubName && clubNameSet.has(matchClubName));
      })
    : allFixtures;
  const appearances = [];
  let runs = 0;
  let balls = 0;
  let wickets = 0;
  let catches = 0;
  let fours = 0;
  let sixes = 0;
  let matchesAvailable = 0;
  let matchesMaybe = 0;
  let matchesUnavailable = 0;
  let matchesNoResponse = 0;
  const fixtureSortValue = (value) => {
    const parsed = Date.parse(value || "");
    return Number.isFinite(parsed) ? parsed : 0;
  };

  relevantFixtures.forEach((match) => {
    const entries = (match.performances || []).filter((item) => item.player_name === playerName);
    const availabilityStatus = match.availability_statuses?.[playerName] || "no response";
    if (availabilityStatus === "available") {
      matchesAvailable += 1;
    } else if (availabilityStatus === "maybe") {
      matchesMaybe += 1;
    } else if (availabilityStatus === "unavailable") {
      matchesUnavailable += 1;
    } else {
      matchesNoResponse += 1;
    }
    const totals = entries.reduce(
      (acc, item) => {
        acc.runs += Number(item.runs || 0);
        acc.balls += Number(item.balls || 0);
        acc.wickets += Number(item.wickets || 0);
        acc.catches += Number(item.catches || 0);
        acc.fours += Number(item.fours || 0);
        acc.sixes += Number(item.sixes || 0);
        return acc;
      },
      { runs: 0, balls: 0, wickets: 0, catches: 0, fours: 0, sixes: 0 }
    );
    runs += totals.runs;
    balls += totals.balls;
    wickets += totals.wickets;
    catches += totals.catches;
    fours += totals.fours;
    sixes += totals.sixes;
    appearances.push({
      matchId: match.id,
      clubName: match.club_name || match.details?.club_name || state.dashboard.focus_club?.name || state.dashboard.club?.name || "Club",
      date: match.date || "",
      dateLabel: match.date_label,
      dateSort: fixtureSortValue(match.date),
      opponent: match.opponent,
      status: match.status,
      result: match.scorecard.result || match.result || "TBD",
      availability: availabilityStatus,
      played: entries.length > 0,
      ...totals,
      notes: entries.map((item) => item.notes).filter(Boolean).join(" · "),
    });
  });
  appearances.sort((a, b) => b.dateSort - a.dateSort || b.matchId.localeCompare(a.matchId));
  const playedAppearances = appearances.filter((item) => item.played);
  const upcomingGames = appearances
    .filter((item) => String(item.status || "").toLowerCase() === "scheduled" && item.dateSort >= fixtureSortValue(new Date().toISOString().slice(0, 10)))
    .slice()
    .sort((a, b) => a.dateSort - b.dateSort || a.matchId.localeCompare(b.matchId))
    .slice(0, 5);
  const lastGame = playedAppearances[0] || null;

  const clubRankings = membershipSummary.clubMemberships.map((club) => {
    const rankingBundle = state.dashboard.club_rankings?.[club.club_name] || {};
    return {
      club_name: club.club_name,
      teams: club.teams || [],
      batting: clubRankForPlayer(rankingBundle, playerName, "batting_rankings"),
      bowling: clubRankForPlayer(rankingBundle, playerName, "bowling_rankings"),
      fielding: clubRankForPlayer(rankingBundle, playerName, "fielding_rankings"),
    };
  });
  const availability = {
    matches_available: matchesAvailable,
    matches_maybe: matchesMaybe,
    matches_unavailable: matchesUnavailable,
    matches_no_response: matchesNoResponse,
    matches_total: relevantFixtures.length,
  };

  return {
    player,
    availability,
    memberships: membershipSummary,
    clubRankings,
    pending,
    appearances,
    upcomingGames,
    lastGame,
    totals: {
      runs,
      balls,
      wickets,
      catches,
      fours,
      sixes,
      innings: appearances.length,
      battingAverage: formatMetric(combinedRecord.batting_average || 0),
      strikeRate: formatMetric(combinedRecord.strike_rate || 0),
      storedRuns: runs + Number(pending.runs || 0),
      storedMatches: appearances.length + Number(pending.matches || 0),
      matchesAvailable,
      matchesMaybe,
      matchesUnavailable,
      matchesNoResponse,
    },
  };
}

function renderPlayerProfile() {
  const player = currentPlayer();
  if (!player) {
    return;
  }
  syncPlayerEditForm(player);
  const profile = getPlayerSeasonProfile(player.name);
  const displayName = player.full_name ? `${player.name} (${player.full_name})` : player.name;
  const availability = profile.availability;
  const clubsLabel = profile.memberships.clubMemberships.length
    ? profile.memberships.clubMemberships.map((club) => club.club_name).join(", ")
    : "No club memberships stored";
  const teamsLabel = profile.memberships.teamNames.length
    ? profile.memberships.teamNames.join(", ")
    : player.team_name || "No teams stored";
  const clubRankingCards = profile.clubRankings.length
    ? profile.clubRankings
        .map((club) => {
          const battingLabel = club.batting ? `#${club.batting.rank} batting` : "No batting rank yet";
          const bowlingLabel = club.bowling ? `#${club.bowling.rank} bowling` : "No bowling rank yet";
          const fieldingLabel = club.fielding ? `#${club.fielding.rank} fielding` : "No fielding rank yet";
          return `
            <article class="summary-card">
              <span>${club.club_name}</span>
              <strong>${battingLabel}</strong>
              <p>${bowlingLabel} · ${fieldingLabel}</p>
              <small>${(club.teams || []).join(", ") || "No teams mapped"}</small>
            </article>
          `;
        })
        .join("")
    : `<article class="summary-card"><span>Club Rankings</span><strong>No club memberships yet</strong><p>Add team memberships from one or more clubs to see club-specific rankings here.</p></article>`;

  elements.playerIdentity.innerHTML = `
    <article class="player-hero">
      <div class="player-hero-main">
        <div class="avatar-fallback profile-avatar">${player.picture}</div>
        <div>
          <h3>${displayName}</h3>
          <p>${player.gender || "Gender TBD"} · ${player.role} · Age ${player.age || "TBD"}</p>
          <p>${player.batting_style || "Batting style TBD"} / ${player.bowling_style || "Bowling style TBD"}</p>
          <small>Clubs: ${clubsLabel}</small>
          <small>Teams: ${teamsLabel}</small>
          <small>${player.phone || "No mobile stored"} ${player.email ? "· " + player.email : ""}</small>
          ${(player.aliases || []).length ? `<small>Aliases: ${(player.aliases || []).join(", ")}</small>` : ""}
          <small>${player.notes || "No extra profile notes yet."}</small>
        </div>
      </div>
      <div class="player-hero-meta">
        <span class="fixture-badge">${availability ? availability.matches_available : 0} available matches</span>
        <button class="secondary-button" type="button" data-follow-player="${player.name}" data-following="${isPlayerFollowed(player.name) ? "false" : "true"}">${isPlayerFollowed(player.name) ? "Unfollow player" : "Follow player"}</button>
      </div>
    </article>
  `;

  elements.playerSeasonSummary.innerHTML = `
    ${clubRankingCards}
    <article class="summary-card"><span>Clubs</span><strong>${profile.memberships.clubMemberships.length}</strong><p>${profile.memberships.clubMemberships.length ? "All linked clubs are included below" : "No club memberships stored"}</p></article>
    <article class="summary-card"><span>Stored Runs</span><strong>${profile.totals.storedRuns}</strong><p>${profile.totals.runs} confirmed + ${profile.pending.runs || 0} reviewed historical archive runs</p></article>
    <article class="summary-card"><span>Confirmed Runs</span><strong>${profile.totals.runs}</strong></article>
    <article class="summary-card"><span>Batting Average</span><strong>${profile.totals.battingAverage}</strong></article>
    <article class="summary-card"><span>Balls</span><strong>${profile.totals.balls}</strong></article>
    <article class="summary-card"><span>Strike Rate</span><strong>${profile.totals.strikeRate}</strong></article>
    <article class="summary-card"><span>Confirmed Wickets</span><strong>${profile.totals.wickets}</strong></article>
    <article class="summary-card"><span>Confirmed Catches</span><strong>${profile.totals.catches}</strong></article>
    <article class="summary-card"><span>Boundaries</span><strong>${profile.totals.fours}x4 · ${profile.totals.sixes}x6</strong></article>
    <article class="summary-card"><span>Scored Matches</span><strong>${profile.totals.innings}</strong></article>
    <article class="summary-card"><span>Historical Archive Runs</span><strong>${profile.pending.runs}</strong><p>${profile.pending.matches || 0} reviewed archive scorecards</p></article>
    <article class="summary-card"><span>Availability</span><strong>${availability ? `${availability.matches_available} yes / ${availability.matches_unavailable} no / ${availability.matches_no_response || 0} no response` : "n/a"}</strong></article>
  `;

  const lastGameLabel = profile.lastGame
    ? `${profile.lastGame.clubName} · ${profile.lastGame.dateLabel} vs ${profile.lastGame.opponent}`
    : "No played fixtures stored yet";
  const lastGameDetails = profile.lastGame
    ? `${profile.lastGame.runs} runs · ${profile.lastGame.wickets} wickets · ${profile.lastGame.catches} catches · ${profile.lastGame.result}`
    : "This will populate once the player appears in a saved match.";
  const upcomingGamesCards = profile.upcomingGames.length
    ? profile.upcomingGames
        .map(
          (item) => `
            <article class="summary-card">
              <span>${item.clubName}</span>
              <strong>${item.dateLabel}</strong>
              <p>vs ${item.opponent} · ${item.status}</p>
              <small>${item.availability === "no response" ? "Availability not yet set" : `Availability: ${item.availability}`}</small>
            </article>
          `
        )
        .join("")
    : `<article class="summary-card"><span>Upcoming Games</span><strong>No upcoming fixtures</strong><p>Once the player is linked to scheduled games, they will appear here.</p></article>`;
  elements.playerCareerSnapshot.innerHTML = `
    <article class="summary-card"><span>Last Game</span><strong>${lastGameLabel}</strong><p>${lastGameDetails}</p></article>
    ${upcomingGamesCards}
    <article class="summary-card"><span>Involvement</span><strong>${profile.appearances.filter((item) => item.played).length} played fixtures</strong><p>${profile.totals.runs} runs · ${profile.totals.wickets} wickets · ${profile.totals.catches} catches across ${profile.memberships.clubMemberships.length} clubs</p></article>
  `;

  elements.playerPendingHistory.innerHTML = renderLimitedCollection(profile.pending.sources || [], {
    key: `player-pending-${player.name}`,
    emptyMessage: `<p class="empty-state">No reviewed historical archive scores are stored for ${displayName} right now.</p>`,
    renderItem: (item) => `
      <article class="history-card pending-card">
        <div>
          <strong>${item.file_name}</strong>
          <p>${item.runs} runs${item.balls ? ` off ${item.balls}` : ""} · ${item.wickets} wickets · ${item.catches} catches</p>
          <small>${item.notes || "OCR suggested score from archive"}</small>
        </div>
        <div class="history-side">
          <span class="status-pill maybe">${item.confidence || "low"}</span>
          <small>Stored as reviewed historical archive data</small>
        </div>
      </article>
    `,
  });

  elements.playerMatchHistory.innerHTML = renderLimitedCollection(profile.appearances || [], {
    key: `player-history-${player.name}`,
    emptyMessage: `<p class="empty-state">No saved player performance entries yet for ${displayName}. Add scores from the Performance panel to build the profile history.</p>`,
    renderItem: (item) => `
      <article class="history-card">
        <div>
          <strong>${item.clubName} · ${item.dateLabel} vs ${item.opponent}</strong>
          <p>${item.runs} runs off ${item.balls} · ${item.wickets} wickets · ${item.catches} catches</p>
          <small>${item.result}</small>
        </div>
        <div class="history-side">
          <span class="status-pill ${item.availability === "available" ? "yes" : item.availability === "maybe" ? "maybe" : "no"}">${item.availability}</span>
          <small>${item.notes || item.status}</small>
        </div>
      </article>
    `,
  });
}

function renderArchive(uploads) {
  const filtered = filteredArchiveUploads(uploads);
  renderArchiveSearchSummary(filtered.length, uploads.length);
  elements.archiveList.innerHTML = renderLimitedCollection(filtered, {
    key: `archive-list-${elements.archiveSearchInput.value.trim()}-${elements.archiveDateInput.value}-${elements.archiveYearSelect.value}`,
    emptyMessage: `<p class="empty-state">${uploads.length ? "No archive scorecards match the current date, year, or player filters." : "No uploaded scorecard images yet."}</p>`,
    renderItem: (item) => `
      <article class="archive-card">
        <div>
          <strong>${item.file_name}</strong>
          <p>Status: ${archiveReviewStatus(item)}</p>
          <small>${item.season || ARCHIVE_SEASON_LABEL} · ${item.created_at}</small>
        </div>
        ${item.preview_url ? `<a class="inline-link" href="${item.preview_url}" target="_blank" rel="noreferrer">Open image</a>` : ""}
      </article>
    `,
  });
}

function archiveReviewPayload(item) {
  const draft = item.draft_scorecard || {};
  const suggested = item.suggested_performances || [];
  const heartlakeRuns = Number(draft.heartlake_runs || 0);
  const heartlakeWickets = Number(draft.heartlake_wickets || 0);
  const heartlakeOvers = draft.heartlake_overs ? Number(draft.heartlake_overs) : null;
  const extrasMatch = (draft.live_summary || item.extracted_summary || "").match(/Extras:\s*(\d+)/i);
  const extrasTotal = extrasMatch ? Number(extrasMatch[1]) : null;
  return {
    match: {
      format: "limited_overs",
      teams: {
        batting: focusClubShortName(),
        bowling: state.dashboard.fixtures.find((match) => match.id === item.match_id)?.opponent || "Opponent",
      },
      innings: [
        {
          inning_number: 1,
          batting_team: focusClubShortName(),
          total_runs: heartlakeRuns || null,
          wickets: Number.isFinite(heartlakeWickets) ? heartlakeWickets : null,
          overs: heartlakeOvers,
          extras: {
            byes: null,
            wides: null,
            leg_byes: null,
            no_balls: null,
            penalty: null,
            total: extrasTotal,
          },
          batting: suggested.map((entry) => ({
            name: entry.player_name,
            runs: Number(entry.runs || 0),
            balls: entry.balls ? Number(entry.balls) : null,
            fours: Number(entry.fours || 0),
            sixes: Number(entry.sixes || 0),
            dismissal: {
              type: null,
              bowler: null,
            },
            notes: entry.notes || "",
            confidence: entry.confidence || "",
          })),
          did_not_bat: [],
          fall_of_wickets: [],
        },
      ],
    },
  };
}

function archiveReviewTable(item) {
  const suggested = item.suggested_performances || [];
  if (!suggested.length) {
    return `<p class="empty-state">No batting rows extracted yet for review.</p>`;
  }
  return `
    <div class="review-table-wrap">
      <table class="review-table">
        <thead>
          <tr>
            <th>Player</th>
            <th>Runs</th>
            <th>Balls</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          ${suggested
            .map(
              (entry) => `
                <tr>
                  <td>${entry.player_name}</td>
                  <td>${entry.runs || 0}</td>
                  <td>${entry.balls || "--"}</td>
                  <td>${entry.confidence || entry.source || "review"}</td>
                </tr>
              `
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderDuplicates(duplicates) {
  elements.duplicateList.innerHTML = renderLimitedCollection(duplicates, {
    key: "duplicate-list",
    emptyMessage: `<p class="empty-state">No duplicate scorecards waiting for manual review.</p>`,
    renderItem: (item) => `
      <article class="archive-card">
        <div>
          <strong>${item.duplicate_file_name}</strong>
          <p>${item.reason}. Original: ${item.original_file_name}</p>
          <small>${item.status} · ${item.created_at}</small>
        </div>
        <div class="review-links">
          ${item.original_review_url ? `<a class="inline-link" href="${item.original_review_url}" target="_blank" rel="noreferrer">Open original</a>` : ""}
          ${item.duplicate_review_url ? `<a class="inline-link" href="${item.duplicate_review_url}" target="_blank" rel="noreferrer">Open duplicate</a>` : ""}
        </div>
      </article>
    `,
  });
}

function renderArchiveScorecards(uploads) {
  const filtered = filteredArchiveUploads(uploads);
  elements.archiveScorecards.innerHTML = renderLimitedCollection(filtered, {
    key: `archive-scorecards-${elements.archiveSearchInput.value.trim()}-${elements.archiveDateInput.value}-${elements.archiveYearSelect.value}`,
    emptyMessage: `<p class="empty-state">${uploads.length ? "No extracted scorecards match the current archive filters." : "No extracted scorecards are available yet."}</p>`,
    renderItem: (item) => {
          return `
            <article class="scorecard-card">
              <div class="scorecard-head">
                <div>
                  <strong>${item.file_name}</strong>
                  <p>${item.file_name} · ${item.season || ARCHIVE_SEASON_LABEL}</p>
                  <small>Archive date: ${archiveDateLabel(item) || "Unknown"}</small>
                </div>
                <span class="status-pill ${archiveReviewStatus(item) === "Approved" ? "yes" : "maybe"}">${archiveReviewStatus(item)}</span>
              </div>
              <p class="scorecard-result">${archiveReviewStatus(item) === "Approved" ? "Stored in the database" : "Waiting for admin review"}</p>
              <div class="scorecard-notes">
                <small>${item.created_at}</small>
              </div>
            </article>
          `;
        },
  });
}

function loadArchiveIntoEditor(archiveId) {
  const upload = state.dashboard.archive_uploads.find((item) => item.id === archiveId);
  if (!upload) {
    return;
  }
  elements.archiveSelect.value = archiveId;
  elements.archiveImportSelect.value = archiveId;
  syncArchiveDraft();
  if (upload.match_id && state.dashboard.fixtures.some((match) => match.id === upload.match_id)) {
    state.selectedMatchId = upload.match_id;
    renderDashboard(state.dashboard);
    elements.archiveSelect.value = archiveId;
    elements.archiveImportSelect.value = archiveId;
    syncArchiveDraft();
  }
  elements.archiveApplyForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderTeamPage() {
  const team = currentTeam();
  if (!team) {
    return;
  }
  const clubName = focusClubName();
  const clubRankingBundle = state.dashboard.club_rankings?.[clubName] || {};
  const rosterRows = clubRankingBundle.player_stats || [];
  const playerMap = new Map((state.dashboard.all_members || state.dashboard.members || []).map((member) => [member.name, member]));
  const roster = rosterRows.map((item) => playerMap.get(item.player_name) || {
    name: item.player_name,
    full_name: "",
    picture: item.player_name ? item.player_name.slice(0, 2).toUpperCase() : "PL",
    role: "Player",
    age: "",
    jersey_number: "",
    batting_style: "",
    bowling_style: "",
    notes: "",
    team_name: clubName,
  });
  const scoreRows = rosterRows;
  const pendingMap = Object.fromEntries((state.dashboard.player_pending_stats || []).map((item) => [item.player_name, item]));
  const fixtureInfo = state.dashboard.visiting_teams.find((item) => item.name === team.name);

  elements.teamSummary.innerHTML = `
    <article class="summary-card"><span>Team</span><strong>${team.display_name || team.name}</strong></article>
    <article class="summary-card"><span>Roster Size</span><strong>${roster.length}</strong></article>
    <article class="summary-card"><span>Fixtures</span><strong>${team.name === "Heartlake" ? state.dashboard.summary.fixture_count : fixtureInfo?.fixture_count || 0}</strong></article>
    <article class="summary-card"><span>Top Scorer</span><strong>${scoreRows[0]?.player_name || "TBD"}</strong><p>${scoreRows[0]?.runs || 0} runs</p></article>
  `;

  elements.teamRoster.innerHTML = renderLimitedCollection(roster, {
    key: `team-roster-${team.name}`,
    emptyMessage: `<p class="empty-state">No players are stored for ${team.display_name || team.name} yet.</p>`,
    renderItem: (member) => {
          const displayName = member.full_name ? `${member.name} (${member.full_name})` : member.name;
          const stats = state.dashboard.player_stats.find((item) => item.player_name === member.name) || {
            runs: 0,
            wickets: 0,
            catches: 0,
            matches: 0,
          };
          const pending = pendingMap[member.name] || { runs: 0, matches: 0 };
          const storedRuns = Number(stats.runs || 0) + Number(pending.runs || 0);
          return `
            <article class="member-card clickable-card" data-player="${member.name}">
              ${member.picture_url ? `<img class="avatar-image" src="${member.picture_url}" alt="${member.name}" />` : `<div class="avatar-fallback">${member.picture}</div>`}
              <div>
                <h3>${displayName}</h3>
                <p>${member.role} · Age ${member.age || "TBD"}</p>
                <p class="member-stats">${storedRuns} stored runs · ${stats.wickets} wickets · ${stats.matches} applied matches</p>
                <small>${pending.runs ? `${stats.runs} confirmed + ${pending.runs} reviewed historical archive runs` : `${stats.runs} confirmed runs`}</small>
                <small>${member.notes || "No profile notes yet."}</small>
              </div>
            </article>
          `;
        },
  });

  elements.teamPlayerScores.innerHTML = renderLimitedCollection(scoreRows, {
    key: `team-scores-${team.name}`,
    emptyMessage: `<p class="empty-state">No player score entries are stored yet for ${team.display_name || team.name}.</p>`,
    renderItem: (item) => {
            const pending = pendingMap[item.player_name] || { runs: 0, matches: 0 };
            const storedRuns = Number(item.runs || 0) + Number(pending.runs || 0);
            return `
              <article class="leader-card clickable-card" data-player="${item.player_name}">
                <strong>${item.player_name}</strong>
                <p>${item.matches} applied matches</p>
                <p>${storedRuns} stored runs · ${item.wickets} wickets · ${item.catches} catches</p>
                <small>${pending.runs ? `${item.runs} confirmed + ${pending.runs} reviewed historical archive runs` : `${item.runs} confirmed runs`}</small>
              </article>
            `;
          },
  });
}

function syncArchiveDraft() {
  const uploadId = elements.archiveSelect.value;
  const upload = state.dashboard.archive_uploads.find((item) => item.id === uploadId);
  if (!upload) return;
  const draft = upload.draft_scorecard || {};
  elements.archiveHeartlakeRunsInput.value = draft.heartlake_runs || "";
  elements.archiveHeartlakeWicketsInput.value = draft.heartlake_wickets || "";
  elements.archiveHeartlakeOversInput.value = draft.heartlake_overs || "";
  elements.archiveOpponentRunsInput.value = draft.opponent_runs || "";
  elements.archiveOpponentWicketsInput.value = draft.opponent_wickets || "";
  elements.archiveOpponentOversInput.value = draft.opponent_overs || "";
  elements.archiveResultInput.value = draft.result || "";
  if (!elements.archiveSourceNoteInput.value) {
    elements.archiveSourceNoteInput.value = `Recovered from archive OCR for ${upload.file_name}`;
  }
  elements.archiveImportSelect.value = uploadId;
}

function updateWhatsappLink(match) {
  const text = encodeURIComponent(
    `${state.dashboard.focus_club?.name || state.dashboard.club?.name || "Club"} update: ${match.date_label} vs ${match.opponent}. Status: ${match.status}. Available players: ${match.availability.join(", ") || "none yet"}.`
  );
  elements.whatsappLink.href = `https://wa.me/${state.dashboard.club.whatsapp_number}?text=${text}`;
}

function renderDashboard(dashboard) {
  state.dashboard = dashboard;
  const permissions = dashboard.user?.permissions || [];
  state.isAdmin = permissions.includes("view_admin") || permissions.includes("manage_club") || permissions.includes("manage_scorecards") || permissions.includes("manage_players");
  state.canManageOtherAvailability = canManageOtherAvailability();
  if (elements.uploadForm) elements.uploadForm.hidden = true;
  if (elements.resetScoresButton) elements.resetScoresButton.hidden = true;
  if (elements.archiveImportForm) elements.archiveImportForm.hidden = true;
  if (elements.archiveApplyForm) elements.archiveApplyForm.hidden = true;
  state.selectedFocusClubId = dashboard.focus_club?.id || dashboard.viewer_profile?.primary_club_id || state.selectedFocusClubId;
  if (state.selectedFocusClubId) {
    window.localStorage.setItem("heartlakePrimaryClubId", state.selectedFocusClubId);
    document.cookie = `heartlakePrimaryClubId=${encodeURIComponent(state.selectedFocusClubId)}; path=/; samesite=lax`;
  }
  const currentYear = String(new Date().getFullYear());
  state.selectedSeasonYear = dashboard.selected_season_year || dashboard.default_season_year || state.selectedSeasonYear || currentYear;
  if (state.selectedSeasonYear) {
    window.localStorage.setItem("heartlakeSelectedSeasonYear", state.selectedSeasonYear);
    document.cookie = `heartlakeSelectedSeasonYear=${encodeURIComponent(state.selectedSeasonYear)}; path=/; samesite=lax`;
  }
  setLiveSeasonMode(String(state.selectedSeasonYear || "").trim() === currentYear, state.selectedSeasonYear || currentYear);
  if (!state.selectedMatchId || !dashboard.fixtures.some((match) => match.id === state.selectedMatchId)) {
    state.selectedMatchId = dashboard.upcoming_match.id;
  }
  const memberNameForViewer = getViewerMemberNameFromAuth() || viewerMemberName(dashboard);
  if (!state.selectedPlayerName || !dashboard.members.some((member) => member.name === state.selectedPlayerName)) {
    state.selectedPlayerName = memberNameForViewer || dashboard.members[0]?.name || null;
  }
  if (!state.selectedAvailabilityPlayerName || !dashboard.members.some((member) => member.name === state.selectedAvailabilityPlayerName)) {
    state.selectedAvailabilityPlayerName = state.canManageOtherAvailability
      ? (state.selectedPlayerName || dashboard.members[0]?.name || null)
      : (memberNameForViewer || state.selectedPlayerName || dashboard.members[0]?.name || null);
  }
  if (!state.canManageOtherAvailability) {
    state.selectedAvailabilityPlayerName = memberNameForViewer || state.selectedPlayerName || dashboard.members[0]?.name || null;
  }
  if (!state.selectedTeamName || !dashboard.teams.some((team) => team.name === state.selectedTeamName)) {
    state.selectedTeamName = dashboard.teams[0]?.name || null;
  }
  const match = currentMatch();
  const landingNextMatch = dashboard.landing_upcoming_matches?.[0] || dashboard.upcoming_match || {};
  const selectedYear = state.selectedSeasonYear || currentYear;
  const isLiveSeason = String(state.selectedSeasonYear || "").trim() === currentYear;
  const totalFixtures = dashboard.summary?.fixture_count ?? (dashboard.fixtures || []).length;
  const playedMatches = dashboard.summary?.matches_played ?? 0;
  const pendingMatches = Math.max(0, totalFixtures - playedMatches);
  const upcomingAvailability = Array.isArray(landingNextMatch.availability) ? landingNextMatch.availability.length : 0;
  const totalPlayers = (dashboard.members || []).length;
  elements.seasonLabel.textContent = `${selectedYear} Season`;
  if (elements.availabilityLabel) {
    elements.availabilityLabel.textContent = totalPlayers
      ? `${upcomingAvailability}/${totalPlayers}`
      : `${upcomingAvailability} available`;
  }
  if (isLiveSeason) {
    if (elements.nextMatchLabelTitle) {
      elements.nextMatchLabelTitle.textContent = "Next Match";
    }
    elements.nextMatchLabel.textContent = landingNextMatch.date_label
      ? `${landingNextMatch.date_label} vs ${landingNextMatch.opponent}`
      : "No upcoming match";
    if (elements.seasonModeLabel) {
      elements.seasonModeLabel.textContent = `Fixtures : ${totalFixtures}, Played: ${playedMatches}, Pending: ${pendingMatches}`;
    }
  } else {
    if (elements.nextMatchLabelTitle) {
      elements.nextMatchLabelTitle.textContent = "Last Match";
    }
    const historicalSummary = getHistoricalSeasonSummary(dashboard);
    elements.nextMatchLabel.textContent = historicalSummary.headline;
    if (elements.seasonModeLabel) {
      elements.seasonModeLabel.textContent = historicalSummary.details;
    }
  }
  elements.llmLabel.textContent = dashboard.llm.model || dashboard.llm.provider;
  elements.uploadSeason.value = elements.uploadSeason.value || ARCHIVE_SEASON_LABEL;
  renderViewerProfile(dashboard);
  updateViewerPlayerSnapshot(dashboard);
  populateMatchSelects(dashboard.fixtures);
  populatePlayerSelects(dashboard.members, dashboard.all_members || dashboard.members || []);
  if (!state.canManageOtherAvailability && elements.availabilityPlayerSelect) {
    elements.availabilityPlayerSelect.hidden = true;
    elements.availabilityPlayerSelect.disabled = true;
    elements.availabilityPlayerSelect.value = currentSignedInMemberName(dashboard) || dashboard.members[0]?.name || "";
  }
  populateTeamSelect(dashboard.teams || []);
  populateArchiveSelect(dashboard.archive_uploads);
  populateArchiveYearSelect(dashboard.archive_uploads);
  populateRankingYearSelect(dashboard);
  if (!elements.archiveSourceNoteInput.value) {
    elements.archiveSourceNoteInput.value = "Offline scorecard sync";
  }
  renderSummary(dashboard.summary);
  renderSelectedMatch(match);
  renderFormValues(match);
  renderScorebook(match);
  renderMembers(dashboard.members);
  renderSchedule(dashboard.fixtures);
  renderVisitingTeams(dashboard.visiting_teams);
  renderAvailabilityMatrix(dashboard.availability_board, dashboard.fixtures);
  renderLeaderboard();
  renderPlayerProfile();
  renderTeamPage();
  renderAvailabilityFixtureEditor(dashboard.fixtures);
  renderArchive(dashboard.archive_uploads);
  renderDuplicates(dashboard.duplicate_uploads || []);
  renderArchiveScorecards(dashboard.archive_uploads);
  updateWhatsappLink(match);
  syncArchiveDraft();
}

async function loadDashboard() {
  try {
    state.viewerAuth = await window.HeartlakePages.authMe();
  } catch {
    state.viewerAuth = null;
  }
  const query = state.selectedFocusClubId ? `?focus_club_id=${encodeURIComponent(state.selectedFocusClubId)}` : "";
  const dashboard = await runAction(() => getJson(`/api/dashboard${query}`), "Club dashboard loaded.");
  if (dashboard) {
    renderDashboard(dashboard);
  }
}

elements.activeMatchSelect.addEventListener("change", () => {
  state.selectedMatchId = elements.activeMatchSelect.value;
  renderDashboard(state.dashboard);
});

elements.playerProfileSelect.addEventListener("change", () => {
  state.selectedPlayerName = elements.playerProfileSelect.value;
  renderDashboard(state.dashboard);
});

elements.teamProfileSelect.addEventListener("change", () => {
  state.selectedTeamName = elements.teamProfileSelect.value;
  renderDashboard(state.dashboard);
});

elements.rankingYearSelect.addEventListener("change", async () => {
  state.selectedSeasonYear = elements.rankingYearSelect.value;
  const dashboard = await runAction(
    () => postJson("/api/viewer-profile", currentViewerProfilePayload(state.selectedSeasonYear)),
    "Season updated."
  );
  if (dashboard) {
    renderDashboard(dashboard);
  }
});

elements.playerSearchInput.addEventListener("input", () => {
  const query = elements.playerSearchInput.value.trim().toLowerCase();
  if (!query) {
    return;
  }
  const match = state.dashboard.members.find((member) => {
    const full = member.full_name || "";
    const aliases = (member.aliases || []).join(" ").toLowerCase();
    return member.name.toLowerCase().includes(query) || full.toLowerCase().includes(query) || aliases.includes(query);
  });
  if (!match) {
    return;
  }
  state.selectedPlayerName = match.name;
  renderDashboard(state.dashboard);
});

elements.viewerProfileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = currentViewerProfilePayload(state.selectedSeasonYear);
  const dashboard = await runAction(
    () => postJson("/api/viewer-profile", payload),
    "Primary club and local profile saved."
  );
  if (dashboard) {
    renderDashboard(dashboard);
  }
});

elements.primaryClubSelect.addEventListener("change", async () => {
  const payload = currentViewerProfilePayload(state.selectedSeasonYear);
  const dashboard = await runAction(
    () => postJson("/api/viewer-profile", payload),
    "Primary club updated."
  );
  if (dashboard) {
    renderDashboard(dashboard);
  }
});

if (elements.clubSearchInput) {
  elements.clubSearchInput.addEventListener("input", () => {
    renderClubSearchResults();
  });
}

elements.landingPlayerSearchInput.addEventListener("input", () => {
  renderLandingPlayerResults();
});

elements.detailsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    heartlake_captain: elements.captainInput.value,
    venue: elements.venueInput.value,
    match_type: elements.matchTypeInput.value,
    scheduled_time: elements.scheduledTimeInput.value,
    overs: elements.oversInput.value,
    toss_winner: elements.tossWinnerInput.value,
    toss_decision: elements.tossDecisionInput.value,
    weather: elements.weatherInput.value,
    umpires: elements.umpiresInput.value,
    scorer: elements.scorerInput.value,
    whatsapp_thread: elements.whatsappThreadInput.value,
    notes: elements.matchNotesInput.value,
    status: elements.matchStatusInput.value,
  };
  const dashboard = await runAction(
    () => postJson(`/api/matches/${state.selectedMatchId}/details`, payload),
    "Match setup saved."
  );
  if (dashboard) renderDashboard(dashboard);
});

elements.scoreForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    heartlake_runs: elements.heartlakeRunsInput.value,
    heartlake_wickets: elements.heartlakeWicketsInput.value,
    heartlake_overs: elements.heartlakeOversInput.value,
    opponent_runs: elements.opponentRunsInput.value,
    opponent_wickets: elements.opponentWicketsInput.value,
    opponent_overs: elements.opponentOversInput.value,
    result: elements.resultInput.value,
    live_summary: elements.liveSummaryInput.value,
    status: elements.matchStatusInput.value,
  };
  const dashboard = await runAction(
    () => postJson(`/api/matches/${state.selectedMatchId}/scorecard`, payload),
    "Online scorecard updated."
  );
  if (dashboard) renderDashboard(dashboard);
});

elements.scorebookInningsSelect.addEventListener("change", () => {
  renderScorebook(currentMatch());
});

elements.scorebookSetupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const batters = Array.from(elements.scorebookBatters.querySelectorAll("[data-batter-slot]")).map((input) => input.value.trim());
  const bowlers = Array.from(elements.scorebookBowlers.querySelectorAll("[data-bowler-slot]")).map((input) => input.value.trim());
  const payload = {
    innings_number: Number(elements.scorebookInningsSelect.value || 1),
    batting_team: elements.scorebookBattingTeamInput.value.trim(),
    bowling_team: elements.scorebookBowlingTeamInput.value.trim(),
    overs_limit: Number(elements.scorebookOversLimitInput.value || 20),
    target_runs: elements.scorebookTargetRunsInput.value ? Number(elements.scorebookTargetRunsInput.value) : null,
    status: elements.scorebookStatusInput.value,
    batters,
    bowlers,
  };
  const dashboard = await runAction(
    () => postJson(`/api/matches/${state.selectedMatchId}/scorebook/setup`, payload),
    "Innings scorebook saved."
  );
  if (dashboard) {
    renderDashboard(dashboard);
  }
});

elements.scorebookBallForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    innings_number: Number(elements.scorebookInningsSelect.value || 1),
    over_number: Number(elements.scorebookOverNumberInput.value || 1),
    ball_number: Number(elements.scorebookBallNumberInput.value || 1),
    striker: elements.scorebookStrikerInput.value.trim(),
    non_striker: elements.scorebookNonStrikerInput.value.trim(),
    bowler: elements.scorebookBowlerInput.value.trim(),
    runs_bat: Number(elements.scorebookRunsBatInput.value || 0),
    extras_type: elements.scorebookExtrasTypeInput.value,
    extras_runs: Number(elements.scorebookExtrasRunsInput.value || 0),
    wicket: elements.scorebookWicketInput.value === "true",
    wicket_type: elements.scorebookWicketTypeInput.value.trim(),
    wicket_player: elements.scorebookWicketPlayerInput.value.trim(),
    fielder: elements.scorebookFielderInput.value.trim(),
    commentary: elements.scorebookBallCommentaryInput.value.trim(),
  };
  const dashboard = await runAction(
    () => postJson(`/api/matches/${state.selectedMatchId}/scorebook/ball`, payload),
    "Delivery logged."
  );
  if (dashboard) {
    renderDashboard(dashboard);
    elements.scorebookBallForm.reset();
    elements.scorebookExtrasTypeInput.value = "none";
    elements.scorebookWicketInput.value = "false";
  }
});

async function saveDashboardAvailability() {
  const payload = {
    player_name: currentAvailabilityPlayerName(),
    status: elements.availabilityStatusSelect.value,
    note: elements.availabilityNoteInput.value,
    club_id: state.selectedFocusClubId || currentMatch().club_id || "",
  };
  const dashboard = await runAction(
    () => postJson(`/api/matches/${state.selectedMatchId}/availability`, payload),
    "Availability updated."
  );
  if (dashboard) {
    renderDashboard(dashboard);
    elements.availabilityNoteInput.value = "";
  }
}

window.HeartlakeDashboard = {
  saveDashboardAvailability,
};

elements.availabilityForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveDashboardAvailability();
});

if (elements.availabilityFixturesEditor) {
  elements.availabilityFixturesEditor.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-fixture-availability-form]");
    if (!form) return;
    event.preventDefault();
    const playerName = currentAvailabilityPlayerName();
    if (!playerName) {
      return;
    }
    const dashboard = await runAction(
      () =>
        postJson(`/api/matches/${form.dataset.fixtureAvailabilityForm}/availability`, {
          player_name: playerName,
          status: form.elements.status.value,
          note: form.elements.note.value.trim(),
          club_id: state.selectedFocusClubId || currentMatch().club_id || "",
        }),
      "Availability updated."
    );
    if (dashboard) {
      renderDashboard(dashboard);
      elements.availabilityNoteInput.value = "";
    }
  });
}

async function autoSaveDashboardAvailability() {
  if (!elements.availabilityStatusSelect.value) {
    return;
  }
  await saveDashboardAvailability();
}

elements.availabilityStatusSelect.addEventListener("change", autoSaveDashboardAvailability);
elements.availabilityPlayerSelect.addEventListener("change", () => {
  if (!state.canManageOtherAvailability) {
    return;
  }
  state.selectedAvailabilityPlayerName = elements.availabilityPlayerSelect.value || state.selectedAvailabilityPlayerName;
  autoSaveDashboardAvailability();
});

elements.performanceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    player_name: elements.performancePlayerSelect.value,
    runs: Number(elements.performanceRunsInput.value || 0),
    balls: Number(elements.performanceBallsInput.value || 0),
    wickets: Number(elements.performanceWicketsInput.value || 0),
    catches: Number(elements.performanceCatchesInput.value || 0),
    fours: Number(elements.performanceFoursInput.value || 0),
    sixes: Number(elements.performanceSixesInput.value || 0),
    notes: elements.performanceNotesInput.value,
    source: "manual",
  };
  const dashboard = await runAction(
    () => postJson(`/api/matches/${state.selectedMatchId}/performances`, payload),
    "Player performance saved."
  );
  if (dashboard) {
    renderDashboard(dashboard);
    elements.performanceForm.reset();
  }
});

elements.commentaryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    mode: elements.commentaryMode.value,
    text: elements.commentaryText.value,
  };
  const dashboard = await runAction(
    () => postJson(`/api/matches/${state.selectedMatchId}/commentary`, payload),
    "Commentary saved to the selected match."
  );
  if (dashboard) {
    renderDashboard(dashboard);
    elements.commentaryText.value = "";
  }
});

elements.memberForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(elements.memberForm);
  const payload = Object.fromEntries(form.entries());
  payload.age = Number(payload.age);
  const dashboard = await runAction(() => postJson("/api/members", payload), "Player profile created.");
  if (dashboard) {
    renderDashboard(dashboard);
    elements.memberForm.reset();
  }
});

elements.playerEditForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const player = currentPlayer();
  if (!player) {
    setStatus("Choose a player first.", "error");
    return;
  }
  const payload = {
    name: elements.editPlayerName.value.trim(),
    full_name: elements.editPlayerFullName.value.trim(),
    gender: elements.editPlayerGender ? elements.editPlayerGender.value : "",
    aliases: elements.editPlayerAliases.value,
    team_name: elements.editPlayerTeamName.value,
    team_memberships: elements.editPlayerTeamMemberships.value,
    age: elements.editPlayerAge.value ? Number(elements.editPlayerAge.value) : null,
    role: elements.editPlayerRole.value.trim(),
    batting_style: elements.editPlayerBattingStyle.value.trim(),
    bowling_style: elements.editPlayerBowlingStyle.value.trim(),
    jersey_number: elements.editPlayerJerseyNumber.value.trim(),
    phone: elements.editPlayerPhone.value.trim(),
    email: elements.editPlayerEmail.value.trim(),
    picture_url: elements.editPlayerPictureUrl.value.trim(),
    notes: elements.editPlayerNotes.value.trim(),
  };
  const dashboard = await runAction(
    () => postJson(`/api/members/${player.id}`, payload),
    "Player profile updated."
  );
  if (dashboard) {
    const nextName = payload.name || player.name;
    state.selectedPlayerName = dashboard.members.find((member) => member.name === nextName)?.name || nextName;
    renderDashboard(dashboard);
  }
});

elements.memberList.addEventListener("click", (event) => {
  const card = event.target.closest("[data-player]");
  if (!card) return;
  state.selectedPlayerName = card.dataset.player;
  renderDashboard(state.dashboard);
  elements.playerIdentity.scrollIntoView({ behavior: "smooth", block: "start" });
});

elements.teamRoster.addEventListener("click", (event) => {
  const card = event.target.closest("[data-player]");
  if (!card) return;
  state.selectedPlayerName = card.dataset.player;
  renderDashboard(state.dashboard);
  elements.playerIdentity.scrollIntoView({ behavior: "smooth", block: "start" });
});

elements.playerLeaderboard.addEventListener("click", (event) => {
  const card = event.target.closest("[data-player]");
  if (!card) return;
  state.selectedPlayerName = card.dataset.player;
  renderDashboard(state.dashboard);
  elements.playerIdentity.scrollIntoView({ behavior: "smooth", block: "start" });
});

elements.teamPlayerScores.addEventListener("click", (event) => {
  const card = event.target.closest("[data-player]");
  if (!card) return;
  state.selectedPlayerName = card.dataset.player;
  renderDashboard(state.dashboard);
  elements.playerIdentity.scrollIntoView({ behavior: "smooth", block: "start" });
});

elements.scheduleBoard.addEventListener("click", (event) => {
  const card = event.target.closest("[data-match]");
  if (!card) return;
  state.selectedMatchId = card.dataset.match;
  renderDashboard(state.dashboard);
  document.getElementById("match-center")?.scrollIntoView({ behavior: "smooth", block: "start" });
});

elements.landingMatches.addEventListener("click", (event) => {
  const card = event.target.closest("[data-match]");
  if (!card) return;
  state.selectedMatchId = card.dataset.match;
  renderDashboard(state.dashboard);
  document.getElementById("match-center")?.scrollIntoView({ behavior: "smooth", block: "start" });
});

elements.uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = new FormData();
  if (elements.uploadFile.files[0]) body.append("file", elements.uploadFile.files[0]);
  body.append("match_id", state.selectedMatchId);
  body.append("season", elements.uploadSeason.value);
  body.append("focus_club_id", state.selectedFocusClubId || "");
  const data = await runAction(
    async () => {
      const response = await fetch("/api/scorecards/upload", {
        method: "POST",
        body,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || payload.message || "Upload failed.");
      }
      return payload;
    },
    ""
  );
  if (data?.dashboard) {
    renderDashboard(data.dashboard);
    elements.uploadForm.reset();
    elements.uploadSeason.value = "";
    setStatus(data.message || "Scorecard image processed.", "success");
  }
});

for (const eventName of ["input", "change"]) {
  elements.archiveSearchInput.addEventListener(eventName, () => {
    renderArchive(state.dashboard.archive_uploads);
    renderArchiveScorecards(state.dashboard.archive_uploads);
  });
  elements.archiveDateInput.addEventListener(eventName, () => {
    renderArchive(state.dashboard.archive_uploads);
    renderArchiveScorecards(state.dashboard.archive_uploads);
  });
  elements.archiveYearSelect.addEventListener(eventName, () => {
    renderArchive(state.dashboard.archive_uploads);
    renderArchiveScorecards(state.dashboard.archive_uploads);
  });
}

elements.archiveClearFilters.addEventListener("click", () => {
  elements.archiveSearchInput.value = "";
  elements.archiveDateInput.value = "";
  elements.archiveYearSelect.value = "";
  renderArchive(state.dashboard.archive_uploads);
  renderArchiveScorecards(state.dashboard.archive_uploads);
});

elements.resetScoresButton.addEventListener("click", async () => {
  const data = await runAction(
    () => postJson("/api/archive/reset-scores", {}),
    ""
  );
  if (data?.dashboard) {
    renderDashboard(data.dashboard);
    setStatus(data.message, "success");
  }
});

elements.archiveSelect.addEventListener("change", syncArchiveDraft);
elements.archiveImportSelect.addEventListener("change", () => {
  const archiveId = elements.archiveImportSelect.value;
  if (!archiveId) return;
  elements.archiveSelect.value = archiveId;
  syncArchiveDraft();
});

elements.archiveImportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!elements.archiveImportSelect.value) {
    setStatus("Choose an archive scorecard first.", "error");
    return;
  }
  const text = elements.archiveImportText.value.trim();
  if (!text) {
    setStatus("Paste the extracted scorecard text or JSON first.", "error");
    return;
  }
  const data = await runAction(
    () =>
      postJson(clubScopedApi(`/api/archive/${elements.archiveImportSelect.value}/import-extraction`), {
        text,
      }),
    ""
  );
  if (!data?.dashboard) return;
  renderDashboard(data.dashboard);
  elements.archiveSelect.value = elements.archiveImportSelect.value;
  syncArchiveDraft();
  setStatus(data.message, "success");
});

elements.archiveScorecards.addEventListener("click", (event) => {
  const extractButton = event.target.closest("[data-archive-extract]");
  if (extractButton) {
    runAction(
      () => postJson(clubScopedApi(`/api/archive/${extractButton.dataset.archiveExtract}/extract`), {}),
      ""
    ).then((data) => {
      if (!data?.dashboard) return;
      renderDashboard(data.dashboard);
      elements.archiveSelect.value = extractButton.dataset.archiveExtract;
      syncArchiveDraft();
      setStatus(data.message, "success");
    });
    return;
  }
  const reviewButton = event.target.closest("[data-archive-review-json]");
  if (reviewButton) {
    const upload = state.dashboard.archive_uploads.find((item) => item.id === reviewButton.dataset.archiveReviewJson);
    if (!upload) return;
    elements.archiveImportSelect.value = upload.id;
    elements.archiveSelect.value = upload.id;
    elements.archiveImportText.value = JSON.stringify(archiveReviewPayload(upload), null, 2);
    syncArchiveDraft();
    elements.archiveImportForm.scrollIntoView({ behavior: "smooth", block: "start" });
    setStatus(`Loaded ${upload.file_name} review JSON into the import box.`, "success");
    return;
  }
  const button = event.target.closest("[data-archive-load]");
  if (!button) return;
  loadArchiveIntoEditor(button.dataset.archiveLoad);
});

elements.archiveApplyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!elements.archiveSelect.value) return;
  const payload = {
    match_id: state.selectedMatchId,
    heartlake_runs: elements.archiveHeartlakeRunsInput.value,
    heartlake_wickets: elements.archiveHeartlakeWicketsInput.value,
    heartlake_overs: elements.archiveHeartlakeOversInput.value,
    opponent_runs: elements.archiveOpponentRunsInput.value,
    opponent_wickets: elements.archiveOpponentWicketsInput.value,
    opponent_overs: elements.archiveOpponentOversInput.value,
    result: elements.archiveResultInput.value,
    source_note: elements.archiveSourceNoteInput.value,
  };
  const dashboard = await runAction(
    () => postJson(clubScopedApi(`/api/archive/${elements.archiveSelect.value}/apply`), payload),
    "Archive scorecard applied to the selected match."
  );
  if (dashboard) {
    renderDashboard(dashboard);
    elements.archiveSourceNoteInput.value = "";
  }
});

document.addEventListener("click", (event) => {
  const followButton = event.target.closest("[data-follow-player]");
  if (followButton) {
    const playerName = followButton.dataset.followPlayer;
    const following = followButton.dataset.following === "true";
    runAction(
      () => postJson("/api/viewer-profile/follow-player", { player_name: playerName, following }),
      following ? "Player followed." : "Player unfollowed."
    ).then((dashboard) => {
      if (!dashboard) return;
      renderDashboard(dashboard);
    });
    return;
  }
  const playerJump = event.target.closest("[data-player-jump]");
  if (playerJump) {
    state.selectedPlayerName = playerJump.dataset.playerJump;
    renderDashboard(state.dashboard);
    elements.playerIdentity.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  const toggle = event.target.closest("[data-list-toggle]");
  if (!toggle) {
    return;
  }
  const key = toggle.dataset.listToggle;
  setListExpanded(key, !isListExpanded(key));
  if (state.dashboard) {
    renderDashboard(state.dashboard);
  }
});

elements.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = elements.chatInput.value.trim();
  if (!question) return;
  addMessage("user", question);
  elements.chatInput.value = "";
  const history = state.chatHistory.slice(0, -1);
  const data = await runAction(() =>
    postJson("/api/chat", {
      question,
      session_id: state.chatSessionId,
      history,
      focus_club_id: state.selectedFocusClubId,
    })
  );
  if (data) addMessage("assistant", data.answer);
});

window.addEventListener("storage", (event) => {
  if (event.key !== "heartlakePrimaryClubId") {
    return;
  }
  state.selectedFocusClubId = event.newValue || null;
  if (state.dashboard) {
    loadDashboard();
  }
});

function ensureSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setStatus("Browser speech-to-text is not available here. You can still paste a transcript manually.", "error");
    return null;
  }
  if (recognition) {
    return recognition;
  }
  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-CA";
  recognition.onstart = () => {
    recognitionActive = true;
    elements.commentaryMode.value = "voice";
    setStatus("Mic transcription started. Speak and the transcript will appear in the commentary box.", "success");
  };
  recognition.onresult = (event) => {
    let transcript = "";
    for (let index = 0; index < event.results.length; index += 1) {
      transcript += event.results[index][0].transcript;
    }
    elements.commentaryText.value = transcript.trim();
    elements.commentaryMode.value = "voice";
  };
  recognition.onerror = () => {
    recognitionActive = false;
    setStatus("Mic transcription hit an error. You can retry or type the commentary manually.", "error");
  };
  recognition.onend = () => {
    if (recognitionActive) {
      recognitionActive = false;
      setStatus("Mic transcription stopped.", "info");
    }
  };
  return recognition;
}

elements.startVoiceCommentary.addEventListener("click", () => {
  const instance = ensureSpeechRecognition();
  if (!instance) return;
  recognitionActive = true;
  instance.start();
});

elements.stopVoiceCommentary.addEventListener("click", () => {
  if (!recognition) return;
  recognitionActive = false;
  recognition.stop();
  setStatus("Mic transcription stopped.", "info");
});

restoreChatHistory();
loadDashboard();
