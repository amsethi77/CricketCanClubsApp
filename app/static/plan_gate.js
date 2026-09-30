/*
 * Plan gate: when the server answers 402 (a Super or Premium feature, or the monthly
 * upload limit), show a friendly "Upgrade" pop-up instead of a raw error.
 * Loaded on signed-in pages by multipage.js. Server side: _require_feature() in app/main.py.
 * Documented in README.md -> "Subscriptions and plans".
 */
(() => {
  if (window.CCPlanGate) return;
  const originalFetch = window.fetch.bind(window);
  let lastShown = 0;

  const style = document.createElement("style");
  style.textContent = `
    .plan-gate-backdrop{position:fixed;inset:0;z-index:2500;display:grid;place-items:center;padding:16px;background:rgba(15,23,42,.5)}
    .plan-gate-backdrop[hidden]{display:none}
    .plan-gate-card{font-family:"Inter",system-ui,sans-serif;width:min(440px,100%);display:grid;gap:12px;padding:22px;border-radius:22px;background:#fff;box-shadow:0 30px 70px rgba(15,23,42,.3);color:#0f172a}
    .plan-gate-card h2{font-family:"Sora","Inter",sans-serif;margin:0;font-size:1.25rem;font-weight:800}
    .plan-gate-card p{margin:0;color:#475569;line-height:1.5}
    .plan-gate-kicker{font-size:.72rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#7c3aed}
    .plan-gate-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}
    .plan-gate-actions a,.plan-gate-actions button{min-height:44px;padding:0 18px!important;border-radius:12px!important;font-weight:800;display:inline-flex;align-items:center;cursor:pointer;text-decoration:none}
    .plan-gate-actions a{background:linear-gradient(135deg,#7c3aed,#e11d48)!important;color:#fff!important;border:0!important}
    .plan-gate-actions button{background:#fff!important;color:#0f172a!important;border:1.5px solid #e2e8f0!important}
  `;
  document.head.appendChild(style);

  const backdrop = document.createElement("div");
  backdrop.className = "plan-gate-backdrop";
  backdrop.hidden = true;
  backdrop.innerHTML = `
    <div class="plan-gate-card" role="dialog" aria-modal="true" aria-labelledby="planGateTitle">
      <p class="plan-gate-kicker">⭐ Upgrade</p>
      <h2 id="planGateTitle">This is a paid feature</h2>
      <p id="planGateText"></p>
      <div class="plan-gate-actions">
        <a id="planGateLink" href="/pricing">See plans</a>
        <button type="button" data-plan-gate-close>Not now</button>
      </div>
    </div>`;
  const mount = () => document.body && !backdrop.isConnected && document.body.appendChild(backdrop);
  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount);

  function show(message) {
    mount();
    const text = String(message || "This feature is part of a paid plan.").replace(/\s*See \/pricing to upgrade\.?/i, "");
    const isUploads = /upload/i.test(text);
    backdrop.querySelector("#planGateTitle").textContent = isUploads ? "Monthly upload limit reached" : "This is a paid feature";
    backdrop.querySelector("#planGateText").textContent = text;
    backdrop.hidden = false;
    lastShown = Date.now();
  }

  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop || event.target.closest("[data-plan-gate-close]")) backdrop.hidden = true;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") backdrop.hidden = true;
  });

  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    if (response.status === 402 && Date.now() - lastShown > 1500) {
      response
        .clone()
        .json()
        .then((data) => show(data && data.detail))
        .catch(() => show(""));
    }
    return response;
  };

  window.CCPlanGate = { show };
})();
