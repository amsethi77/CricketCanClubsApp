/*
 * Stats page extras (/dashboard/widgets/performance, menu "Stats"). README: "Stats: basic for everyone, more for Pro".
 *  - Everyone signed in: season rankings, team roster and scoreboard (rendered by app.js).
 *  - Only people who can manage players: the Invite player and Add player performance forms
 *    (hidden with CSS from <body data-can-manage="0">, set by main.py; the APIs check permissions too).
 *  - Pro members and site admins (<body data-paid="1">): "Season by season" table, each player's runs and
 *    wickets per season. Free members see a short "Pro" card with an Upgrade link instead.
 *  - If the chosen season has no numbers yet but another season does, a hint offers to switch to it.
 */
(() => {
  if (document.body.dataset.dashboardWidget !== "performance") return;
  const paid = document.body.dataset.paid === "1";
  const box = document.getElementById("statsProTrends");
  const hint = document.getElementById("statsSeasonHint");
  const yearSelect = document.getElementById("rankingYearSelect");
  let byYear = {};

  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);

  function renderLocked() {
    box.innerHTML = `
      <div class="stats-pro-card stats-pro-locked">
        <p class="section-kicker">Pro</p>
        <h3>Season by season</h3>
        <p>See every player's runs and wickets for each season side by side, and who improved the most.</p>
        <a class="primary-button" href="/pricing">Upgrade to Pro</a>
      </div>`;
  }

  function renderTrends(rows, years) {
    if (!rows.length) {
      box.innerHTML = `
        <div class="stats-pro-card">
          <p class="section-kicker">Pro</p>
          <h3>Season by season</h3>
          <p class="empty-state">Numbers show here once scorecards are published or matches are scored in the app.</p>
        </div>`;
      return;
    }
    const head = years.map((year) => `<th scope="col">${esc(year)}</th>`).join("");
    const body = rows
      .map((row) => {
        const cells = years
          .map((year) => {
            const s = row.years[year];
            return `<td>${s ? `<strong>${s.runs}</strong> runs<br><small>${s.wickets} wkts</small>` : "–"}</td>`;
          })
          .join("");
        return `<tr><th scope="row">${esc(row.name)}</th>${cells}<td>${row.best ? esc(row.best) : "–"}</td></tr>`;
      })
      .join("");
    const improved = rows
      .filter((row) => row.change > 0)
      .sort((a, b) => b.change - a.change)[0];
    box.innerHTML = `
      <div class="stats-pro-card">
        <p class="section-kicker">Pro</p>
        <h3>Season by season</h3>
        ${improved ? `<p>📈 Most improved: <strong>${esc(improved.name)}</strong>, +${improved.change} runs on the season before.</p>` : ""}
        <div class="stats-pro-scroll">
          <table class="stats-pro-table">
            <thead><tr><th scope="col">Player</th>${head}<th scope="col">Best season</th></tr></thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      </div>`;
  }

  function seasonHint() {
    if (!hint || !yearSelect) return;
    const chosen = yearSelect.value;
    const withData = Object.keys(byYear)
      .filter((year) => byYear[year] > 0)
      .sort()
      .reverse();
    if (!chosen || byYear[chosen] > 0 || !withData.length) {
      hint.hidden = true;
      return;
    }
    hint.hidden = false;
    hint.className = "status-banner info stats-season-hint";
    hint.innerHTML = `No numbers for ${esc(chosen)} yet. <button type="button" class="secondary-button" data-year="${esc(withData[0])}">See ${esc(withData[0])}</button>`;
  }

  hint?.addEventListener("click", (event) => {
    const year = event.target.closest("[data-year]")?.dataset.year;
    if (!year || !yearSelect) return;
    yearSelect.value = year;
    yearSelect.dispatchEvent(new Event("change", { bubbles: true }));
    setTimeout(seasonHint, 300);
  });
  yearSelect?.addEventListener("change", () => setTimeout(seasonHint, 300));
  // app.js fills the season list after its own data load: check again when the options appear.
  if (yearSelect) new MutationObserver(() => setTimeout(seasonHint, 100)).observe(yearSelect, { childList: true });

  if (!paid && box) renderLocked();

  fetch("/api/dashboard", { credentials: "same-origin" })
    .then((response) => (response.ok ? response.json() : null))
    .then((data) => {
      if (!data) return;
      const memberIds = new Set((data.members || []).map((member) => String(member.id)));
      const players = {};
      byYear = {};
      for (const stat of data.member_year_stats || []) {
        if (!memberIds.has(String(stat.member_id))) continue;
        const year = String(stat.season_year || "");
        const runs = Number(stat.runs || 0);
        const wickets = Number(stat.wickets || 0);
        byYear[year] = (byYear[year] || 0) + runs + wickets;
        if (!runs && !wickets) continue;
        const player = (players[stat.member_id] ||= { name: stat.player_name || stat.full_name || "Player", years: {}, total: 0 });
        player.years[year] = { runs, wickets };
        player.total += runs;
      }
      seasonHint();
      if (!paid || !box) return;
      const years = Object.keys(byYear).filter((year) => byYear[year] > 0).sort().slice(-4);
      const rows = Object.values(players)
        .map((player) => {
          let best = "";
          let bestRuns = -1;
          for (const year of years) {
            const s = player.years[year];
            if (s && s.runs > bestRuns) {
              bestRuns = s.runs;
              best = year;
            }
          }
          const last = player.years[years[years.length - 1]]?.runs || 0;
          const before = player.years[years[years.length - 2]]?.runs || 0;
          return { ...player, best, change: years.length > 1 && before ? last - before : 0 };
        })
        .sort((a, b) => b.total - a.total)
        .slice(0, 15);
      renderTrends(rows, years);
    })
    .catch(() => {});
})();
