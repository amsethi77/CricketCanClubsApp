/*
 * /leagues - Nov 10 2026 (Amit): leagues / series. Everyone sees each league's groups, points tables and matches.
 * The superadmin also creates leagues, adds groups (A, B, C...), puts clubs in groups and adds played matches.
 * README "Leagues and series".
 */
(function leaguesPage() {
  const list = document.getElementById("leaguesList");
  const adminBox = document.getElementById("leagueAdmin");
  const adminMsg = document.getElementById("leagueAdminMsg");
  let isSuperadmin = false;
  let clubs = [];

  const token = () => {
    try {
      return localStorage.getItem("cricketClubAppAuthToken") || "";
    } catch (error) {
      return "";
    }
  };
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  const api = async (url, method = "GET", body) => {
    const response = await fetch(url, {
      method,
      headers: { "X-Auth-Token": token(), Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Something went wrong. Try again.");
    return data;
  };
  const say = (text, isError) => {
    adminMsg.textContent = text || "";
    adminMsg.style.color = isError ? "#b42318" : "";
  };
  const nrr = (value) => (value === null || value === undefined ? "-" : (value > 0 ? "+" : "") + Number(value).toFixed(3));

  function standingsTable(group) {
    const rows = group.standings
      .map(
        (row, index) => `<tr>
          <td>${index + 1}</td><td>${esc(row.club_name)}${isSuperadmin ? ` <button class="secondary-button" data-remove-team="${esc(group.id)}|${esc(row.club_id)}" title="Remove from group">✕</button>` : ""}</td>
          <td>${row.played}</td><td>${row.won}</td><td>${row.lost}</td><td>${row.tied}</td><td>${row.no_result}</td>
          <td><strong>${row.points}</strong></td><td>${nrr(row.nrr)}</td></tr>`
      )
      .join("");
    const addTeam = isSuperadmin
      ? `<form class="toolbar-actions" data-add-team="${esc(group.id)}">
          <select required><option value="">Add a club to group ${esc(group.name)}...</option>${clubs
            .map((club) => `<option value="${esc(club.id)}">${esc(club.name)}</option>`)
            .join("")}</select>
          <button class="secondary-button" type="submit">Add club</button>
          <button class="secondary-button" type="button" data-remove-group="${esc(group.id)}">Remove group</button>
        </form>`
      : "";
    return `<div class="detail-card">
        <h3>Group ${esc(group.name)} <small class="lede">(ID ${esc(group.id)})</small></h3>
        <div class="rankings-table-wrap"><table class="custom-table">
          <thead><tr><th>#</th><th>Team</th><th>P</th><th>W</th><th>L</th><th>T</th><th>NR</th><th>Pts</th><th>NRR</th></tr></thead>
          <tbody>${rows || `<tr><td colspan="9">No teams in this group yet.</td></tr>`}</tbody>
        </table></div>${addTeam}</div>`;
  }

  function matchesList(league) {
    const groupName = Object.fromEntries(league.groups.map((group) => [group.id, group.name]));
    const items = league.matches
      .map((match) => {
        const scores = match.teams.map((team) => `${esc(team)}${match.scores[team] ? ` ${esc(match.scores[team])}` : ""}`).join(" v ");
        const remove = isSuperadmin ? ` <button class="secondary-button" data-remove-match="${esc(league.id)}|${esc(match.ref)}" title="Take out of league">✕</button>` : "";
        return `<li><a href="${esc(match.url)}">${esc(match.date || "No date")} · ${scores}</a> - <strong>${esc(match.result)}</strong>${match.group_id ? ` <small>(Group ${esc(groupName[match.group_id] || "")})</small>` : ""}${remove}</li>`;
      })
      .join("");
    return `<h3>Matches</h3>${items ? `<ul class="league-matches">${items}</ul>` : `<p class="lede">No matches yet. Pick this league when adding a fixture or uploading a scorecard.</p>`}`;
  }

  function leagueCard(league) {
    const admin = isSuperadmin
      ? `<div class="toolbar-actions">
          <form class="toolbar-actions" data-add-group="${esc(league.id)}">
            <input type="text" maxlength="20" placeholder="Group name (blank = next letter)" />
            <button class="secondary-button" type="submit">Add group</button>
          </form>
          <button class="secondary-button" type="button" data-candidates="${esc(league.id)}">Add a played match</button>
          <button class="secondary-button" type="button" data-delete-league="${esc(league.id)}">Delete league</button>
        </div>
        <div data-candidate-box="${esc(league.id)}"></div>`
      : "";
    return `<article class="detail-card league-card">
        <h2>${esc(league.name)}${league.season ? ` <small>${esc(league.season)}</small>` : ""}</h2>
        <p class="lede">League ID ${esc(league.id)} · ${league.groups.length} group(s)</p>
        ${admin}
        ${league.groups.map(standingsTable).join("") || `<p class="lede">No groups yet.</p>`}
        ${matchesList(league)}
      </article>`;
  }

  async function load() {
    try {
      const data = await api("/api/leagues");
      list.innerHTML = data.leagues.length
        ? data.leagues.map(leagueCard).join("")
        : `<p class="lede">No leagues yet.${isSuperadmin ? " Create one above." : ""}</p>`;
    } catch (error) {
      list.innerHTML = `<p class="lede">${esc(error.message)}</p>`;
    }
  }

  async function act(promise, reload = true) {
    try {
      const data = await promise;
      say(data.message || "Done.");
      if (reload) await load();
    } catch (error) {
      say(error.message, true);
    }
  }

  list.addEventListener("submit", (event) => {
    const form = event.target;
    event.preventDefault();
    if (form.dataset.addTeam) {
      const clubId = form.querySelector("select").value;
      if (clubId) act(api(`/api/leagues/groups/${encodeURIComponent(form.dataset.addTeam)}/teams`, "POST", { club_id: clubId }));
    } else if (form.dataset.addGroup) {
      act(api(`/api/leagues/${encodeURIComponent(form.dataset.addGroup)}/groups`, "POST", { name: form.querySelector("input").value }));
    } else if (form.dataset.addMatch) {
      const ref = form.querySelector("select").value;
      if (ref) act(api(`/api/leagues/${encodeURIComponent(form.dataset.addMatch)}/matches`, "POST", { match_ref: ref }));
    }
  });

  list.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button || button.type === "submit") return;
    const d = button.dataset;
    if (d.removeTeam) {
      const [groupId, clubId] = d.removeTeam.split("|");
      act(api(`/api/leagues/groups/${encodeURIComponent(groupId)}/teams/${encodeURIComponent(clubId)}`, "DELETE"));
    } else if (d.removeGroup) {
      if (window.confirm("Remove this group? Its clubs come out of the group; matches stay.")) act(api(`/api/leagues/groups/${encodeURIComponent(d.removeGroup)}`, "DELETE"));
    } else if (d.removeMatch) {
      const [leagueId, ref] = d.removeMatch.split("|");
      act(api(`/api/leagues/${encodeURIComponent(leagueId)}/matches/${encodeURIComponent(ref)}`, "DELETE"));
    } else if (d.deleteLeague) {
      if (window.confirm("Delete this league? Matches and scorecards are not deleted.")) act(api(`/api/leagues/${encodeURIComponent(d.deleteLeague)}`, "DELETE"));
    } else if (d.candidates) {
      const box = list.querySelector(`[data-candidate-box="${CSS.escape(d.candidates)}"]`);
      box.innerHTML = `<p class="lede">Finding played matches between this league's teams...</p>`;
      try {
        const data = await api(`/api/leagues/${encodeURIComponent(d.candidates)}/candidates`);
        box.innerHTML = data.matches.length
          ? `<form class="toolbar-actions" data-add-match="${esc(d.candidates)}"><select required><option value="">Pick a match...</option>${data.matches
              .map((match) => `<option value="${esc(match.ref)}">${esc(match.label)}</option>`)
              .join("")}</select><button class="secondary-button" type="submit">Add to league</button></form>`
          : `<p class="lede">No played matches between this league's teams that aren't in a league already. Put clubs in the groups first.</p>`;
      } catch (error) {
        box.innerHTML = `<p class="lede">${esc(error.message)}</p>`;
      }
    }
  });

  document.getElementById("leagueCreateForm").addEventListener("submit", (event) => {
    event.preventDefault();
    act(
      api("/api/leagues", "POST", {
        name: document.getElementById("leagueName").value,
        season: document.getElementById("leagueSeason").value,
      }).then((data) => {
        event.target.reset();
        return data;
      })
    );
  });

  (async function start() {
    if (token()) {
      const me = await fetch("/api/auth/me", { headers: { "X-Auth-Token": token() } })
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);
      const roles = me?.user?.roles || [];
      isSuperadmin = me?.user?.effective_role === "superadmin" || roles.includes("superadmin");
    }
    if (isSuperadmin) {
      adminBox.hidden = false;
      clubs = (await fetch("/api/public/clubs").then((r) => r.json()).catch(() => ({ clubs: [] }))).clubs || [];
    }
    await load();
  })();
})();
