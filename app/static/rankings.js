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

  function renderTable(container, caption, rows, columns) {
    if (!container) return;
    if (!rows.length) {
      container.classList.remove("rankings-table-wrap");
      container.innerHTML = `<div class="live-empty">No ${escapeHtml(caption.toLowerCase())} yet.</div>`;
      return;
    }
    container.classList.add("rankings-table-wrap");
    container.innerHTML = `
      <table class="custom-table">
        <caption>${escapeHtml(caption)}</caption>
        <thead><tr><th scope="col">Rank</th>${columns.map((column) => `<th scope="col">${escapeHtml(column.label)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((row, index) => `
          <tr>
            <td><span class="rank-badge">${index + 1}</span></td>
            ${columns.map((column) => `<td${column.numeric ? ' class="numeric-data"' : ""}>${escapeHtml(column.value(row))}</td>`).join("")}
          </tr>`).join("")}
        </tbody>
      </table>`;
  }

  function renderBattingChart(rows) {
    const panel = document.querySelector(".rankings-chart-panel");
    const chart = document.getElementById("rankingsBattingChart");
    if (!panel || !chart || !window.Plotly || !rows.length) {
      if (panel) panel.hidden = true;
      return;
    }

    const players = rows.map((row) => String(row.player_name || "Player"));
    const runs = rows.map((row) => Number(row.runs) || 0);
    chart.hidden = false;
    panel.hidden = false;

    window.Plotly.newPlot(
      chart,
      [{
        type: "bar",
        x: players,
        y: runs,
        marker: { color: "#D32F2F", line: { color: "#9A1B1B", width: 1 } },
        hovertemplate: "%{x}<br>%{y} runs<extra></extra>",
      }],
      {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { family: "Inter, sans-serif", color: "#1A1A1A" },
        margin: { t: 12, r: 12, b: 72, l: 48 },
        xaxis: { tickangle: -25, automargin: true, showgrid: false, zeroline: false },
        yaxis: { title: "Runs", gridcolor: "#EAEAEA", zeroline: false, rangemode: "tozero" },
      },
      { responsive: true, displayModeBar: false }
    ).catch((error) => {
      console.warn("[Rankings] Chart could not be rendered.", error);
      panel.hidden = true;
    });
  }

  async function loadRankings() {
    try {
      const response = await fetch("/api/public/signin-stats", { headers: { Accept: "application/json" } });
      if (!response.ok) {
        throw new Error("Unable to load rankings.");
      }
      const data = await response.json();
      const batting = Array.isArray(data.batting_leaders) ? data.batting_leaders : [];
      const bowling = Array.isArray(data.bowling_leaders) ? data.bowling_leaders : [];
      const clubs = Array.isArray(data.club_leaders) ? data.club_leaders : [];
      if (battingCountEl) battingCountEl.textContent = `${batting.length} shown`;
      if (bowlingCountEl) bowlingCountEl.textContent = `${bowling.length} shown`;
      if (clubCountEl) clubCountEl.textContent = `${clubs.length} shown`;
      renderTable(battingEl, "Batting leaders", batting, [
        { label: "Player", value: (row) => row.player_name || "Player" },
        { label: "Runs", value: (row) => formatNumber(row.runs), numeric: true },
        { label: "Average", value: (row) => formatNumber(row.batting_average, 1), numeric: true },
        { label: "Matches", value: (row) => formatNumber(row.matches), numeric: true },
      ]);
      renderTable(bowlingEl, "Bowling leaders", bowling, [
        { label: "Player", value: (row) => row.player_name || "Player" },
        { label: "Wickets", value: (row) => formatNumber(row.wickets), numeric: true },
        { label: "Wickets / match", value: (row) => formatNumber(row.wickets_per_match, 1), numeric: true },
        { label: "Matches", value: (row) => formatNumber(row.matches), numeric: true },
      ]);
      renderTable(clubsEl, "Club standings", clubs, [
        { label: "Club", value: (row) => row.club_name || "Club" },
        { label: "Won", value: (row) => formatNumber(row.matches_won), numeric: true },
        { label: "Played", value: (row) => formatNumber(row.matches_played), numeric: true },
        { label: "Win rate", value: (row) => `${formatNumber(Number(row.win_rate || 0) * 100)}%`, numeric: true },
      ]);
      renderBattingChart(batting);
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
