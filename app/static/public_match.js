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
  const battersEl = document.getElementById("publicMatchBatters");
  const bowlersEl = document.getElementById("publicMatchBowlers");
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

  function uniqueByName(rows) {
    const seen = new Set();
    return rows.filter((row) => {
      const key = String(row.player_name || "").trim().toLowerCase();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function renderBattingCards(rows) {
    if (!rows.length) {
      return `<div class="public-empty public-empty-dark">No batting figures recorded yet.</div>`;
    }
    return rows
      .map(
        (row) => `
          <article class="public-player-card">
            <div class="public-player-card-head">
              <div>
                <strong>${escapeHtml(row.player_name || "Player")}</strong>
                <small>${escapeHtml(row.dismissal || row.notes || "Batting card")}</small>
              </div>
              <div class="public-player-card-score">
                <span>${escapeHtml(row.runs ?? 0)}</span>
                <small>runs</small>
              </div>
            </div>
            <div class="public-player-card-grid">
              <div>
                <span>Balls</span>
                <strong>${escapeHtml(row.balls ?? 0)}</strong>
              </div>
              <div>
                <span>SR</span>
                <strong>${escapeHtml(Number(row.strike_rate || 0).toFixed(1).replace(/\.0$/, ""))}</strong>
              </div>
              <div>
                <span>4s</span>
                <strong>${escapeHtml(row.fours ?? 0)}</strong>
              </div>
              <div>
                <span>6s</span>
                <strong>${escapeHtml(row.sixes ?? 0)}</strong>
              </div>
            </div>
          </article>
        `,
      )
      .join("");
  }

  function renderBowlingCards(rows) {
    if (!rows.length) {
      return `<div class="public-empty public-empty-dark">No bowling figures recorded yet.</div>`;
    }
    return rows
      .map(
        (row) => `
          <article class="public-player-card">
            <div class="public-player-card-head">
              <div>
                <strong>${escapeHtml(row.player_name || "Bowler")}</strong>
                <small>${escapeHtml(row.notes || "Bowling card")}</small>
              </div>
              <div class="public-player-card-score">
                <span>${escapeHtml(row.wickets ?? 0)}</span>
                <small>wkts</small>
              </div>
            </div>
            <div class="public-player-card-grid">
              <div>
                <span>Overs</span>
                <strong>${escapeHtml(row.overs || "0.0")}</strong>
              </div>
              <div>
                <span>Runs</span>
                <strong>${escapeHtml(row.runs_conceded ?? 0)}</strong>
              </div>
              <div>
                <span>Econ</span>
                <strong>${escapeHtml(Number(row.economy || 0).toFixed(1).replace(/\.0$/, ""))}</strong>
              </div>
              <div>
                <span>Dots</span>
                <strong>${escapeHtml(row.dot_balls ?? 0)}</strong>
              </div>
            </div>
          </article>
        `,
      )
      .join("");
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
      const recentBalls = innings.flatMap((inning) => Array.isArray(inning.balls) ? inning.balls : []);
      const battingRows = uniqueByName(
        innings.flatMap((inning) => (Array.isArray(inning.summary?.batting) ? inning.summary.batting : [])),
      ).slice(0, 8);
      const bowlingRows = uniqueByName(
        innings.flatMap((inning) => (Array.isArray(inning.summary?.bowling) ? inning.summary.bowling : [])),
      ).slice(0, 8);
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
      if (battersEl) {
        battersEl.innerHTML = renderBattingCards(battingRows);
      }
      if (bowlersEl) {
        bowlersEl.innerHTML = renderBowlingCards(bowlingRows);
      }
      if (commentaryEl) {
        const commentary = Array.isArray(match.commentary) ? match.commentary.slice().reverse() : [];
        commentaryEl.innerHTML = commentary.length
          ? commentary
              .map(
                (item) => `
                  <article class="public-timeline-item">
                    <div class="public-timeline-dot ${escapeHtml(String(item.mode || "text").toLowerCase())}"></div>
                    <div class="public-timeline-copy">
                      <strong>${escapeHtml(String(item.mode || "text").toUpperCase())}</strong>
                      <p>${escapeHtml(item.text || "")}</p>
                      <small>${escapeHtml(item.created_at || "")}</small>
                    </div>
                  </article>
                `,
              )
              .join("")
          : `<div class="public-empty public-empty-dark">No commentary has been added yet.</div>`;
      }
      if (performancesEl) {
        const performances = Array.isArray(match.performances) ? match.performances : [];
        performancesEl.innerHTML = performances.length
          ? performances
              .map(
                (item) => `
                  <article class="public-player-card">
                    <div class="public-player-card-head">
                      <div>
                        <strong>${escapeHtml(item.player_name || "Player")}</strong>
                        <small>${escapeHtml(item.source || item.notes || "Performance")}</small>
                      </div>
                      <div class="public-player-card-score">
                        <span>${escapeHtml(item.runs ?? 0)}</span>
                        <small>runs</small>
                      </div>
                    </div>
                    <div class="public-player-card-grid">
                      <div>
                        <span>Wkts</span>
                        <strong>${escapeHtml(item.wickets ?? 0)}</strong>
                      </div>
                      <div>
                        <span>Catches</span>
                        <strong>${escapeHtml(item.catches ?? 0)}</strong>
                      </div>
                      <div>
                        <span>Score</span>
                        <strong>${escapeHtml((item.confidence ?? item.runs ?? 0))}</strong>
                      </div>
                      <div>
                        <span>Status</span>
                        <strong>${escapeHtml(item.status || "Published")}</strong>
                      </div>
                    </div>
                  </article>
                `,
              )
              .join("")
          : `<div class="public-empty public-empty-dark">No player performances have been published yet.</div>`;
      }
      if (readOnlyNoteEl) {
        readOnlyNoteEl.hidden = false;
        readOnlyNoteEl.textContent = "Read-only public scorecard.";
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
