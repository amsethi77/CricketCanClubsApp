/*
 * Shared innings markup (Nov 9 2026): the uploaded scorecard page (scorecard.js), the Admin Center preview and the
 * live match page (public_match.js) all draw innings with these functions, so one scorecard looks the same everywhere.
 * Styles: public_match.css.
 */
(() => {
  const DASH = "–";

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function num(value) {
    return value === null || value === undefined || value === "" ? DASH : escapeHtml(value);
  }

  // "c Singh b Singh" -> "c & b Singh" (caught by the bowler), README req 165
  function howOutText(text) {
    const m = /^c\s+(.+?)\s+b\s+(.+)$/i.exec(String(text || "").trim());
    return m && m[1].trim().toLowerCase() === m[2].trim().toLowerCase() ? `c & b ${m[2].trim()}` : String(text || "");
  }

  const rate = (runs, overs) => {
    const o = Number(overs);
    if (!Number.isFinite(o) || !o || runs === null || runs === undefined) return "";
    const balls = Math.floor(o) * 6 + Math.round((o - Math.floor(o)) * 10);
    return balls ? ((Number(runs) / balls) * 6).toFixed(2) : "";
  };

  // A registered player's name opens his read-only profile (/players/<player id>). `suffix` is ready-made HTML (captain tag).
  function nameHtml(name, playerKey, suffix = "") {
    return playerKey
      ? `<a class="pm-name" href="/players/${encodeURIComponent(playerKey)}">${escapeHtml(name)}${suffix}</a>`
      : `<span class="pm-name">${escapeHtml(name)}${suffix}</span>`;
  }

  // Nov 16 2026 (Amit: "make sure we have the icon shown besides the player names - captain, vc, wk ... for uploaded
  // scorecards as well"); Nov 17 2026 (Dhruvika: "did you match the icons with cric buss?"): written the Cricbuzz way,
  // after the name: "Rohit (c)", "Pant (wk)", "Ravi (c & wk)", "Sam (vc)". row.tags come from the server for uploaded
  // and live-scored cards alike. Batter / bowler icons are not on scorecards (Cricbuzz has none there); they stay on
  // player lists (Admin Center -> People & roles).
  // Nov 17 2026 (Dhruvika: "change the icon of bowler, place a ball instead"): a red cricket ball for bowlers
  const BALL_ICON = '<svg class="pm-ballicon" viewBox="0 0 16 16" width="1em" height="1em" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="#c8102e"/><circle cx="6" cy="5.5" r="2" fill="#fff" opacity=".25"/><path d="M5.2 1.6c1.6 3.9 1.6 8.9 0 12.8M10.8 1.6c-1.6 3.9-1.6 8.9 0 12.8" fill="none" stroke="#fff" stroke-width=".9" stroke-dasharray="1.1 1"/></svg>';
  const ROLE_ICONS = { Batter: "🏏", Bowler: BALL_ICON, "All-rounder": "⚡", "Wicket keeper": "🧤" };
  const TAG_NAMES = { C: "Captain", VC: "Vice-captain", WK: "Wicket keeper" };
  // Nov 17 2026 role icons after the name were removed on Nov 20 2026 (Dhruvika: "remove the batter and bowler icons,
  // but keep the C, VC, WK"): names show only (c) / (vc) / (wk). ROLE_ICONS stays for other code that may use it.
  const ROLE_SOURCE = { profile: "", career: " (from his figures)", match: " (in this match)" };
  function roleBadges(row = {}) {
    const tags = (Array.isArray(row.tags) ? row.tags : []).filter((tag) => TAG_NAMES[tag]);
    const text = tags.map((tag) => tag.toLowerCase()).join(" & ");
    const tagHtml = tags.length ? ` <span class="pm-cap" title="${escapeHtml(tags.map((tag) => TAG_NAMES[tag]).join(", "))}">(${escapeHtml(text)})</span>` : "";
    // Nov 20 2026 (Dhruvika: "remove the batter and bowler icons, but keep the C, VC, WK"): only (c) / (vc) / (wk)
    return tagHtml;
  }

  function ballSplit(row, fields) {
    const bits = fields
      .filter(([key]) => row[key] !== null && row[key] !== undefined && row[key] !== "")
      .map(([key, label]) => `${label} ${escapeHtml(row[key])}`);
    return bits.length ? `<small class="pm-split">${bits.join(" · ")}</small>` : "";
  }

  // Nov 17 2026 (Dhruvika sent Cricbuzz's NZ v IND scorecard: "do similar to this"): a green bar "India  209-10
  // (42.1 Ov)"; grey header rows; Batter | how out | R B 4s 6s SR with R bold; "Shreyas Iyer (c)", "Ishan Kishan (wk)"
  // as part of the name; "Extras 10 (b 0, lb 2, w 7, nb 1, p 0)"; "Total 209-10 (42.1 Overs, RR: 4.96)"; Bowler
  // O M R W NB WD ECO with W bold; Fall of Wickets table (Batter | Score | Over); Partnerships table. Kept from Amit's
  // earlier asks: the 0s 1s 2s 3s columns (after SR, lighter) and a bowler's runs per over (small line).
  const scoreText = (runs, wickets) => (runs === null || runs === undefined ? DASH : `${escapeHtml(runs)}${wickets === null || wickets === undefined ? "" : `-${escapeHtml(wickets)}`}`);

  function battingTable(inn) {
    const batters = inn.batting || [];
    const has = (key) => batters.some((b) => b[key] !== null && b[key] !== undefined && b[key] !== "");
    const extra = [
      ["dots", "0s"],
      ["ones", "1s"],
      ["twos", "2s"],
      ["threes", "3s"],
    ].filter(([key]) => has(key));
    const cols = [["runs", "R", "pm-r"], ["balls", "B", ""], ["fours", "4s", ""], ["sixes", "6s", ""], ["strike_rate", "SR", ""], ...extra.map(([key, label]) => [key, label, "pm-more"])];
    const rows = batters
      .map((b) => {
        const how = howOutText(b.dismissal) || (b.not_out ? "not out" : "");
        return `<tr class="${b.not_out ? "pm-notout" : ""}">
          <th scope="row">${nameHtml(b.name, b.player_key, roleBadges(b))}${how ? `<small class="pm-how-m">${escapeHtml(how)}</small>` : ""}</th>
          <td class="pm-how">${escapeHtml(how)}</td>
          ${cols.map(([key, , cls]) => `<td class="pm-c${cls ? ` ${cls}` : ""}">${num(b[key])}</td>`).join("")}</tr>`;
      })
      .join("");
    const span = cols.length;
    const rr = rate(inn.runs, inn.overs);
    const totalBits = [inn.overs ? `${escapeHtml(inn.overs)} Overs` : "", rr ? `RR: ${rr}` : ""].filter(Boolean).join(", ");
    return `
      <div class="pm-table-wrap">
        <table class="pm-table pm-cb pm-bat">
          <thead><tr><th scope="col">Batter</th><th scope="col" class="pm-how"></th>${cols.map(([, label, cls]) => `<th scope="col" class="pm-c${cls ? ` ${cls}` : ""}">${label}</th>`).join("")}</tr></thead>
          <tbody>${rows || `<tr><td colspan="${span + 2}" class="pm-empty">Batting details were not recorded for this innings.</td></tr>`}</tbody>
        </table>
      </div>
      <table class="pm-table pm-cb pm-sum">
        <tr><th scope="row">Extras</th><td><b>${num(inn.extras)}</b>${inn.extras_detail ? ` (${escapeHtml(inn.extras_detail)})` : ""}</td></tr>
        <tr><th scope="row">Total</th><td><b>${scoreText(inn.runs, inn.wickets)}</b>${totalBits ? ` (${totalBits})` : ""}</td></tr>
        ${inn.did_not_bat && inn.did_not_bat.length ? `<tr><th scope="row">Did not Bat</th><td>${inn.did_not_bat.map((name) => `<span class="pm-name-in">${escapeHtml(name)}${roleBadges({ tags: (inn.did_not_bat_tags || {})[name] || [] })}</span>`).join(", ")}</td></tr>` : ""}
      </table>`;
  }

  function bowlingTable(inn) {
    if (!inn.bowling || !inn.bowling.length) return '<p class="pm-note">Bowling figures were not recorded for this innings.</p>';
    const rows = inn.bowling
      .map(
        (b) => `<tr>
          <th scope="row">${nameHtml(b.name, b.player_key, roleBadges(b))}${ballSplit(b, [["dots", "Dots"], ["fours", "4s"], ["sixes", "6s"]])}${Array.isArray(b.over_runs) && b.over_runs.length ? `<small class="pm-split">Runs per over: ${b.over_runs.map((value) => escapeHtml(value)).join(" · ")}</small>` : ""}</th>
          <td class="pm-c"${b.overs_approximate ? ' title="Approximate - shared out from the innings overs"' : ""}>${b.overs_approximate ? "≈" : ""}${num(b.overs)}</td><td class="pm-c">${num(b.maidens)}</td><td class="pm-c"${b.runs_approximate ? ' title="Approximate - shared out from the innings total"' : ""}>${b.runs_approximate ? "≈" : ""}${num(b.runs)}</td><td class="pm-c pm-r">${num(b.wickets)}</td><td class="pm-c">${num(b.no_balls)}</td><td class="pm-c">${num(b.wides)}</td><td class="pm-c">${num(b.economy)}</td></tr>`
      )
      .join("");
    return `
      <div class="pm-table-wrap">
        <table class="pm-table pm-cb pm-bowl">
          <thead><tr><th scope="col">Bowler</th><th scope="col" class="pm-c">O</th><th scope="col" class="pm-c">M</th><th scope="col" class="pm-c">R</th><th scope="col" class="pm-c">W</th><th scope="col" class="pm-c">NB</th><th scope="col" class="pm-c">WD</th><th scope="col" class="pm-c">ECO</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function fallOfWickets(inn) {
    const fow = Array.isArray(inn.fall_of_wickets) ? inn.fall_of_wickets : [];
    if (!fow.length) return "";
    return `
      <div class="pm-table-wrap">
        <table class="pm-table pm-cb pm-fowt">
          <thead><tr><th scope="col">Fall of Wickets</th><th scope="col" class="pm-c">Score</th><th scope="col" class="pm-c">Over</th></tr></thead>
          <tbody>${fow.map((w) => `<tr><th scope="row"><span class="pm-name">${escapeHtml(w.batter || "")}</span></th><td class="pm-c">${escapeHtml(w.runs)}-${escapeHtml(w.wicket)}</td><td class="pm-c">${escapeHtml(w.over || "")}</td></tr>`).join("")}</tbody>
        </table>
      </div>`;
  }

  function partnershipsTable(inn) {
    const list = Array.isArray(inn.partnerships) ? inn.partnerships : [];
    if (!list.length) return "";
    return `
      <div class="pm-table-wrap">
        <table class="pm-table pm-cb pm-part">
          <thead><tr><th scope="col" colspan="3">Partnerships</th></tr></thead>
          <tbody>${list
            .map(
              (p) => `<tr>
                <td class="pm-pl"><span class="pm-name-in">${escapeHtml(p.left || "")}</span> ${escapeHtml(p.left_runs)}(${escapeHtml(p.left_balls)})</td>
                <td class="pm-c"><b>${escapeHtml(p.runs)}</b>(${escapeHtml(p.balls)})</td>
                <td class="pm-pr">${p.right ? `${escapeHtml(p.right_runs)}(${escapeHtml(p.right_balls)}) <span class="pm-name-in">${escapeHtml(p.right)}</span>` : ""}</td></tr>`
            )
            .join("")}</tbody>
        </table>
      </div>`;
  }

  function inningsBlock(inn, open) {
    return `<section class="pm-inn pm-cb-inn${open ? " open" : ""}">
        <button type="button" class="pm-innhead" data-sc-inn aria-expanded="${open}">
          <span>${escapeHtml(inn.team)}</span>
          <b>${scoreText(inn.runs, inn.runs === null || inn.runs === undefined ? null : inn.wickets ?? 0)}${inn.overs ? ` <small>(${escapeHtml(inn.overs)} Ov)</small>` : ""}</b><i aria-hidden="true">▾</i>
        </button>
        <div class="pm-inn-body">${battingTable(inn)}${bowlingTable(inn)}${fallOfWickets(inn)}${partnershipsTable(inn)}</div>
      </section>`;
  }

  // Every innings of a card. Innings with figures show (and open); with none, all show and the last one opens.
  function inningsSections(card) {
    const innings = Array.isArray(card?.innings) ? card.innings : [];
    const blocks = innings.filter((inn) => inn.has_data);
    const shown = blocks.length ? blocks : innings;
    return shown.map((inn) => inningsBlock(inn, Boolean(inn.has_data) || shown.every((i) => !i.has_data))).join("");
  }

  window.CricketClubAppScorecardView = { DASH, escapeHtml, num, rate, nameHtml, roleBadges, ROLE_ICONS, battingTable, bowlingTable, inningsBlock, inningsSections };
})();
