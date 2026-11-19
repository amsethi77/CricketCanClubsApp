// Admin Center -> "Costs" (Nov 18 2026, Amit: "track costs - Gemini, Azure, WhatsApp"). The app counts every AI call
// and every WhatsApp message; the superadmin types in the prices from the bills and this tab shows the estimate per
// month. Server: GET /api/admin/costs?month=YYYY-MM, POST /api/admin/costs/rates. README "Costs (Admin Center)".
(function adminCosts() {
  const root = document.getElementById("adminCosts");
  if (!root) return;
  let token = "";
  try {
    token = localStorage.getItem("cricketClubAppAuthToken") || "";
  } catch (error) {
    token = "";
  }
  const headers = { "X-Auth-Token": token, Accept: "application/json" };
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
  const num = (value) => Number(value || 0).toLocaleString();
  let currency = "USD";
  const money = (value) => {
    const amount = Number(value || 0);
    const tiny = amount > 0 && amount < 0.01;
    const text = `${currency === "USD" ? "$" : ""}${tiny ? "0.01" : amount.toFixed(2)}${currency === "USD" ? "" : " " + esc(currency)}`;
    return tiny ? `&lt; ${text}` : text;
  };
  const monthName = (month) => {
    const [y, m] = String(month).split("-").map(Number);
    return new Date(y, (m || 1) - 1, 1).toLocaleString([], { month: "short", year: "numeric" });
  };
  const KIND = { fixture: "📅 New fixture", scorecard: "📋 Scorecard published", processed: "📤 Upload read", live: "🔴 Live score", test: "🧪 Test" };
  let shownMonth = "";

  async function load(month) {
    const query = month ? `?month=${encodeURIComponent(month)}` : "";
    const response = await fetch(`/api/admin/costs${query}`, { headers }).catch(() => null);
    const data = response && response.ok ? await response.json().catch(() => null) : null;
    if (!data) {
      root.innerHTML = '<p class="empty-state">Couldn\'t add up the costs. Only the superadmin can see this.</p>';
      return;
    }
    render(data);
  }

  function render(data) {
    const rates = data.rates || {};
    currency = rates.currency || "USD";
    const cur = data.current || {};
    shownMonth = cur.month;
    const geminiPriced = Number(rates.gemini_input_per_million) > 0 || Number(rates.gemini_output_per_million) > 0;
    const tiles = `
      <div class="aco-tiles">
        <div class="aco-tile"><span>🤖 AI (Gemini)</span><strong>${geminiPriced ? money(cur.ai_cost) : "—"}</strong><small>${num(cur.ai_calls)} calls · ${num(cur.ai_tokens)} tokens${geminiPriced ? "" : " · type the price below (0 on the free tier)"}</small></div>
        <div class="aco-tile"><span>💬 WhatsApp</span><strong>${money(cur.whatsapp_cost)}</strong><small>${num(cur.whatsapp_messages)} messages sent</small></div>
        <div class="aco-tile"><span>☁️ Azure</span><strong>${Number(rates.azure_monthly) > 0 ? money(cur.azure_cost) : "—"}</strong><small>${Number(rates.azure_monthly) > 0 ? "fixed monthly plan" : "type the plan price below"}</small></div>
        <div class="aco-tile is-total"><span>Total ${esc(monthName(cur.month))}</span><strong>${money(cur.total)}</strong><small>estimate${Number(rates.other_monthly) > 0 ? ` · incl. ${money(cur.other_cost)} other` : ""}</small></div>
      </div>`;
    const aiRows = (cur.ai || [])
      .map((r) => `<tr><td>${esc(r.purpose)}</td><td><code>${esc(r.model)}</code></td><td>${num(r.calls)}${r.answered < r.calls ? ` <small>(${num(r.calls - r.answered)} failed)</small>` : ""}</td><td>${num(r.input_tokens)}</td><td>${num(r.output_tokens + r.thinking_tokens)}</td><td>${geminiPriced ? money(r.cost) : "—"}</td></tr>`)
      .join("");
    const waRows = (cur.whatsapp || [])
      .map((r) => `<tr><td>${KIND[r.kind] || esc(r.kind)}</td><td>${num(r.messages)}</td><td>${money(r.cost)}</td></tr>`)
      .join("");
    const history = (data.history || [])
      .map((h) => `<tr class="${h.month === cur.month ? "is-shown" : ""}"><td><button type="button" class="aco-month" data-month="${esc(h.month)}">${esc(monthName(h.month))}</button></td><td>${num(h.ai_calls)}</td><td>${geminiPriced ? money(h.ai_cost) : "—"}</td><td>${num(h.whatsapp_messages)}</td><td>${money(h.whatsapp_cost)}</td><td>${money(h.azure_cost + h.other_cost)}</td><td><b>${money(h.total)}</b></td></tr>`)
      .join("");
    const field = (key, label, hint, step) =>
      `<label>${label}<input name="${key}" type="number" min="0" step="${step}" value="${esc(rates[key] ?? 0)}" /><small>${hint}</small></label>`;
    root.innerHTML = `
      ${tiles}
      <h3>AI calls in ${esc(monthName(cur.month))}</h3>
      ${aiRows ? `<div class="aco-scroll"><table class="aco-table"><thead><tr><th>What for</th><th>Model</th><th>Calls</th><th>Tokens in</th><th>Tokens out</th><th>Cost</th></tr></thead><tbody>${aiRows}</tbody></table></div>` : '<p class="empty-state">No AI calls counted this month yet (counting started on Nov 18 2026).</p>'}
      <h3>WhatsApp messages in ${esc(monthName(cur.month))}</h3>
      ${waRows ? `<div class="aco-scroll"><table class="aco-table"><thead><tr><th>Alert</th><th>Messages</th><th>Cost</th></tr></thead><tbody>${waRows}</tbody></table></div>` : '<p class="empty-state">No WhatsApp messages sent this month.</p>'}
      <h3>Last 6 months</h3>
      <div class="aco-scroll"><table class="aco-table"><thead><tr><th>Month</th><th>AI calls</th><th>AI</th><th>WhatsApp msgs</th><th>WhatsApp</th><th>Azure + other</th><th>Total</th></tr></thead><tbody>${history}</tbody></table></div>
      <h3>Prices used</h3>
      <form class="aco-rates" id="acoRates">
        ${field("gemini_input_per_million", "Gemini: price per 1M tokens in", "Google AI Studio → Billing. 0 on the free tier.", "0.01")}
        ${field("gemini_output_per_million", "Gemini: price per 1M tokens out", "Thinking tokens count as out.", "0.01")}
        ${field("whatsapp_utility", "WhatsApp: price per message", "Meta, Utility template, US/Canada numbers: about 0.0034.", "0.0001")}
        ${field("azure_monthly", "Azure: plan price per month", "Azure portal → Cost Management, or the App Service plan.", "0.01")}
        ${field("other_monthly", "Other per month", "Storage, domain name, ...", "0.01")}
        <label>Currency<input name="currency" type="text" maxlength="3" value="${esc(currency)}" /><small>USD, CAD, ...</small></label>
        <button class="primary-button" type="submit">💾 Save prices</button>
      </form>
      <p class="aco-msg" id="acoMsg" role="status"></p>
      <p class="aco-note">Estimates from what the app counted. The real amounts are on the Google, Meta and Azure bills.</p>`;
    root.querySelectorAll(".aco-month").forEach((button) => button.addEventListener("click", () => load(button.dataset.month)));
    const form = root.querySelector("#acoRates");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const msg = root.querySelector("#acoMsg");
      msg.className = "aco-msg";
      msg.textContent = "Saving...";
      const body = Object.fromEntries(new FormData(form).entries());
      Object.keys(body).forEach((key) => {
        if (key !== "currency") body[key] = Number(body[key] || 0);
      });
      const response = await fetch("/api/admin/costs/rates", { method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => null);
      const result = response ? await response.json().catch(() => ({})) : {};
      if (response && response.ok) {
        await load(shownMonth);
        const again = root.querySelector("#acoMsg");
        again.className = "aco-msg is-ok";
        again.textContent = result.message || "Saved.";
      } else {
        msg.className = "aco-msg is-bad";
        msg.textContent = result.detail || "Couldn't save. Try again.";
      }
    });
  }

  document.addEventListener("click", (event) => {
    if (event.target.closest('[data-admin-section="costs"]')) load(shownMonth);
  });
  load();
})();
