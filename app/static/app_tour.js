/*
 * App tour: shown once per account, on the first page after someone signs in for the first time.
 * Each step points at a menu item and says what to do there ("Step 1 · Mark your availability").
 * Captains / club admins / site admins (can_score) get the scoring and upload steps; players get
 * "follow live scores" and "see scorecards" instead.
 * Seen is saved on the account (GET /api/tour, POST /api/tour/seen) so it doesn't show again on
 * another phone or browser. It is only for first-time users (no menu item); support can still show it with ?tour=1.
 * Loaded on signed-in pages by multipage.js. README: "Simple menu and app tour".
 *
 * Oct 27 (README "App tour in the phone apps and for visitors"):
 *  - Inside the iPhone / Android app (user agent "CricketCanClubsApp") the website's bottom bar is hidden and the
 *    app has native tabs (Home, Live, Score, Scorecards, Upload), so those steps say "tap Score at the bottom"
 *    and the card sits just above the tabs instead of pointing at a hidden button.
 *  - First-time visitors who are not signed in get a short 3-step welcome on the Live page (once per browser;
 *    loaded by public_header.js). ?tour=1 shows it again.
 */
(() => {
  if (window.CCAppTour) return;
  const SEEN_KEY = "cricketClubAppTourSeen";
  const VISITOR_SEEN_KEY = "cricketClubAppVisitorTourSeen";
  const IN_APP = /CricketCanClubsApp/.test(navigator.userAgent || "");
  let visitorMode = false;
  const TOKEN_KEY = "cricketClubAppAuthToken";

  const nav = (href) => [
    `.shared-topbar-host .top-nav a[href="${href}"]`,
    `.mobile-tabbar a[href="${href}"]`,
    `#bottomAppNav a[href="${href}"]`,
  ];

  function buildSteps(info) {
    const hello = info.name ? `Welcome, ${info.name} 🎉` : "Welcome 🎉";
    const needsClub = onClubsPage() || info.has_club === false;
    const steps = [
      {
        title: hello,
        text: "Here's what to do first. Each step takes a few seconds.",
      },
      {
        skip: !needsClub,
        find: () => Array.from(document.querySelectorAll("button, a")).find((el) => /^\s*select club\s*$/i.test(el.textContent || "") && visible(el)),
        targets: [".shared-topbar-host .account-button", "#navMoreToggle"],
        task: true, title: "Pick your club",
        text: onClubsPage()
          ? "Tap “Select club” next to your club. Everything you see after that is for your club."
          : "Open your account menu → Clubs and tap “Select club” next to your club. Everything after that is for your club.",
      },
      {
        targets: nav("/matches"),
        task: true, title: "Mark your availability",
        text: "Open Matches and tap Available, Maybe or Not available for each upcoming game, so your captain knows who's in.",
      },
    ];
    if (info.can_score) {
      steps.push(
        {
          targets: nav("/score"),
          task: true, title: "Score a match",
          text: "On match day, tap Score, choose the game, set both line-ups, then tap 0–6, Wd, Nb or W after every ball.",
          appTab: true,
          appText: "On match day, tap <strong>Score</strong> in the tabs at the bottom, choose the game, set both line-ups, then tap 0–6, Wd, Nb or W after every ball.",
        },
        {
          targets: nav("/scorecards"),
          task: true, title: "Upload a paper scorecard",
          text: "Open Scorecards → 📷 Upload a scorecard. Take a photo, check what the app read, fix anything wrong, then tap Publish.",
          appTab: true,
          appText: "Tap <strong>Upload</strong> in the tabs at the bottom and take a photo of the paper scorecard. Check what the app read, fix anything wrong, then tap Publish.",
        }
      );
    } else {
      steps.push(
        {
          targets: nav("/dashboard"),
          task: true, title: "Follow the live score",
          text: "Home shows matches being played right now, recent results and what's coming up.",
          appTab: true,
          appText: "Tap <strong>Live</strong> in the tabs at the bottom to follow matches being played right now. <strong>Home</strong> shows your club's results and what's coming up.",
        },
        {
          targets: nav("/scorecards"),
          task: true, title: "See your scorecards",
          text: "Open Scorecards to see every published match and your own runs and wickets.",
          appTab: true,
          appText: "Tap <strong>Scorecards</strong> in the tabs at the bottom to see every published match and your own runs and wickets.",
        }
      );
    }
    steps.push(
      {
        targets: ["#assistantFloatingButton", "#museFab", ".muse-fab"],
        title: "Need help? Ask the AI Assistant",
        text: "Type what you want, like “mark me available Saturday” or “what's the score?”. It does it for you after you confirm.",
      },
      {
        targets: [".shared-topbar-host .account-button", "#navMoreToggle"],
        title: "You're all set ✅",
        text: "Your profile, clubs and plan are in this menu. Ask the AI Assistant if you get stuck.",
      }
    );
    // Drop steps that don't apply, then number the to-do steps: "Step 1 · …", "Step 2 · …".
    let number = 0;
    return steps
      .filter((step) => !step.skip)
      .map((step) => (step.task ? { ...step, title: `Step ${(number += 1)} · ${step.title}` } : step));
  }

  // Signed-out first visit (Live page): what the app is, sign in / register, quick match without an account.
  function visitorSteps() {
    const quick = () =>
      Array.from(document.querySelectorAll("a")).find((el) => /score a quick match/i.test(el.textContent || "") && visible(el));
    return [
      {
        title: "Welcome to CricketCanClubs 🏏",
        text: "Live scores, results, fixtures and scorecards for community cricket clubs across Canada. Here's how to get started.",
      },
      {
        targets: ['[data-public-nav="signin"]', "#homeHeroActions a"],
        title: "Sign in or register your club",
        text: "Players and captains sign in here. New club? Tap <strong>Register your club</strong> on this page to add your club and players.",
      },
      {
        find: quick,
        targets: ['[data-public-nav="score"]'],
        title: "Score a quick match - no account needed",
        text: IN_APP
          ? "Want to try it? Tap <strong>Score</strong> in the tabs at the bottom, or the quick match link on this page, and score ball by ball."
          : "Want to try it? Tap “Score a quick match” and score ball by ball, no sign-in needed.",
      },
    ];
  }

  let steps = [];
  let index = 0;
  let layer = null;

  const style = document.createElement("style");
  style.textContent = `
    .cc-tour{position:fixed;inset:0;z-index:3000;pointer-events:none}
    .cc-tour-shade{position:fixed;inset:0;background:rgba(15,23,42,.55);pointer-events:auto}
    .cc-tour-spot{position:fixed;border-radius:14px;box-shadow:0 0 0 9999px rgba(15,23,42,.55);outline:3px solid #fbbf24;transition:all .2s ease;pointer-events:none}
    .cc-tour-card{position:fixed;width:min(360px,calc(100vw - 32px));display:grid;gap:10px;padding:18px;border-radius:18px;background:#fff;color:#0f172a;box-shadow:0 24px 60px rgba(15,23,42,.35);font-family:"Roboto",system-ui,sans-serif;pointer-events:auto}
    .cc-tour-card h2{margin:0;font-family:"Roboto",sans-serif;font-size:1.1rem;font-weight:800}
    .cc-tour-card p{margin:0;color:#475569;line-height:1.5}
    .cc-tour-bar{height:6px;border-radius:99px;background:#e2e8f0;overflow:hidden}
    .cc-tour-bar span{display:block;height:100%;background:#e11d48;border-radius:99px;transition:width .2s ease}
    .cc-tour-foot{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}
    .cc-tour-dots{font-size:.8rem;color:#64748b;font-weight:700}
    .cc-tour-btns{display:flex;gap:8px}
    .cc-tour-btns button{min-height:42px;padding:0 14px;border-radius:12px;font-weight:800;cursor:pointer;border:1.5px solid #e2e8f0;background:#fff;color:#0f172a}
    .cc-tour-btns button.primary{background:#0f172a;border-color:#0f172a;color:#fff}
  `;
  document.head.appendChild(style);

  function token() {
    try {
      return localStorage.getItem(TOKEN_KEY) || "";
    } catch (error) {
      return "";
    }
  }

  function visible(el) {
    if (!el || el.hidden) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width < 4 || rect.height < 4) return false;
    if (rect.bottom < 0 || rect.top > window.innerHeight || rect.right < 0 || rect.left > window.innerWidth) return false;
    const css = getComputedStyle(el);
    return css.visibility !== "hidden" && css.display !== "none" && Number(css.opacity || 1) > 0.05;
  }

  function onClubsPage() {
    return (window.location.pathname.replace(/\/+$/, "") || "/") === "/clubs";
  }

  function findTarget(step) {
    if (step.find) {
      const found = step.find();
      if (found) return found;
    }
    for (const selector of step.targets || []) {
      const found = Array.from(document.querySelectorAll(selector)).find(visible);
      if (found) return found;
    }
    return null;
  }

  function markSeen() {
    if (visitorMode) {
      try {
        localStorage.setItem(VISITOR_SEEN_KEY, new Date().toISOString());
      } catch (error) {
        /* private mode */
      }
      return;
    }
    try {
      localStorage.setItem(SEEN_KEY, new Date().toISOString());
    } catch (error) {
      /* private mode */
    }
    const t = token();
    if (t) fetch("/api/tour/seen", { method: "POST", headers: { "X-Auth-Token": t } }).catch(() => {});
  }

  function close(seen = true) {
    if (layer) layer.remove();
    layer = null;
    window.removeEventListener("resize", place);
    if (seen) markSeen();
  }

  function place() {
    if (!layer) return;
    const step = steps[index];
    const target = IN_APP && step.appTab ? null : findTarget(step);
    const spot = layer.querySelector(".cc-tour-spot");
    const shade = layer.querySelector(".cc-tour-shade");
    const card = layer.querySelector(".cc-tour-card");
    const margin = 16;
    if (target) {
      const rect = target.getBoundingClientRect();
      const pad = 6;
      Object.assign(spot.style, { display: "block", top: `${rect.top - pad}px`, left: `${rect.left - pad}px`, width: `${rect.width + pad * 2}px`, height: `${rect.height + pad * 2}px` });
      shade.style.background = "transparent";
      const cardRect = card.getBoundingClientRect();
      const below = rect.bottom + 14;
      const top = below + cardRect.height + margin <= window.innerHeight ? below : Math.max(margin, rect.top - cardRect.height - 14);
      const left = Math.min(Math.max(margin, rect.left + rect.width / 2 - cardRect.width / 2), window.innerWidth - cardRect.width - margin);
      Object.assign(card.style, { top: `${top}px`, left: `${left}px`, bottom: "auto", transform: "none" });
    } else if (IN_APP && step.appTab) {
      // The tab is in the app's own bar just below the page: put the card at the bottom, pointing down at it.
      spot.style.display = "none";
      shade.style.background = "rgba(15,23,42,.55)";
      Object.assign(card.style, { top: "auto", bottom: `${margin}px`, left: "50%", transform: "translateX(-50%)" });
    } else {
      spot.style.display = "none";
      shade.style.background = "rgba(15,23,42,.55)";
      Object.assign(card.style, { top: "50%", left: "50%", bottom: "auto", transform: "translate(-50%, -50%)" });
    }
  }

  function render() {
    const step = steps[index];
    const last = index === steps.length - 1;
    const percent = Math.round(((index + 1) / steps.length) * 100);
    layer.querySelector(".cc-tour-card").innerHTML = `
      <div class="cc-tour-bar" aria-hidden="true"><span style="width:${percent}%"></span></div>
      <h2 id="ccTourTitle">${step.title}</h2>
      <p>${IN_APP && step.appText ? step.appText : step.text}</p>${IN_APP && step.appTab ? '<p style="text-align:center;font-size:1.4rem;margin:0">👇</p>' : ""}
      <div class="cc-tour-foot">
        <span class="cc-tour-dots">${index + 1} of ${steps.length}</span>
        <div class="cc-tour-btns">
          ${last ? "" : '<button type="button" data-tour="skip">Skip</button>'}
          ${index ? '<button type="button" data-tour="back">Back</button>' : ""}
          <button type="button" class="primary" data-tour="next">${last ? "Let's go" : index ? "Next" : "Show me"}</button>
        </div>
      </div>`;
    place();
    const next = layer.querySelector('[data-tour="next"]');
    if (next) next.focus();
  }

  function start(info) {
    close(false);
    visitorMode = false;
    steps = buildSteps(info || window.CCAppTour.info || {});
    index = 0;
    layer = document.createElement("div");
    layer.className = "cc-tour";
    layer.innerHTML = `<div class="cc-tour-shade"></div><div class="cc-tour-spot"></div><div class="cc-tour-card" role="dialog" aria-modal="true" aria-labelledby="ccTourTitle"></div>`;
    layer.addEventListener("click", (event) => {
      const action = event.target.closest("[data-tour]")?.dataset.tour;
      if (action === "next") {
        if (index >= steps.length - 1) close();
        else {
          index += 1;
          render();
        }
      } else if (action === "back") {
        index = Math.max(0, index - 1);
        render();
      } else if (action === "skip") {
        close();
      }
    });
    document.body.appendChild(layer);
    window.addEventListener("resize", place);
    render();
  }

  document.addEventListener("keydown", (event) => {
    if (!layer) return;
    if (event.key === "Escape") close();
    if (event.key === "ArrowRight") layer.querySelector('[data-tour="next"]')?.click();
    if (event.key === "ArrowLeft") layer.querySelector('[data-tour="back"]')?.click();
  });

  function startVisitor() {
    close(false);
    visitorMode = true;
    steps = visitorSteps();
    index = 0;
    layer = document.createElement("div");
    layer.className = "cc-tour";
    layer.innerHTML = `<div class="cc-tour-shade"></div><div class="cc-tour-spot"></div><div class="cc-tour-card" role="dialog" aria-modal="true" aria-labelledby="ccTourTitle"></div>`;
    layer.addEventListener("click", onLayerClick);
    document.body.appendChild(layer);
    window.addEventListener("resize", place);
    render();
  }

  function onLayerClick(event) {
    const action = event.target.closest("[data-tour]")?.dataset.tour;
    if (action === "next") {
      if (index >= steps.length - 1) close();
      else {
        index += 1;
        render();
      }
    } else if (action === "back") {
      index = Math.max(0, index - 1);
      render();
    } else if (action === "skip") {
      close();
    }
  }

  window.CCAppTour = { start: (info) => start(info), startVisitor, close, info: {} };

  // Start on its own only after signing in, and only if this account has never seen it (or ?tour=1).
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  const asked = new URLSearchParams(window.location.search).get("tour") === "1";
  const authPage = path === "/signin" || path === "/register" || path.startsWith("/signin/");
  const t = token();
  if (authPage) return;
  if (!t) {
    // Visitor welcome: only on the public Live / home page, once per browser.
    if (!(path === "/" || path === "/live")) return;
    let seen = false;
    try {
      seen = Boolean(localStorage.getItem(VISITOR_SEEN_KEY));
    } catch (error) {
      seen = true;
    }
    if (seen && !asked) return;
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      const ready = document.querySelector('[data-public-nav="signin"]');
      if (ready || tries > 40) {
        clearInterval(timer);
        if (ready && !token()) setTimeout(startVisitor, 800);
      }
    }, 250);
    return;
  }

  fetch("/api/tour", { headers: { "X-Auth-Token": t } })
    .then((response) => (response.ok ? response.json() : null))
    .then((info) => {
      if (!info) return;
      window.CCAppTour.info = info;
      if (info.seen && !asked) return;
      let tries = 0;
      const timer = setInterval(() => {
        tries += 1;
        const ready = document.querySelector('.shared-topbar-host .top-nav a[href="/matches"], #bottomAppNav a[href="/matches"], .mobile-tabbar a[href="/matches"]');
        if (ready || tries > 40) {
          clearInterval(timer);
          if (ready) setTimeout(() => start(info), 500);
        }
      }, 250);
    })
    .catch(() => {});
})();
