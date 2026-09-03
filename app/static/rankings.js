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

  function rowCard(rank, title, meta, value, tone = "") {
    return `
      <article class="rankings-row-card ${tone}">
        <div class="rankings-row-left">
          <span class="signin-rank">${rank}</span>
          <div>
            <strong>${escapeHtml(title)}</strong>
            <small>${escapeHtml(meta)}</small>
          </div>
        </div>
        <span class="signin-widget-pill">${escapeHtml(value)}</span>
      </article>
    `;
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
      if (battingEl) {
        battingEl.innerHTML = batting.length
          ? batting.map((row, index) => rowCard(index + 1, row.player_name || "Player", `${formatNumber(row.runs)} runs · ${formatNumber(row.batting_average, 1)} avg · ${formatNumber(row.matches)} matches`, `${formatNumber(row.runs)} runs`)).join("")
          : `<div class="live-empty">No batting leaders yet.</div>`;
      }
      if (bowlingEl) {
        bowlingEl.innerHTML = bowling.length
          ? bowling.map((row, index) => rowCard(index + 1, row.player_name || "Player", `${formatNumber(row.wickets)} wickets · ${formatNumber(row.wickets_per_match, 1)} wickets/match · ${formatNumber(row.matches)} matches`, `${formatNumber(row.wickets)} wickets`)).join("")
          : `<div class="live-empty">No bowling leaders yet.</div>`;
      }
      if (clubsEl) {
        clubsEl.innerHTML = clubs.length
          ? clubs.map((row, index) => rowCard(index + 1, row.club_name || "Club", `${formatNumber(row.matches_won)} won · ${formatNumber(row.matches_played)} played`, `${formatNumber((Number(row.win_rate || 0) * 100), 0)}%`)).join("")
          : `<div class="live-empty">No club results yet.</div>`;
      }
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
