/*
 * /players/<player id>: a player's profile and stats, read only (Nov 7 2026, Amit).
 * Data: GET /api/public/players/<player id> - name, clubs, career / year / club stats, recent scorecards.
 * No phone, email or age is shown.
 */
(() => {
  const head = document.getElementById("ppHead");
  const body = document.getElementById("ppBody");
  const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const num = (v) => (v === null || v === undefined || v === "" ? "–" : esc(v));
  const key = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");

  function statTable(title, rows, firstLabel, firstKey) {
    if (!rows.length) return "";
    const head = `<tr><th scope="col">${esc(firstLabel)}</th><th scope="col">M</th><th scope="col">Runs</th><th scope="col">HS</th><th scope="col">Avg</th><th scope="col">SR</th><th scope="col">4s</th><th scope="col">6s</th><th scope="col">Wkts</th><th scope="col">Ct</th></tr>`;
    const lines = rows
      .map(
        (r) => `<tr><th scope="row"><span class="pm-name">${esc(r[firstKey])}</span></th><td>${num(r.matches)}</td><td class="pm-r">${num(r.runs)}</td><td>${num(r.highest_score)}</td><td>${num(r.batting_average)}</td><td>${num(r.strike_rate)}</td><td>${num(r.fours)}</td><td>${num(r.sixes)}</td><td>${num(r.wickets)}</td><td>${num(r.catches)}</td></tr>`
      )
      .join("");
    return `<div class="pm-subhead"><h2>${esc(title)}</h2></div><div class="pm-table-wrap"><table class="pm-table"><thead>${head}</thead><tbody>${lines}</tbody></table></div>`;
  }

  function recentList(items) {
    if (!items.length) return "";
    const lines = items
      .map((m) => {
        const bat = m.batting ? `${num(m.batting.runs)}${m.batting.not_out ? "*" : ""}${m.batting.balls ? ` (${esc(m.batting.balls)})` : ""}` : "";
        const bowl = m.bowling ? `${num(m.bowling.wickets)}/${num(m.bowling.runs)}${m.bowling.overs ? ` (${esc(m.bowling.overs)} ov)` : ""}` : "";
        return `<tr><th scope="row"><a class="pm-name" href="/scorecards/${encodeURIComponent(m.id)}">${esc(m.title)}</a><small>${esc(m.date_label || m.date || "")}${m.result ? ` · ${esc(m.result)}` : ""}</small></th><td class="pm-r">${bat || "–"}</td><td>${bowl || "–"}</td></tr>`;
      })
      .join("");
    return `<div class="pm-subhead"><h2>Recent matches</h2></div><div class="pm-table-wrap"><table class="pm-table"><thead><tr><th scope="col">Match</th><th scope="col">Batting</th><th scope="col">Bowling</th></tr></thead><tbody>${lines}</tbody></table></div>`;
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
      const career = s && s.matches ? [{ label: "All matches", ...s }] : [];
      body.innerHTML =
        statTable("Career", career, "", "label") +
        statTable("Season by season", data.years || [], "Season", "season_year") +
        statTable("By club", data.clubs || [], "Club", "club_name") +
        recentList(data.recent || []) || `<p class="pm-note">No stats recorded yet.</p>`;
    })
    .catch((error) => {
      head.innerHTML = `<p class="pm-info">${esc(error.message)}</p>`;
    });
})();
