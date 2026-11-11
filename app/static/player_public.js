/*
 * /players/<player id>: a player's profile and stats, read only (Nov 7 2026, Amit).
 * Data: GET /api/public/players/<player id> - name, clubs, career / year / club stats, recent scorecards.
 * No phone, email or age is shown.
 */
(() => {
  const head = document.getElementById("ppHead");
  const body = document.getElementById("ppBody");
  const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const key = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");

  const dash = (v) => (v === null || v === undefined || v === "" ? "–" : esc(v));
  const perMatch = (n, m) => (m ? (Number(n || 0) / m).toFixed(2) : null);
  // Table cell tinted by group (bat / bowl / field); edge "l" or "r" rounds that side of the tile.
  const groupCell = (v, grp, edge = "", extra = "") => {
    const cls = [grp ? `pm-g-${grp}` : "", edge.includes("l") ? "pm-tl" : "", edge.includes("r") ? "pm-tr" : "", extra].filter(Boolean).join(" ");
    return `<td${cls ? ` class="${cls}"` : ""}>${v}</td>`;
  };
  const gapCell = `<td class="pm-gap"></td>`;

  function summaryTiles(bat, bowl, fld) {
    const tile = (grp, title, pairs) =>
      `<div class="pm-stat-card pm-c-${grp}"><h3>${title}</h3><dl>${pairs.map(([k, v]) => `<div><dt>${k}</dt><dd>${dash(v)}</dd></div>`).join("")}</dl></div>`;
    return `<div class="pm-stat-grid">${tile("bat", "Batting", [
      ["Matches", bat.matches],
      ["Runs", bat.runs],
      ["Highest", bat.highest_score],
      ["Average", bat.batting_average],
      ["Strike rate", bat.strike_rate],
    ])}${tile("bowl", "Bowling", [
      ["Innings", bowl.innings],
      ["Wickets", bowl.wickets],
      ["Best", bowl.best],
      ["Economy", bowl.economy],
      ["Average", bowl.bowling_average],
    ])}${tile("field", "Fielding", [
      ["Catches", bat.catches],
      ["Run outs", fld.run_outs],
      ["Per match", perMatch(bat.catches, bat.matches)],
    ])}</div>`;
  }

  // One row per season (or club): Batting | Bowling | Fielding, separated by a bar and under a group header.
  function statRows(title, batRows, bowlRows, fieldRows, key, firstLabel) {
    const batBy = new Map(batRows.map((r) => [r[key], r]));
    const bowlBy = new Map(bowlRows.map((r) => [r[key], r]));
    const fieldBy = new Map(fieldRows.map((r) => [r[key], r]));
    const keys = [...new Set([...batRows, ...bowlRows, ...fieldRows].map((r) => r[key]))];
    if (!keys.length) return "";
    const cell = groupCell;
    const gap = gapCell;
    const lines = keys
      .map((k) => {
        const b = batBy.get(k) || {};
        const w = bowlBy.get(k) || {};
        const f = fieldBy.get(k) || {};
        return `<tr><th scope="row"><span class="pm-name">${esc(k)}</span>${b.matches ? `<small>${esc(b.matches)} ${b.matches == 1 ? "match" : "matches"}</small>` : ""}</th>${cell(dash(b.matches), "bat", "l")}${cell(dash(b.runs), "bat", "", "pm-r")}${cell(dash(b.highest_score), "bat")}${cell(dash(b.batting_average), "bat")}${cell(dash(b.strike_rate), "bat", "r")}${gap}${cell(dash(w.overs), "bowl", "l")}${cell(dash(w.wickets), "bowl")}${cell(dash(w.economy), "bowl", "r")}${gap}${cell(dash(b.catches), "field", "l")}${cell(dash(f.run_outs), "field", "r")}</tr>`;
      })
      .join("");
    const band = `<tr class="pm-band"><th scope="col"></th><th scope="colgroup" colspan="5" class="pm-g-bat pm-tl pm-tr">Batting</th>${gap}<th scope="colgroup" colspan="3" class="pm-g-bowl pm-tl pm-tr">Bowling</th>${gap}<th scope="colgroup" colspan="2" class="pm-g-field pm-tl pm-tr">Fielding</th></tr>`;
    const head = `<tr><th scope="col">${esc(firstLabel)}</th><th scope="col">M</th><th scope="col">Runs</th><th scope="col">HS</th><th scope="col">Avg</th><th scope="col">SR</th>${gap}<th scope="col">Ov</th><th scope="col">Wkts</th><th scope="col">Econ</th>${gap}<th scope="col">C</th><th scope="col" title="Run outs">RO</th></tr>`;
    return `<div class="pm-subhead"><h2>${esc(title)}</h2></div><div class="pm-table-wrap"><table class="pm-table pm-combined"><thead>${band}${head}</thead><tbody>${lines}</tbody></table></div>`;
  }

  // Recent matches: the same Batting | Bowling | Fielding bands as the season and club tables, one row per match.
  function recentList(items) {
    if (!items.length) return "";
    const cell = groupCell;
    const gap = gapCell;
    const lines = items
      .map((m) => {
        const b = m.batting || {};
        const w = m.bowling || {};
        const f = m.fielding || {};
        const sr = b.balls ? ((Number(b.runs || 0) / Number(b.balls)) * 100).toFixed(1) : null;
        const runs = b.runs === undefined || b.runs === null ? null : `${esc(b.runs)}${b.not_out ? "*" : ""}`;
        return `<tr><th scope="row"><a class="pm-name" href="/scorecards/${encodeURIComponent(m.id)}">${esc(m.title)}</a><small>${esc(m.date_label || m.date || "")}${m.result ? ` · ${esc(m.result)}` : ""}</small></th>${cell(runs ?? "–", "bat", "l", "pm-r")}${cell(dash(b.balls), "bat")}${cell(dash(sr), "bat", "r")}${gap}${cell(dash(w.overs), "bowl", "l")}${cell(dash(w.wickets), "bowl")}${cell(dash(w.runs), "bowl", "r")}${gap}${cell(dash(f.catches), "field", "l")}${cell(dash(f.run_outs), "field", "r")}</tr>`;
      })
      .join("");
    const band = `<tr class="pm-band"><th scope="col"></th><th scope="colgroup" colspan="3" class="pm-g-bat pm-tl pm-tr">Batting</th>${gap}<th scope="colgroup" colspan="3" class="pm-g-bowl pm-tl pm-tr">Bowling</th>${gap}<th scope="colgroup" colspan="2" class="pm-g-field pm-tl pm-tr">Fielding</th></tr>`;
    const head = `<tr><th scope="col">Match</th><th scope="col">R</th><th scope="col">B</th><th scope="col">SR</th>${gap}<th scope="col">Ov</th><th scope="col">W</th><th scope="col">R</th>${gap}<th scope="col">C</th><th scope="col" title="Run outs">RO</th></tr>`;
    return `<div class="pm-subhead"><h2>Recent matches</h2></div><div class="pm-table-wrap"><table class="pm-table pm-combined"><thead>${band}${head}</thead><tbody>${lines}</tbody></table></div>`;
  }

  fetch(`/api/public/players/${encodeURIComponent(key)}`, { headers: { Accept: "application/json" } })
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(r.status === 404 ? "Player not found." : "Couldn't load this player."))))
    .then((data) => {
      const p = data.player || {};
      const s = data.summary || {};
      document.title = `${p.name || "Player"} · CricketClubApp`;
      const facts = [p.player_id ? `Player ID ${esc(p.player_id)}` : "", p.role ? esc(p.role) : "", p.batting_style ? esc(p.batting_style) : "", p.bowling_style ? esc(p.bowling_style) : ""].filter(Boolean).join(" · ");
      head.innerHTML = `
        <h1 class="pm-title">${esc(p.name || "Player")}</h1>
        ${p.full_name && p.full_name !== p.name ? `<p class="pm-info">${esc(p.full_name)}</p>` : ""}
        ${facts ? `<p class="pm-info">${facts}</p>` : ""}
        ${(p.clubs || []).length ? `<p class="pm-info">Clubs: ${p.clubs.map(esc).join(" · ")}</p>` : ""}
        ${(p.aliases || []).length ? `<p class="pm-info">Also written as: ${p.aliases.map(esc).join(", ")}</p>` : ""}
        <p class="pm-info"><small>Read only</small></p>`;
      const bowl = data.bowling || {};
      const bowlSummary = bowl.summary || {};
      const fielding = data.fielding || {};
      const sections =
        (s.matches || bowlSummary.innings ? summaryTiles(s, bowlSummary, fielding.summary || {}) : "") +
        statRows("Season by season", data.years || [], bowl.years || [], fielding.years || [], "season_year", "Season") +
        statRows("By club", data.clubs || [], bowl.clubs || [], fielding.clubs || [], "club_name", "Club") +
        recentList(data.recent || []);
      body.innerHTML = sections || `<p class="pm-note">No stats recorded yet.</p>`;
    })
    .catch((error) => {
      head.innerHTML = `<p class="pm-info">${esc(error.message)}</p>`;
    });
})();
