// Admin Center -> "WhatsApp alerts" (Nov 17 2026, Dhruvika: "so whatsapp thing is not done?"). The alerts are built
// (fixtures, published scorecards, the uploader's result, live score); this tab shows whether the Azure settings are
// there, the four Meta templates to create, a test send and the last messages. Server: GET /api/admin/whatsapp,
// POST /api/admin/whatsapp/test.
(function adminWhatsApp() {
  const root = document.getElementById("adminWhatsApp");
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
  const when = (value) => {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? esc(value) : d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };
  const KIND = { fixture: "📅 Fixture", scorecard: "📋 Scorecard", processed: "📤 Upload read", live: "🔴 Live score", test: "🧪 Test" };

  async function load() {
    const response = await fetch("/api/admin/whatsapp", { headers }).catch(() => null);
    const data = response && response.ok ? await response.json().catch(() => null) : null;
    if (!data) {
      root.innerHTML = '<p class="empty-state">Couldn\'t check WhatsApp. Only the superadmin can see this.</p>';
      return;
    }
    render(data);
  }

  function render(data) {
    const tick = (ok) => (ok ? '<span class="done">✅</span>' : "⬜");
    // Nov 17 2026: test mode - only WHATSAPP_TEST_NUMBERS get alerts until WHATSAPP_LIVE=true
    const mode = data.live
      ? '<div class="awa-status is-off">⚠️ LIVE: alerts go to every player of the club (WHATSAPP_LIVE=true)</div>'
      : `<div class="awa-status is-on">🧪 Test mode: alerts go only to ${data.test_numbers && data.test_numbers.length ? data.test_numbers.map(esc).join(", ") : "nobody yet"} <small>· set WHATSAPP_TEST_NUMBERS in Azure (e.g. 4165550123,6475550199); everyone else is skipped until WHATSAPP_LIVE=true</small></div>`;
    const status = data.configured
      ? `<div class="awa-status is-on">✅ WhatsApp is switched on <small>· last 7 days: ${data.last_7_days.sent} sent, ${data.last_7_days.failed} failed</small></div>`
      : '<div class="awa-status is-off">⏸️ WhatsApp is built but switched off <small>· the app only shows the bell alerts until the steps below are done</small></div>';
    const steps = `
      <ol class="awa-steps">
        <li>${tick(data.configured)} In <b>Meta WhatsApp Manager</b> (business.facebook.com), add the club's WhatsApp number and create the 4 templates below (category <b>Utility</b>, language <b>English</b>, exact names). Meta approves them, usually within minutes to a day.</li>
        <li>${tick(data.token_set)} In <b>Azure → the web app → Configuration</b>, add <code>WHATSAPP_TOKEN</code> (a permanent System user token with whatsapp_business_messaging).</li>
        <li>${tick(data.phone_id_set)} Add <code>WHATSAPP_PHONE_NUMBER_ID</code> (WhatsApp Manager → API setup → Phone number ID), save and restart the app.</li>
        <li>${tick(data.configured && data.last_7_days.sent > 0)} Send yourself a test below: first <b>hello_world</b> (Meta's ready-made one), then each of the 4 templates.</li>
      </ol>`;
    const templates = (data.template_list || [])
      .map((t) => `<div class="awa-tpl"><code>${esc(t.name)}</code><small>${esc(t.when)}</small><q>${esc(t.text)}</q></div>`)
      .join("");
    const options = [`<option value="hello_world">hello_world (Meta's test message)</option>`, ...(data.template_list || []).map((t) => `<option value="${esc(t.key)}">${esc(t.name)}</option>`)].join("");
    const rows = (data.recent || [])
      .map((r) => `<tr><td>${when(r.sent_at)}</td><td>${KIND[r.kind] || esc(r.kind)}</td><td>…${esc(r.phone_end)}</td><td class="is-${esc(r.status)}">${esc(r.status)}</td><td>${r.status === "failed" ? esc(r.detail) : ""}</td></tr>`)
      .join("");
    root.innerHTML = `
      ${status}
      ${mode}
      <h3>Setup (done once, by the superadmin)</h3>
      ${steps}
      <h3>The 4 message templates</h3>
      <div class="awa-grid">${templates}</div>
      <h3>Send a test</h3>
      <form class="awa-test" id="awaTest">
        <label>Mobile number<input name="phone" type="tel" required placeholder="e.g. 416 555 0123" ${data.configured ? "" : "disabled"} /></label>
        <label>Message<select name="template" ${data.configured ? "" : "disabled"}>${options}</select></label>
        <button class="primary-button" type="submit" ${data.configured ? "" : "disabled"}>📨 Send test</button>
      </form>
      <p class="awa-msg" id="awaMsg" role="status">${data.configured ? "" : "Tests can be sent once steps 2 and 3 are done."}</p>
      <h3>Last messages</h3>
      ${rows ? `<div class="awa-scroll"><table class="awa-log"><thead><tr><th>When</th><th>Alert</th><th>To</th><th>Result</th><th>Meta's reason</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="empty-state">No WhatsApp messages sent yet.</p>'}`;
    const form = root.querySelector("#awaTest");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const msg = root.querySelector("#awaMsg");
      msg.className = "awa-msg";
      msg.textContent = "Sending...";
      const body = Object.fromEntries(new FormData(form).entries());
      const response = await fetch("/api/admin/whatsapp/test", { method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => null);
      const result = response ? await response.json().catch(() => ({})) : {};
      const ok = Boolean(response && response.ok && result.ok);
      msg.className = `awa-msg ${ok ? "is-ok" : "is-bad"}`;
      msg.textContent = result.message || result.detail || "Couldn't send. Try again.";
      if (response && response.ok) setTimeout(load, 600);
    });
  }

  document.addEventListener("click", (event) => {
    if (event.target.closest('[data-admin-section="whatsapp"]')) load();
  });
  load();
})();
