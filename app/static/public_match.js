/*
 * Public live scorecard (/live/{id}, /public/match/{id}) - README "Public scorecard (Oct 29 2026)" and
 * "Live page like a cricket score app (Oct 30 2026)".
 *
 * Laid out like the big cricket score apps (Amit, Oct 30): a compact white header with one row per team
 * (badge, name, score, overs, target), the situation line ("India need 104 runs in 28 balls"), then three tabs:
 *  - Live: CRR / RRR / last 5 overs, the recent balls by over, the two batters (R B 4s 6s SR) and the
 *    current + previous bowler (O M R W ECON), partnership, last wicket and the latest commentary;
 *  - Scorecard: every innings (tap the bar to open / close) with one row per batter and per bowler,
 *    extras, total, yet to bat and fall of wickets;
 *  - Commentary: every ball, latest first, with an end-of-over line.
 * Everything is worked out from the ball-by-ball scorebook (GET /api/public/match/{id}), so the page always
 * matches the Score page. Live matches refresh every 10 seconds (only redrawn when something changed) and new
 * fours / sixes / wickets / fifties / hundreds and the win are celebrated (celebrate.js).
 */
(() => {
  const root = document.getElementById("pmApp");
  const esc = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const TABS = ["live", "scorecard", "commentary"];
  let activeTab = TABS.includes(window.location.hash.slice(1)) ? window.location.hash.slice(1) : "live";
  let openInnings = null; // Set of innings numbers opened on the Scorecard tab (null = just the latest)
  let lastData = null;
  let lastJson = "";
  let lastFinished = false;
  const POLL_MS = 10000;

  function matchIdFromPath() {
    const parts = window.location.pathname.split("/").filter(Boolean);
    return parts.length ? decodeURIComponent(parts[parts.length - 1]) : "";
  }

  // ---------- cricket maths from the balls ----------
  const isLegal = (b) => !["wide", "no_ball"].includes(b.extras_type);
  const overs = (legal) => `${Math.floor(legal / 6)}.${legal % 6}`;
  const oversShort = (legal) => (legal % 6 ? overs(legal) : String(legal / 6));
  const ballNo = (b) => `${Math.max(0, Number(b.over_number || 1) - 1)}.${b.ball_number || 1}`;
  const ballRuns = (b) => Number(b.runs_bat || 0) + Number(b.extras_runs || 0);
  const rate = (runs, legal) => (legal ? (runs / (legal / 6)).toFixed(2) : "0.00");
  const same = (a, b) => String(a || "").toLowerCase() === String(b || "").toLowerCase();

  function inningsFacts(inn) {
    const balls = Array.isArray(inn.balls) ? inn.balls : [];
    const sum = inn.summary || {};
    const extras = { wd: 0, nb: 0, b: 0, lb: 0 };
    const dismissal = {};
    const fallOfWickets = [];
    const overOf = new Map(); // ball -> over index (0-based), worked out from legal balls
    const overEnd = []; // [over index] -> { runs, wickets, overRuns } once the over is complete
    let runs = 0;
    let wickets = 0;
    let legal = 0;
    let overRuns = 0;
    let lastWicketBall = null;
    balls.forEach((b) => {
      overOf.set(b, Math.floor(legal / 6));
      const er = Number(b.extras_runs || 0);
      runs += ballRuns(b);
      overRuns += ballRuns(b);
      if (b.extras_type === "wide") extras.wd += er;
      if (b.extras_type === "no_ball") extras.nb += er;
      if (b.extras_type === "bye") extras.b += er;
      if (b.extras_type === "leg_bye") extras.lb += er;
      if (isLegal(b)) legal += 1;
      if (b.wicket) {
        wickets += 1;
        lastWicketBall = { ball: b, runs, wickets, legal };
      }
      if (b.wicket && b.wicket_player) {
        dismissal[b.wicket_player] = howOut(b);
        fallOfWickets.push(`${runs}-${fallOfWickets.length + 1} (${b.wicket_player}, ${overs(legal)})`);
      }
      if (isLegal(b) && legal % 6 === 0) {
        overEnd[legal / 6 - 1] = { runs, wickets, overRuns };
        overRuns = 0;
      }
    });
    return {
      balls,
      legal,
      runs: Number(sum.runs ?? runs),
      wickets: Number(sum.wickets ?? wickets),
      extras,
      extrasTotal: extras.wd + extras.nb + extras.b + extras.lb,
      dismissal,
      fallOfWickets,
      overOf,
      overEnd,
      lastWicketBall,
      last: balls[balls.length - 1],
      batting: Array.isArray(sum.batting) ? sum.batting : [],
      bowling: Array.isArray(sum.bowling) ? sum.bowling : [],
      oversLimit: Number(inn.overs_limit || 20),
      started: balls.length > 0,
      done: String(inn.status || "").toLowerCase() === "completed",
    };
  }

  function howOut(b) {
    const bowler = b.bowler || "";
    const f = b.fielder || "";
    switch (b.wicket_type) {
      case "bowled":
        return `b ${bowler}`;
      case "caught":
        return f && f === bowler ? `c & b ${bowler}` : `c ${f || "?"} b ${bowler}`;
      case "lbw":
        return `lbw b ${bowler}`;
      case "run_out":
        return `run out${f ? ` (${f})` : ""}`;
      case "stumped":
        return `st ${f || "?"} b ${bowler}`;
      case "hit_wicket":
        return `hit wicket b ${bowler}`;
      case "retired_hurt":
        return "retired hurt";
      default:
        return String(b.wicket_type || "out").replace("_", " ");
    }
  }

  // Who is in now: the last ball's batters, after strike changes (runs, end of over) and wickets.
  function currentPair(facts) {
    const b = facts.last;
    if (!b) return { striker: "", nonStriker: "", bowler: "", lastBowler: "" };
    let striker = b.striker || "";
    let nonStriker = b.non_striker || "";
    const ran = Number(b.runs_bat || 0) + (["bye", "leg_bye"].includes(b.extras_type) ? Number(b.extras_runs || 0) : 0) + (b.extras_type === "wide" ? Math.max(0, Number(b.extras_runs || 1) - 1) : 0);
    if (ran % 2 === 1) [striker, nonStriker] = [nonStriker, striker];
    const overDone = isLegal(b) && facts.legal > 0 && facts.legal % 6 === 0;
    if (overDone) [striker, nonStriker] = [nonStriker, striker];
    if (b.wicket && b.wicket_player) {
      if (striker === b.wicket_player) striker = "";
      if (nonStriker === b.wicket_player) nonStriker = "";
    }
    return { striker, nonStriker, bowler: overDone ? "" : b.bowler || "", lastBowler: b.bowler || "" };
  }

  function ballLabel(b) {
    if (b.wicket) return "W";
    const er = Number(b.extras_runs || 0);
    const rb = Number(b.runs_bat || 0);
    if (b.extras_type === "wide") return er > 1 ? `${er}wd` : "wd";
    if (b.extras_type === "no_ball") return rb ? `nb+${rb}` : "nb";
    if (b.extras_type === "bye") return `${er}b`;
    if (b.extras_type === "leg_bye") return `${er}lb`;
    return String(rb);
  }

  function ballClass(b) {
    if (b.wicket) return "w";
    const plain = !b.extras_type || b.extras_type === "none";
    if (plain && Number(b.runs_bat) === 6) return "six";
    if (plain && Number(b.runs_bat) === 4) return "four";
    if (!plain) return "x";
    return Number(b.runs_bat) ? "run" : "dot";
  }

  function commentaryLine(b) {
    const who = `${b.bowler || "Bowler"} to ${b.striker || "batter"}`;
    const rb = Number(b.runs_bat || 0);
    const er = Number(b.extras_runs || 0);
    let what;
    if (b.wicket) what = `<b class="pm-w">OUT!</b> ${esc(b.wicket_player)} ${esc(howOut(b))}${rb ? `, ${rb} run${rb === 1 ? "" : "s"} completed` : ""}`;
    else if (b.extras_type === "wide") what = `wide${er > 1 ? `, ${er} runs` : ""}`;
    else if (b.extras_type === "no_ball") what = `no ball${rb === 4 ? ", <b>FOUR</b> off it" : rb === 6 ? ", <b>SIX</b> off it" : rb ? `, ${rb} off the bat` : ""}`;
    else if (b.extras_type === "bye") what = `${er} bye${er === 1 ? "" : "s"}`;
    else if (b.extras_type === "leg_bye") what = `${er} leg bye${er === 1 ? "" : "s"}`;
    else if (rb === 6) what = '<b class="pm-6">SIX!</b>';
    else if (rb === 4) what = '<b class="pm-4">FOUR!</b>';
    else if (rb === 0) what = "no run";
    else what = `${rb} run${rb === 1 ? "" : "s"}`;
    return `${esc(who)}, ${what}`;
  }

  // ---------- captain / vice-captain / keeper tags (README "Captain, vice-captain and keeper") ----------
  const ROLE_TAGS = { captain: "C", vice_captain: "VC", keeper: "WK" };
  const ROLE_NAMES = { C: "Captain", VC: "Vice-captain", WK: "Wicket keeper" };
  function sideOfTeam(match, team) {
    return same(team, match.club_name) ? "club" : "opponent";
  }
  function tagHtml(match, side, name) {
    const roles = ((match.lineups || {}).roles || {})[side] || {};
    const tags = Object.keys(ROLE_TAGS).filter((role) => roles[role] && roles[role] === name).map((role) => ROLE_TAGS[role]);
    return tags.length ? ` <em class="pm-tag" title="${tags.map((t) => ROLE_NAMES[t]).join(", ")}">${tags.join(" ")}</em>` : "";
  }

  // ---------- team badges: "New Zealand" -> NZ, "India" -> IND, "Heartlake Cricket Club" -> HCC ----------
  function shortCode(name) {
    const words = String(name || "").replace(/[^A-Za-z0-9 ]/g, " ").split(/\s+/).filter(Boolean);
    if (!words.length) return "?";
    if (words.length === 1) return words[0].length <= 4 && words[0] === words[0].toUpperCase() ? words[0] : words[0].slice(0, 3).toUpperCase();
    return words.map((w) => w[0]).join("").slice(0, 3).toUpperCase();
  }
  function badgeHue(name) {
    let h = 0;
    for (const ch of String(name || "")) h = (h * 31 + ch.charCodeAt(0)) % 360;
    return h;
  }

  // ---------- working out the match state ----------
  function matchState(match) {
    const innings = (Array.isArray(match.scorebook?.innings) ? match.scorebook.innings : []).slice().sort((a, b) => a.inning_number - b.inning_number);
    const played = innings.filter((i) => (i.balls || []).length);
    const live = played.filter((i) => String(i.status || "").toLowerCase() === "live").pop() || null;
    const current = live || played[played.length - 1] || null;
    const done = String(match.status || "").toLowerCase() === "completed" || Boolean(match.result && !/^tbd$/i.test(String(match.result)));
    const first = innings.find((i) => i.inning_number === 1);
    const firstFacts = first && (first.balls || []).length ? inningsFacts(first) : null;
    const facts = current ? inningsFacts(current) : null;
    const isChase = Boolean(current && current.inning_number === 2 && firstFacts);
    const target = isChase ? firstFacts.runs + 1 : null;
    const isLive = !done && Boolean(live) && !(facts && facts.done);
    const inBreak = !done && Boolean(current) && !isLive;
    // Team order: the side that batted first on top
    const firstBat = first?.batting_team || "";
    const teams = firstBat
      ? [firstBat, same(firstBat, match.club_name) ? match.opponent : match.club_name]
      : [match.club_name || "Team 1", match.opponent || "Team 2"];
    return { innings, played, live, current, done, facts, firstFacts, isChase, target, isLive, inBreak, teams };
  }

  function teamScore(state, team) {
    const inn = state.played.find((i) => same(i.batting_team, team));
    if (!inn) return null;
    const f = inn === state.current ? state.facts : inningsFacts(inn);
    return { inn, f };
  }

  function statusLine(match, state) {
    const { done, current, facts, target, isLive, inBreak } = state;
    if (done) return { cls: "done", text: match.result || "Match finished" };
    if (!current) {
      const when = [match.scheduled_time, match.date_label].filter(Boolean).join(", ");
      return { cls: "wait", text: when ? `Match starts ${when}. This page updates by itself.` : "Scoring hasn't started yet. This page updates by itself." };
    }
    const otherTeam = state.teams.find((t) => !same(t, current.batting_team)) || "";
    if (inBreak && current.inning_number === 1) return { cls: "break", text: `Innings break · ${otherTeam} need ${facts.runs + 1} runs to win` };
    if (target) {
      const need = Math.max(0, target - facts.runs);
      const left = facts.oversLimit * 6 - facts.legal;
      if (need <= 0) return { cls: "live", text: `${current.batting_team} have reached the target` };
      return { cls: "live", text: `${current.batting_team} need ${need} run${need === 1 ? "" : "s"} in ${left} ball${left === 1 ? "" : "s"}` };
    }
    if (isLive) return { cls: "live", text: `${current.batting_team} batting · ${otherTeam} yet to bat` };
    return { cls: "break", text: "Waiting for the next innings" };
  }

  // ---------- header (always on top), laid out like Cricbuzz (Dhruvika, Oct 30) ----------
  function renderHeader(match, state) {
    const { done, isLive, inBreak, current } = state;
    const pill = done
      ? '<span class="pm-state done">RESULT</span>'
      : isLive
      ? '<span class="pm-state live"><i></i>LIVE</span>'
      : inBreak
      ? '<span class="pm-state break"><i></i>INNINGS BREAK</span>'
      : '<span class="pm-state">UPCOMING</span>';
    const rows = state.teams
      .map((team) => {
        const s = teamScore(state, team);
        const batting = (current && same(current.batting_team, team) && !done) || (done && String(match.result || "").toLowerCase().startsWith(String(team || "").toLowerCase()));
        let score = "";
        if (s) {
          const live = s.inn === current && !s.f.done && !done;
          const tgt = s.inn.inning_number === 2 && state.target && !done ? `, T:${state.target}` : "";
          const ov = live ? `(${overs(s.f.legal)}/${s.f.oversLimit} ov${tgt}) ` : done || s.f.legal < s.f.oversLimit * 6 ? `(${oversShort(s.f.legal)} ov) ` : "";
          score = `<span class="pm-tscore">${ov ? `<small>${ov}</small>` : ""}<b>${s.f.runs}/${s.f.wickets}</b></span>`;
        } else if (current) {
          score = '<span class="pm-tscore"><small>Yet to bat</small></span>';
        }
        return `<div class="pm-trow${batting ? " bat" : ""}">
          <span class="pm-badge pm-flag" style="--h:${badgeHue(team)}" aria-hidden="true"></span>
          <span class="pm-tname" title="${esc(team)}">${esc(shortCode(team))}</span>${score}</div>`;
      })
      .join("");
    const status = statusLine(match, state);
    // CRR / RRR / last 5 overs right under the situation, like Cricbuzz
    let rates = "";
    if (current && !done && state.facts) {
      const f = state.facts;
      const bits = [`CRR: ${rate(f.runs, f.legal)}`];
      if (state.target && !f.done) {
        const need = Math.max(0, state.target - f.runs);
        const left = f.oversLimit * 6 - f.legal;
        if (need > 0 && left > 0) bits.push(`RRR: ${((need / left) * 6).toFixed(2)}`);
      }
      const last5 = lastOversRate(f);
      rates = `<p class="pm-rates">${bits.join("&nbsp; ")}${last5 ? ` &bull; Last 5 ov (RR): ${last5}` : ""}</p>`;
    }
    const info = [
      `${match.club_name || "Team 1"} vs ${match.opponent || "Team 2"}`,
      match.match_type,
      match.overs ? `${match.overs} overs` : "",
      match.venue && !/^venue tbd$/i.test(match.venue) ? match.venue : "",
      [match.date_label || match.date, match.scheduled_time].filter(Boolean).join(" "),
    ]
      .filter(Boolean)
      .map(esc)
      .join(", ");
    return `<section class="pm-head">
      <div class="pm-head-top">${pill}<span class="pm-updated" id="pmUpdated"></span></div>
      <div class="pm-teams">${rows}</div>
      <p class="pm-status ${status.cls}">${esc(status.text)}${status.cls === "live" || status.cls === "break" ? "." : ""}</p>
      ${rates}
      <p class="pm-info">${info}</p>
    </section>`;
  }

  function renderTabs() {
    const label = { live: "Live", scorecard: "Scorecard", commentary: "Commentary" };
    return `<nav class="pm-tabbar" role="tablist">${TABS.map(
      (t) => `<button type="button" role="tab" data-tab="${t}" aria-selected="${t === activeTab}" class="${t === activeTab ? "on" : ""}">${label[t]}</button>`
    ).join("")}</nav>`;
  }

  // ---------- Live tab ----------
  const ordinal = (n) => `${n}${[, "st", "nd", "rd"][((n % 100) - 20) % 10] || [, "st", "nd", "rd"][n % 100] || "th"}`;

  // The ball strip: newest on the LEFT; each finished over has a "15th · 3 RUNS" marker (like Cricbuzz).
  function overStrip(f, maxOvers = 6) {
    const groups = [];
    f.balls.forEach((b) => {
      const over = f.overOf.get(b);
      if (!groups.length || groups[groups.length - 1].over !== over) groups.push({ over, balls: [] });
      groups[groups.length - 1].balls.push(b);
    });
    return groups
      .slice(-maxOvers)
      .reverse()
      .map((g) => {
        const total = g.balls.reduce((n, b) => n + ballRuns(b), 0);
        const head = f.overEnd[g.over] ? `<span class="pm-ovmark"><small>${ordinal(g.over + 1)}</small><b>${total}<br />RUN${total === 1 ? "" : "S"}</b></span>` : "";
        const chips = g.balls
          .slice()
          .reverse()
          .map((b) => `<b class="pm-chip ${ballClass(b)}">${ballClass(b) === "dot" ? "&bull;" : esc(ballLabel(b))}</b>`)
          .join("");
        return `${head ? `<i class="pm-ovsep" aria-hidden="true"></i>${head}` : ""}<span class="pm-ovgrp">${chips}</span>`;
      })
      .join("");
  }

  function lastOversRate(f, n = 5) {
    if (f.legal < n * 6) return "";
    let legal = 0;
    let runs = 0;
    let wkts = 0;
    for (let i = f.balls.length - 1; i >= 0 && legal < n * 6; i -= 1) {
      const b = f.balls[i];
      runs += ballRuns(b);
      if (b.wicket) wkts += 1;
      if (isLegal(b)) legal += 1;
    }
    return `${runs}/${wkts} (${rate(runs, legal)})`;
  }

  function partnership(f) {
    const from = f.lastWicketBall ? f.balls.indexOf(f.lastWicketBall.ball) + 1 : 0;
    const balls = f.balls.slice(from);
    return { runs: balls.reduce((n, b) => n + ballRuns(b), 0), balls: balls.filter(isLegal).length };
  }

  // Win probability: our own estimate from runs, balls and wickets left (there's no betting data for club games).
  function winProbability(match, state) {
    const { current, facts: f, done } = state;
    if (done || !current || !f) return null;
    const bat = current.batting_team;
    const bowl = state.teams.find((t) => !same(t, bat)) || "";
    const logistic = (x) => 1 / (1 + Math.exp(-x));
    let pBat;
    const ballsTotal = f.oversLimit * 6;
    const left = Math.max(0, ballsTotal - f.legal);
    const wktsLeft = Math.max(0, 10 - f.wickets);
    if (state.target && current.inning_number === 2) {
      const need = state.target - f.runs;
      if (need <= 0) pBat = 1;
      else if (!left || !wktsLeft) pBat = 0;
      else {
        // runs we expect from here: the scoring rate so far (at least a run a ball / 1.0) cut down for wickets lost
        const pace = Math.max(6, Math.min(12, f.legal >= 12 ? (f.runs / f.legal) * 6 : 7.5));
        const expected = (left / 6) * pace * Math.min(1, Math.sqrt(wktsLeft / 10) * 1.05);
        const spread = Math.max(4, Math.sqrt(left) * 2.2);
        pBat = logistic((expected - need) / spread);
      }
    } else {
      // first innings: compare where the score is heading with a fair score for these overs (7.5 an over)
      const pace = f.legal >= 6 ? (f.runs / f.legal) * 6 : 7.5;
      const projected = f.runs + (left / 6) * pace * Math.sqrt(Math.max(0.1, wktsLeft / 10));
      const par = 7.5 * f.oversLimit;
      pBat = logistic((projected - par) / Math.max(6, par * 0.12));
    }
    pBat = Math.min(0.9999, Math.max(0.0001, pBat));
    const pct = (p) => (p * 100).toFixed(2);
    return { bat: shortCode(bat), bowl: shortCode(bowl), pBat: pct(pBat), pBowl: pct(1 - pBat), width: (pBat * 100).toFixed(1) };
  }

  function renderLive(match, state) {
    const { current, facts: f, isLive } = state;
    if (!current) return '<p class="pm-empty">No balls bowled yet. The score shows here as soon as scoring starts.</p>';
    const parts = [];
    const showNow = isLive && !f.done;
    if (f.balls.length) parts.push(`<div class="pm-strip" data-recent>${overStrip(f)}</div>`);
    const wp = winProbability(match, state);
    if (wp) {
      parts.push(`<div class="pm-wp">
        <p class="pm-wp-row"><span class="pm-wp-title"><span aria-hidden="true">📈</span> Win Probability <span class="pm-wp-i" title="Our estimate from the runs, balls and wickets left. It changes after every ball.">ⓘ</span></span>
          <span class="pm-wp-teams"><span><i class="a"></i>${esc(wp.bat)} ${wp.pBat}%</span><span><i class="b"></i>${esc(wp.bowl)} ${wp.pBowl}%</span></span></p>
        <div class="pm-wp-bar"><span style="width:${wp.width}%"></span></div>
      </div>`);
    }
    if (showNow) {
      const pair = currentPair(f);
      const side = sideOfTeam(match, current.batting_team);
      const batRow = (name, star) => {
        if (!name) return "";
        const r = f.batting.find((b) => b.player_name === name) || {};
        const sr = r.balls ? ((Number(r.runs || 0) / Number(r.balls)) * 100).toFixed(2) : "0.00";
        return `<tr><th scope="row"><span class="pm-name">${esc(name)}${star ? "*" : ""}${tagHtml(match, side, name)}</span></th><td class="pm-r">${r.runs || 0}</td><td>${r.balls || 0}</td><td>${r.fours || 0}</td><td>${r.sixes || 0}</td><td>${sr}</td></tr>`;
      };
      const names = [];
      for (let i = f.balls.length - 1; i >= 0 && names.length < 2; i -= 1) {
        const n = f.balls[i].bowler;
        if (n && !names.includes(n)) names.push(n);
      }
      const bowlSide = sideOfTeam(match, current.bowling_team);
      const bowlRows = names
        .map((name) => {
          const r = f.bowling.find((b) => b.player_name === name) || {};
          return `<tr><th scope="row"><span class="pm-name">${esc(name)}${tagHtml(match, bowlSide, name)}</span></th><td>${esc(r.overs || "0.0")}</td><td>${r.maidens || 0}</td><td>${r.runs_conceded || 0}</td><td class="pm-r">${r.wickets || 0}</td><td>${Number(r.economy || 0).toFixed(2)}</td></tr>`;
        })
        .join("");
      parts.push(`<div class="pm-table-wrap pm-bleed"><table class="pm-table pm-mini">
        <thead><tr><th scope="col">Batting</th><th scope="col">R</th><th scope="col">B</th><th scope="col">4s</th><th scope="col">6s</th><th scope="col">SR</th></tr></thead>
        <tbody>${batRow(pair.striker, true) + batRow(pair.nonStriker, false)}</tbody>
        <thead><tr><th scope="col">Bowling</th><th scope="col">O</th><th scope="col">M</th><th scope="col">R</th><th scope="col">W</th><th scope="col">ECON</th></tr></thead>
        <tbody>${bowlRows}</tbody></table></div>`);
      const p = partnership(f);
      const lines = [`<span>P'ship: ${p.runs} Run${p.runs === 1 ? "" : "s"}, ${p.balls} B (RR: ${rate(p.runs, p.balls)})</span>`];
      if (f.lastWicketBall && f.lastWicketBall.ball.wicket_player) {
        const w = f.lastWicketBall;
        const r = f.batting.find((b) => b.player_name === w.ball.wicket_player) || {};
        lines.push(`<span>Last Wkt: ${esc(w.ball.wicket_player)} ${r.runs || 0}(${r.balls || 0}) - ${w.runs}/${w.wickets} in ${overs(w.legal)} ov.</span>`);
      }
      parts.push(`<p class="pm-facts">${lines.join("")}</p>`);
    } else {
      parts.push(renderKeyPlayers(match, state));
    }
    const latest = f.balls.slice(-6).reverse();
    if (latest.length) {
      parts.push(`<div class="pm-subhead"><h2>Commentary</h2><button type="button" class="pm-link" data-tab="commentary">Full commentary ›</button></div>
        <ol class="pm-comm">${latest.map((b) => commentaryItem(b)).join("")}</ol>`);
    }
    return parts.join("");
  }

  function renderKeyPlayers(match, state) {
    // Innings break / result: the top two batters and bowlers of each innings.
    const blocks = state.played
      .map((inn) => {
        const f = inn === state.current ? state.facts : inningsFacts(inn);
        const bats = f.batting
          .filter((b) => Number(b.balls || 0) || Number(b.runs || 0))
          .slice()
          .sort((a, b) => Number(b.runs || 0) - Number(a.runs || 0) || Number(a.balls || 0) - Number(b.balls || 0))
          .slice(0, 2);
        const bowls = f.bowling
          .filter((b) => Number(b.legal_balls || 0) || Number(b.runs_conceded || 0))
          .slice()
          .sort((a, b) => Number(b.wickets || 0) - Number(a.wickets || 0) || Number(a.runs_conceded || 0) - Number(b.runs_conceded || 0))
          .slice(0, 2);
        return `<div class="pm-key">
          <p class="pm-key-head">${esc(inn.batting_team)} <b>${f.runs}/${f.wickets}</b> <small>(${oversShort(f.legal)} ov)</small></p>
          <div class="pm-key-grid">
            <ul>${bats.map((b) => `<li><span>${esc(b.player_name)}${f.dismissal[b.player_name] ? "" : "*"}</span><b>${b.runs || 0}</b><small>(${b.balls || 0})</small></li>`).join("")}</ul>
            <ul>${bowls.map((b) => `<li><span>${esc(b.player_name)}</span><b>${b.wickets || 0}-${b.runs_conceded || 0}</b><small>(${esc(b.overs || "0")})</small></li>`).join("")}</ul>
          </div></div>`;
      })
      .join("");
    return blocks ? `<div class="pm-subhead"><h2>Key players</h2><button type="button" class="pm-link" data-tab="scorecard">Full scorecard ›</button></div>${blocks}` : "";
  }

  function commentaryItem(b) {
    const note = b.commentary && !/^AI Scorer:/.test(b.commentary) ? `<p class="pm-extra-note">${esc(b.commentary)}</p>` : "";
    return `<li class="${ballClass(b)}"><div class="pm-cno"><small>${ballNo(b)}</small><span class="pm-ball ${ballClass(b)}">${esc(ballLabel(b))}</span></div><div><p>${commentaryLine(b)}</p>${note}</div></li>`;
  }

  // ---------- Scorecard tab ----------
  function renderScorecard(inn, match, lineups) {
    const f = inningsFacts(inn);
    if (!f.started) return `<p class="pm-empty">${esc(inn.batting_team || "This team")} hasn't batted yet.</p>`;
    const pair = currentPair(f);
    const batted = f.batting.filter((b) => b.status !== "not_batted" || b.balls || b.runs);
    const side = sideOfTeam(match, inn.batting_team);
    const batRows = batted
      .map((b) => {
        const sr = b.balls ? ((Number(b.runs || 0) / Number(b.balls)) * 100).toFixed(2) : "0.00";
        const out = f.dismissal[b.player_name];
        const inNow = b.player_name === pair.striker || b.player_name === pair.nonStriker;
        const how = out || (f.done || !inNow ? "not out" : b.player_name === pair.striker ? "batting *" : "batting");
        return `<tr class="${out ? "" : "pm-notout"}">
          <th scope="row"><span class="pm-name">${esc(b.player_name)}${tagHtml(match, side, b.player_name)}</span><small>${esc(how)}</small></th>
          <td class="pm-r">${b.runs || 0}</td><td>${b.balls || 0}</td><td>${b.fours || 0}</td><td>${b.sixes || 0}</td><td>${sr}</td></tr>`;
      })
      .join("");
    const battedNames = new Set(batted.map((b) => b.player_name));
    const yetToBat = (lineups || []).filter((n) => !battedNames.has(n));
    const e = f.extras;
    const bowlSide = sideOfTeam(match, inn.bowling_team);
    const bowlRows = f.bowling
      .filter((b) => Number(b.legal_balls || 0) || Number(b.runs_conceded || 0))
      .map(
        (b) => `<tr>
          <th scope="row"><span class="pm-name">${esc(b.player_name)}${tagHtml(match, bowlSide, b.player_name)}</span></th>
          <td>${esc(b.overs || "0.0")}</td><td>${b.maidens || 0}</td><td>${b.runs_conceded || 0}</td><td class="pm-r">${b.wickets || 0}</td><td>${Number(b.economy || 0).toFixed(2)}</td></tr>`
      )
      .join("");
    return `
      <div class="pm-table-wrap">
        <table class="pm-table">
          <thead><tr><th scope="col">Batter</th><th scope="col">R</th><th scope="col">B</th><th scope="col">4s</th><th scope="col">6s</th><th scope="col">SR</th></tr></thead>
          <tbody>${batRows}</tbody>
          <tfoot>
            <tr><th scope="row">Extras <small>(b ${e.b}, lb ${e.lb}, w ${e.wd}, nb ${e.nb})</small></th><td class="pm-r" colspan="5">${f.extrasTotal}</td></tr>
            <tr class="pm-total"><th scope="row">Total <small>(${f.wickets} wkts, ${oversShort(f.legal)} Ov, RR ${rate(f.runs, f.legal)})</small></th><td class="pm-r" colspan="5">${f.runs}</td></tr>
          </tfoot>
        </table>
      </div>
      ${yetToBat.length ? `<p class="pm-note"><b>Yet to bat:</b> ${yetToBat.map((n) => `${esc(n)}${tagHtml(match, side, n)}`).join(", ")}</p>` : ""}
      ${f.fallOfWickets.length ? `<p class="pm-note"><b>Fall of wickets:</b> ${f.fallOfWickets.map(esc).join(", ")}</p>` : ""}
      <div class="pm-table-wrap">
        <table class="pm-table">
          <thead><tr><th scope="col">Bowler</th><th scope="col">O</th><th scope="col">M</th><th scope="col">R</th><th scope="col">W</th><th scope="col">ECON</th></tr></thead>
          <tbody>${bowlRows || '<tr><td colspan="6" class="pm-empty">No overs bowled yet.</td></tr>'}</tbody>
        </table>
      </div>`;
  }

  function renderScorecardTab(match, state) {
    if (!state.played.length) return '<p class="pm-empty">No balls bowled yet.</p>';
    const latest = state.played[state.played.length - 1].inning_number;
    const open = openInnings || new Set([latest]);
    const lineupFor = (team) => (same(team, match.club_name) ? match.lineups?.club : match.lineups?.opponent) || [];
    return state.played
      .map((inn) => {
        const f = inn === state.current ? state.facts : inningsFacts(inn);
        const isOpen = open.has(inn.inning_number);
        return `<section class="pm-inn${isOpen ? " open" : ""}">
          <button type="button" class="pm-innhead" data-inn="${inn.inning_number}" aria-expanded="${isOpen}">
            <span>${esc(inn.batting_team || `Innings ${inn.inning_number}`)} Innings</span>
            <b>${f.runs}-${f.wickets} <small>(${oversShort(f.legal)} Ov)</small></b><i aria-hidden="true">▾</i>
          </button>
          ${isOpen ? `<div class="pm-inn-body">${renderScorecard(inn, match, lineupFor(inn.batting_team))}</div>` : ""}
        </section>`;
      })
      .join("");
  }

  // ---------- Commentary tab ----------
  function renderCommentaryTab(match, state) {
    if (!state.played.length) return '<p class="pm-empty">No balls bowled yet.</p>';
    const notes = Array.isArray(match.commentary) ? match.commentary.slice().reverse().slice(0, 10) : [];
    const blocks = state.played
      .slice()
      .reverse()
      .map((inn) => {
        const f = inn === state.current ? state.facts : inningsFacts(inn);
        const items = [];
        for (let i = f.balls.length - 1; i >= 0; i -= 1) {
          const b = f.balls[i];
          const over = f.overOf.get(b);
          const next = f.balls[i + 1];
          // first (newest) ball of a finished over: put the end-of-over line above it
          if ((!next || f.overOf.get(next) !== over) && f.overEnd[over]) {
            const end = f.overEnd[over];
            items.push(`<li class="pm-overend"><b>End of over ${over + 1}</b><span>${end.overRuns} run${end.overRuns === 1 ? "" : "s"}</span><span>${esc(inn.batting_team)} ${end.runs}/${end.wickets}</span></li>`);
          }
          items.push(commentaryItem(b));
        }
        return `${state.played.length > 1 ? `<p class="pm-comm-inn">${esc(inn.batting_team)} innings</p>` : ""}<ol class="pm-comm">${items.join("")}</ol>`;
      })
      .join("");
    const scorer = notes.length
      ? `<div class="pm-subhead"><h2>From the scorer</h2></div><ul class="pm-notes">${notes.map((n) => `<li>${esc(n.text || "")}</li>`).join("")}</ul>`
      : "";
    return scorer + blocks;
  }

  // ---------- page ----------
  function render(match) {
    const state = matchState(match);
    const body = activeTab === "scorecard" ? renderScorecardTab(match, state) : activeTab === "commentary" ? renderCommentaryTab(match, state) : renderLive(match, state);
    const updated = document.getElementById("pmUpdated")?.textContent || "";
    root.innerHTML = `
      ${renderHeader(match, state)}
      ${renderTabs()}
      <section class="pm-body" role="tabpanel">${body}</section>
      <p class="pm-foot">Read-only scorecard.${state.isLive ? " Updates by itself every 10 seconds." : ""}</p>`;
    const stamp = document.getElementById("pmUpdated");
    if (stamp) stamp.textContent = updated;
  }

  root?.addEventListener("click", (event) => {
    if (!lastData) return;
    const tab = event.target.closest("[data-tab]");
    if (tab) {
      activeTab = tab.dataset.tab;
      try {
        history.replaceState(null, "", activeTab === "live" ? window.location.pathname : `#${activeTab}`);
      } catch (e) {
        /* ignore */
      }
      render(lastData);
      if (tab.classList.contains("pm-link")) root.querySelector(".pm-tabbar")?.scrollIntoView({ block: "start", behavior: "smooth" });
      return;
    }
    const inn = event.target.closest("[data-inn]");
    if (inn) {
      const state = matchState(lastData);
      const latest = state.played.length ? state.played[state.played.length - 1].inning_number : 1;
      if (!openInnings) openInnings = new Set([latest]);
      const n = Number(inn.dataset.inn);
      if (openInnings.has(n)) openInnings.delete(n);
      else openInnings.add(n);
      render(lastData);
    }
  });

  // ---------- celebrations for new balls (README "Easier live scoring") ----------
  const seenBalls = new Set();
  const seenRuns = {};
  let firstLoad = true;
  let refreshTimer = null;

  function celebrateNew(innings) {
    const fresh = [];
    innings.forEach((inning) => {
      (Array.isArray(inning.balls) ? inning.balls : []).forEach((ball) => {
        if (ball.id && !seenBalls.has(ball.id)) fresh.push({ ball, inning });
      });
    });
    const runsNow = {};
    innings.forEach((inning) => {
      (inning.summary?.batting || []).forEach((row) => {
        runsNow[`${inning.inning_number}:${row.player_name}`] = { runs: Number(row.runs || 0), balls: Number(row.balls || 0) };
      });
    });
    if (!firstLoad && fresh.length && window.ccCelebrateBall) {
      const score = ({ ball, inning }) => {
        const key = `${inning.inning_number}:${ball.striker}`;
        const before = seenRuns[key]?.runs || 0;
        const after = runsNow[key]?.runs || 0;
        if (ball.wicket) return 5;
        if (before < 100 && after >= 100) return 4;
        if (before < 50 && after >= 50) return 3;
        if (Number(ball.runs_bat) === 6 && !["bye", "leg_bye"].includes(ball.extras_type)) return 2;
        if (Number(ball.runs_bat) === 4 && !["bye", "leg_bye"].includes(ball.extras_type)) return 1;
        return 0;
      };
      const best = fresh.slice().sort((a, b) => score(b) - score(a))[0];
      if (score(best) > 0) {
        const key = `${best.inning.inning_number}:${best.ball.striker}`;
        const now = runsNow[key] || { runs: 0, balls: 0 };
        window.ccCelebrateBall(best.ball, seenRuns[key]?.runs || 0, now.runs, now.balls);
      }
    }
    fresh.forEach(({ ball }) => seenBalls.add(ball.id));
    Object.assign(seenRuns, runsNow);
    firstLoad = false;
  }

  async function loadMatch() {
    const matchId = matchIdFromPath();
    if (!root) return;
    if (!matchId) {
      root.innerHTML = '<p class="pm-empty">Match not found.</p>';
      return;
    }
    try {
      const response = await fetch(`/api/public/match/${encodeURIComponent(matchId)}`, { headers: { Accept: "application/json" }, cache: "no-store" });
      if (!response.ok) throw new Error(response.status === 404 ? "Match not found." : "The scorecard couldn't be loaded.");
      const text = await response.text();
      const data = JSON.parse(text);
      const match = data.match || {};
      const innings = Array.isArray(match.scorebook?.innings) ? match.scorebook.innings : [];
      document.title = `${match.club_name || "Team 1"} vs ${match.opponent || "Team 2"} · Live scorecard`;
      const resultNow = String(match.result || "TBD");
      const finishedNow = String(match.status || "").toLowerCase() === "completed" || !/^tbd$/i.test(resultNow);
      const justWon = lastData && !lastFinished && finishedNow;
      lastFinished = finishedNow;
      lastData = match;
      // Only redraw when the match changed, so the page doesn't jump while people read it.
      const json = JSON.stringify(match);
      if (json !== lastJson) {
        lastJson = json;
        render(match);
      }
      if (justWon && window.ccCelebrateWin) setTimeout(() => window.ccCelebrateWin(resultNow), 900);
      celebrateNew(innings);
      const updated = document.getElementById("pmUpdated");
      if (updated) updated.textContent = `Updated ${new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}`;
      const isLive = String(match.status || "").toLowerCase() === "live" || innings.some((inning) => String(inning.status || "").toLowerCase() === "live");
      clearTimeout(refreshTimer);
      refreshTimer = isLive ? setTimeout(() => !document.hidden && loadMatch(), POLL_MS) : null;
    } catch (error) {
      console.error("[Public Match]", error);
      if (!lastData) root.innerHTML = `<p class="pm-empty">${esc(error.message)}</p>`;
      clearTimeout(refreshTimer);
      refreshTimer = setTimeout(() => !document.hidden && loadMatch(), 30000);
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && refreshTimer) loadMatch();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadMatch);
  } else {
    loadMatch();
  }
})();
