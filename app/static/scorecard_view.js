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

  function ballSplit(row, fields) {
    const bits = fields
      .filter(([key]) => row[key] !== null && row[key] !== undefined && row[key] !== "")
      .map(([key, label]) => `${label} ${escapeHtml(row[key])}`);
    return bits.length ? `<small class="pm-split">${bits.join(" · ")}</small>` : "";
  }

  // Nov 10 2026 (Amit: "add 1s, 2s, 3s on the right along with 4s and 6s and calculate balls faced and strike rate
  // from them"): R B 1s 2s 3s 4s 6s SR, plus a dots column when the scorer wrote dots. The 1s-3s / dots columns show
  // only when the innings has them (a typed-in card keeps R B 4s 6s SR).
  function battingTable(inn) {
    const batters = inn.batting || [];
    const has = (key) => batters.some((b) => b[key] !== null && b[key] !== undefined && b[key] !== "");
    const extra = [
      ["dots", "0s"],
      ["ones", "1s"],
      ["twos", "2s"],
      ["threes", "3s"],
    ].filter(([key]) => has(key));
    const cols = [["runs", "R", "pm-r"], ["balls", "B", ""], ...extra.map(([key, label]) => [key, label, ""]), ["fours", "4s", ""], ["sixes", "6s", ""], ["strike_rate", "SR", ""]];
    const rows = batters
      .map((b) => {
        const how = howOutText(b.dismissal) || (b.not_out ? "not out" : "");
        return `<tr class="${b.not_out ? "pm-notout" : ""}">
          <th scope="row">${nameHtml(b.name, b.player_key)}${how ? `<small>${escapeHtml(how)}</small>` : ""}</th>
          ${cols.map(([key, , cls]) => `<td${cls ? ` class="${cls}"` : ""}>${num(b[key])}</td>`).join("")}</tr>`;
      })
      .join("");
    const span = cols.length;
    const rr = rate(inn.runs, inn.overs);
    const totalBits = [inn.wickets !== null && inn.wickets !== undefined ? `${escapeHtml(inn.wickets)} wkts` : "", inn.overs ? `${escapeHtml(inn.overs)} Ov` : "", rr ? `RR ${rr}` : ""].filter(Boolean).join(", ");
    return `
      <div class="pm-table-wrap">
        <table class="pm-table">
          <thead><tr><th scope="col">Batter</th>${cols.map(([, label]) => `<th scope="col">${label}</th>`).join("")}</tr></thead>
          <tbody>${rows || `<tr><td colspan="${span + 1}" class="pm-empty">Batting details were not recorded for this innings.</td></tr>`}</tbody>
          <tfoot>
            <tr><th scope="row">Extras${inn.extras_detail ? ` <small>(${escapeHtml(inn.extras_detail)})</small>` : ""}</th><td class="pm-r" colspan="${span}">${num(inn.extras)}</td></tr>
            <tr class="pm-total"><th scope="row">Total${totalBits ? ` <small>(${totalBits})</small>` : ""}</th><td class="pm-r" colspan="${span}">${inn.runs === null || inn.runs === undefined ? DASH : escapeHtml(inn.runs)}</td></tr>
          </tfoot>
        </table>
      </div>
      ${inn.did_not_bat && inn.did_not_bat.length ? `<p class="pm-note"><b>Did not bat:</b> ${inn.did_not_bat.map(escapeHtml).join(", ")}</p>` : ""}`;
  }

  function bowlingTable(inn) {
    if (!inn.bowling || !inn.bowling.length) return '<p class="pm-note">Bowling figures were not recorded for this innings.</p>';
    const rows = inn.bowling
      .map(
        (b) => `<tr>
          <th scope="row">${nameHtml(b.name, b.player_key)}${ballSplit(b, [["dots", "Dots"], ["wides", "Wd"], ["no_balls", "Nb"], ["fours", "4s"], ["sixes", "6s"]])}${Array.isArray(b.over_runs) && b.over_runs.length ? `<small class="pm-split">Runs per over: ${b.over_runs.map((value) => escapeHtml(value)).join(" · ")}</small>` : ""}</th>
          <td>${num(b.overs)}</td><td>${num(b.maidens)}</td><td>${num(b.runs)}</td><td class="pm-r">${num(b.wickets)}</td><td>${num(b.economy)}</td></tr>`
      )
      .join("");
    return `
      <div class="pm-table-wrap">
        <table class="pm-table">
          <thead><tr><th scope="col">Bowler</th><th scope="col">O</th><th scope="col">M</th><th scope="col">R</th><th scope="col">W</th><th scope="col">ECON</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function inningsBlock(inn, open) {
    const score = inn.runs === null || inn.runs === undefined ? DASH : `${escapeHtml(inn.runs)}/${escapeHtml(inn.wickets ?? 0)}`;
    return `<section class="pm-inn${open ? " open" : ""}">
        <button type="button" class="pm-innhead" data-sc-inn aria-expanded="${open}">
          <span>${escapeHtml(inn.team)} Innings</span>
          <b>${score}${inn.overs ? ` <small>(${escapeHtml(inn.overs)} Ov)</small>` : ""}</b><i aria-hidden="true">▾</i>
        </button>
        <div class="pm-inn-body">${battingTable(inn)}${bowlingTable(inn)}</div>
      </section>`;
  }

  // Every innings of a card. Innings with figures show (and open); with none, all show and the last one opens.
  function inningsSections(card) {
    const innings = Array.isArray(card?.innings) ? card.innings : [];
    const blocks = innings.filter((inn) => inn.has_data);
    const shown = blocks.length ? blocks : innings;
    return shown.map((inn) => inningsBlock(inn, Boolean(inn.has_data) || shown.every((i) => !i.has_data))).join("");
  }

  window.CricketClubAppScorecardView = { DASH, escapeHtml, num, rate, nameHtml, battingTable, bowlingTable, inningsBlock, inningsSections };
})();
