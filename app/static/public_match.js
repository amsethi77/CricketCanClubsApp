(() => {
  const titleEl = document.getElementById("publicMatchTitle");
  const metaEl = document.getElementById("publicMatchMeta");
  const teamOneBadgeEl = document.getElementById("publicMatchTeamOneBadge");
  const teamTwoBadgeEl = document.getElementById("publicMatchTeamTwoBadge");
  const opponentTitleEl = document.getElementById("publicMatchOpponentTitle");
  const venueEl = document.getElementById("publicMatchVenue");
  const teamOneScoreEl = document.getElementById("publicMatchTeamOneScore");
  const teamOneOversEl = document.getElementById("publicMatchTeamOneOvers");
  const teamTwoScoreEl = document.getElementById("publicMatchTeamTwoScore");
  const teamTwoOversEl = document.getElementById("publicMatchTeamTwoOvers");
  const targetEl = document.getElementById("publicMatchTarget");
  const statusEl = document.getElementById("publicMatchStatus");
  const requiredRunsEl = document.getElementById("publicMatchRequiredRuns");
  const requiredRateEl = document.getElementById("publicMatchRequiredRate");
  const ballsLeftEl = document.getElementById("publicMatchBallsLeft");
  const momentumEl = document.getElementById("publicMatchMomentum");
  const availabilityCountEl = document.getElementById("publicMatchAvailabilityCount");
  const selectionCountEl = document.getElementById("publicMatchSelectionCount");
  const recentBallsEl = document.getElementById("publicMatchRecentBalls");
  const inningsEl = document.getElementById("publicMatchInnings");
  const commentaryEl = document.getElementById("publicMatchCommentary");
  const performancesEl = document.getElementById("publicMatchPerformances");
  const readOnlyNoteEl = document.getElementById("publicMatchReadOnlyNote");

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function matchIdFromPath() {
    const parts = window.location.pathname.split("/").filter(Boolean);
    return parts.length ? parts[parts.length - 1] : "";
  }

  function formatOvers(value) {
    return String(value || "0.0");
  }

  function renderSummaryCard(label, value, note = "") {
    return `
      <article class="mini-stat">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
        ${note ? `<small>${escapeHtml(note)}</small>` : ""}
      </article>
    `;
  }

  function renderBattingTable(rows) {
    if (!rows.length) {
      return `<p class="public-empty">No batting figures recorded yet.</p>`;
    }
    return `
      <div class="public-score-table">
        <div class="public-score-table-head">
          <span>Batter</span><span>Runs</span><span>Balls</span><span>SR</span>
        </div>
        ${rows
          .map(
            (row) => `
              <div class="public-score-table-row">
                <strong>${escapeHtml(row.player_name || "Player")}</strong>
                <span>${escapeHtml(row.runs ?? 0)}</span>
                <span>${escapeHtml(row.balls ?? 0)}</span>
                <span>${escapeHtml(Number(row.strike_rate || 0).toFixed(2).replace(/\.00$/, ""))}</span>
              </div>
            `,
          )
          .join("")}
      </div>
    `;
  }

  function renderBowlingTable(rows) {
    if (!rows.length) {
      return `<p class="public-empty">No bowling figures recorded yet.</p>`;
    }
    return `
      <div class="public-score-table">
        <div class="public-score-table-head public-score-table-head-five">
          <span>Bowler</span><span>Overs</span><span>Runs</span><span>Wkts</span><span>Econ</span>
        </div>
        ${rows
          .map(
            (row) => `
              <div class="public-score-table-row public-score-table-row-five">
                <strong>${escapeHtml(row.player_name || "Bowler")}</strong>
                <span>${escapeHtml(row.overs || "0.0")}</span>
                <span>${escapeHtml(row.runs_conceded ?? 0)}</span>
                <span>${escapeHtml(row.wickets ?? 0)}</span>
                <span>${escapeHtml(Number(row.economy || 0).toFixed(2).replace(/\.00$/, ""))}</span>
              </div>
            `,
          )
          .join("")}
      </div>
    `;
  }

  function renderBalls(rows) {
    if (!rows.length) {
      return `<p class="public-empty">No deliveries logged yet.</p>`;
    }
    return `
      <div class="public-ball-strip">
        ${rows
          .slice()
          .reverse()
          .slice(0, 20)
          .map((ball) => {
            const extras = ball.extras_type && ball.extras_type !== "none" ? ` + ${ball.extras_runs} ${String(ball.extras_type).replace("_", " ")}` : "";
            const wicket = ball.wicket
              ? ` · Wicket${ball.wicket_player ? `: ${ball.wicket_player}` : ""}${ball.fielder ? ` · Fielder: ${ball.fielder}` : ""}`
              : "";
            return `
              <article class="history-card scorebook-ball">
                <strong>${escapeHtml(ball.over_number)}.${escapeHtml(ball.ball_number)}</strong>
                <div>
                  <p>${escapeHtml(ball.striker || "Striker")} vs ${escapeHtml(ball.bowler || "Bowler")} · ${escapeHtml(ball.runs_bat ?? 0)} run(s)${escapeHtml(extras)}${escapeHtml(wicket)}</p>
                  <small>${escapeHtml(ball.commentary || "No commentary for this ball.")}</small>
                </div>
              </article>
            `;
          })
          .join("")}
      </div>
    `;
  }

  function renderRecentBalls(rows) {
    if (!rows.length) {
      return `<div class="public-empty public-empty-dark">No deliveries logged yet.</div>`;
    }
    return rows
      .slice()
      .reverse()
      .slice(0, 12)
      .map((ball) => {
        const extras = ball.extras_type && ball.extras_type !== "none" ? ` + ${ball.extras_runs} ${String(ball.extras_type).replace("_", " ")}` : "";
        const wicket = ball.wicket ? " · W" : "";
        const runs = String(ball.runs_bat ?? 0);
        const chipClass =
          runs === "4" ? "is-four" :
          runs === "6" ? "is-six" :
          wicket ? "is-wicket" :
          ball.extras_type && ball.extras_type !== "none" ? "is-extra" :
          "is-dot";
        return `
          <article class="public-ball-chip ${chipClass}">
            <strong>${escapeHtml(ball.over_number)}.${escapeHtml(ball.ball_number)}</strong>
            <span>${escapeHtml(ball.runs_bat ?? 0)}${escapeHtml(extras)}${escapeHtml(wicket)}</span>
          </article>
        `;
      })
      .join("");
  }

  function shortTeamCode(name) {
    return String(name || "CL")
      .split(/\s+/)
      .map((part) => part[0] || "")
      .join("")
      .slice(0, 2)
      .toUpperCase() || "CL";
  }

  function targetText(match, liveScore) {
    const raw = liveScore.target || match.target || match.chase_target || "";
    return raw ? String(raw) : "--";
  }

  async function loadMatch() {
    const matchId = matchIdFromPath();
    if (!matchId) {
      if (readOnlyNoteEl) {
        readOnlyNoteEl.textContent = "Match not found.";
      }
      return;
    }
    try {
      const response = await fetch(`/api/public/match/${encodeURIComponent(matchId)}`, { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error("Public scorecard could not be loaded.");
      }
      const data = await response.json();
      const match = data.match || {};
      const innings = Array.isArray(match.scorebook?.innings) ? match.scorebook.innings : [];
      const liveScore = match.scorecard || {};
      const firstInning = innings[0]?.summary || {};
      const secondInning = innings[1]?.summary || {};
      const recentBalls = innings.flatMap((inning) => Array.isArray(inning.balls) ? inning.balls : []);
      const requiredRuns = match.required_runs ?? liveScore.required_runs ?? match.chase_required_runs ?? "--";
      const requiredRate = match.required_run_rate ?? liveScore.required_run_rate ?? "--";
      const ballsLeft = match.balls_left ?? liveScore.balls_left ?? "--";

      document.title = `${match.club_name || "Club"} vs ${match.opponent || "Opponent"} · Public Scorecard`;
      if (titleEl) {
        titleEl.textContent = `${match.club_name || "Club"} vs ${match.opponent || "Opponent"}`;
      }
      if (metaEl) {
        metaEl.textContent = `${match.date_label || match.date || "Date TBD"} · ${match.venue || "Venue TBD"} · ${match.match_type || "Friendly"} · ${match.scheduled_time || "Time TBD"}`;
      }
      if (teamOneBadgeEl) {
        teamOneBadgeEl.textContent = shortTeamCode(match.club_name || "Club");
      }
      if (teamTwoBadgeEl) {
        teamTwoBadgeEl.textContent = shortTeamCode(match.opponent || "Opp");
      }
      if (opponentTitleEl) {
        opponentTitleEl.textContent = match.opponent || "Opponent";
      }
      if (venueEl) {
        venueEl.textContent = `${match.venue || "Venue TBD"} · ${match.match_type || "Friendly"}`;
      }
      if (teamOneScoreEl) {
        teamOneScoreEl.textContent = `${liveScore.heartlake_runs || match.heartlake_score || "--"}/${liveScore.heartlake_wickets || "--"}`;
      }
      if (teamOneOversEl) {
        teamOneOversEl.textContent = `${liveScore.heartlake_overs || "--"} overs`;
      }
      if (teamTwoScoreEl) {
        teamTwoScoreEl.textContent = `${liveScore.opponent_runs || match.opponent_score || "--"}/${liveScore.opponent_wickets || "--"}`;
      }
      if (teamTwoOversEl) {
        teamTwoOversEl.textContent = `${liveScore.opponent_overs || "--"} overs`;
      }
      if (targetEl) {
        targetEl.textContent = targetText(match, liveScore);
      }
      if (statusEl) {
        statusEl.textContent = match.status || "Scheduled";
      }
      if (requiredRunsEl) {
        requiredRunsEl.textContent = String(requiredRuns);
      }
      if (requiredRateEl) {
        requiredRateEl.textContent = `Required rate ${requiredRate}`;
      }
      if (ballsLeftEl) {
        ballsLeftEl.textContent = String(ballsLeft);
      }
      if (momentumEl) {
        momentumEl.textContent = match.live_summary || liveScore.live_summary || "Read-only public scorecard";
      }
      if (availabilityCountEl) {
        availabilityCountEl.textContent = `${Array.isArray(match.availability) ? match.availability.length : 0} responses`;
      }
      if (selectionCountEl) {
        selectionCountEl.textContent = `${Array.isArray(match.selected_playing_xi) ? match.selected_playing_xi.length : 0} selected XI`;
      }
      if (recentBallsEl) {
        recentBallsEl.innerHTML = renderRecentBalls(recentBalls);
      }
      if (inningsEl) {
        inningsEl.innerHTML = innings.length
          ? innings
              .map((inning) => {
                const summary = inning.summary || {};
                const battingRows = Array.isArray(summary.batting) ? summary.batting : [];
                const bowlingRows = Array.isArray(summary.bowling) ? summary.bowling : [];
                return `
                  <article class="public-innings-card">
                    <div class="public-innings-head">
                      <div>
                        <p class="section-kicker">Inning ${escapeHtml(inning.inning_number || 1)}</p>
                        <h3>${escapeHtml(inning.batting_team || "Batting team")} vs ${escapeHtml(inning.bowling_team || "Bowling team")}</h3>
                      </div>
                      <div class="public-innings-score">
                        <strong>${escapeHtml(summary.runs ?? 0)}/${escapeHtml(summary.wickets ?? 0)}</strong>
                        <small>${escapeHtml(formatOvers(summary.overs || "0.0"))} overs · ${escapeHtml(inning.status || "Not started")}</small>
                      </div>
                    </div>
                    <div class="public-score-section-grid">
                      <div>
                        <strong>Batting card</strong>
                        ${renderBattingTable(battingRows)}
                      </div>
                      <div>
                        <strong>Bowling card</strong>
                        ${renderBowlingTable(bowlingRows)}
                      </div>
                      <div class="wide">
                        <strong>Recent balls</strong>
                        ${renderBalls(Array.isArray(inning.balls) ? inning.balls : [])}
                      </div>
                    </div>
                  </article>
                `;
              })
              .join("")
          : `<div class="public-empty">No scorebook entries have been logged yet for this match.</div>`;
      }
      if (commentaryEl) {
        const commentary = Array.isArray(match.commentary) ? match.commentary.slice().reverse() : [];
        commentaryEl.innerHTML = commentary.length
          ? commentary
              .map(
                (item) => `
                  <article class="detail-card">
                    <strong>${escapeHtml(String(item.mode || "text").toUpperCase())}</strong>
                    <p>${escapeHtml(item.text || "")}</p>
                    <small>${escapeHtml(item.created_at || "")}</small>
                  </article>
                `,
              )
              .join("")
          : `<div class="public-empty">No commentary has been added yet.</div>`;
      }
      if (performancesEl) {
        const performances = Array.isArray(match.performances) ? match.performances : [];
        performancesEl.innerHTML = performances.length
          ? performances
              .map(
                (item) => `
                  <article class="detail-card">
                    <strong>${escapeHtml(item.player_name || "Player")}</strong>
                    <p>${escapeHtml(item.runs ?? 0)} runs · ${escapeHtml(item.wickets ?? 0)} wickets · ${escapeHtml(item.catches ?? 0)} catches</p>
                    <small>${escapeHtml(item.notes || item.source || "")}</small>
                  </article>
                `,
              )
              .join("")
          : `<div class="public-empty">No player performances have been published yet.</div>`;
      }
      if (readOnlyNoteEl) {
        readOnlyNoteEl.hidden = false;
        readOnlyNoteEl.textContent = "Read-only public scorecard. Sign in to manage scoring, availability, and lineups.";
      }
    } catch (error) {
      console.error("[Public Match]", error);
      if (readOnlyNoteEl) {
        readOnlyNoteEl.hidden = false;
        readOnlyNoteEl.textContent = "This scorecard could not be loaded right now.";
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadMatch);
  } else {
    loadMatch();
  }
})();
