/*
 * Signed-in Home (/dashboard) redesign.
 * Runs only on the overview page. Adds: welcome banner actions, a live/results/upcoming
 * match strip, and a "Latest scorecards" panel. Hides duplicate panels via dashboard_home.css.
 * Styles for the strip and scorecard cards come from home.css (shared with the public home).
 */
(() => {
  if (document.body.dataset.dashboardWidget !== "overview") return;
  document.body.classList.add("home-v2", "dash-v2");

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const shell = document.querySelector(".page-shell");
  const hero = document.querySelector(".dashboard-hero-panel");
  const matchPanel = document.querySelector(".dashboard-match-panel");
  if (!shell) return;

  const esc = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  async function getJson(url) {
    try {
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      return response.ok ? await response.json() : null;
    } catch (error) {
      return null;
    }
  }

  function shortDate(iso) {
    const [y, m, d] = String(iso || "").split("-").map(Number);
    if (!y || !m || !d) return "Date TBD";
    return `${DAYS[new Date(y, m - 1, d).getDay()]} ${d} ${MONTHS[m - 1]}`;
  }

  function todayIso() {
    const n = new Date();
    return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
  }

  function currentClubId() {
    try {
      return localStorage.getItem("cricketClubAppPrimaryClubId") || "";
    } catch (error) {
      return "";
    }
  }

  // ---------- 1. Welcome banner: greeting + quick actions ----------
  if (hero && !hero.querySelector(".dash-hero-actions")) {
    const copy = hero.querySelector(".template-header-copy") || hero;
    copy.insertAdjacentHTML(
      "beforeend",
      `<p class="dash-hello" id="dashHello"></p>
       <div class="dash-hero-actions">
         <a class="home-btn primary small" href="/score">🎯 Score a match</a>
         <a class="home-btn ghost small" href="/matches" data-paid-action="availability">✅ Update availability</a>
         <a class="home-btn ghost small" href="/scorecards/upload" data-scorer-action hidden>📤 Upload scorecard</a>
         <a class="home-btn ghost small" href="/scorecards">📋 Scorecards</a>
         <a class="home-btn ghost small" href="/pricing" data-free-only hidden>⭐ See plans</a>
       </div>`
    );
    // Plan-based actions (README: "Plan-based menu"): Free members see scoring and viewing; paid plans see everything.
    fetch("/api/auth/me", { headers: { Accept: "application/json", "X-Auth-Token": localStorage.getItem("cricketClubAppAuthToken") || "" } })
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        const user = data && data.user;
        if (!user) return;
        const role = String(user.effective_role || user.role || "");
        const paid = role === "superadmin" || (user.plan && user.plan !== "free");
        hero.querySelectorAll('[data-paid-action="availability"]').forEach((el) => (el.hidden = !(paid || user.club_paid)));
        hero.querySelectorAll("[data-free-only]").forEach((el) => (el.hidden = paid));
        // Captains and club admins upload scorecards (README: "Scorecard uploads: checks, review and duplicates").
        hero.querySelectorAll("[data-scorer-action]").forEach((el) => (el.hidden = !(user.permissions || []).includes("score_matches")));
      })
      .catch(() => null);
    const fillHello = () => {
      const hello = document.getElementById("dashHello");
      const badge = document.getElementById("userIdentityBadge");
      const name = String(badge?.title || "").trim().split(/\s+/)[0];
      if (hello && name) hello.textContent = `Welcome back, ${name} 👋`;
      return Boolean(name);
    };
    if (!fillHello()) {
      let tries = 0;
      const timer = setInterval(() => {
        tries += 1;
        if (fillHello() || tries > 20) clearInterval(timer);
      }, 300);
    }
  }

  // ---------- 2. Match strip ----------
  const strip = document.createElement("section");
  strip.className = "home-strip dash-strip";
  strip.setAttribute("aria-label", "Matches");
  strip.innerHTML = `
    <div class="dash-strip-head">
      <h2>Matches</h2>
      <div class="home-strip-tabs" role="tablist">
        <button type="button" class="home-strip-tab is-active" data-strip="all" role="tab" aria-selected="true">Overview</button>
        <button type="button" class="home-strip-tab" data-strip="live" role="tab" aria-selected="false">Live</button>
        <button type="button" class="home-strip-tab" data-strip="result" role="tab" aria-selected="false">Results</button>
        <button type="button" class="home-strip-tab" data-strip="upcoming" role="tab" aria-selected="false">Upcoming</button>
      </div>
    </div>
    <div class="home-strip-wrap">
      <button type="button" class="home-strip-nav prev" aria-label="Scroll left" hidden>‹</button>
      <div class="home-strip-row"><div class="home-strip-empty">Loading matches…</div></div>
      <button type="button" class="home-strip-nav next" aria-label="Scroll right" hidden>›</button>
    </div>`;
  (hero || shell.querySelector(".page-topbar"))?.insertAdjacentElement("afterend", strip);
  const row = strip.querySelector(".home-strip-row");
  let items = [];
  let filter = "all";

  function fromFixture(f, kindOverride) {
    const status = String(f.status_key || f.status || "").toLowerCase();
    // A past game is never "live" or "upcoming": show it as a result (README: "Past matches are locked").
    const isPast = String(f.date || "").slice(0, 10) < new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const kind = kindOverride || (isPast ? "result" : status === "live" ? "live" : status === "completed" ? "result" : "upcoming");
    const sc = (v) => {
      const t = String(v ?? "").trim();
      return t && t !== "0" ? t : "";
    };
    const result = String(f.result || "").replace(/^result:\s*/i, "").trim();
    return {
      id: f.id,
      club: f.club_id,
      kind,
      date: f.date,
      teams: [
        { name: f.club_name || "Club", score: sc(f.heartlake_score) },
        { name: f.opponent || "Opponent", score: sc(f.opponent_score) },
      ],
      note:
        kind === "upcoming"
          ? [f.scheduled_time !== "Time TBD" ? f.scheduled_time : "", f.venue !== "Venue TBD" ? f.venue : ""].filter(Boolean).join(" · ") || "Time TBD"
          : !result || /^(tbd|club won)$/i.test(result)
            ? kind === "live" ? "In progress" : sc(f.heartlake_score) || sc(f.opponent_score) ? "Full time" : "Result not recorded"
            : result,
      meta: [f.match_type, f.overs ? `${f.overs} ov` : ""].filter(Boolean).join(" · "),
      href: kind === "upcoming" ? "/matches" : `/live/${encodeURIComponent(f.id)}`,
    };
  }

  function card(m) {
    const mine = m.club && m.club === currentClubId();
    const badge =
      m.kind === "live"
        ? `<span class="home-badge live"><span class="home-dot"></span>LIVE</span>`
        : m.kind === "result"
          ? `<span class="home-badge result">RESULT</span>`
          : `<span class="home-badge upcoming">${esc(shortDate(m.date))}</span>`;
    return `
      <a class="home-strip-card is-${m.kind}${mine ? " is-mine" : ""}" href="${m.href}">
        <div class="home-strip-top">${badge}<span class="home-strip-meta">${esc(m.kind === "upcoming" ? m.meta : shortDate(m.date))}</span></div>
        ${m.teams.map((t) => `<div class="home-strip-team"><span>${esc(t.name)}</span><strong>${esc(t.score)}</strong></div>`).join("")}
        <p class="home-strip-note">${esc(m.note)}</p>
      </a>`;
  }

  function updateNav() {
    if (row.classList.contains("is-grouped")) return;
    const prev = strip.querySelector(".home-strip-nav.prev");
    const next = strip.querySelector(".home-strip-nav.next");
    prev.hidden = row.scrollLeft <= 4;
    next.hidden = row.scrollLeft + row.clientWidth >= row.scrollWidth - 4;
  }

  // Overview: clear "Live now", "Recent results" and "Coming up" rows (README: "Home: live and past matches").
  function renderGrouped() {
    const groups = [
      ["live", "🔴 Live now", "No match is live right now.", `<a class="home-link" href="/score">Score a match →</a>`],
      ["result", "🏁 Recent results", "No results yet.", `<a class="home-link" href="/scorecards">All scorecards →</a>`],
      ["upcoming", "📅 Coming up", "No upcoming fixtures.", ""],
    ];
    row.classList.add("is-grouped");
    row.innerHTML = groups
      .map(([kind, title, empty, link]) => {
        const list = items.filter((m) => m.kind === kind);
        return `<div class="dash-group">
          <div class="dash-group-head"><h3>${title}${list.length ? ` <span>${list.length}</span>` : ""}</h3>${link}</div>
          <div class="dash-group-row">${list.length ? list.map(card).join("") : `<div class="home-strip-empty">${empty}</div>`}</div>
        </div>`;
      })
      .join("");
    strip.querySelectorAll(".home-strip-nav").forEach((b) => (b.hidden = true));
  }

  function renderStrip() {
    if (filter === "all") return renderGrouped();
    row.classList.remove("is-grouped");
    const list = items.filter((m) => m.kind === filter);
    row.innerHTML = list.length
      ? list.map(card).join("")
      : `<div class="home-strip-empty">${
          filter === "live" ? "No matches are live right now." : filter === "upcoming" ? "No upcoming fixtures scheduled yet." : "No matches yet."
        }</div>`;
    row.scrollLeft = 0;
    updateNav();
  }

  strip.querySelectorAll(".home-strip-tab").forEach((tab) =>
    tab.addEventListener("click", () => {
      filter = tab.dataset.strip;
      strip.querySelectorAll(".home-strip-tab").forEach((t) => {
        t.classList.toggle("is-active", t === tab);
        t.setAttribute("aria-selected", t === tab ? "true" : "false");
      });
      renderStrip();
    })
  );
  strip.querySelector(".prev").addEventListener("click", () => row.scrollBy({ left: -row.clientWidth * 0.8, behavior: "smooth" }));
  strip.querySelector(".next").addEventListener("click", () => row.scrollBy({ left: row.clientWidth * 0.8, behavior: "smooth" }));
  row.addEventListener("scroll", updateNav, { passive: true });
  window.addEventListener("resize", updateNav);

  // ---------- 3. Latest scorecards ----------
  const scPanel = document.createElement("section");
  scPanel.className = "home-section dash-scorecards";
  scPanel.innerHTML = `
    <div class="home-section-head">
      <div>
        <p class="home-kicker">Scorecard archive</p>
        <h2>Latest scorecards</h2>
      </div>
      <a class="home-link" href="/scorecards">View all scorecards →</a>
    </div>
    <div class="home-card-grid"><div class="home-empty">Loading scorecards…</div></div>`;
  (matchPanel || strip).insertAdjacentElement("afterend", scPanel);

  function scCard(sc) {
    const [y, mo, d] = String(sc.date || "").split("-").map(Number);
    const day = y ? DAYS[new Date(y, mo - 1, d).getDay()] : "";
    return `
      <a class="home-sc-card" href="/scorecards/${encodeURIComponent(sc.id)}">
        <div class="home-sc-date"><span>${esc(day)}</span><strong>${d || "–"}</strong><span>${esc(MONTHS[(mo || 1) - 1])}</span><small>${y || ""}</small></div>
        <div class="home-sc-body">
          ${(sc.teams || []).map((t) => `<div class="home-strip-team"><span>${esc(t.name)}</span><strong>${esc(t.score || "–")}</strong></div>`).join("")}
          <p class="home-sc-result">${esc(sc.result || "Result not recorded")}</p>
          ${sc.has_photo ? `<span class="home-tag">📷 Photo</span>` : ""}
        </div>
      </a>`;
  }

  // ---------- 4. AI Muse card at the bottom of Home ----------
  const museCard = document.createElement("section");
  museCard.className = "muse-home";
  museCard.innerHTML = `
    <div>
      <p class="home-kicker">AI Muse</p>
      <h2>Your AI assistant</h2>
      <p>Ask about players and clubs, or tell AI Muse what to do: mark availability, ask the squad, pick the XI, add a fixture or update the score. It shows you the plan first.</p>
    </div>
    <form class="muse-home-form">
      <input placeholder="e.g. How can Amit S improve?  or  Heartlake 145/6, Imran XI 120/9…" aria-label="Message AI Muse" />
      <button type="submit">Ask Muse</button>
    </form>
    <div class="muse-home-chips">
      <button type="button" data-muse="Who is available for the next match?">✅ Who's available?</button>
      <button type="button" data-muse="Ask everyone for availability for the next match">📣 Ask for availability</button>
      <button type="button" data-muse="Mark me available for the next match">🙋 I'm available</button>
      <button type="button" data-muse="Pick the best XI for the next match">🏏 Pick the XI</button>
      <button type="button" data-muse="How can our club improve its ranking?">📈 Improve our ranking</button>
    </div>`;
  shell.appendChild(museCard);
  const openMuse = (text) => {
    if (window.CCMuse) window.CCMuse.open("chat", text);
    else setTimeout(() => window.CCMuse && window.CCMuse.open("chat", text), 600);
  };
  museCard.querySelector("form").addEventListener("submit", (event) => {
    event.preventDefault();
    const field = museCard.querySelector("input");
    const text = field.value.trim();
    field.value = "";
    openMuse(text);
  });
  museCard.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-muse]");
    if (chip) openMuse(chip.dataset.muse);
  });

  // ---------- Load ----------
  (async () => {
    const [live, fixtures, scorecards] = await Promise.all([
      getJson("/api/public/live-page"),
      getJson("/api/public/fixtures-page"),
      getJson("/api/public/scorecards"),
    ]);
    const clubId = currentClubId();
    const mineFirst = (a, b) => Number(b.club === clubId) - Number(a.club === clubId);

    const liveList = (live?.live_matches || []).map((f) => fromFixture(f, "live"));
    const liveIds = new Set(liveList.map((m) => m.id));
    const all = (fixtures?.fixtures || []).map((f) => fromFixture(f)).filter((m) => !liveIds.has(m.id));
    const results = all.filter((m) => m.kind === "result").sort((a, b) => String(b.date).localeCompare(String(a.date)));
    const today = todayIso();
    const upcoming = all
      .filter((m) => m.kind === "upcoming" && String(m.date) >= today)
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));
    items = [...liveList.sort(mineFirst), ...results.slice(0, 8), ...upcoming.slice(0, 8)];
    renderStrip();

    const grid = scPanel.querySelector(".home-card-grid");
    const list = (scorecards?.scorecards || []).slice();
    list.sort((a, b) => Number(b.club_id === clubId) - Number(a.club_id === clubId) || String(b.date).localeCompare(String(a.date)));
    grid.innerHTML = list.length
      ? list.slice(0, 4).map(scCard).join("")
      : `<div class="home-empty">No approved scorecards yet. <a href="/scorecards/upload">Upload a scorecard photo</a></div>`;
  })();
})();
