/*
 * Celebrations for live scoring (README "Easier live scoring"): FOUR, SIX, WICKET, FIFTY and HUNDRED.
 * A big animated banner + a short phone buzz, on the Score page (/score) and on the public live page (/live/{id}).
 * It never blocks taps (pointer-events: none) and goes away by itself. Reduced-motion users get a plain banner.
 *
 *   window.ccCelebrate("six", "SIX!", "Ravi · 38 (21)")
 *   window.ccCelebrateBall(ball, runsBefore, runsAfter)   // picks the right celebration for a scored ball
 */
(() => {
  if (window.ccCelebrate) return;

  const STYLE = `
  .cc-cele{position:fixed;inset:0;z-index:2147483000;display:grid;place-items:center;pointer-events:none;}
  .cc-cele-card{display:grid;gap:4px;justify-items:center;padding:22px 34px;border-radius:26px;color:#fff;
    box-shadow:0 24px 60px rgba(15,23,42,.35);animation:cc-pop 1.9s cubic-bezier(.2,.9,.25,1.2) forwards;text-align:center;max-width:88vw;}
  .cc-cele-title{font:900 clamp(2.6rem,13vw,4.6rem)/1 Sora,Inter,system-ui,sans-serif;letter-spacing:.02em;text-shadow:0 4px 18px rgba(0,0,0,.25);}
  .cc-cele-sub{font:700 1.05rem/1.3 Inter,system-ui,sans-serif;opacity:.95;}
  .cc-cele.four .cc-cele-card{background:linear-gradient(135deg,#2563eb,#1d4ed8);}
  .cc-cele.six .cc-cele-card{background:linear-gradient(135deg,#8b5cf6,#6d28d9);}
  .cc-cele.wicket .cc-cele-card{background:linear-gradient(135deg,#f43f5e,#be123c);}
  .cc-cele.fifty .cc-cele-card,.cc-cele.hundred .cc-cele-card{background:linear-gradient(135deg,#f59e0b,#d97706);}
  .cc-bit{position:absolute;top:50%;left:50%;width:10px;height:14px;border-radius:3px;opacity:0;animation:cc-burst 1.3s ease-out forwards;}
  @keyframes cc-pop{0%{transform:scale(.3);opacity:0}14%{transform:scale(1.08);opacity:1}24%{transform:scale(1)}80%{transform:scale(1);opacity:1}100%{transform:scale(.92) translateY(-14px);opacity:0}}
  @keyframes cc-burst{0%{transform:translate(-50%,-50%) rotate(0);opacity:1}100%{transform:translate(calc(-50% + var(--x)),calc(-50% + var(--y))) rotate(var(--r));opacity:0}}
  @media (prefers-reduced-motion: reduce){.cc-cele-card{animation:cc-fade 1.9s linear forwards}.cc-bit{display:none}
    @keyframes cc-fade{0%,85%{opacity:1}100%{opacity:0}}}`;

  const COLORS = {
    four: ["#93c5fd", "#ffffff", "#2563eb"],
    six: ["#c4b5fd", "#fde68a", "#7c3aed"],
    wicket: ["#fecdd3", "#ffffff", "#e11d48"],
    fifty: ["#fde68a", "#ffffff", "#f59e0b", "#34d399"],
    hundred: ["#fde68a", "#ffffff", "#f59e0b", "#34d399", "#60a5fa"],
  };
  const BUZZ = { four: [60], six: [60, 50, 90], wicket: [180], fifty: [70, 50, 70, 50, 160], hundred: [90, 60, 90, 60, 260] };

  let current = null;
  function addStyle() {
    if (document.getElementById("ccCeleStyle")) return;
    const style = document.createElement("style");
    style.id = "ccCeleStyle";
    style.textContent = STYLE;
    document.head.appendChild(style);
  }

  function celebrate(kind, title, sub = "") {
    if (!COLORS[kind] || !document.body) return;
    addStyle();
    if (current) current.remove();
    const wrap = document.createElement("div");
    wrap.className = `cc-cele ${kind}`;
    wrap.setAttribute("role", "status");
    wrap.setAttribute("aria-live", "polite");
    const card = document.createElement("div");
    card.className = "cc-cele-card";
    const t = document.createElement("div");
    t.className = "cc-cele-title";
    t.textContent = title;
    card.appendChild(t);
    if (sub) {
      const s = document.createElement("div");
      s.className = "cc-cele-sub";
      s.textContent = sub;
      card.appendChild(s);
    }
    wrap.appendChild(card);
    const bits = kind === "four" ? 18 : 34;
    for (let i = 0; i < bits; i += 1) {
      const bit = document.createElement("span");
      bit.className = "cc-bit";
      const angle = (Math.PI * 2 * i) / bits + Math.random() * 0.4;
      const dist = 120 + Math.random() * 160;
      bit.style.setProperty("--x", `${Math.round(Math.cos(angle) * dist)}px`);
      bit.style.setProperty("--y", `${Math.round(Math.sin(angle) * dist)}px`);
      bit.style.setProperty("--r", `${Math.round(Math.random() * 540 - 270)}deg`);
      bit.style.background = COLORS[kind][i % COLORS[kind].length];
      bit.style.animationDelay = `${Math.random() * 0.12}s`;
      wrap.appendChild(bit);
    }
    document.body.appendChild(wrap);
    current = wrap;
    try {
      if (navigator.vibrate) navigator.vibrate(BUZZ[kind]);
    } catch (e) {
      /* some browsers block vibration */
    }
    setTimeout(() => {
      wrap.remove();
      if (current === wrap) current = null;
    }, 2000);
  }

  const HOW = { bowled: "bowled", caught: "caught", lbw: "LBW", run_out: "run out", stumped: "stumped", hit_wicket: "hit wicket" };

  /** Picks the celebration for one ball. runsBefore / runsAfter are the striker's runs either side of it. */
  function celebrateBall(ball, runsBefore = 0, runsAfter = 0, ballsAfter = null) {
    if (!ball) return false;
    if (ball.wicket) {
      const how = HOW[ball.wicket_type] || String(ball.wicket_type || "out").replace("_", " ");
      const by = ball.fielder ? ` · ${ball.fielder}` : "";
      celebrate("wicket", "WICKET!", `${ball.wicket_player || ball.striker || ""} ${how}${by}`.trim());
      return true;
    }
    const who = ball.striker || "";
    const card = ballsAfter != null ? ` · ${runsAfter} (${ballsAfter})` : ` · ${runsAfter}`;
    if (runsBefore < 100 && runsAfter >= 100) {
      celebrate("hundred", "HUNDRED!", `${who}${card}`);
      return true;
    }
    if (runsBefore < 50 && runsAfter >= 50) {
      celebrate("fifty", "FIFTY!", `${who}${card}`);
      return true;
    }
    const bat = Number(ball.runs_bat || 0);
    const bySelf = !["bye", "leg_bye"].includes(ball.extras_type);
    if (bySelf && bat === 6) {
      celebrate("six", "SIX!", who);
      return true;
    }
    if (bySelf && bat === 4) {
      celebrate("four", "FOUR!", who);
      return true;
    }
    return false;
  }

  window.ccCelebrate = celebrate;
  window.ccCelebrateBall = celebrateBall;
})();
