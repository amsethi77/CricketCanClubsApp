/*
 * Quick Score (/score): phone-first ball-by-ball scoring.
 *
 *  1. Pick today's fixture (or "Start a match now").
 *  2. Pick batting side, openers and bowler.
 *  3. Tap big buttons (0 1 2 3 4 6 / Wd Nb Bye LB / W), speak ("four", "wide", "bowled")
 *     or type shorthand ("1 4 0 wd 6 w"). Strike rotates and overs change automatically.
 *
 * Uses the existing scorebook APIs:
 *   POST   /api/matches/{id}/scorebook/setup
 *   POST   /api/matches/{id}/scorebook/ball
 *   DELETE /api/matches/{id}/scorebook/ball   (undo)
 * plus GET /api/quick-score/fixtures, GET /api/quick-score/{id}, POST /api/quick-score/start.
 * Every ball also triggers live alerts (bell icon) on the server.
 *
 * Pro (or a Free user's one free AI match): AI Live Scorer (🤖 button). Say or type what happened ("wide, then two runs",
 * "caught by Sam"); POST /api/matches/{id}/ai-scorer turns it into ball events and each
 * event is saved through the same scorebook/ball API, so the scoring engine does the maths.
 * Documented in README.md -> "Quick Score" and "Subscriptions and plans".
 *
 * Oct 2026: both line-ups (2-11 players each) must be set before scoring starts, and people who
 * aren't signed in can score a guest match (body data-mode="guest", /api/guest/... APIs, match code
 * sent as X-Guest-Code). README: "Line-ups and guest matches".
 *
 * Oct 29 2026 (README "Easier live scoring"): names are picked by tapping player buttons (no typing), the next
 * bowler / extras / wicket pop-ups save on one tap (wicket: How out -> fielder if needed -> next batter), any ball in
 * "This over" can be tapped to fix it (POST .../ball with the ball's id), line-ups have Select all / quick opponent
 * names, and FOUR / SIX / WICKET / FIFTY / HUNDRED get a celebration + phone buzz (celebrate.js).
 */
