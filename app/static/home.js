/*
 * Public home page (/live): score strip, hero + featured match, latest scorecards,
 * recent results, upcoming fixtures. Uses public APIs only.
 */
(() => {
  const $ = (id) => document.getElementById(id);
  const stripEl = $("homeStrip");
  const featureEl = $("homeFeature");
  const scorecardsEl = $("homeScorecards");
  const resultsEl = $("homeResults");
  const upcomingEl = $("homeUpcoming");
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  let stripItems = [];
  let stripFilter = "all";

  function esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  async function getJson(url) {
    try {
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) return null;
      return await response.json();
    } catch (error) {
      return null;
    }
  }

  function shortDate(iso) {
    const [y, m, d] = String(iso || "").split("-").map(Number);
    if (!y || !m || !d) return "Date TBD";
    const date = new Date(y, m - 1, d);
    return `${DAYS[date.getDay()]} ${d} ${MONTHS[m - 1]}`;
  }

  function todayIso() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  }

  function cleanResult(text) {
    const value = String(text || "").replace(/^result:\s*/i, "").trim();
    if (!value || /^(tbd|club won|pending review)$/i.test(value)) return "";
    return value;
  }

  function score(value) {
    const text = String(value ?? "").trim();
    return text && text !== "0" ? text : "";
  }

  // ---------- Normalise matches from the fixtures API ----------
  function fromFixture(f) {
    const status = String(f.status_key || f.status || "").toLowerCase();
    const kind = status === "live" ? "live" : status === "completed" ? "result" : "upcoming";
    return {
      id: f.id,
      kind,
      date: f.date,
      teams: [
        { name: f.club_name || "Club", score: score(f.heartlake_score) },
        { name: f.opponent || "Opponent", score: score(f.opponent_score) },
      ],
      note:
        kind === "upcoming"
          ? [f.scheduled_time && f.scheduled_time !== "Time TBD" ? f.scheduled_time : "", f.venue && f.venue !== "Venue TBD" ? f.venue : ""].filter(Boolean).join(" · ") || "Time TBD"
          : cleanResult(f.result) || (kind === "live" ? "In progress" : "Result not recorded"),
      meta: [f.match_type, f.overs ? `${f.overs} ov` : ""].filter(Boolean).join(" · "),
      href: kind === "upcoming" ? "/fixtures" : `/live/${encodeURIComponent(f.id)}`,
      balls: Array.isArray(f.recent_balls) ? f.recent_balls : [],
      venue: f.venue && f.venue !== "Venue TBD" ? f.venue : "",
    };
  }

  // ---------- Score strip ----------
  function stripCard(m) {
    const badge =
      m.kind === "live"
        ? `<span class="home-badge live"><span class="home-dot"></span>LIVE</span>`
        : m.kind === "result"
          ? `<span class="home-badge result">RESULT</span>`
          : `<span class="home-badge upcoming">${esc(shortDate(m.date))}</span>`;
    return `
      <a class="home-strip-card is-${m.kind}" href="${m.href}">
        <div class="home-strip-top">${badge}<span class="home-strip-meta">${esc(m.kind === "upcoming" ? m.meta : shortDate(m.date))}</span></div>
        ${m.teams
          .map(
            (t) => `<div class="home-strip-team"><span>${esc(t.name)}</span><strong>${esc(t.score)}</strong></div>`
          )
          .join("")}
        <p class="home-strip-note">${esc(m.note)}</p>
      </a>`;
  }

  function renderStrip() {
    const items = stripItems.filter((m) => stripFilter === "all" || m.kind === stripFilter);
    stripEl.innerHTML = items.length
      ? items.map(stripCard).join("")
      : `<div class="home-strip-empty">${
          stripFilter === "live" ? "No matches are live right now." : stripFilter === "upcoming" ? "No upcoming fixtures scheduled yet." : "No matches yet."
        }</div>`;
    stripEl.scrollLeft = 0;
    updateStripNav();
  }

  function updateStripNav() {
    const prev = document.querySelector(".home-strip-nav.prev");
    const next = document.querySelector(".home-strip-nav.next");
    if (!prev || !next) return;
    prev.hidden = stripEl.scrollLeft <= 4;
    next.hidden = stripEl.scrollLeft + stripEl.clientWidth >= stripEl.scrollWidth - 4;
  }

  document.querySelectorAll(".home-strip-tab").forEach((tab) =>
    tab.addEventListener("click", () => {
      stripFilter = tab.dataset.strip;
      document.querySelectorAll(".home-strip-tab").forEach((t) => {
        const on = t === tab;
        t.classList.toggle("is-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      renderStrip();
    })
  );
  document.querySelector(".home-strip-nav.prev")?.addEventListener("click", () => stripEl.scrollBy({ left: -stripEl.clientWidth * 0.8, behavior: "smooth" }));
  document.querySelector(".home-strip-nav.next")?.addEventListener("click", () => stripEl.scrollBy({ left: stripEl.clientWidth * 0.8, behavior: "smooth" }));
  stripEl.addEventListener("scroll", updateStripNav, { passive: true });
  window.addEventListener("resize", updateStripNav);

  // ---------- Featured match ----------
  function ballsHtml(balls) {
    if (!balls.length) return "";
    return `<div class="home-balls">${balls
      .slice(-6)
      .map((ball) => {
        const v = String(ball || "0").toUpperCase();
        const cls = v === "4" ? "four" : v === "6" ? "six" : v === "W" ? "wicket" : v === "WD" || v === "NB" ? "extra" : "";
        return `<span class="home-ball ${cls}">${esc(v)}</span>`;
      })
      .join("")}</div>`;
  }

  function renderFeature(m) {
    if (!m) {
      featureEl.innerHTML = `
        <div class="home-feature-top"><span class="home-badge upcoming">NO LIVE MATCHES</span></div>
        <h3 class="home-feature-title">Check back on match day</h3>
        <p class="home-feature-note">Live scores appear here as soon as a club starts scoring.</p>
        <a class="home-btn primary small" href="/fixtures">View fixtures</a>`;
      return;
    }
    const label = m.kind === "live" ? `<span class="home-badge live"><span class="home-dot"></span>LIVE NOW</span>` : `<span class="home-badge result">LATEST RESULT</span>`;
    featureEl.innerHTML = `
      <div class="home-feature-top">${label}<span class="home-strip-meta">${esc([shortDate(m.date), m.venue].filter(Boolean).join(" · "))}</span></div>
      <div class="home-feature-teams">
        ${m.teams
          .map(
            (t) => `<div class="home-feature-team"><span>${esc(t.name)}</span><strong>${esc(t.score || "–")}</strong></div>`
          )
          .join("")}
      </div>
      <p class="home-feature-note">${esc(m.note)}</p>
      ${m.kind === "live" ? `<p class="home-feature-sub">Recent balls</p>${ballsHtml(m.balls)}` : ""}
      <a class="home-btn primary small" href="${m.href}">${m.kind === "live" ? "Open match centre" : "View scorecard"}</a>`;
  }

  // ---------- Latest scorecards ----------
  function scorecardCard(sc) {
    const [y, mo, d] = String(sc.date || "").split("-").map(Number);
    const day = y ? DAYS[new Date(y, mo - 1, d).getDay()] : "";
    return `
      <a class="home-sc-card" href="/scorecards/${encodeURIComponent(sc.id)}">
        <div class="home-sc-date"><span>${esc(day)}</span><strong>${d || "–"}</strong><span>${esc(MONTHS[(mo || 1) - 1])}</span><small>${y || ""}</small></div>
        <div class="home-sc-body">
          ${(sc.teams || [])
            .map((t) => `<div class="home-strip-team"><span>${esc(t.name)}</span><strong>${esc(t.score || "–")}</strong></div>`)
            .join("")}
          <p class="home-sc-result">${esc(sc.result || "Result not recorded")}</p>
          ${sc.has_photo ? `<span class="home-tag">📷 Photo</span>` : ""}
        </div>
      </a>`;
  }

  // ---------- Lists ----------
  function listRow(m) {
    const [y, mo, d] = String(m.date || "").split("-").map(Number);
    return `
      <a class="home-row" href="${m.href}">
        <div class="home-row-date"><strong>${d || "–"}</strong><span>${esc(MONTHS[(mo || 1) - 1] || "")}</span></div>
        <div class="home-row-body">
          <strong>${esc(m.teams[0].name)} <em>vs</em> ${esc(m.teams[1].name)}</strong>
          <span>${esc(m.kind === "upcoming" ? m.note : [m.teams[0].score && `${m.teams[0].score}`, m.teams[1].score && `${m.teams[1].score}`].filter(Boolean).join(" · ") || m.meta || "")}</span>
          ${m.kind === "result" ? `<span class="home-row-result">${esc(m.note)}</span>` : ""}
        </div>
        <span class="home-row-go" aria-hidden="true">›</span>
      </a>`;
  }

  function empty(text, link, label) {
    return `<div class="home-empty">${esc(text)}${link ? ` <a href="${link}">${esc(label)}</a>` : ""}</div>`;
  }

  // ---------- Load ----------
  (async () => {
    const [live, fixtures, scorecards, clubs] = await Promise.all([
      getJson("/api/public/live-page"),
      getJson("/api/public/fixtures-page"),
      getJson("/api/public/scorecards"),
      getJson("/api/public/clubs"),
    ]);

    const all = (fixtures?.fixtures || []).map(fromFixture);
    const liveIds = new Set((live?.live_matches || []).map((m) => m.id));
    const liveMatches = (live?.live_matches || []).map((f) => ({ ...fromFixture(f), kind: "live", href: `/live/${encodeURIComponent(f.id)}` }));
    const results = all.filter((m) => m.kind === "result" && !liveIds.has(m.id)).sort((a, b) => String(b.date).localeCompare(String(a.date)));
    const today = todayIso();
    const upcoming = all
      .filter((m) => m.kind === "upcoming" && String(m.date) >= today)
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));

    // Strip
    stripItems = [...liveMatches, ...results.slice(0, 8), ...upcoming.slice(0, 8)];
    renderStrip();

    // Feature: live first, else latest result
    renderFeature(liveMatches[0] || results[0] || null);

    // Stats
    const setText = (id, value) => {
      const el = $(id);
      if (el) el.textContent = value;
    };
    setText("homeStatClubs", String((clubs?.clubs || []).length || "–"));
    setText("homeStatFixtures", String(fixtures?.hero?.total_fixtures ?? all.length ?? "–"));
    setText("homeStatScorecards", String((scorecards?.scorecards || []).length));

    // Scorecards
    const cards = (scorecards?.scorecards || []).slice(0, 4);
    scorecardsEl.innerHTML = cards.length
      ? cards.map(scorecardCard).join("")
      : empty("No approved scorecards yet.", "/scorecards", "Open the archive");

    // Lists
    resultsEl.innerHTML = results.length ? results.slice(0, 5).map(listRow).join("") : empty("No results yet.");
    upcomingEl.innerHTML = upcoming.length
      ? upcoming.slice(0, 5).map(listRow).join("")
      : empty("No upcoming fixtures scheduled yet.", "/fixtures", "See all fixtures");
  })();
})();
