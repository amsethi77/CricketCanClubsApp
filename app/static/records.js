/*
 * /records: search every club's history (Nov 27 2026, Amit: "Search records by player, club, country, year,
 * tournament and performance etc"). Data: GET /api/public/records. The search is kept in the address, so a
 * search can be shared as a link. README "Cricket records search".
 */
(() => {
  const form = document.getElementById("rcForm");
  const results = document.getElementById("rcResults");
  const count = document.getElementById("rcCount");
  const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const dash = (v) => (v === null || v === undefined || v === "" ? "–" : esc(v));
  const fields = { q: "rcQuery", club: "rcClub", country: "rcCountry", year: "rcYear", league: "rcLeague", min_runs: "rcMinRuns", min_wickets: "rcMinWickets", sort: "rcSort", order: "rcOrder" };
  const params = new URLSearchParams(location.search);
  let view = ["players", "batting", "bowling", "matches"].includes(params.get("view")) ? params.get("view") : "players";
  let filled = false;
  let timer = 0;
  let asked = 0;

  for (const [key, id] of Object.entries(fields)) {
    const el = document.getElementById(id);
    if (el && params.get(key)) el.value = params.get(key);
  }

  function fillSelect(id, values, keep) {
    const el = document.getElementById(id);
    if (!el) return;
    const first = el.options[0].outerHTML;
    el.innerHTML = first + values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("");
    if (keep) el.value = keep;
  }

  function showView() {
    form.querySelectorAll("[data-view]").forEach((b) => {
      const on = b.dataset.view === view;
      b.classList.toggle("on", on);
      b.setAttribute("aria-selected", String(on));
    });
    form.querySelectorAll("[data-for]").forEach((label) => {
      label.hidden = !label.dataset.for.split(" ").includes(view);
    });
  }

  function query() {
    const q = new URLSearchParams({ view });
    for (const [key, id] of Object.entries(fields)) {
      const el = document.getElementById(id);
      if (!el || el.closest("[hidden]")) continue;
      const value = String(el.value || "").trim();
      if (!value) continue;
      q.set(key === "order" ? "sort" : key, value);
      if (key === "order") q.set("order", value);
    }
    return q;
  }

  const player = (row) => (row.player_key ? `<a href="/players/${encodeURIComponent(row.player_key)}">${esc(row.player)}</a>` : esc(row.player));
  const match = (row) => `<a href="${esc(row.match_url)}">${esc(row.team)} v ${esc(row.opponent)}</a>`;
  const when = (row) => `${esc(row.date)}${row.league ? `<small>${esc(row.league)}</small>` : ""}`;

  function table(head, rows) {
    return `<div class="rc-table-wrap"><table class="rc-table"><thead><tr>${head.map((h) => `<th scope="col">${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
  }

  function render(data) {
    const list = data.results || [];
    count.textContent = list.length < data.total ? `Showing the top ${list.length} of ${data.total}.` : `${data.total} found.`;
    if (!list.length) {
      results.innerHTML = `<p class="rc-empty">Nothing matches this search. Try fewer filters or another name.</p>`;
      return;
    }
    if (view === "players") {
      results.innerHTML = table(
        ["Player", "Clubs", "Mat", "Runs", "HS", "Avg", "SR", "50s", "100s", "Wkts", "Best", "5w"],
        list.map((r) => `<tr><th scope="row">${r.url ? `<a href="${esc(r.url)}">${esc(r.player)}</a>` : esc(r.player)}${r.full_name && r.full_name !== r.player ? `<small>${esc(r.full_name)}</small>` : ""}</th><td class="rc-clubs">${esc(r.clubs.join(", "))}${r.countries.length ? `<small>${esc(r.countries.join(", "))}</small>` : ""}</td><td>${dash(r.matches)}</td><td class="rc-strong">${dash(r.runs)}</td><td>${dash(r.highest)}</td><td>${dash(r.average)}</td><td>${dash(r.strike_rate)}</td><td>${dash(r.fifties)}</td><td>${dash(r.hundreds)}</td><td class="rc-strong">${dash(r.wickets)}</td><td>${dash(r.best)}</td><td>${dash(r.five_wickets)}</td></tr>`),
      );
    } else if (view === "batting") {
      results.innerHTML = table(
        ["Player", "Runs", "Balls", "4s", "6s", "For", "Match", "Date"],
        list.map((r) => `<tr><th scope="row">${player(r)}</th><td class="rc-strong">${esc(r.runs)}${r.not_out ? "*" : ""}</td><td>${dash(r.balls)}</td><td>${dash(r.fours)}</td><td>${dash(r.sixes)}</td><td>${esc(r.club)}</td><td>${match(r)}</td><td>${when(r)}</td></tr>`),
      );
    } else if (view === "bowling") {
      results.innerHTML = table(
        ["Player", "Figures", "Overs", "For", "Match", "Date"],
        list.map((r) => `<tr><th scope="row">${player(r)}</th><td class="rc-strong">${esc(r.wickets)}/${dash(r.runs_conceded)}</td><td>${dash(r.overs)}</td><td>${esc(r.club)}</td><td>${match(r)}</td><td>${when(r)}</td></tr>`),
      );
    } else {
      results.innerHTML = table(
        ["Match", "Scores", "Result", "Date"],
        list.map((r) => `<tr><th scope="row"><a href="${esc(r.url)}">${esc(r.teams.join(" v "))}</a><small>Match ID ${esc(r.match_code)}</small></th><td>${r.scores.map(esc).join("<br />")}</td><td>${dash(r.result)}</td><td>${when(r)}</td></tr>`),
      );
    }
  }

  async function search() {
    const q = query();
    history.replaceState(null, "", `/records?${q.toString()}`);
    const mine = ++asked;
    results.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(`/api/public/records?${q.toString()}`, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("The records couldn't be loaded. Try again.");
      const data = await response.json();
      if (mine !== asked) return; // a newer search is on its way
      if (!filled && data.filters) {
        filled = true;
        fillSelect("rcClub", data.filters.clubs || [], params.get("club"));
        fillSelect("rcCountry", data.filters.countries || [], params.get("country"));
        fillSelect("rcYear", data.filters.years || [], params.get("year"));
        fillSelect("rcLeague", data.filters.leagues || [], params.get("league"));
      }
      render(data);
    } catch (error) {
      results.innerHTML = `<p class="rc-empty">${esc(error.message)}</p>`;
    } finally {
      results.removeAttribute("aria-busy");
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    search();
  });
  form.addEventListener("change", () => search());
  form.querySelector("#rcQuery").addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(search, 350);
  });
  form.querySelectorAll("[data-view]").forEach((button) =>
    button.addEventListener("click", () => {
      view = button.dataset.view;
      showView();
      search();
    }),
  );
  showView();
  search();
})();