(() => {
  const app = document.getElementById("qsApp");
  const modal = document.getElementById("qsModal");
  const modalTitle = document.getElementById("qsModalTitle");
  const modalBody = document.getElementById("qsModalBody");
  const params = new URLSearchParams(location.search);
  const matchId = params.get("match") || "";
  const guest = document.body.dataset.mode === "guest";
  const guestKey = (id) => `qsGuestCode:${id}`;
  if (guest && matchId && params.get("code")) {
    try {
      localStorage.setItem(guestKey(matchId), params.get("code").trim().toUpperCase());
    } catch (e) {
      /* ignore */
    }
  }
  const guestCode = () => {
    try {
      return localStorage.getItem(guestKey(matchId)) || "";
    } catch (e) {
      return "";
    }
  };
  // API addresses: signed-in club matches vs guest matches
  const enc = encodeURIComponent;
  const URLS = guest
    ? { state: () => `/api/guest/matches/${enc(matchId)}`, setup: () => `/api/guest/matches/${enc(matchId)}/setup`, ball: () => `/api/guest/matches/${enc(matchId)}/ball` }
    : { state: () => `/api/quick-score/${enc(matchId)}`, setup: () => `/api/matches/${enc(matchId)}/scorebook/setup`, ball: () => `/api/matches/${enc(matchId)}/scorebook/ball` };
  const TOKEN_KEY = "cricketClubAppAuthToken";

  let data = null; // /api/quick-score/{id}
  let busy = false;
  let recognition = null;
  let plan = null; // /api/subscription/me -> subscription
  let aiMode = false;
  let aiRecognition = null;
  let aiLast = null; // last AI Scorer result

  const esc = (v) =>
    String(v ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  function token() {
    try {
      return localStorage.getItem(TOKEN_KEY) || "";
    } catch (e) {
      return "";
    }
  }

  async function api(method, url, body) {
    const response = await fetch(url, {
      method,
      headers: guest
        ? { "Content-Type": "application/json", Accept: "application/json", "X-Guest-Code": guestCode() }
        : { "Content-Type": "application/json", Accept: "application/json", "X-Auth-Token": token() },
      body: body ? JSON.stringify(body) : undefined,
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (e) {
      payload = null;
    }
    if (!response.ok) throw new Error((payload && payload.detail) || `Request failed (${response.status})`);
    return payload;
  }

  function toast(text, tone = "info") {
    let el = document.querySelector(".qs-toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "qs-toast";
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.dataset.tone = tone;
    el.hidden = false;
    clearTimeout(el._t);
    el._t = setTimeout(() => (el.hidden = true), tone === "error" ? 6000 : 2200);
  }

  // ---------- local memory of who is on strike / bowling (per match + innings) ----------
  const stateKey = (inn) => `qs:${matchId}:${inn}`;
  function loadLocal(inn) {
    try {
      return JSON.parse(localStorage.getItem(stateKey(inn)) || "null") || {};
    } catch (e) {
      return {};
    }
  }
  function saveLocal(inn, value) {
    try {
      localStorage.setItem(stateKey(inn), JSON.stringify(value));
    } catch (e) {
      /* ignore */
    }
  }

  // ---------- helpers on the match payload ----------
  function innings() {
    return (data?.match?.scorebook?.innings || []).slice().sort((a, b) => a.inning_number - b.inning_number);
  }
  function currentInnings() {
    const list = innings();
    const live = list.find((inn) => inn.status === "Live");
    if (live) return live;
    const first = list[0];
    const second = list[1];
    if (first && first.status !== "Completed") return first;
    if (second && second.status !== "Completed") return second;
    return second || first;
  }
  function legalBalls(inn) {
    return (inn.balls || []).filter((b) => !["wide", "no_ball"].includes(b.extras_type)).length;
  }
  function overString(balls) {
    return `${Math.floor(balls / 6)}.${balls % 6}`;
  }
  function battingIsClub(inn) {
    const club = String(data?.club?.name || "").toLowerCase();
    return String(inn.batting_team || "").toLowerCase() === club || (!inn.batting_team && inn.inning_number === 1);
  }
  function rosterFor(side) {
    const lineups = data.lineups || {};
    if ((lineups.club || []).length) return side === "club" ? lineups.club : lineups.opponent || [];
    return side === "club" ? data.roster || [] : [];
  }

  // Who is on strike now? Stored locally; falls back to the last ball.
  function players(inn) {
    const local = loadLocal(inn.inning_number);
    const balls = inn.balls || [];
    const last = balls[balls.length - 1];
    return {
      striker: local.striker || last?.striker || "",
      nonStriker: local.nonStriker || last?.non_striker || "",
      bowler: local.bowler || last?.bowler || "",
    };
  }

  // ---------- rendering ----------
  function renderFixtureList(list) {
    const fixtures = list.fixtures || [];
    const open = fixtures.filter((f) => f.open);
    const later = fixtures.filter((f) => !f.open);
    app.innerHTML = `
      <section class="qs-card">
        <p class="qs-kicker">Quick Score</p>
        <h1>Score a match</h1>
        <p class="qs-muted">Big buttons, voice scoring and automatic strike rotation. Everyone in ${esc(list.club?.name || "the club")} gets live alerts.</p>
        ${
          open.length
            ? `<div class="qs-list">${open
                .map(
                  (f) => `<a class="qs-fixture is-open" href="/score?match=${encodeURIComponent(f.id)}">
                    <span><strong>vs ${esc(f.opponent)}</strong><small>${esc(f.date_label)} · ${esc(f.overs)} overs</small></span>
                    <span class="qs-go">Score now ›</span></a>`
                )
                .join("")}</div>`
            : `<p class="qs-empty">No match is open for scoring today. Scoring opens on the match day.</p>`
        }
        ${
          list.can_create
            ? `<form id="qsStart" class="qs-start">
                <p class="qs-kicker">Start a match now</p>
                <div class="qs-row">
                  <input id="qsOpp" placeholder="Opponent name" required />
                  <input id="qsOvers" type="number" min="1" max="50" value="20" aria-label="Overs" />
                  <button class="qs-btn primary" type="submit">Start</button>
                </div>
              </form>`
            : ""
        }
        ${
          later.length
            ? `<p class="qs-kicker qs-later">Coming up</p><div class="qs-list">${later
                .map((f) => `<div class="qs-fixture"><span><strong>vs ${esc(f.opponent)}</strong><small>${esc(f.date_label)}</small></span><span class="qs-muted">Opens on match day</span></div>`)
                .join("")}</div>`
            : ""
        }
        <p class="qs-foot"><a href="/dashboard/widgets/scoring">Advanced scoring</a> · <a href="/scorecards/upload">Upload a scorecard photo</a></p>
      </section>`;
    const form = document.getElementById("qsStart");
    if (form) {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
          const res = await api("POST", "/api/quick-score/start", {
            opponent: document.getElementById("qsOpp").value,
            overs: String(document.getElementById("qsOvers").value || "20"),
          });
          location.href = `/score?match=${encodeURIComponent(res.match_id)}`;
        } catch (e) {
          toast(e.message, "error");
        }
      });
    }
  }

  function renderSetup(inn) {
    const m = data.match;
    const clubName = data.club?.name || m.club_name;
    const first = innings()[0];
    const isSecond = inn.inning_number === 2;
    const clubBatsFirst = !isSecond ? true : !battingIsClub(first);
    app.innerHTML = `
      <section class="qs-card">
        <p class="qs-kicker">${isSecond ? "Second innings" : "New match"} · ${esc(clubName)} vs ${esc(m.opponent)}</p>
        <h1>${isSecond ? "Start the chase" : "Who's batting?"}</h1>
        <form id="qsSetup" class="qs-form">
          ${
            isSecond
              ? `<p class="qs-muted">Target: <strong>${esc((first?.summary?.runs || 0) + 1)}</strong> to win</p>
                 <input type="hidden" id="qsBat" value="${clubBatsFirst ? "club" : "opp"}" />`
              : `<div class="qs-toggle" role="radiogroup">
                  <label><input type="radio" name="bat" value="club" checked /> <span>${esc(clubName)} bat</span></label>
                  <label><input type="radio" name="bat" value="opp" /> <span>${esc(m.opponent)} bat</span></label>
                </div>`
          }
          <label>Overs<input id="qsOversLimit" type="number" min="1" max="50" value="${esc(inn.overs_limit || m.overs || 20)}" /></label>
          <div id="qsPickers" class="qs-pickers"></div>
          <button class="qs-btn primary wide" type="submit">Start scoring</button>
        </form>
      </section>`;
    const pickers = document.getElementById("qsPickers");
    const sideOf = () => (isSecond ? document.getElementById("qsBat").value : app.querySelector('input[name="bat"]:checked').value);
    const picked = { striker: "", nonStriker: "", bowler: "" };
    const TITLES = { striker: "On strike", nonStriker: "Non-striker", bowler: "Opening bowler" };
    const drawPickers = () => {
      const bat = sideOf();
      const bats = rosterFor(bat === "club" ? "club" : "opp");
      const bowls = rosterFor(bat === "club" ? "opp" : "club");
      const group = (key, names, taken) =>
        `<div class="qs-pickgroup${picked[key] ? " done" : ""}"><p class="qs-step">${TITLES[key]}${picked[key] ? `: <b>${esc(picked[key])}</b>` : ""}</p>
          ${chipList(names, `data-role="${key}"`, taken, {}, picked[key])}${otherName(`qsOther_${key}`, TITLES[key], names.length === 0)}</div>`;
      pickers.innerHTML = group("striker", bats, [picked.nonStriker]) + group("nonStriker", bats, [picked.striker]) + group("bowler", bowls, []);
    };
    drawPickers();
    pickers.addEventListener("click", (event) => {
      const chip = event.target.closest("[data-role]");
      const other = event.target.closest("[data-other]");
      if (chip) {
        picked[chip.dataset.role] = chip.dataset.name;
      } else if (other) {
        const key = other.dataset.other.replace("qsOther_", "");
        const value = document.getElementById(other.dataset.other).value.trim();
        if (!value) return;
        picked[key] = value;
      } else {
        return;
      }
      if (picked.striker && picked.striker === picked.nonStriker) picked.nonStriker = "";
      drawPickers();
    });
    app.querySelectorAll('input[name="bat"]').forEach((r) =>
      r.addEventListener("change", () => {
        picked.striker = picked.nonStriker = picked.bowler = "";
        drawPickers();
      })
    );
    document.getElementById("qsSetup").addEventListener("submit", async (event) => {
      event.preventDefault();
      const bat = sideOf();
      const battingTeam = bat === "club" ? clubName : m.opponent;
      const bowlingTeam = bat === "club" ? m.opponent : clubName;
      const { striker, nonStriker, bowler } = picked;
      if (!striker || !nonStriker || !bowler) return toast("Tap the two opening batters and the bowler.", "error");
      if (striker === nonStriker) return toast("Striker and non-striker must be different.", "error");
      try {
        await api("POST", URLS.setup(), {
          innings_number: inn.inning_number,
          batting_team: battingTeam,
          bowling_team: bowlingTeam,
          overs_limit: Number(document.getElementById("qsOversLimit").value || 20),
          target_runs: isSecond ? Number(first?.summary?.runs || 0) : null,
          status: "Live",
          batters: [striker, nonStriker],
          bowlers: [bowler],
        });
        saveLocal(inn.inning_number, { striker, nonStriker, bowler, setup: true });
        await load();
      } catch (e) {
        toast(e.message, "error");
      }
    });
  }

  function renderScoring(inn) {
    const m = data.match;
    const sum = inn.summary || {};
    const p = players(inn);
    const legal = legalBalls(inn);
    const oversLimit = Number(inn.overs_limit || 20);
    const target = inn.inning_number === 2 ? Number(innings()[0]?.summary?.runs || 0) + 1 : null;
    const need = target ? Math.max(0, target - (sum.runs || 0)) : null;
    const ballsLeft = oversLimit * 6 - legal;
    const batterRow = (name, star) => {
      const row = (sum.batting || []).find((b) => b.player_name === name) || {};
      return `<div class="qs-batter${star ? " on-strike" : ""}"><span>${esc(name || "–")}${star ? " *" : ""}</span><strong>${row.runs || 0}<small> (${row.balls || 0})</small></strong></div>`;
    };
    const bowlRow = (sum.bowling || []).find((b) => b.player_name === p.bowler) || {};
    const overStart = Math.floor(legal / 6) * 6;
    let count = 0;
    const thisOver = [];
    (inn.balls || []).forEach((b) => {
      const isLegal = !["wide", "no_ball"].includes(b.extras_type);
      if (count >= overStart) thisOver.push(b);
      if (isLegal) count += 1;
    });
    // balls bowled after the last completed over
    const recent = (inn.balls || []).slice(-(thisOver.length || 0));
    const label = (b) => {
      if (b.wicket) return "W";
      if (b.extras_type === "wide") return `${b.extras_runs > 1 ? b.extras_runs : ""}wd`;
      if (b.extras_type === "no_ball") return `nb${b.runs_bat ? "+" + b.runs_bat : ""}`;
      if (b.extras_type === "bye") return `${b.extras_runs}b`;
      if (b.extras_type === "leg_bye") return `${b.extras_runs}lb`;
      return String(b.runs_bat || 0);
    };
    const done = inn.status === "Completed" || (target && (sum.runs || 0) >= target);
    app.innerHTML = `
      <section class="qs-board">
        <div class="qs-board-top">
          <span class="qs-live"><span class="qs-dot"></span>${done ? "INNINGS OVER" : "LIVE"}</span>
          <a class="qs-link" href="/live/${encodeURIComponent(matchId)}" target="_blank" rel="noopener">Public scorecard ↗</a>
        </div>
        <p class="qs-team">${esc(inn.batting_team || m.club_name)} <small>${inn.inning_number === 1 ? "1st" : "2nd"} innings</small></p>
        <p class="qs-score">${sum.runs || 0}/${sum.wickets || 0} <small>(${overString(legal)} / ${oversLimit} ov)</small></p>
        <p class="qs-rates">CRR ${legal ? ((sum.runs || 0) / (legal / 6)).toFixed(2) : "0.00"}${
          target ? ` · Need ${need} from ${ballsLeft} balls${ballsLeft > 0 ? ` · RRR ${((need / ballsLeft) * 6).toFixed(2)}` : ""}` : ""
        }</p>
        <div class="qs-batters">${batterRow(p.striker, true)}${batterRow(p.nonStriker, false)}</div>
        <div class="qs-bowler"><span>🎯 ${esc(p.bowler || "–")}</span><strong>${esc(bowlRow.overs || "0.0")}-${bowlRow.maidens || 0}-${bowlRow.runs_conceded || 0}-${bowlRow.wickets || 0}</strong></div>
        <div class="qs-over"><span>This over</span>${recent.map((b) => `<button type="button" class="qs-ball ${b.wicket ? "w" : b.runs_bat === 4 ? "four" : b.runs_bat === 6 ? "six" : b.extras_type !== "none" ? "x" : ""}"${String(b.id || "").startsWith("local-") ? " disabled" : ` data-fix="${esc(b.id)}"`} aria-label="Fix this ball: ${esc(label(b))}">${esc(label(b))}</button>`).join("") || '<em class="qs-muted">–</em>'}</div>
        ${recent.length ? '<p class="qs-fix-hint">Wrong ball? Tap it to fix it.</p>' : ""}
      </section>

      ${
        done
          ? `<section class="qs-card qs-done">
              <h2>${inn.inning_number === 1 ? "First innings complete" : "Match complete"}</h2>
              <p class="qs-muted">${esc(inn.batting_team)} scored ${sum.runs || 0}/${sum.wickets || 0} in ${overString(legal)} overs.</p>
              ${
                inn.inning_number === 1
                  ? `<button class="qs-btn primary wide" data-act="second">Start 2nd innings</button>`
                  : `<a class="qs-btn primary wide" href="/live/${encodeURIComponent(matchId)}">View scorecard</a>`
              }
              <button class="qs-btn ghost wide" data-act="undo">↶ Undo last ball</button>
            </section>`
          : `<section class="qs-pad" aria-label="Score this ball">
              ${["0", "1", "2", "3", "4", "6"].map((r) => `<button class="qs-key run${r === "4" ? " four" : r === "6" ? " six" : ""}" data-run="${r}">${r}</button>`).join("")}
              <button class="qs-key extra" data-extra="wide">Wd</button>
              <button class="qs-key extra" data-extra="no_ball">Nb</button>
              <button class="qs-key extra" data-extra="bye">Bye</button>
              <button class="qs-key extra" data-extra="leg_bye">LB</button>
              <button class="qs-key wicket" data-act="wicket">W</button>
              <button class="qs-key util" data-act="undo">↶ Undo</button>
            </section>
            <section class="qs-tools">
              <button class="qs-btn ghost" data-act="swap">⇄ Swap strike</button>
              <button class="qs-btn ghost" data-act="bowler">🎯 Change bowler</button>
              <button class="qs-btn ${recognition ? "primary" : "ghost"}" data-act="voice" aria-pressed="${recognition ? "true" : "false"}">🎙️ ${recognition ? "Listening…" : "Voice"}</button>
              ${guest ? "" : `<button class="qs-btn ${aiMode ? "primary" : "ghost"} qs-ai-btn" data-act="ai" aria-pressed="${aiMode ? "true" : "false"}">🤖 AI Scorer${hasAi() ? "" : " 🔒"}</button>`}
            </section>
            ${aiMode ? aiPanel() : ""}
            <form id="qsShort" class="qs-short">
              <input id="qsShortInput" placeholder="Type balls: 1 4 0 wd 6 w" autocomplete="off" />
              <button class="qs-btn primary" type="submit">Add</button>
            </form>
            <p class="qs-help">Voice: say “dot”, “single”, “two”, “four”, “six”, “wide”, “no ball”, “bye”, “leg bye”, “bowled”, “caught”, “LBW”, “run out” or “undo”.</p>`
      }`;
  }

  // ---------- AI Live Scorer (Pro; Free users get one free AI match) ----------
  function aiTrialHere() {
    const trial = plan && plan.ai_trial;
    return Boolean(trial && (!trial.used || trial.match_id === matchId));
  }

  function hasAi() {
    return Boolean(plan && ((plan.features || []).includes("ai_live_scorer") || aiTrialHere()));
  }

  function aiTrialNote() {
    const trial = plan && plan.ai_trial;
    if (!trial || (plan.features || []).includes("ai_live_scorer")) return "";
    return trial.used
      ? `<p class="qs-ai-trial">🎁 This is your free AI match. Other matches need Pro.</p>`
      : `<p class="qs-ai-trial">🎁 Free plan: try AI on one match for free. Using it here makes this your free AI match.</p>`;
  }

  function aiPanel() {
    if (!hasAi()) {
      return `<section class="qs-ai qs-ai-locked">
        <p class="qs-kicker">Pro</p>
        <h2>AI Live Scorer</h2>
        <p class="qs-muted">You've used your free AI match. Say “four”, “wide, then two runs” or “caught by Sam” and the scorecard updates by itself. Live scoring with the buttons stays free.</p>
        <a class="qs-btn primary" href="/pricing?feature=ai_live_scorer">See Pro ($9/month)</a>
      </section>`;
    }
    const last = aiLast
      ? `<div class="qs-ai-last">
          <p class="qs-ai-heard">Heard: “${esc(aiLast.heard)}”</p>
          ${
            aiLast.events.length
              ? `<p class="qs-ai-events">${aiLast.events.map((e) => `<b>${esc(e.label)}</b>`).join(" → ")}</p><p class="qs-ai-score">${esc(aiLast.before)} → <strong>${esc(aiLast.after)}</strong></p>`
              : ""
          }
          ${(aiLast.problems || []).map((p) => `<p class="qs-ai-problem">${esc(p)}</p>`).join("")}
        </div>`
      : `<p class="qs-muted">Say what happened on each ball, or type it below. Examples: “four”, “dot”, “wide, then two runs”, “no ball and a six”, “two leg byes”, “bowled”, “caught by Sam”, “undo”.</p>`;
    return `<section class="qs-ai">
      ${aiTrialNote()}
      <div class="qs-ai-head">
        <span class="qs-ai-status ${aiRecognition ? "on" : ""}">${aiRecognition ? "🎙️ Listening" : "⏸ Mic off"}</span>
        <button type="button" class="qs-btn ghost" data-act="ai-mic">${aiRecognition ? "Pause mic" : "Start mic"}</button>
      </div>
      ${last}
      <form id="qsAiForm" class="qs-short">
        <input id="qsAiInput" placeholder="e.g. wide, then two runs" autocomplete="off" />
        <button class="qs-btn primary" type="submit">Score it</button>
      </form>
    </section>`;
  }

  async function aiScore(text) {
    const phrase = String(text || "").trim();
    if (!phrase) return;
    const inn = currentInnings();
    let result;
    try {
      result = await api("POST", `/api/matches/${encodeURIComponent(matchId)}/ai-scorer`, { text: phrase, innings_number: inn.inning_number });
    } catch (e) {
      toast(`AI Scorer: ${e.message}`, "error");
      return;
    }
    aiLast = result;
    for (const event of result.events || []) {
      if (event.type === "UNDO") {
        await undo();
        continue;
      }
      if (event.type === "WICKET") {
        render();
        askWicket(event.wicket_type || "", event.fielder || "", event.runs_bat || 0);
        return; // the scorer confirms who is out and the new batter
      }
      record({ runs_bat: event.runs_bat || 0, extras_type: event.extras_type || "none", extras_runs: event.extras_runs || 0, commentary: `AI Scorer: ${event.heard || phrase}` });
      if (!modal.hidden) break; // over finished: pick the next bowler before scoring more
    }
    if ((result.events || []).length) toast(`🤖 ${(result.events || []).map((e) => e.label).join(" → ")}`);
    render();
  }

  function toggleAiMic() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      toast("Voice needs Chrome or Edge. You can still type what happened.", "error");
      return;
    }
    if (aiRecognition) {
      aiRecognition.onend = null;
      aiRecognition.stop();
      aiRecognition = null;
      render();
      return;
    }
    if (recognition) toggleVoice(); // only one microphone at a time
    aiRecognition = new SR();
    aiRecognition.lang = "en-IN";
    aiRecognition.continuous = true;
    aiRecognition.interimResults = false;
    aiRecognition.onresult = (event) => {
      const result = event.results[event.results.length - 1];
      if (result && result.isFinal) aiScore(result[0].transcript.trim());
    };
    aiRecognition.onerror = (event) => {
      if (event.error !== "no-speech") toast(`Voice: ${event.error}`, "error");
    };
    aiRecognition.onend = () => {
      if (aiRecognition) aiRecognition.start(); // hands-free: keep listening
    };
    aiRecognition.start();
    render();
  }

  function render() {
    if (!data.open) {
      app.innerHTML = `<section class="qs-card"><p class="qs-kicker">Quick Score</p><h1>Scoring is closed</h1>
        <p class="qs-muted">Ball-by-ball scoring opens on the match day. For past matches, use AI Assistant (“Heartlake 145/6, Imran XI 120/9…”) or upload a scorecard photo in Archives.</p>
        <a class="qs-btn primary" href="/score">Back to matches</a></section>`;
      return;
    }
    if (!data.can_score) {
      app.innerHTML = `<section class="qs-card"><h1>Scorers only</h1><p class="qs-muted">Ask a club admin to give you the scorer role. You can follow the match on the public scorecard.</p>
        <a class="qs-btn primary" href="/live/${encodeURIComponent(matchId)}">Follow live</a></section>`;
      return;
    }
    if (!data.lineups_ready) return renderLineups();
    const inn = currentInnings();
    const local = loadLocal(inn.inning_number);
    const hasBalls = (inn.balls || []).length > 0;
    if (!hasBalls && !local.setup) return renderSetup(inn);
    renderScoring(inn);
    if (guest) showGuestBanner();
  }

  // ---------- line-ups (both teams, 2-11 players, before scoring) ----------
  function lineupCount(text) {
    return cleanNames(text).length;
  }

  // "1. Ravi Kumar (c)", "2) Sam 🏏" pasted from WhatsApp -> "Ravi Kumar", "Sam"
  function cleanNames(text) {
    return String(text || "")
      .split(/[\n,;]+/)
      .map((n) =>
        n
          .replace(/^\s*\d{1,2}\s*[.)\-:]\s*/, "")
          .replace(/\((c|vc|wk|captain|keeper)\)|\*/gi, "")
          .replace(/[^\p{L}\p{N}\s.'-]/gu, "")
          .replace(/\s+/g, " ")
          .trim()
      )
      .filter(Boolean);
  }

  function renderLineups() {
    const m = data.match;
    const clubName = data.club?.name || m.club_name;
    const roster = data.roster || [];
    const saved = data.lineups || {};
    const chosen = new Set(saved.club || []);
    app.innerHTML = `
      <section class="qs-card">
        <p class="qs-kicker">Before the first ball · ${esc(clubName)} vs ${esc(m.opponent)}</p>
        <h1>Team line-ups</h1>
        <p class="qs-muted">Pick the players for both teams (2 to 11 each). Scoring starts once both line-ups are in.</p>
        <form id="qsLineups" class="qs-form">
          <fieldset class="qs-lineup">
            <legend>${esc(clubName)} <span class="qs-count" data-count="club">0</span></legend>
            ${
              roster.length
                ? `<div class="qs-picks">${roster
                    .map((n) => `<label class="qs-pick"><input type="checkbox" name="club" value="${esc(n)}"${chosen.has(n) ? " checked" : ""} /> <span>${esc(n)}</span></label>`)
                    .join("")}</div>`
                : ""
            }
            ${roster.length ? `<div class="qs-lineup-tools"><button type="button" class="qs-btn ghost" data-lineup="all">Select all</button><button type="button" class="qs-btn ghost" data-lineup="none">Clear</button></div>` : ""}
            <label>${roster.length ? "Other players (one per line)" : "Players (one per line)"}<textarea id="qsClubExtra" rows="${roster.length ? 2 : 6}" placeholder="Name\nName"></textarea></label>
          </fieldset>
          <fieldset class="qs-lineup">
            <legend>${esc(m.opponent)} <span class="qs-count" data-count="opp">0</span></legend>
            <label>Players (one per line, or paste the WhatsApp list)<textarea id="qsOppList" rows="6" placeholder="Name\nName">${esc((saved.opponent || []).join("\n"))}</textarea></label>
            <div class="qs-lineup-tools"><span class="qs-muted">Don't know their names?</span><button type="button" class="qs-btn ghost" data-lineup="opp11">Use Player 1–11</button></div>
          </fieldset>
          <button class="qs-btn primary wide" type="submit">Save line-ups</button>
        </form>
      </section>`;
    const form = document.getElementById("qsLineups");
    const clubNames = () => [
      ...Array.from(form.querySelectorAll('input[name="club"]:checked')).map((i) => i.value),
      ...cleanNames(document.getElementById("qsClubExtra").value),
    ];
    const oppNames = () => cleanNames(document.getElementById("qsOppList").value);
    form.addEventListener("click", (event) => {
      const tool = event.target.closest("[data-lineup]")?.dataset.lineup;
      if (!tool) return;
      if (tool === "all" || tool === "none") {
        const boxes = Array.from(form.querySelectorAll('input[name="club"]'));
        boxes.forEach((box, i) => (box.checked = tool === "all" && i < 11));
        if (tool === "all" && boxes.length > 11) toast("Ticked the first 11. Untick anyone not playing, then tick the others.");
      } else if (tool === "opp11") {
        document.getElementById("qsOppList").value = Array.from({ length: 11 }, (_, i) => `Player ${i + 1}`).join("\n");
      }
      updateCounts();
    });
    const updateCounts = () => {
      const c = clubNames().length;
      const o = oppNames().length;
      form.querySelector('[data-count="club"]').textContent = `${c}/11`;
      form.querySelector('[data-count="opp"]').textContent = `${o}/11`;
      form.querySelector('[data-count="club"]').classList.toggle("ok", c >= 2 && c <= 11);
      form.querySelector('[data-count="opp"]').classList.toggle("ok", o >= 2 && o <= 11);
    };
    form.addEventListener("input", updateCounts);
    form.addEventListener("change", (event) => {
      // 11 players at most per team (Amit, Oct 29)
      if (event.target.name === "club" && event.target.checked && clubNames().length > 11) {
        event.target.checked = false;
        toast("11 players at most. Untick someone first.", "error");
      }
      updateCounts();
    });
    updateCounts();
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const c = clubNames().length;
      const o = oppNames().length;
      if (c < 2 || c > 11) return toast(`${clubName} needs 2 to 11 players (now ${c}).`, "error");
      if (o < 2 || o > 11) return toast(`${m.opponent} needs 2 to 11 players (now ${o}).`, "error");
      try {
        await api("POST", `/api/matches/${enc(matchId)}/lineups`, { club: clubNames(), opponent: oppNames() });
        toast("Line-ups saved ✓");
        await load();
      } catch (e) {
        toast(e.message, "error");
      }
    });
  }

  // ---------- guest matches (no sign-in) ----------
  function showGuestBanner() {
    if (document.querySelector(".qs-guest-banner")) return;
    const code = guestCode();
    const banner = document.createElement("div");
    banner.className = "qs-guest-banner";
    banner.innerHTML = `Guest match · code <strong>${esc(code)}</strong> <span>Use it to keep scoring on another phone. Followers watch at <a href="/live/${enc(matchId)}">/live</a>.</span>`;
    app.insertAdjacentElement("beforebegin", banner);
  }

  function renderGuestStart() {
    app.innerHTML = `
      <section class="qs-card">
        <p class="qs-kicker">Score a match · no sign-in needed</p>
        <h1>Start a new match</h1>
        <p class="qs-muted">Enter both teams and their line-ups (2 to 11 players each), then score ball by ball. You'll get a match code to keep scoring on another phone. The match shows on the Live page while you play.</p>
        <form id="qsGuest" class="qs-form">
          <div class="qs-row2">
            <label>Team 1<input id="qsTeamA" required maxlength="40" placeholder="e.g. Sunday Strikers" /></label>
            <label>Team 2<input id="qsTeamB" required maxlength="40" placeholder="e.g. Park Royals" /></label>
          </div>
          <div class="qs-row2">
            <label>Overs<input id="qsGuestOvers" type="number" min="1" max="50" value="20" /></label>
            <label>Ground (optional)<input id="qsGuestVenue" maxlength="60" placeholder="e.g. Heart Lake Park" /></label>
          </div>
          <label>Team 1 line-up <span class="qs-count" data-count="a">0/11</span><textarea id="qsLineupA" rows="6" placeholder="One player per line"></textarea></label>
          <label>Team 2 line-up <span class="qs-count" data-count="b">0/11</span><textarea id="qsLineupB" rows="6" placeholder="One player per line"></textarea></label>
          <button class="qs-btn primary wide" type="submit">Create match and start scoring</button>
        </form>
        <form id="qsResume" class="qs-short qs-resume">
          <input id="qsResumeCode" maxlength="6" placeholder="Have a match code? e.g. K7P2QX" autocomplete="off" />
          <button class="qs-btn ghost" type="submit">Continue</button>
        </form>
        <p class="qs-foot">Scoring for your club? <a href="/signin">Sign in</a> to use your club's fixtures, player stats and alerts.</p>
      </section>`;
    const form = document.getElementById("qsGuest");
    const counts = () => {
      const a = lineupCount(document.getElementById("qsLineupA").value);
      const b = lineupCount(document.getElementById("qsLineupB").value);
      form.querySelector('[data-count="a"]').textContent = `${a}/11`;
      form.querySelector('[data-count="b"]').textContent = `${b}/11`;
      form.querySelector('[data-count="a"]').classList.toggle("ok", a >= 2 && a <= 11);
      form.querySelector('[data-count="b"]').classList.toggle("ok", b >= 2 && b <= 11);
    };
    form.addEventListener("input", counts);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const res = await fetch("/api/guest/matches", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            team_a: document.getElementById("qsTeamA").value,
            team_b: document.getElementById("qsTeamB").value,
            overs: Number(document.getElementById("qsGuestOvers").value || 20),
            venue: document.getElementById("qsGuestVenue").value,
            lineup_a: cleanNames(document.getElementById("qsLineupA").value).join("\n"),
            lineup_b: cleanNames(document.getElementById("qsLineupB").value).join("\n"),
          }),
        });
        const payload = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(payload.detail || "Couldn't create the match");
        try {
          localStorage.setItem(guestKey(payload.match_id), payload.code);
        } catch (e) {
          /* ignore */
        }
        location.href = `/score?match=${enc(payload.match_id)}`;
      } catch (e) {
        toast(e.message, "error");
      }
    });
    document.getElementById("qsResume").addEventListener("submit", async (event) => {
      event.preventDefault();
      const code = document.getElementById("qsResumeCode").value.trim().toUpperCase();
      if (!code) return;
      try {
        const res = await fetch(`/api/guest/resume?code=${enc(code)}`, { headers: { Accept: "application/json" } });
        const payload = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(payload.detail || "Code not found");
        location.href = `/score?match=${enc(payload.match_id)}&code=${enc(code)}`;
      } catch (e) {
        toast(e.message, "error");
      }
    });
  }

  async function load() {
    const [match, me] = await Promise.all([
      api("GET", URLS.state()),
      plan || guest ? Promise.resolve(null) : api("GET", "/api/subscription/me").catch(() => null),
    ]);
    data = match;
    if (me) plan = me.subscription;
    render();
  }

  // ---------- recording a ball ----------
  function runsRotate(runs) {
    return runs % 2 === 1;
  }

  // Taps are queued and saved one after another, so fast scoring never loses a ball.
  const queue = [];
  let pendingLegal = 0;
  let draining = false;

  function showPending() {
    let el = document.querySelector(".qs-pending");
    if (!el) {
      el = document.createElement("div");
      el.className = "qs-pending";
      document.body.appendChild(el);
    }
    el.hidden = !queue.length && !draining;
    el.textContent = `Saving ${queue.length + (draining ? 1 : 0)} ball${queue.length + (draining ? 1 : 0) === 1 ? "" : "s"}…`;
  }

  async function drain() {
    if (draining) return;
    draining = true;
    showPending();
    try {
      while (queue.length) {
        const item = queue[0];
        try {
          await api("POST", URLS.ball(), item.payload);
        } catch (e) {
          toast(`A ball wasn't saved: ${e.message}`, "error");
        }
        queue.shift();
        if (item.legal) pendingLegal = Math.max(0, pendingLegal - 1);
        showPending();
      }
      await load();
    } finally {
      draining = false;
      showPending();
    }
  }

  function record(ball) {
    const inn = currentInnings();
    const p = players(inn);
    if (!p.striker || !p.bowler) {
      toast("Pick the striker and bowler first.", "error");
      return;
    }
    const legal = legalBalls(inn) + pendingLegal;
    const isLegal = !["wide", "no_ball"].includes(ball.extras_type || "none");
    const payload = {
      innings_number: inn.inning_number,
      over_number: Math.floor(legal / 6) + 1,
      ball_number: (legal % 6) + 1,
      striker: p.striker,
      non_striker: p.nonStriker,
      bowler: p.bowler,
      runs_bat: ball.runs_bat || 0,
      extras_type: ball.extras_type || "none",
      extras_runs: ball.extras_runs || 0,
      wicket: Boolean(ball.wicket),
      wicket_type: ball.wicket_type || "",
      wicket_player: ball.wicket_player || "",
      fielder: ball.fielder || "",
      commentary: ball.commentary || "",
    };
    // Strike rotation, worked out straight away
    let { striker, nonStriker, bowler } = p;
    if (runsRotate(ranRuns(ball))) [striker, nonStriker] = [nonStriker, striker];
    const overDone = isLegal && (legal + 1) % 6 === 0;
    if (overDone) [striker, nonStriker] = [nonStriker, striker];
    if (ball.wicket) {
      if (ball.wicket_player === nonStriker) nonStriker = ball.new_batter || "";
      else striker = ball.new_batter || "";
    }
    saveLocal(inn.inning_number, { ...loadLocal(inn.inning_number), striker, nonStriker, bowler, setup: true });
    if (isLegal) pendingLegal += 1;
    queue.push({ payload, legal: isLegal });
    const row = (inn.summary?.batting || []).find((b) => b.player_name === payload.striker) || {};
    const runsBefore = Number(row.runs || 0);
    const bySelf = !["bye", "leg_bye", "wide"].includes(payload.extras_type);
    optimistic(inn, payload);
    drain();
    if (window.ccCelebrateBall) {
      window.ccCelebrateBall(payload, runsBefore, runsBefore + (bySelf ? payload.runs_bat || 0 : 0), Number(row.balls || 0) + (payload.extras_type === "wide" ? 0 : 1));
    }
    const oversLimit = Number(inn.overs_limit || 20);
    if (overDone && legal + 1 < oversLimit * 6) {
      const overBalls = (inn.balls || []).filter((b) => Number(b.over_number) === payload.over_number);
      const overRuns = overBalls.reduce((sum, b) => sum + Number(b.runs_bat || 0) + Number(b.extras_runs || 0), 0);
      const overWkts = overBalls.filter((b) => b.wicket).length;
      askBowler(`Over ${payload.over_number} done: ${overRuns} run${overRuns === 1 ? "" : "s"}${overWkts ? `, ${overWkts} wicket${overWkts === 1 ? "" : "s"}` : ""}${overRuns === 0 && !overWkts ? " · maiden!" : ""}`, true);
    }
  }

  // Runs the batters ran on a ball (decides strike rotation)
  function ranRuns(ball) {
    return (
      (ball.runs_bat || 0) +
      (["bye", "leg_bye"].includes(ball.extras_type) ? ball.extras_runs || 0 : 0) +
      (ball.extras_type === "wide" ? Math.max(0, (ball.extras_runs || 1) - 1) : 0)
    );
  }

  // Show the ball on screen right away (the server copy replaces it when saving finishes)
  function optimistic(inn, payload) {
    inn.balls = [...(inn.balls || []), { ...payload, id: `local-${Date.now()}` }];
    const sum = inn.summary || (inn.summary = {});
    const extra = payload.extras_type !== "none" ? payload.extras_runs || 0 : 0;
    sum.runs = (sum.runs || 0) + (payload.runs_bat || 0) + extra;
    if (payload.wicket) sum.wickets = (sum.wickets || 0) + 1;
    const batter = (sum.batting || []).find((b) => b.player_name === payload.striker);
    if (batter && !["wide"].includes(payload.extras_type)) {
      batter.runs = (batter.runs || 0) + (["bye", "leg_bye"].includes(payload.extras_type) ? 0 : payload.runs_bat || 0);
      batter.balls = (batter.balls || 0) + 1;
    }
    pendingLegal = Math.max(0, pendingLegal); // legalBalls() now counts the optimistic ball
    if (!["wide", "no_ball"].includes(payload.extras_type)) pendingLegal = Math.max(0, pendingLegal - 1);
    render();
  }

  async function undo() {
    if (queue.length || draining) {
      toast("Wait for the last balls to save, then undo.");
      return;
    }
    if (busy) return;
    busy = true;
    try {
      const inn = currentInnings();
      const removed = (inn.balls || [])[(inn.balls || []).length - 1];
      await api("DELETE", URLS.ball());
      await load();
      const now = currentInnings();
      if (removed) {
        saveLocal(now.inning_number, {
          ...loadLocal(now.inning_number),
          striker: removed.striker,
          nonStriker: removed.non_striker,
          bowler: removed.bowler,
          setup: true,
        });
      }
      render();
      toast("Last ball removed.");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
    }
  }

  // ---------- pop-ups (README "Easier live scoring": tap a name or a choice and it saves) ----------
  function openModal(title, bodyHtml, onOk) {
    modalTitle.textContent = title;
    modalBody.innerHTML = bodyHtml;
    modal.hidden = false;
    const ok = modal.querySelector("[data-modal-ok]");
    const cancel = modal.querySelector("[data-modal-cancel]");
    ok.hidden = false;
    const close = () => {
      modal.hidden = true;
      ok.onclick = null;
      cancel.onclick = null;
    };
    ok.onclick = async () => {
      const keep = await onOk();
      if (keep !== false) close();
    };
    cancel.onclick = close;
    const first = modalBody.querySelector("input, select");
    if (first) setTimeout(() => first.focus(), 50);
  }

  // A pop-up without a Save button: tapping a choice does the job. onTap(target, close) gets every tap inside it.
  function openSheet(title, bodyHtml, onTap) {
    modalTitle.textContent = title;
    modalBody.innerHTML = bodyHtml;
    modal.hidden = false;
    modal.classList.add("qs-sheet");
    const ok = modal.querySelector("[data-modal-ok]");
    const cancel = modal.querySelector("[data-modal-cancel]");
    ok.hidden = true;
    const close = () => {
      modal.hidden = true;
      modal.classList.remove("qs-sheet");
      ok.hidden = false;
      cancel.onclick = null;
      modalBody.onclick = null;
      modalBody.onkeydown = null;
    };
    cancel.onclick = close;
    modalBody.onclick = (event) => onTap(event.target, close);
    // Enter in a "Someone else?" box works like its OK button
    modalBody.onkeydown = (event) => {
      if (event.key !== "Enter" || !event.target.matches("input")) return;
      event.preventDefault();
      event.target.parentElement.querySelector("[data-other]")?.click();
    };
    return close;
  }

  // Big name buttons. taken = names shown greyed out; sub = small text under a name; selected = highlighted name.
  function chipList(names, attrs = "", taken = [], sub = {}, selected = "") {
    const skip = new Set((taken || []).filter(Boolean));
    if (!names.length) return "";
    return `<div class="qs-chips">${names
      .map(
        (n) =>
          `<button type="button" class="qs-chip${n === selected ? " on" : ""}" data-name="${esc(n)}" ${attrs}${skip.has(n) ? " disabled" : ""}>${esc(n)}${
            sub[n] ? `<small>${esc(sub[n])}</small>` : ""
          }</button>`
      )
      .join("")}</div>`;
  }

  // "Someone else?" for a player who isn't in the line-up
  function otherName(id, placeholder, open = false) {
    return `<details class="qs-other"${open ? " open" : ""}><summary>${open ? "Type the name" : "Someone else?"}</summary>
      <div class="qs-short"><input id="${id}" placeholder="${esc(placeholder)}" autocomplete="off" /><button type="button" class="qs-btn primary" data-other="${id}">OK</button></div></details>`;
  }

  // The name chosen by a tap: a name button, or the OK next to a typed name
  function tappedName(target) {
    const chip = target.closest("[data-name]");
    if (chip && !chip.disabled) return chip.dataset.name;
    const other = target.closest("[data-other]");
    if (other) return (document.getElementById(other.dataset.other)?.value || "").trim();
    return "";
  }

  function bowlingRoster(inn) {
    return rosterFor(battingIsClub(inn) ? "opp" : "club");
  }
  function battingRoster(inn) {
    return rosterFor(battingIsClub(inn) ? "club" : "opp");
  }

  // Next bowler: one tap. afterOver = the over just ended, so the same bowler can't continue.
  function askBowler(note = "", afterOver = false) {
    const inn = currentInnings();
    const p = players(inn);
    const figures = {};
    (inn.summary?.bowling || []).forEach((b) => {
      figures[b.player_name] = `${b.overs || "0.0"}-${b.maidens || 0}-${b.runs_conceded || 0}-${b.wickets || 0}`;
    });
    const list = bowlingRoster(inn);
    openSheet(
      "Who bowls next?",
      `${note ? `<p class="qs-sheet-note">${esc(note)}</p>` : ""}
       ${chipList(list, "", afterOver ? [p.bowler] : [], figures, afterOver ? "" : p.bowler)}
       ${otherName("qsNewBowler", "Bowler's name", list.length === 0)}
       ${afterOver ? '<p class="qs-muted">The same bowler can\'t bowl two overs in a row.</p>' : ""}`,
      (target, close) => {
        const name = tappedName(target);
        if (!name) return;
        close();
        const now = currentInnings();
        const q = players(now);
        saveLocal(now.inning_number, { ...loadLocal(now.inning_number), striker: q.striker, nonStriker: q.nonStriker, bowler: name, setup: true });
        render();
      }
    );
  }

  // Wicket in 2-3 taps: How out -> (fielder, and for a run out who / runs) -> next batter.
  function askWicket(preset = "", fielder = "", runsDone = 0) {
    const inn = currentInnings();
    const p = players(inn);
    const batted = new Set((inn.summary?.batting || []).map((b) => b.player_name));
    const remaining = battingRoster(inn).filter((n) => n !== p.striker && n !== p.nonStriker && !batted.has(n));
    const fielders = bowlingRoster(inn);
    const HOW = [
      ["bowled", "Bowled"],
      ["caught", "Caught"],
      ["lbw", "LBW"],
      ["run_out", "Run out"],
      ["stumped", "Stumped"],
      ["hit_wicket", "Hit wicket"],
    ];
    const needsFielder = (how) => ["caught", "run_out", "stumped"].includes(how);
    const w = { how: preset, out: p.striker, fielder: fielder || "", runs: Number(runsDone) || 0 };
    let step = !preset ? "how" : needsFielder(preset) && !fielder ? "fielder" : "batter";

    const draw = () => {
      const howLabel = (HOW.find(([v]) => v === w.how) || [])[1] || "";
      if (step === "how") {
        modalTitle.textContent = "Wicket! How out?";
        modalBody.innerHTML = `<p class="qs-sheet-note">${esc(p.striker)} on strike · ${esc(p.bowler)} bowling</p>
          <div class="qs-chips big">${HOW.map(([v, l]) => `<button type="button" class="qs-chip" data-how="${v}">${l}</button>`).join("")}</div>`;
      } else if (step === "fielder") {
        modalTitle.textContent = w.how === "caught" ? "Caught by?" : w.how === "stumped" ? "Stumped by?" : "Run out";
        const runOut =
          w.how === "run_out"
            ? `<p class="qs-step">Who is out?</p>
               <div class="qs-chips">${[
                 [p.striker, "striker"],
                 [p.nonStriker, "non-striker"],
               ]
                 .filter(([n]) => n)
                 .map(([n, role]) => `<button type="button" class="qs-chip${w.out === n ? " on" : ""}" data-out="${esc(n)}">${esc(n)}<small>${role}</small></button>`)
                 .join("")}</div>
               <p class="qs-step">Runs completed before the run out</p>
               <div class="qs-chips">${[0, 1, 2, 3].map((r) => `<button type="button" class="qs-chip${w.runs === r ? " on" : ""}" data-wruns="${r}">${r}</button>`).join("")}</div>
               <p class="qs-step">Fielder</p>`
            : "";
        const sub = {};
        if (p.bowler) sub[p.bowler] = "bowler";
        modalBody.innerHTML = `${runOut}${chipList(fielders, "", [], sub)}${otherName("qsFielderOther", "Fielder's name", fielders.length === 0)}
          <button type="button" class="qs-btn ghost wide" data-skip-fielder>Don't know · skip</button>`;
      } else {
        modalTitle.textContent = "Next batter in";
        modalBody.innerHTML = `<p class="qs-sheet-note">${esc(w.out)} ${esc(howLabel.toLowerCase())}${w.fielder ? ` · ${esc(w.fielder)}` : ""}</p>
          ${chipList(remaining)}
          ${otherName("qsNewBat", "Next batter's name", remaining.length === 0)}
          <button type="button" class="qs-btn ghost wide" data-no-batter>No more batters (all out)</button>`;
      }
    };

    const finish = async (close, newBatter) => {
      close();
      await record({
        wicket: true,
        wicket_type: w.how,
        wicket_player: w.out,
        fielder: w.fielder,
        runs_bat: w.how === "run_out" ? w.runs : 0,
        new_batter: newBatter,
      });
    };

    openSheet("Wicket!", "", (target, close) => {
      const how = target.closest("[data-how]")?.dataset.how;
      if (how) {
        w.how = how;
        w.out = p.striker;
        step = needsFielder(how) ? "fielder" : "batter";
        return draw();
      }
      if (step === "fielder") {
        const out = target.closest("[data-out]")?.dataset.out;
        if (out) {
          w.out = out;
          return draw();
        }
        const runs = target.closest("[data-wruns]")?.dataset.wruns;
        if (runs != null) {
          w.runs = Number(runs);
          return draw();
        }
        if (target.closest("[data-skip-fielder]")) {
          w.fielder = "";
          step = "batter";
          return draw();
        }
        const name = tappedName(target);
        if (name) {
          w.fielder = name;
          step = "batter";
          return draw();
        }
        return;
      }
      if (step === "batter") {
        if (target.closest("[data-no-batter]")) return finish(close, "");
        const name = tappedName(target);
        if (name) return finish(close, name);
      }
    });
    draw();
  }

  // Byes, leg byes and no balls: one tap on the number. Wide = 1 straight away (fix it by tapping the ball).
  function askExtra(type) {
    const labels = { wide: "Wide", no_ball: "No ball", bye: "Byes", leg_bye: "Leg byes" };
    if (type === "wide") return record({ extras_type: "wide", extras_runs: 1 });
    const nb = type === "no_ball";
    const options = nb ? [0, 1, 2, 3, 4, 6] : [1, 2, 3, 4];
    openSheet(
      nb ? "No ball · runs off the bat?" : `${labels[type]} · how many?`,
      `<div class="qs-chips big">${options.map((n) => `<button type="button" class="qs-chip" data-x="${n}">${nb ? (n ? `+${n}` : "No runs") : n}</button>`).join("")}</div>
       ${nb ? '<p class="qs-muted">1 no-ball run is added by itself.</p>' : ""}`,
      (target, close) => {
        const chip = target.closest("[data-x]");
        if (!chip) return;
        close();
        const n = Number(chip.dataset.x);
        if (nb) record({ extras_type: "no_ball", extras_runs: 1, runs_bat: n });
        else record({ extras_type: type, extras_runs: n });
      }
    );
  }

  // Fix any ball already scored: tap it in "This over".
  const FIX_CHOICES = [
    ["0", { runs_bat: 0 }],
    ["1", { runs_bat: 1 }],
    ["2", { runs_bat: 2 }],
    ["3", { runs_bat: 3 }],
    ["4", { runs_bat: 4 }],
    ["6", { runs_bat: 6 }],
    ["Wd", { extras_type: "wide", extras_runs: 1 }],
    ["2 wd", { extras_type: "wide", extras_runs: 2 }],
    ["5 wd", { extras_type: "wide", extras_runs: 5 }],
    ["Nb", { extras_type: "no_ball", extras_runs: 1, runs_bat: 0 }],
    ["Nb +1", { extras_type: "no_ball", extras_runs: 1, runs_bat: 1 }],
    ["Nb +4", { extras_type: "no_ball", extras_runs: 1, runs_bat: 4 }],
    ["Nb +6", { extras_type: "no_ball", extras_runs: 1, runs_bat: 6 }],
    ["1 bye", { extras_type: "bye", extras_runs: 1 }],
    ["4 byes", { extras_type: "bye", extras_runs: 4 }],
    ["1 lb", { extras_type: "leg_bye", extras_runs: 1 }],
    ["4 lb", { extras_type: "leg_bye", extras_runs: 4 }],
  ];

  function ballText(b) {
    if (b.wicket) return `wicket (${String(b.wicket_type || "out").replace("_", " ")})`;
    if (b.extras_type === "wide") return `${b.extras_runs || 1} wide`;
    if (b.extras_type === "no_ball") return `no ball${b.runs_bat ? ` +${b.runs_bat}` : ""}`;
    if (b.extras_type === "bye") return `${b.extras_runs} bye${b.extras_runs === 1 ? "" : "s"}`;
    if (b.extras_type === "leg_bye") return `${b.extras_runs} leg bye${b.extras_runs === 1 ? "" : "s"}`;
    return `${b.runs_bat || 0} run${b.runs_bat === 1 ? "" : "s"}`;
  }

  function askFix(ballId) {
    if (queue.length || draining || busy) return toast("Wait a second for the last balls to save, then tap again.");
    const inn = currentInnings();
    const balls = inn.balls || [];
    const index = balls.findIndex((b) => b.id === ballId);
    if (index < 0) return;
    const b = balls[index];
    const isLast = index === balls.length - 1;
    openSheet(
      `Fix ball ${b.over_number - 1}.${b.ball_number}`,
      `<p class="qs-sheet-note">${esc(b.bowler)} to ${esc(b.striker)} · scored as <b>${esc(ballText(b))}</b></p>
       ${b.wicket ? `<p class="qs-muted">Picking a new result below takes the wicket away${isLast ? "" : ". The batter who came in stays in"}.</p>` : ""}
       <p class="qs-step">What really happened?</p>
       <div class="qs-chips">${FIX_CHOICES.map(([label], i) => `<button type="button" class="qs-chip" data-fixto="${i}">${esc(label)}</button>`).join("")}</div>
       ${
         isLast
           ? `<div class="qs-fix-more">
               ${b.wicket ? "" : '<button type="button" class="qs-btn ghost" data-fix-wicket>It was a wicket</button>'}
               <button type="button" class="qs-btn ghost" data-fix-delete>Delete this ball</button>
             </div>`
           : ""
       }`,
      async (target, close) => {
        if (target.closest("[data-fix-delete]")) {
          close();
          return undo();
        }
        if (target.closest("[data-fix-wicket]")) {
          close();
          await undo();
          return askWicket();
        }
        const chip = target.closest("[data-fixto]");
        if (!chip) return;
        close();
        const result = FIX_CHOICES[Number(chip.dataset.fixto)][1];
        await saveFix(inn, b, result, isLast);
      }
    );
  }

  async function saveFix(inn, b, result, isLast) {
    if (busy) return;
    busy = true;
    try {
      await api("POST", URLS.ball(), {
        id: b.id,
        innings_number: inn.inning_number,
        over_number: b.over_number,
        ball_number: b.ball_number,
        striker: b.striker,
        non_striker: b.non_striker,
        bowler: b.bowler,
        runs_bat: 0,
        extras_type: "none",
        extras_runs: 0,
        wicket: false,
        commentary: b.commentary || "",
        ...result,
      });
      await load();
      if (isLast && !b.wicket) {
        // Work out strike again from the fixed ball
        const now = currentInnings();
        const fixed = { ...b, runs_bat: 0, extras_type: "none", extras_runs: 0, ...result };
        let striker = b.striker;
        let nonStriker = b.non_striker;
        if (runsRotate(ranRuns(fixed))) [striker, nonStriker] = [nonStriker, striker];
        const legal = legalBalls(now);
        const isLegal = !["wide", "no_ball"].includes(fixed.extras_type);
        const overEnded = isLegal && legal > 0 && legal % 6 === 0;
        if (overEnded) [striker, nonStriker] = [nonStriker, striker];
        const local = loadLocal(now.inning_number);
        saveLocal(now.inning_number, { ...local, striker, nonStriker, bowler: overEnded ? local.bowler || b.bowler : b.bowler, setup: true });
        render();
        toast(`Ball fixed: ${ballText(fixed)} ✓`);
      } else {
        toast("Ball fixed ✓ If the batters are at the wrong ends, tap ⇄ Swap strike.");
      }
    } catch (e) {
      toast(e.message, "error");
    } finally {
      busy = false;
    }
  }

  // ---------- shorthand + voice ----------
  function tokenToBall(tok) {
    const t = tok.toLowerCase();
    if (/^[0-6]$/.test(t)) return { runs_bat: Number(t) };
    if (t === "." ) return { runs_bat: 0 };
    if (/^\d?wd$/.test(t)) return { extras_type: "wide", extras_runs: Number(t.replace("wd", "") || 1) };
    if (/^nb\d?$/.test(t)) return { extras_type: "no_ball", extras_runs: 1, runs_bat: Number(t.replace("nb", "") || 0) };
    if (/^\d?lb$/.test(t)) return { extras_type: "leg_bye", extras_runs: Number(t.replace("lb", "") || 1) };
    if (/^\d?b$/.test(t)) return { extras_type: "bye", extras_runs: Number(t.replace("b", "") || 1) };
    if (t === "w") return "wicket";
    return null;
  }

  async function playShorthand(text) {
    const tokens = String(text || "").trim().split(/[\s,]+/).filter(Boolean);
    for (const tok of tokens) {
      const ball = tokenToBall(tok);
      if (ball === "wicket") {
        askWicket();
        return; // wait for the wicket details
      }
      if (!ball) {
        toast(`Didn't understand "${tok}"`, "error");
        return;
      }
      record(ball);
    }
  }

  const VOICE = [
    [/\bundo\b/, "undo"],
    [/\bleg ?bye/, { extras_type: "leg_bye", extras_runs: 1 }],
    [/\bbye/, { extras_type: "bye", extras_runs: 1 }],
    [/\bwide/, { extras_type: "wide", extras_runs: 1 }],
    [/\bno ?ball/, { extras_type: "no_ball", extras_runs: 1 }],
    [/\bbowled\b/, "bowled"],
    [/\bcaught\b|\bcatch\b/, "caught"],
    [/\bl ?b ?w\b|\bleg before\b/, "lbw"],
    [/\brun ?out\b/, "run_out"],
    [/\bstumped\b/, "stumped"],
    [/\bout\b|\bwicket\b/, "caught"],
    [/\bsix\b|\bmaximum\b|\b6\b/, { runs_bat: 6 }],
    [/\bfour\b|\bboundary\b|\b4\b/, { runs_bat: 4 }],
    [/\bthree\b|\b3\b/, { runs_bat: 3 }],
    [/\btwo\b|\bdouble\b|\b2\b/, { runs_bat: 2 }],
    [/\bsingle\b|\bone\b|\b1\b/, { runs_bat: 1 }],
    [/\bdot\b|\bno run\b|\bzero\b|\b0\b/, { runs_bat: 0 }],
  ];

  function handleVoice(transcript) {
    const t = transcript.toLowerCase();
    for (const [pattern, action] of VOICE) {
      if (!pattern.test(t)) continue;
      toast(`🎙️ “${transcript}”`);
      if (action === "undo") return undo();
      if (typeof action === "string") return askWicket(action);
      return record(action);
    }
    toast(`Didn't catch that: “${transcript}”`, "error");
  }

  function toggleVoice() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      toast("Voice scoring needs Chrome or Edge.", "error");
      return;
    }
    if (recognition) {
      recognition.onend = null;
      recognition.stop();
      recognition = null;
      render();
      return;
    }
    recognition = new SR();
    recognition.lang = "en-IN";
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const result = event.results[event.results.length - 1];
      if (result && result.isFinal) handleVoice(result[0].transcript.trim());
    };
    recognition.onerror = (event) => toast(`Voice: ${event.error}`, "error");
    recognition.onend = () => {
      if (recognition) recognition.start(); // keep listening until switched off
    };
    recognition.start();
    render();
  }

  // ---------- events ----------
  app.addEventListener("click", async (event) => {
    const runKey = event.target.closest("[data-run]");
    if (runKey) return record({ runs_bat: Number(runKey.dataset.run) });
    const extraKey = event.target.closest("[data-extra]");
    if (extraKey) return askExtra(extraKey.dataset.extra);
    const fixKey = event.target.closest("[data-fix]");
    if (fixKey) return askFix(fixKey.dataset.fix);
    const act = event.target.closest("[data-act]")?.dataset.act;
    if (!act) return;
    if (act === "wicket") return askWicket();
    if (act === "undo") return undo();
    if (act === "voice") {
      if (aiRecognition) toggleAiMic();
      return toggleVoice();
    }
    if (act === "ai") {
      aiMode = !aiMode;
      if (!aiMode && aiRecognition) toggleAiMic();
      render();
      if (aiMode && hasAi()) {
        document.getElementById("qsAiInput")?.focus();
        if (!aiRecognition) toggleAiMic();
      }
      return;
    }
    if (act === "ai-mic") return toggleAiMic();
    if (act === "bowler") return askBowler("", false);
    if (act === "swap") {
      const inn = currentInnings();
      const p = players(inn);
      saveLocal(inn.inning_number, { ...loadLocal(inn.inning_number), striker: p.nonStriker, nonStriker: p.striker, bowler: p.bowler, setup: true });
      return render();
    }
    if (act === "second") {
      const list = innings();
      if (list[1]) renderSetup(list[1]);
    }
  });

  app.addEventListener("submit", (event) => {
    if (event.target.id === "qsAiForm") {
      event.preventDefault();
      const input = document.getElementById("qsAiInput");
      const text = input.value;
      input.value = "";
      aiScore(text);
      return;
    }
    if (event.target.id !== "qsShort") return;
    event.preventDefault();
    const input = document.getElementById("qsShortInput");
    const text = input.value;
    input.value = "";
    playShorthand(text);
  });

  // ---------- start ----------
  (async () => {
    try {
      if (!matchId && guest) {
        renderGuestStart();
      } else if (guest && !guestCode()) {
        app.innerHTML = `<section class="qs-card"><h1>Enter the match code</h1><p class="qs-muted">This guest match needs its 6-character code to score. You can still follow it live.</p>
          <form id="qsCodeForm" class="qs-short"><input id="qsCodeInput" maxlength="6" placeholder="e.g. K7P2QX" /><button class="qs-btn primary" type="submit">Continue</button></form>
          <p class="qs-foot"><a href="/live/${enc(matchId)}">Follow live</a></p></section>`;
        document.getElementById("qsCodeForm").addEventListener("submit", (event) => {
          event.preventDefault();
          location.href = `/score?match=${enc(matchId)}&code=${enc(document.getElementById("qsCodeInput").value.trim().toUpperCase())}`;
        });
      } else if (!matchId) {
        renderFixtureList(await api("GET", "/api/quick-score/fixtures"));
      } else {
        await load();
      }
    } catch (e) {
      app.innerHTML = `<section class="qs-card"><h1>Couldn't load</h1><p class="qs-muted">${esc(e.message)}</p><a class="qs-btn primary" href="/score">Back</a></section>`;
    }
  })();
})();
