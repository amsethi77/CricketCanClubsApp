/*
 * Plans page (/pricing): Free, Super ($4.99/month) and Premium ($100/year).
 * Signed out: plan cards + comparison. Signed in: "Your plan" (trial days, uploads used),
 * Upgrade buttons (Stripe Checkout when switched on), Manage billing.
 * Site admins: set any user's plan by hand and see who is on which plan.
 * APIs: GET /api/plans, GET /api/subscription/me, POST /api/subscription/checkout,
 *       POST /api/subscription/portal, GET /api/admin/subscriptions, POST /api/admin/subscriptions/set
 * Documented in README.md -> "Subscriptions and plans".
 */
(() => {
  const app = document.getElementById("pricingApp");
  if (!app) return;
  const params = new URLSearchParams(location.search);
  const TOKEN_KEY = "cricketClubAppAuthToken";
  const esc = (v) =>
    String(v ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  const token = () => {
    try {
      return localStorage.getItem(TOKEN_KEY) || "";
    } catch (e) {
      return "";
    }
  };

  async function api(method, url, body) {
    const response = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json", Accept: "application/json", "X-Auth-Token": token() },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Object.assign(new Error(data.detail || `Request failed (${response.status})`), { status: response.status });
    return data;
  }

  let state = { catalog: null, me: null, admin: null, message: "", tone: "" };

  const PLAN_ICON = { free: "🏏", super: "⚡", premium: "👑" };
  const fmtDate = (iso) => {
    if (!iso) return "";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso.slice(0, 10) : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  };

  function banner() {
    const checkout = params.get("checkout");
    const feature = params.get("feature");
    const featureInfo = (state.catalog?.features || []).find((f) => f.key === feature);
    const parts = [];
    if (checkout === "success") parts.push(`<div class="pr-banner good">🎉 Thanks! Your payment went through. Your new plan switches on within a minute. Refresh if you don't see it yet.</div>`);
    if (checkout === "cancelled") parts.push(`<div class="pr-banner">Checkout was cancelled. Nothing was charged.</div>`);
    if (featureInfo) {
      const plan = (state.catalog.plans || []).find((p) => p.id === featureInfo.plan);
      parts.push(`<div class="pr-banner info">⭐ <strong>${esc(featureInfo.label)}</strong> is part of the ${esc(plan?.name || featureInfo.plan)} plan.</div>`);
    }
    if (state.message) parts.push(`<div class="pr-banner ${esc(state.tone)}">${esc(state.message)}</div>`);
    return parts.join("");
  }

  function yourPlan() {
    const sub = state.me?.subscription;
    if (!sub) return "";
    let when = "";
    if (sub.source === "site_admin") when = "Site admins always have every feature.";
    else if (sub.is_trial) when = `Free Premium trial: ${esc(sub.days_left)} day${sub.days_left === 1 ? "" : "s"} left (ends ${esc(fmtDate(sub.period_end))}). After that you move to Free unless you choose a plan.`;
    else if (sub.plan !== "free" && sub.period_end) when = sub.cancel_at_period_end ? `Ends on ${esc(fmtDate(sub.period_end))}.` : `Renews on ${esc(fmtDate(sub.period_end))}.`;
    else if (sub.source === "expired") when = `Your ${esc(sub.expired_from)} access has ended, so you're on Free now.`;
    else if (sub.plan === "free") when = "Live scoring, stats and scorecards are free forever.";
    const limit = sub.upload_limit;
    const used = Number(sub.uploads_used || 0);
    const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0;
    const uploads =
      limit === null || limit === undefined
        ? `<p class="pr-uploads"><strong>${used}</strong> scorecard uploads this month · unlimited</p>`
        : `<p class="pr-uploads"><strong>${used} of ${limit}</strong> scorecard image uploads used this month</p>
           <div class="pr-meter" role="img" aria-label="${used} of ${limit} uploads used"><span style="width:${pct}%"></span></div>`;
    const club = state.me.club_paid && sub.plan === "free"
      ? `<p class="pr-note">✅ A captain or admin of your club is on a paid plan, so you can mark availability and get match alerts.</p>`
      : "";
    const billing =
      state.catalog?.stripe_enabled && sub.has_stripe_customer
        ? `<button type="button" class="pr-btn ghost" data-act="portal">Manage billing</button>`
        : "";
    return `
      <section class="pr-mine">
        <div class="pr-mine-head">
          <div>
            <p class="pr-kicker">Your plan</p>
            <h2>${PLAN_ICON[sub.plan] || ""} ${esc(sub.plan_name)}${sub.is_trial ? ' <span class="pr-pill">Trial</span>' : ""}</h2>
          </div>
          ${billing}
        </div>
        <p class="pr-muted">${when}</p>
        ${uploads}
        ${club}
      </section>`;
  }

  function planCard(plan) {
    const sub = state.me?.subscription;
    const signedIn = Boolean(state.me);
    const current = Boolean(sub && sub.plan === plan.id);
    let cta = "";
    if (!signedIn) {
      cta = plan.id === "free"
        ? `<a class="pr-btn ghost" href="/register">Get started free</a>`
        : `<a class="pr-btn primary" href="/register?plan=${esc(plan.id)}">Register to choose ${esc(plan.name)}</a>`;
    } else if (current && !sub.is_trial) {
      cta = `<span class="pr-btn current">✓ Your plan</span>`;
    } else if (plan.id === "free") {
      cta = sub?.plan === "free" ? `<span class="pr-btn current">✓ Your plan</span>` : `<span class="pr-btn quiet">Included for everyone</span>`;
    } else if (state.catalog?.stripe_enabled) {
      cta = `<button type="button" class="pr-btn primary" data-checkout="${esc(plan.id)}">${sub?.is_trial && current ? "Keep" : "Choose"} ${esc(plan.name)}</button>`;
    } else {
      cta = `<span class="pr-btn quiet">Online payment coming soon</span><p class="pr-cta-note">Ask your site admin to switch you to ${esc(plan.name)}.</p>`;
    }
    const highlights = (plan.highlights || [])
      .map((h) => (/plus:$/.test(h) ? `<li class="pr-plus">${esc(h)}</li>` : `<li>${esc(h)}</li>`))
      .join("");
    return `
      <article class="pr-plan pr-plan-${esc(plan.id)}${plan.id === "super" ? " is-popular" : ""}${current ? " is-current" : ""}">
        ${plan.id === "super" ? '<span class="pr-ribbon">Most popular</span>' : ""}
        <p class="pr-plan-name">${PLAN_ICON[plan.id] || ""} ${esc(plan.name)}</p>
        <p class="pr-price">${esc(plan.price)}<small> ${esc(plan.price_note)}</small></p>
        <p class="pr-tagline">${esc(plan.tagline)}</p>
        <ul class="pr-list">${highlights}</ul>
        <div class="pr-cta">${cta}</div>
      </article>`;
  }

  function compareTable() {
    const plans = state.catalog?.plans || [];
    const rows = (state.catalog?.features || [])
      .map((f) => {
        const cells = plans
          .map((p) => `<td>${(p.features || []).includes(f.key) ? '<span class="pr-yes" aria-label="Included">✓</span>' : '<span class="pr-no" aria-label="Not included">—</span>'}</td>`)
          .join("");
        return `<tr><th scope="row">${esc(f.label)}</th>${cells}</tr>`;
      })
      .join("");
    const uploads = plans.map((p) => `<td><strong>${p.upload_limit === null ? '<span class="pr-wide">Unlimited</span><span class="pr-narrow" aria-hidden="true">∞</span>' : `${p.upload_limit}<span class="pr-wide">/month</span>`}</strong></td>`).join("");
    return `
      <section class="pr-compare">
        <h2>Compare plans</h2>
        <div class="pr-table-wrap">
          <table class="pr-table">
            <thead><tr><th scope="col">Feature</th>${plans.map((p) => `<th scope="col">${esc(p.name)}</th>`).join("")}</tr></thead>
            <tbody>
              <tr><th scope="row">Scorecard image uploads</th>${uploads}</tr>
              ${rows}
            </tbody>
          </table>
        </div>
      </section>`;
  }

  function faq() {
    const days = state.catalog?.trial_days || 60;
    return `
      <section class="pr-faq">
        <h2>Good to know</h2>
        <details><summary>Is live scoring really free?</summary><p>Yes. Scoring matches, player and club stats, and viewing scorecards are free for everyone, forever. Paid plans add team management, alerts, AI and more uploads.</p></details>
        <details><summary>What is the AI Live Scorer?</summary><p>A Premium feature in Quick Score. Say what happened ("four", "wide, then two runs", "caught by Sam") and the ball is added for you. The normal scoring engine still does all the maths, and you confirm every wicket.</p></details>
        <details><summary>Do all my players need to pay?</summary><p>No. When a captain or club admin is on Super or Premium, every player in that club can mark availability and gets match and live score alerts.</p></details>
        <details><summary>I was already using the app. What happens to me?</summary><p>Everyone who joined before plans started gets ${esc(days)} days of Premium free. After that you move to Free unless you choose a plan. Nothing is deleted.</p></details>
        <details><summary>What happens to uploads when I reach my limit?</summary><p>Your earlier uploads stay. The count resets on the 1st of each month, or you can upgrade for more.</p></details>
      </section>`;
  }

  function adminPanel() {
    if (!state.me?.is_site_admin) return "";
    const admin = state.admin;
    const counts = admin?.counts || {};
    const stripe = state.catalog?.stripe_enabled
      ? `Stripe is on${state.catalog.stripe_test_mode ? " (test mode)" : ""}.`
      : "Stripe is off. Add STRIPE_SECRET_KEY, STRIPE_PRICE_SUPER, STRIPE_PRICE_PREMIUM and STRIPE_WEBHOOK_SECRET to the .env file (see README) and restart the app.";
    const rows = (admin?.users || [])
      .map(
        (u) => `<tr><td>${esc(u.name)}</td><td>${esc(u.role)}</td><td><strong>${esc(u.plan)}</strong></td><td>${esc(u.source)}</td><td>${esc(u.period_end ? fmtDate(u.period_end) : "")}</td><td>${esc(u.uploads_used)}</td></tr>`
      )
      .join("");
    return `
      <section class="pr-admin">
        <p class="pr-kicker">Site admin</p>
        <h2>Manage plans</h2>
        <p class="pr-muted">${esc(stripe)}</p>
        <div class="pr-counts">
          <span>Free <strong>${esc(counts.free ?? "–")}</strong></span>
          <span>Super <strong>${esc(counts.super ?? "–")}</strong></span>
          <span>Premium <strong>${esc(counts.premium ?? "–")}</strong></span>
        </div>
        <form id="prAdminForm" class="pr-admin-form">
          <label>User <input name="user" placeholder="Name, mobile, email or id" required autocomplete="off" /></label>
          <label>Plan
            <select name="plan"><option value="super">Super</option><option value="premium">Premium</option><option value="free">Free</option></select>
          </label>
          <label>Days (0 = no end date) <input name="days" type="number" min="0" value="30" /></label>
          <label>Note <input name="note" placeholder="e.g. paid cash at AGM" autocomplete="off" /></label>
          <button class="pr-btn primary" type="submit">Save plan</button>
        </form>
        <div class="pr-table-wrap">
          <table class="pr-table pr-users">
            <thead><tr><th>User</th><th>Role</th><th>Plan</th><th>How</th><th>Until</th><th>Uploads</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="6">Loading…</td></tr>'}</tbody>
          </table>
        </div>
      </section>`;
  }

  function render() {
    const plans = state.catalog?.plans || [];
    app.innerHTML = `
      <section class="pr-hero">
        <p class="pr-kicker">Plans</p>
        <h1>Your cricket. Every match. One place.</h1>
        <p class="pr-lede">Live scoring, stats and scorecards are free for every player. Upgrade when you want team management, alerts, AI and more history.</p>
      </section>
      ${banner()}
      ${yourPlan()}
      <section class="pr-plans">${plans.map(planCard).join("")}</section>
      ${compareTable()}
      ${faq()}
      ${adminPanel()}`;
  }

  app.addEventListener("click", async (event) => {
    const checkout = event.target.closest("[data-checkout]");
    if (checkout) {
      checkout.disabled = true;
      checkout.textContent = "Opening checkout…";
      try {
        const data = await api("POST", "/api/subscription/checkout", { plan: checkout.dataset.checkout });
        if (data.url) location.href = data.url;
      } catch (e) {
        state.message = e.message;
        state.tone = "bad";
        render();
      }
      return;
    }
    if (event.target.closest('[data-act="portal"]')) {
      try {
        const data = await api("POST", "/api/subscription/portal");
        if (data.url) location.href = data.url;
      } catch (e) {
        state.message = e.message;
        state.tone = "bad";
        render();
      }
    }
  });

  app.addEventListener("submit", async (event) => {
    if (event.target.id !== "prAdminForm") return;
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      const data = await api("POST", "/api/admin/subscriptions/set", {
        user: form.get("user"),
        plan: form.get("plan"),
        days: Number(form.get("days") || 0),
        note: form.get("note") || "",
      });
      state.message = data.message;
      state.tone = "good";
      state.admin = await api("GET", "/api/admin/subscriptions");
      state.me = await api("GET", "/api/subscription/me");
    } catch (e) {
      state.message = e.message;
      state.tone = "bad";
    }
    render();
    app.querySelector(".pr-banner")?.scrollIntoView({ behavior: "smooth", block: "center" });
  });

  (async () => {
    try {
      if (token()) {
        try {
          state.me = await api("GET", "/api/subscription/me");
          state.catalog = state.me;
        } catch (e) {
          state.me = null;
        }
      }
      if (!state.catalog) state.catalog = await api("GET", "/api/plans");
      render();
      if (state.me?.is_site_admin) {
        state.admin = await api("GET", "/api/admin/subscriptions").catch(() => null);
        render();
      }
    } catch (e) {
      app.innerHTML = `<div class="pr-banner bad">Plans couldn't be loaded: ${esc(e.message)}</div>`;
    }
  })();
})();
