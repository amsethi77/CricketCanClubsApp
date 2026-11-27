(() => {
  const battingEl = document.getElementById("rankingsBatting");
  const bowlingEl = document.getElementById("rankingsBowling");
  const clubsEl = document.getElementById("rankingsClubs");
  const battingCountEl = document.getElementById("rankingsBattingCount");
  const bowlingCountEl = document.getElementById("rankingsBowlingCount");
  const clubCountEl = document.getElementById("rankingsClubCount");

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatNumber(value, digits = 0) {
    const number = Number(value || 0);
    if (!Number.isFinite(number)) return "0";
    if (digits > 0) return number.toFixed(digits).replace(/\.0+$/, "").replace(/(\.\d*?)0+$/, "$1");
    return String(Math.round(number));
  }

  // rows may carry their own rank (rankings) and is_me (the signed-in player, shown highlighted; when he is
  // outside the top 10 his row comes last, after a "..." row)
  function renderTable(container, caption, rows, columns, me = null) {
    if (!container) return;
    if (!rows.length && !me) {
      container.classList.remove("rankings-table-wrap");
      container.innerHTML = `<div class="live-empty">No ${escapeHtml(caption.toLowerCase())} yet.</div>`;
      return;
    }
    const line = (row, index) => `
          <tr${row.is_me ? ' class="rankings-me"' : ""}>
            <td><span class="rank-badge">${row.rank === null ? "-" : escapeHtml(row.rank ?? index + 1)}</span></td>
            ${columns.map((column, at) => `<td${column.numeric ? ' class="numeric-data"' : ""}>${escapeHtml(column.value(row))}${at === 0 && row.is_me ? ' <span class="rankings-you">You</span>' : ""}</td>`).join("")}
          </tr>`;
    container.classList.add("rankings-table-wrap");
    container.innerHTML = `
      <table class="custom-table">
        <caption>${escapeHtml(caption)}</caption>
        <thead><tr><th scope="col"><span class="rt-long">Rank</span><span class="rt-short">#</span></th>${columns.map((column) => `<th scope="col"${column.numeric ? ' class="numeric-data"' : ""}>${column.short ? `<span class="rt-long">${escapeHtml(column.label)}</span><span class="rt-short" title="${escapeHtml(column.label)}">${escapeHtml(column.short)}</span>` : escapeHtml(column.label)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map(line).join("")}${me ? `<tr class="rankings-gap"><td colspan="${columns.length + 1}">…</td></tr>${line(me, rows.length)}` : ""}
        </tbody>
      </table>
      ${me && me.rank === null ? `<p class="rankings-note">You are not ranked yet this season - ${caption.includes("owling") ? "take a wicket" : "score a run"} to get on the table.</p>` : ""}`;
  }

  async function renderBattingChart(rows, clubScoped = false) {
    const panel = document.querySelector(".rankings-chart-panel");
    const chart = document.getElementById("rankingsBattingChart");
    if (!panel || !chart || !window.Plotly || !rows.length) {
      if (panel) panel.hidden = true;
      return;
    }

    try {
      let figure;
      if (clubScoped) {
        figure = {
          data: [{ type: "bar", x: rows.slice(0, 10).map((row) => row.player_name || "Player"), y: rows.slice(0, 10).map((row) => Number(row.runs || 0)), marker: { color: "#D32F2F" } }],
          layout: { autosize: true, margin: { l: 40, r: 16, t: 12, b: 80 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { family: "Roboto, sans-serif" }, xaxis: { automargin: true }, yaxis: { rangemode: "tozero", gridcolor: "#EAEAEA" } },
        };
      } else {
        const response = await fetch("/api/public/rankings-chart", { headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("Unable to load the rankings chart.");
        figure = await response.json();
      }
      chart.hidden = false;
      panel.hidden = false;
      await window.Plotly.newPlot(chart, figure.data || [], figure.layout || {}, {
        responsive: true,
        displayModeBar: false,
      });
    } catch (error) {
      console.warn("[Rankings] Chart could not be rendered.", error);
      panel.hidden = true;
    }
  }

  // Nov 14 2026 (Amit): top 10 batters and bowlers of all clubs for the latest season (it starts again with the
  // first match of the new year); a signed-in player also sees his own rank (11 rows when he is outside the top 10).
  async function loadRankings() {
    try {
      let token = "";
      try {
        token = localStorage.getItem("cricketClubAppAuthToken") || "";
      } catch (error) {
        token = "";
      }
      const headers = { Accept: "application/json", ...(token ? { "X-Auth-Token": token } : {}) };
      const [response, publicResponse] = await Promise.all([
        fetch("/api/rankings", { headers }),
        fetch("/api/public/signin-stats", { headers: { Accept: "application/json" } }),
      ]);
      if (!response.ok) throw new Error("Unable to load rankings.");
      const data = await response.json();
      const publicData = publicResponse && publicResponse.ok ? await publicResponse.json() : {};
      const batting = data.batting?.top || [];
      const bowling = data.bowling?.top || [];
      const clubs = Array.isArray(publicData.club_leaders) ? publicData.club_leaders : [];
      const season = data.season || "";
      const seasonEl = document.getElementById("rankingsSeason");
      if (seasonEl) seasonEl.textContent = season;
      const lede = document.getElementById("rankingsLede");
      if (lede) {
        lede.textContent = data.linked_player
          ? `Top 10 batters and bowlers of all clubs in the ${season} season, and where you stand.`
          : `Top 10 batters and bowlers of all clubs in the ${season} season. Sign in to see your own rank.`;
      }
      if (battingCountEl) battingCountEl.textContent = `${batting.length + (data.batting?.me ? 1 : 0)} shown`;
      if (bowlingCountEl) bowlingCountEl.textContent = `${bowling.length + (data.bowling?.me ? 1 : 0)} shown`;
      if (clubCountEl) clubCountEl.textContent = `${clubs.length} shown`;
      renderTable(battingEl, `Batting leaders ${season}`, batting, [
        { label: "Player", value: (row) => row.player_name || "Player" },
        { label: "Runs", value: (row) => formatNumber(row.runs), numeric: true },
        { label: "Average", short: "Avg", value: (row) => formatNumber(row.batting_average, 1), numeric: true },
        { label: "Matches", short: "Mat", value: (row) => formatNumber(row.matches), numeric: true },
      ], data.batting?.me || null);
      renderTable(bowlingEl, `Bowling leaders ${season}`, bowling, [
        { label: "Player", value: (row) => row.player_name || "Player" },
        { label: "Wickets", short: "Wkts", value: (row) => formatNumber(row.wickets), numeric: true },
        { label: "Wickets / match", short: "W/M", value: (row) => formatNumber(row.wickets_per_match, 1), numeric: true },
        { label: "Matches", short: "Mat", value: (row) => formatNumber(row.matches), numeric: true },
      ], data.bowling?.me || null);
      renderTable(clubsEl, "Club standings", clubs, [
        { label: "Club", value: (row) => row.club_name || "Club" },
        { label: "Won", short: "W", value: (row) => formatNumber(row.matches_won), numeric: true },
        { label: "Lost", short: "L", value: (row) => formatNumber(row.matches_lost || 0), numeric: true },
        { label: "No result", short: "NR", value: (row) => formatNumber(row.matches_nr || 0), numeric: true },
        { label: "Played", short: "P", value: (row) => formatNumber(row.matches_played), numeric: true },
        // Nov 11 2026: no decided game yet (only one innings uploaded) -> "-" instead of a misleading 0%
        { label: "Win rate", short: "Win %", value: (row) => (Number(row.matches_won || 0) + Number(row.matches_lost || 0) ? `${formatNumber(Number(row.win_rate || 0) * 100)}%` : "-"), numeric: true },
      ]);
      renderBattingChart(batting, true);
    } catch (error) {
      console.error("[Rankings]", error);
      if (battingEl) battingEl.innerHTML = `<div class="live-empty">Rankings could not be loaded right now.</div>`;
      if (bowlingEl) bowlingEl.innerHTML = `<div class="live-empty">Rankings could not be loaded right now.</div>`;
      if (clubsEl) clubsEl.innerHTML = `<div class="live-empty">Rankings could not be loaded right now.</div>`;
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadRankings);
  } else {
    loadRankings();
  }
})();
