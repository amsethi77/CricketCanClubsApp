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

  // The signed-in member's club (README "Home shows your own club", Oct 27). The club id is kept in
  // sessionStorage by multipage.js; /api/auth/me is the reliable source, so Home asks it once.
  function currentClubId() {
    try {
      return sessionStorage.getItem("cricketClubAppPrimaryClubId") || localStorage.getItem("cricketClubAppPrimaryClubId") || "";
    } catch (error) {
      return "";
    }
  }

  let myClubPromise = null;
  function myClub() {
    if (!myClubPromise) {
      myClubPromise = fetch("/api/auth/me", {
        headers: { Accept: "application/json", "X-Auth-Token": localStorage.getItem("cricketClubAppAuthToken") || "" },
      })
        .then((response) => (response.ok ? response.json() : null))
        .then((data) => {
          const user = (data && data.user) || {};
          return {
            id: String(user.current_club_id || user.primary_club_id || currentClubId() || ""),
            name: String(user.current_club_name || user.primary_club_name || ""),
          };
        })
        .catch(() => ({ id: currentClubId(), name: "" }));
    }
    return myClubPromise;
  }

  async function canEditScorebook(matchId) {
    try {
      const response = await fetch(`/api/quick-score/${encodeURIComponent(matchId)}`, {
        headers: {
          Accept: "application/json",
          "X-Auth-Token": localStorage.getItem("cricketClubAppAuthToken") || "",
        },
      });
      if (!response.ok) return false;
      const payload = await response.json();
      return Boolean(payload.can_edit_scorebook);
    } catch (error) {
      console.error("Could not check match scorebook permissions.", error);
      return false;
    }
  }

  // "Heartlake Cricket Club", "HEARTLAKE CC" and "Heart Lake" are the same club.
  function teamKey(name) {
    return String(name || "")
      .toLowerCase()
      .replace(/cricket|club|\bcc\b|\bxi\b/g, "")
      .replace(/[^a-z0-9]/g, "");
  }

  // ---------- 1. Welcome banner: greeting + quick actions ----------
  if (hero && !hero.querySelector(".dash-hero-actions")) {
    const copy = hero.querySelector(".template-header-copy") || hero;
    copy.insertAdjacentHTML(
      "beforeend",
      `<div class="dash-hero-actions">
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
  let viewerClubId = "";
  let viewerClubKey = ""; // Nov 2: fromFixture used clubKey before it existed (ReferenceError on Home)

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
    const clubIsOpponent = Boolean(viewerClubKey && teamKey(f.opponent) === viewerClubKey && teamKey(f.club_name) !== viewerClubKey);
    const ownName = clubIsOpponent ? (f.opponent || "Club") : (f.club_name || "Club");
    const opponentName = clubIsOpponent ? (f.club_name || "Opponent") : (f.opponent || "Opponent");
    const ownScore = clubIsOpponent ? f.opponent_score : f.heartlake_score;
    const otherScore = clubIsOpponent ? f.heartlake_score : f.opponent_score;
    return {
      id: f.id,
      club: clubIsOpponent ? viewerClubId : f.club_id,
      kind,
      date: f.date,
      teams: [
        { name: ownName, score: sc(ownScore) },
        { name: opponentName, score: sc(otherScore) },
      ],
      note:
        kind === "upcoming"
          ? [f.scheduled_time !== "Time TBD" ? f.scheduled_time : "", f.venue !== "Venue TBD" ? f.venue : ""].filter(Boolean).join(" · ") || "Time TBD"
          : !result || /^(tbd|club won)$/i.test(result)
            ? kind === "live" ? "In progress" : sc(ownScore) || sc(otherScore) ? "Full time" : "Result not recorded"
            : result,
      meta: [f.match_type, f.overs ? `${f.overs} ov` : ""].filter(Boolean).join(" · "),
      href: kind === "upcoming" ? "/matches" : `/live/${encodeURIComponent(f.id)}`,
    };
  }

  function card(m) {
    const mine = m.club && m.club === viewerClubId;
    const canEdit = m.canEditScorebook && m.kind === "result";
    const badge =
      m.kind === "live"
        ? `<span class="home-badge live"><span class="home-dot"></span>LIVE</span>`
        : m.kind === "result"
          ? `<span class="home-badge result">RESULT</span>`
          : `<span class="home-badge upcoming">${esc(shortDate(m.date))}</span>`;
    const scorecard = `
      <a class="home-strip-card is-${m.kind}${mine ? " is-mine" : ""}" href="${m.href}">
        <div class="home-strip-top">${badge}<span class="home-strip-meta">${esc(m.kind === "upcoming" ? m.meta : shortDate(m.date))}</span></div>
        ${m.teams.map((t) => `<div class="home-strip-team"><span>${esc(t.name)}</span><strong>${esc(t.score)}</strong></div>`).join("")}
        <p class="home-strip-note">${esc(m.note)}</p>
      </a>`;
    if (!canEdit) return scorecard;
    const editHref = `/dashboard/widgets/match-center?focus_club_id=${encodeURIComponent(m.club)}&match_id=${encodeURIComponent(m.id)}#selectedAvailabilityTitle`;
    const ballEditHref = `/score?match=${encodeURIComponent(m.id)}&edit=1`;
    return `<div class="home-match-card-wrap">${scorecard}<div class="home-match-actions">
      <a class="home-match-edit-link" href="${esc(editHref)}">Edit scorecard</a>
      <a class="home-match-edit-link" href="${esc(ballEditHref)}">Edit ball-by-ball</a>
    </div></div>`;
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

  // ---------- 4. AI Assistant card at the bottom of Home ----------
  const museCard = document.createElement("section");
  museCard.className = "muse-home";
  museCard.innerHTML = `
    <div>
      <p class="home-kicker">AI Assistant</p>
      <h2>Ask, score or send alerts with AI Assistant</h2>
      <p>Ask about players and clubs, type or say a match score, upload a scorecard photo, or ask the squad for availability.</p>
    </div>
    <form class="muse-home-form">
      <input placeholder="e.g. How can Amit S improve?  or  Heartlake 145/6, Imran XI 120/9…" aria-label="Message AI Assistant" />
      <button type="submit">Ask AI Assistant</button>
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
    const club = await myClub();
    const clubId = club.id;
    viewerClubId = clubId;
    const clubKey = teamKey(club.name);
    viewerClubKey = clubKey;
    const mineFirst = (a, b) => Number(b.club === clubId) - Number(a.club === clubId);
    // A member's Home shows their own club's matches and scorecards only (Amit, Oct 26: Heartlake's Home
    // showed other clubs' scorecards). The club's own card, or a card where the club is one of the teams.
    // When the card names its teams, the club must be one of them (photos of other clubs' games uploaded by
    // a Heartlake member are not Heartlake's). Only cards without team names fall back to the uploading club.
    const isMine = (ownerId, teamNames) => {
      if (!clubId) return true;
      const names = (teamNames || []).filter((name) => teamKey(name).length >= 3);
      if (clubKey.length >= 3 && names.length) return names.some((name) => teamKey(name) === clubKey);
      return ownerId === clubId;
    };

    const liveList = (live?.live_matches || []).map((f) => fromFixture(f, "live")).filter((m) => isMine(m.club, m.teams.map((t) => t.name)));
    const liveIds = new Set(liveList.map((m) => m.id));
    const all = (fixtures?.fixtures || [])
      .map((f) => fromFixture(f))
      .filter((m) => !liveIds.has(m.id) && isMine(m.club, m.teams.map((t) => t.name)));
    const results = all.filter((m) => m.kind === "result").sort((a, b) => String(b.date).localeCompare(String(a.date)));
    await Promise.all(results.slice(0, 8).map(async (match) => {
      match.canEditScorebook = await canEditScorebook(match.id);
    }));
    const today = todayIso();
    const upcoming = all
      .filter((m) => m.kind === "upcoming" && String(m.date) >= today)
      .sort((a, b) => String(a.date).localeCompare(String(b.date)));
    items = [...liveList.sort(mineFirst), ...results.slice(0, 8), ...upcoming.slice(0, 8)];
    renderStrip();

    const grid = scPanel.querySelector(".home-card-grid");
    const list = (scorecards?.scorecards || []).filter((sc) =>
      isMine(sc.club_id, (sc.teams || []).map((t) => t.name))
    );
    list.sort((a, b) => String(b.date).localeCompare(String(a.date)));
    grid.innerHTML = list.length
      ? list.slice(0, 4).map(scCard).join("")
      : `<div class="home-empty">No published scorecards for your club yet. <a href="/scorecards/upload">Upload a scorecard photo</a></div>`;
  })();
})();

// Club page: suggest merging a player record whose name is over 50% similar to the signed-in player's own.
// The request only asks; a club admin approves it in Admin Center > Name matches.
(() => {
  if (document.body.dataset.dashboardWidget !== "overview") return;
  const box = document.getElementById("clubMergeCandidates");
  if (!box) return;
  const list = box.querySelector("[data-merge-list]");
  const requests = box.querySelector("[data-merge-requests]");
  const msg = box.querySelector("[data-merge-msg]");
  const token = () => {
    try {
      return localStorage.getItem("cricketClubAppAuthToken") || "";
    } catch (error) {
      return "";
    }
  };
  const esc = (v) => String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  const statusText = { pending: "Waiting for a club admin", approved: "Approved and merged", rejected: "Not approved" };
  async function load() {
    if (!token()) return;
    const response = await fetch("/api/player/merge-candidates", { headers: { "X-Auth-Token": token() } }).catch(() => null);
    if (!response || !response.ok) return;
    const data = await response.json();
    const candidates = data.candidates || [];
    const history = data.requests || [];
    if (!candidates.length && !history.length) {
      box.hidden = true;
      return;
    }
    list.innerHTML = candidates.length
      ? candidates
          .map((item) => {
            const career = item.career || {};
            const clubs = (item.clubs || []).map((club) => `<span class="merge-chip">${esc(club)}</span>`).join("") || `<span class="merge-chip">No club</span>`;
            const action = item.pending_request_id
              ? `<p class="merge-status">${statusText.pending}</p>`
              : `<button type="button" class="merge-btn merge-btn-primary" data-merge-ask data-keep="older">Merge into older record</button>
                 <button type="button" class="merge-btn merge-btn-primary" data-merge-ask data-keep="newer">Merge into newer record</button>
                 <button type="button" class="merge-btn" data-merge-reject>Not me</button>`;
            return `<article class="merge-card" data-target-id="${esc(item.id)}">
              <header class="merge-card-head">
                <div>
                  <h3 class="merge-name">${esc(item.full_name || item.name)}</h3>
                  <p class="merge-meta">${esc(item.player_id)}</p>
                </div>
                <span class="merge-badge" title="Name similarity">${esc(item.match_percent)}% match</span>
              </header>
              <p class="merge-meta">Older record: <strong>${esc(item.older_name)}</strong> · Newer record: <strong>${esc(item.newer_name)}</strong></p>
              <div class="merge-chips">${clubs}</div>
              <dl class="merge-stats">
                <div><dt>Matches</dt><dd>${esc(career.matches ?? 0)}</dd></div>
                <div><dt>Runs</dt><dd>${esc(career.runs ?? 0)}</dd></div>
                <div><dt>Wickets</dt><dd>${esc(career.wickets ?? 0)}</dd></div>
                <div><dt>High score</dt><dd>${esc(career.highest_score ?? 0)}</dd></div>
              </dl>
              <div class="merge-actions">
                ${action}
                <button type="button" class="merge-btn merge-btn-link" data-merge-details aria-expanded="false">View details</button>
              </div>
              <div class="merge-details" data-merge-details-panel hidden></div>
            </article>`;
          })
          .join("")
      : "";
    requests.innerHTML = history.length
      ? `<p class="lede">Your requests</p>` +
        history.map((item) => `<p class="lede">${esc(item.target_name)}: ${esc(statusText[item.status] || item.status)}${item.decision_note ? ` (${esc(item.decision_note)})` : ""}</p>`).join("")
      : "";
    box.hidden = false;
  }
  list.addEventListener("click", async (event) => {
    const card = event.target.closest("[data-target-id]");
    if (!card) return;
    const targetId = card.dataset.targetId;
    if (event.target.closest("[data-merge-details]")) {
      await toggleDetails(card, targetId);
      return;
    }
    if (event.target.closest("[data-merge-reject]")) {
      msg.textContent = "Saving…";
      const response = await fetch(`/api/player/merge-suggestions/${encodeURIComponent(targetId)}/dismiss`, {
        method: "POST",
        headers: { "X-Auth-Token": token() },
      }).catch(() => null);
      msg.textContent = response && response.ok ? "Thanks. We won't suggest this record again." : "Couldn't save that. Please try again.";
      await load();
      return;
    }
    if (!event.target.closest("[data-merge-ask]")) return;
    const keep = event.target.closest("[data-merge-ask]").dataset.keep || "older";
    msg.textContent = "Sending…";
    const response = await fetch("/api/player/merge-requests", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Auth-Token": token() },
      body: JSON.stringify({ target_member_id: targetId, keep }),
    }).catch(() => null);
    const data = response ? await response.json().catch(() => ({})) : {};
    msg.textContent = response && response.ok ? data.message : data.detail || "Couldn't send the request. Please try again.";
    await load();
  });
  async function toggleDetails(card, targetId) {
    const toggle = card.querySelector("[data-merge-details]");
    const panel = card.querySelector("[data-merge-details-panel]");
    if (!panel.hidden) {
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
      return;
    }
    toggle.setAttribute("aria-expanded", "true");
    panel.hidden = false;
    if (panel.dataset.loaded) return;
    panel.innerHTML = `<p class="merge-meta">Loading…</p>`;
    const response = await fetch(`/api/player/merge-candidates/${encodeURIComponent(targetId)}/details`, {
      headers: { "X-Auth-Token": token() },
    }).catch(() => null);
    if (!response || !response.ok) {
      panel.innerHTML = `<p class="merge-meta">Couldn't load the details.</p>`;
      return;
    }
    const data = await response.json();
    const rows = (data.matches || []).length
      ? data.matches
          .map((row) => `<tr><td>${esc(row.date)}</td><td>${esc(row.club)}</td><td>${esc(row.opponent)}</td><td>${esc(row.runs)}(${esc(row.balls)})</td><td>${esc(row.wickets)}</td><td>${esc(row.catches)}</td></tr>`)
          .join("")
      : `<tr><td colspan="6" class="merge-meta">No match rows found for this player yet.</td></tr>`;
    const aliases = (data.aliases || []).length ? `<p class="merge-meta">Also known as: ${esc(data.aliases.join(", "))}</p>` : "";
    panel.innerHTML = `
      <p class="merge-section-title">Full name</p>
      <p class="merge-fullname">${esc(data.full_name || data.name)}</p>
      ${aliases}
      <p class="merge-section-title">Clubs</p>
      <div class="merge-chips">${(data.clubs || []).map((club) => `<span class="merge-chip">${esc(club)}</span>`).join("") || `<span class="merge-chip">No club</span>`}</div>
      <p class="merge-section-title">Recent matches</p>
      <div class="merge-table-wrap">
        <table class="merge-table">
          <thead><tr><th>Date</th><th>Club</th><th>Opponent</th><th>R(B)</th><th>W</th><th>C</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
    panel.dataset.loaded = "1";
  }
  load();
})();

