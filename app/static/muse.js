/*
 * AI Muse: floating chat agent + notifications bell for signed-in pages.
 * Loaded by multipage.js on every signed-in page.
 *
 *  - Chat (POST /api/muse): an agent that carries out tasks you ask for (availability for you or
 *    named players, availability requests/reminders, best XI, new fixtures, live score updates,
 *    today's final score). Each task shows a plan with Confirm / Cancel; Confirm calls
 *    POST /api/muse/execute. Questions are answered by the LLM assistant (Ollama when running).
 *  - 📎 upload a scorecard photo (POST /api/scorecards/upload) straight from the chat.
 *  - 🎙️ voice input (browser speech recognition).
 *  - Alerts tab + 🔔 bell (GET /api/notifications, polled every 30 s) with optional browser pop-ups.
 *
 * Other pages can open it with window.CCMuse.open("chat" | "alerts", "optional message").
 * Documented in README.md -> "AI Muse and notifications".
 */
(() => {
  if (window.CCMuse) return;
  const TOKEN_KEY = "cricketClubAppAuthToken";
  const CLUB_KEY = "cricketClubAppPrimaryClubId";
  const HISTORY_KEY = "ccMuseHistory";
  const SEEN_KEY = "ccMuseSeenAlerts";
  const POLL_MS = 30000;

  const esc = (v) =>
    String(v ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const read = (store, key, fallback) => {
    try {
      const value = store.getItem(key);
      return value ? JSON.parse(value) : fallback;
    } catch (e) {
      return fallback;
    }
  };
  const write = (store, key, value) => {
    try {
      store.setItem(key, JSON.stringify(value));
    } catch (e) {
      /* ignore */
    }
  };
  const token = () => {
    try {
      return localStorage.getItem(TOKEN_KEY) || "";
    } catch (e) {
      return "";
    }
  };
  const clubId = () => {
    try {
      return sessionStorage.getItem(CLUB_KEY) || "";
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
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error((payload && payload.detail) || `Request failed (${response.status})`);
    return payload;
  }

  // Only on signed-in pages
  if (!document.querySelector(".page-topbar") || !token()) return;

  let history = read(sessionStorage, HISTORY_KEY, []);
  let notifications = [];
  let unread = 0;
  let tab = "chat";
  let recognition = null;
  let sending = false;

  // ---------- DOM ----------
  const fab = document.createElement("button");
  fab.type = "button";
  fab.className = "muse-fab";
  fab.setAttribute("aria-label", "Open the AI assistant (AI Muse)");
  fab.innerHTML = `<span class="muse-fab-icon" aria-hidden="true">✨</span><strong>AI Assistant</strong><span class="muse-badge" hidden></span>`;
  document.body.appendChild(fab);

  const panel = document.createElement("aside");
  panel.className = "muse-panel";
  panel.hidden = true;
  panel.setAttribute("aria-label", "AI Muse");
  panel.innerHTML = `
    <header class="muse-head">
      <div class="muse-title"><span aria-hidden="true">✨</span><div><strong>AI Muse · Assistant</strong><small class="muse-llm">Ask me anything, or tell me what to do</small></div></div>
      <div class="muse-tabs" role="tablist">
        <button type="button" role="tab" data-tab="chat" class="is-active">Chat</button>
        <button type="button" role="tab" data-tab="alerts">Alerts <span class="muse-tab-count" hidden></span></button>
      </div>
      <button type="button" class="muse-close" aria-label="Close">✕</button>
    </header>
    <div class="muse-body" data-view="chat">
      <div class="muse-messages" aria-live="polite"></div>
      <div class="muse-chips">
        <button type="button" data-chip="Mark me available for the next match">✅ I'm available</button>
        <button type="button" data-chip="Who is available for the next match?">👥 Who's available?</button>
        <button type="button" data-chip="Ask everyone for availability for the next match">📣 Ask availability</button>
        <button type="button" data-chip="Pick the best XI for the next match">🏏 Pick the XI</button>
        <button type="button" data-chip="__fixture">📅 Add a fixture</button>
        <button type="button" data-chip="__live">📝 Update score</button>
        <button type="button" data-chip="__upload">📷 Upload scorecard</button>
      </div>
      <form class="muse-form">
        <button type="button" class="muse-icon" data-act="attach" aria-label="Upload a scorecard photo">📎</button>
        <input class="muse-input" placeholder="Ask a question or tell me what to do…" autocomplete="off" />
        <button type="button" class="muse-icon" data-act="mic" aria-label="Speak">🎙️</button>
        <button type="submit" class="muse-send" aria-label="Send">➤</button>
      </form>
      <input type="file" class="muse-file" accept="image/*,.pdf,.heic" hidden />
    </div>
    <div class="muse-body" data-view="alerts" hidden>
      <div class="muse-alert-actions">
        <button type="button" data-act="readall">Mark all read</button>
        <button type="button" data-act="browser">🔔 Turn on browser alerts</button>
      </div>
      <div class="muse-alerts"></div>
    </div>`;
  document.body.appendChild(panel);

  const messagesEl = panel.querySelector(".muse-messages");
  const input = panel.querySelector(".muse-input");
  const fileInput = panel.querySelector(".muse-file");

  // The old "Assistant" button is hidden by muse.css: AI Muse replaces it.

  // ---------- Bell in the laptop header ----------
  function ensureBell() {
    const actions = document.querySelector(".shared-topbar-host .topbar-actions");
    if (!actions || actions.querySelector(".muse-bell")) return;
    const bell = document.createElement("button");
    bell.type = "button";
    bell.className = "muse-bell";
    bell.setAttribute("aria-label", "Notifications");
    bell.innerHTML = `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg><span class="muse-badge" hidden></span>`;
    // A drop-down list right under the bell (README: "AI Muse and notifications"). Click again to close.
    bell.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleBellMenu(bell);
    });
    const account = actions.querySelector(".account-button");
    actions.insertBefore(bell, account || null);
    updateBadges();
  }
  new MutationObserver(ensureBell).observe(document.documentElement, { childList: true, subtree: true });
  ensureBell();

  // ---------- Chat rendering ----------
  function addMessage(role, text, extra = {}) {
    history.push({ role, text, ...extra });
    history = history.slice(-30);
    write(sessionStorage, HISTORY_KEY, history);
    renderMessages();
  }

  function renderMessages() {
    if (!history.length) {
      messagesEl.innerHTML = `<div class="muse-msg muse-bot"><div class="muse-text">Hi! I'm AI Muse, your cricket assistant ✨ Ask me anything about players, clubs and matches, or tell me what to do and I'll do it for you:
• “Mark me available for Saturday”
• “Rahul and Nick are out for the next match”
• “Ask everyone for availability” / “Remind the players who haven't replied”
• “Pick the best XI for the next match”
• “Add a match vs Imran XI on Oct 12 at 10am”
• “We are 85/3 after 12 overs”
I always show you the plan first, and nothing changes until you tap Confirm.</div></div>`;
      return;
    }
    messagesEl.innerHTML = history
      .map((m, index) => {
        const links = (m.links || []).map((l) => `<a class="muse-link" href="${esc(l.href)}">${esc(l.label)} ›</a>`).join("");
        const confirm =
          m.action && !m.state
            ? `<button type="button" class="muse-confirm" data-confirm="${index}">${esc(m.action.confirm_label || "Confirm")}</button><button type="button" class="muse-cancel" data-cancel="${index}">Cancel</button>`
            : m.state === "done"
              ? `<span class="muse-done">✓ Done</span>`
              : m.state === "cancelled"
                ? `<span class="muse-cancelled">Cancelled</span>`
                : m.state === "working"
                  ? `<span class="muse-done">Working…</span>`
                  : "";
        return `<div class="muse-msg ${m.role === "user" ? "muse-user" : "muse-bot"}">${
          m.role !== "user" && m.source ? `<span class="muse-source">${esc(m.source)}</span>` : ""
        }<div class="muse-text">${esc(m.text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")}</div>${links || confirm ? `<div class="muse-actions">${links}${confirm}</div>` : ""}</div>`;
      })
      .join("");
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // Thinking dots for a moment, then the reply types out (README "AI Assistant answers (Gemini)").
  const TYPING_HTML = `<div class="muse-msg muse-bot muse-typing"><div class="muse-text"><span class="muse-dots" aria-label="Thinking"><i></i><i></i><i></i></span></div></div>`;
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function thinkAtLeast(startedAt) {
    const elapsed = Date.now() - startedAt;
    if (elapsed < 1200) await wait(1200 - elapsed);
  }
  function typeOutLast(container) {
    const bubbles = container.querySelectorAll(".muse-msg.muse-bot .muse-text");
    const el = bubbles[bubbles.length - 1];
    if (!el) return;
    const finalHtml = el.innerHTML;
    const full = el.textContent || "";
    const actions = el.parentElement.querySelector(".muse-actions");
    if (actions) actions.style.visibility = "hidden";
    let shown = 0;
    const step = Math.max(1, Math.ceil(full.length / 90)); // about 1.5 seconds for any length
    el.textContent = "";
    const timer = setInterval(() => {
      if (!el.isConnected) return clearInterval(timer);
      shown = Math.min(full.length, shown + step);
      el.textContent = full.slice(0, shown);
      container.scrollTop = container.scrollHeight;
      if (shown >= full.length) {
        clearInterval(timer);
        el.innerHTML = finalHtml;
        if (actions) actions.style.visibility = "";
        container.scrollTop = container.scrollHeight;
      }
    }, 16);
  }

  async function send(text) {
    const message = String(text || "").trim();
    if (!message || sending) return;
    if (message === "__fixture") {
      addMessage("bot", "Tell me the opponent, day and time, e.g. “Add a match vs Imran XI on Saturday at 10am, 20 overs”.");
      input.value = "Add a match vs ";
      input.focus();
      return;
    }
    if (message === "__live") {
      addMessage("bot", "Tell me the score as it goes, e.g. “We are 85/3 after 12 overs” or “They are 40/2 after 6 overs”. For the final result: “Heartlake 145/6, Imran XI 120/9, Heartlake won by 25 runs”.");
      input.value = "We are ";
      input.focus();
      return;
    }
    if (message === "Enter a match score") {
      addMessage("user", message);
      addMessage("bot", "Type or say the score like this:\n“Heartlake 145/6 in 20 overs, Imran XI 120/9. Heartlake won by 25 runs. Amit S 45 off 30, Nick 3 wickets, John 2 catches”\nI'll show you what I understood before saving.");
      return;
    }
    addMessage("user", message);
    sending = true;
    messagesEl.insertAdjacentHTML("beforeend", TYPING_HTML);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    const startedAt = Date.now();
    try {
      const res = await api("POST", "/api/muse", {
        message,
        focus_club_id: clubId(),
        history: history.slice(-8).map((m) => ({ role: m.role === "user" ? "user" : "assistant", text: m.text })),
      });
      await thinkAtLeast(startedAt);
      addMessage("bot", res.reply || "…", {
        source: res.source_label || "AI Muse",
        links: res.links || [],
        action: res.action && typeof res.action === "object" ? res.action : null,
      });
      typeOutLast(messagesEl);
      if (res.action_hint === "open_upload" || res.action === "open_upload") fileInput.click();
    } catch (e) {
      await thinkAtLeast(startedAt);
      addMessage("bot", `Sorry, something went wrong: ${e.message}`);
    } finally {
      sending = false;
      messagesEl.querySelector(".muse-typing")?.remove();
    }
  }

  // Carry out a planned task after the person taps Confirm (the server checks everything again).
  async function confirmAction(index) {
    const m = history[index];
    if (!m || !m.action || m.state) return;
    m.state = "working";
    renderMessages();
    try {
      const res = await api("POST", "/api/muse/execute", { tool: m.action.tool, args: m.action.args || {}, focus_club_id: clubId() });
      m.state = "done";
      write(sessionStorage, HISTORY_KEY, history);
      addMessage("bot", res.reply || "Done ✓", { source: "AI Muse", links: res.links || [] });
      pollNotifications();
    } catch (e) {
      m.state = "";
      write(sessionStorage, HISTORY_KEY, history);
      addMessage("bot", `I couldn't do that: ${e.message}`);
    }
  }

  function cancelAction(index) {
    const m = history[index];
    if (!m || !m.action || m.state) return;
    m.state = "cancelled";
    write(sessionStorage, HISTORY_KEY, history);
    addMessage("bot", "OK, I didn't change anything.");
  }

  // Show which AI model is answering (the LLM from the Assistant page).
  api("GET", "/api/llm/status")
    .then((status) => {
      const label = panel.querySelector(".muse-llm");
      if (!label || !status) return;
      const chat = { gemini: "Google Gemini", claude: "Claude" }[status.chat_provider] || "";
      label.textContent = chat
        ? `Powered by ${chat} · ask or tell me what to do`
        : status.provider === "ollama" && status.model
          ? `Powered by ${status.model} · ask or tell me what to do`
          : "Ask me anything or tell me what to do";
    })
    .catch(() => null);

  async function upload(file) {
    if (!file) return;
    addMessage("user", `📷 ${file.name}`);
    const form = new FormData();
    form.append("file", file);
    const qs = new URLSearchParams();
    if (clubId()) qs.set("focus_club_id", clubId());
    try {
      const response = await fetch(`/api/scorecards/upload?${qs}`, { method: "POST", headers: { "X-Auth-Token": token() }, body: form });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error((payload && payload.detail) || `Upload failed (${response.status})`);
      addMessage("bot", `Uploaded ✓ ${payload?.message || ""}`.trim(), {
        links: [{ label: "Open the digital scorecard", href: payload?.preview_url || "/scorecards" }],
      });
    } catch (e) {
      addMessage("bot", `Upload didn't work: ${e.message}`);
    } finally {
      fileInput.value = "";
    }
  }

  function toggleMic() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const micBtn = panel.querySelector('[data-act="mic"]');
    if (!SR) {
      addMessage("bot", "Voice input needs Chrome or Edge.");
      return;
    }
    if (recognition) {
      recognition.stop();
      return;
    }
    recognition = new SR();
    recognition.lang = "en-IN";
    recognition.interimResults = true;
    micBtn.classList.add("is-on");
    recognition.onresult = (event) => {
      const text = Array.from(event.results).map((r) => r[0].transcript).join(" ");
      input.value = text;
      if (event.results[event.results.length - 1].isFinal) send(input.value), (input.value = "");
    };
    recognition.onend = () => {
      recognition = null;
      micBtn.classList.remove("is-on");
    };
    recognition.start();
  }

  // ---------- Alerts ----------
  function timeAgo(iso) {
    const diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
    return new Date(iso).toLocaleDateString();
  }

  function renderAlerts() {
    const list = panel.querySelector(".muse-alerts");
    list.innerHTML = notifications.length
      ? notifications
          .map(
            (n) => `<button type="button" class="muse-alert${n.read ? "" : " unread"}" data-alert="${esc(n.id)}" data-link="${esc(n.link)}">
              <span class="muse-alert-kind">${esc(kindIcon(n.kind))}</span>
              <span class="muse-alert-copy"><strong>${esc(n.title)}</strong>${n.body ? `<small>${esc(n.body)}</small>` : ""}<em>${esc(timeAgo(n.created_at))}</em></span>
            </button>`
          )
          .join("")
      : `<p class="muse-empty">No alerts yet. You'll see availability requests, live score updates and results here.</p>`;
  }

  // ---------- Notifications drop-down under the 🔔 bell ----------
  let bellMenu = null;
  function closeBellMenu() {
    if (bellMenu) bellMenu.remove();
    bellMenu = null;
  }
  function toggleBellMenu(bell) {
    if (bellMenu) return closeBellMenu();
    bellMenu = document.createElement("div");
    bellMenu.className = "muse-bell-menu";
    bellMenu.setAttribute("role", "dialog");
    bellMenu.setAttribute("aria-label", "Notifications");
    const items = notifications.slice(0, 15);
    bellMenu.innerHTML = `
      <div class="muse-bell-head"><strong>Notifications</strong>${unread ? `<button type="button" data-bell="readall">Mark all read</button>` : ""}</div>
      <div class="muse-bell-list">${
        items.length
          ? items
              .map(
                (n) => `<button type="button" class="muse-alert${n.read ? "" : " unread"}" data-bell-alert="${esc(n.id)}" data-link="${esc(n.link)}">
                  <span class="muse-alert-kind">${esc(kindIcon(n.kind))}</span>
                  <span class="muse-alert-copy"><strong>${esc(n.title)}</strong>${n.body ? `<small>${esc(n.body)}</small>` : ""}<em>${esc(timeAgo(n.created_at))}</em></span>
                </button>`
              )
              .join("")
          : `<p class="muse-empty">No notifications yet.</p>`
      }</div>
      <button type="button" class="muse-bell-all" data-bell="all">Open all in the Assistant</button>`;
    document.body.appendChild(bellMenu);
    const rect = bell.getBoundingClientRect();
    bellMenu.style.top = `${rect.bottom + 8}px`;
    bellMenu.style.right = `${Math.max(8, window.innerWidth - rect.right)}px`;
    bellMenu.addEventListener("click", async (event) => {
      event.stopPropagation();
      const act = event.target.closest("[data-bell]")?.dataset.bell;
      if (act === "readall") {
        await api("POST", "/api/notifications/read", { all: true }).catch(() => null);
        await pollNotifications();
        closeBellMenu();
        return;
      }
      if (act === "all") {
        closeBellMenu();
        open("alerts");
        return;
      }
      const item = event.target.closest("[data-bell-alert]");
      if (item) {
        await api("POST", "/api/notifications/read", { ids: [item.dataset.bellAlert] }).catch(() => null);
        if (item.dataset.link) location.href = item.dataset.link;
        else {
          await pollNotifications();
          closeBellMenu();
        }
      }
    });
  }
  document.addEventListener("click", (event) => {
    if (bellMenu && !bellMenu.contains(event.target)) closeBellMenu();
  });
  window.addEventListener("resize", closeBellMenu);

  function kindIcon(kind) {
    if (String(kind).startsWith("scorecard")) return "📋";
    if (kind === "availability") return "📣";
    if (kind === "result") return "🏆";
    if (kind === "live_wicket") return "☝️";
    if (kind === "live_milestone") return "⭐";
    if (String(kind).startsWith("live")) return "🔴";
    return "🔔";
  }

  function updateBadges() {
    document.querySelectorAll(".muse-fab .muse-badge, .muse-bell .muse-badge, .muse-tab-count").forEach((el) => {
      el.hidden = !unread;
      el.textContent = unread > 9 ? "9+" : String(unread);
    });
  }

  async function pollNotifications() {
    try {
      const res = await api("GET", "/api/notifications");
      notifications = res.notifications || [];
      unread = res.unread || 0;
      updateBadges();
      if (!panel.hidden && tab === "alerts") renderAlerts();
      // Browser pop-ups for alerts we haven't shown yet
      const seen = new Set(read(localStorage, SEEN_KEY, []));
      const fresh = notifications.filter((n) => !n.read && !seen.has(n.id));
      if (fresh.length && "Notification" in window && Notification.permission === "granted" && seen.size) {
        fresh.slice(0, 3).forEach((n) => {
          try {
            const note = new Notification(n.title, { body: n.body || "", tag: n.id });
            note.onclick = () => {
              window.focus();
              if (n.link) location.href = n.link;
            };
          } catch (e) {
            /* ignore */
          }
        });
      }
      notifications.forEach((n) => seen.add(n.id));
      write(localStorage, SEEN_KEY, Array.from(seen).slice(-300));
    } catch (e) {
      /* signed out or offline: ignore */
    }
  }

  // ---------- Open / close ----------
  function setTab(name) {
    tab = name;
    panel.querySelectorAll(".muse-tabs [data-tab]").forEach((b) => b.classList.toggle("is-active", b.dataset.tab === name));
    panel.querySelectorAll(".muse-body").forEach((b) => (b.hidden = b.dataset.view !== name));
    if (name === "alerts") renderAlerts();
    else setTimeout(() => input.focus(), 50);
  }

  function open(name = "chat", message = "") {
    panel.hidden = false;
    document.body.classList.add("muse-open");
    renderMessages();
    setTab(name);
    if (message) send(message);
  }

  function close() {
    panel.hidden = true;
    document.body.classList.remove("muse-open");
  }

  fab.addEventListener("click", () => (panel.hidden ? open("chat") : close()));
  panel.querySelector(".muse-close").addEventListener("click", close);
  panel.querySelectorAll(".muse-tabs [data-tab]").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
  panel.querySelector(".muse-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value;
    input.value = "";
    send(text);
  });
  panel.addEventListener("click", async (event) => {
    const chip = event.target.closest("[data-chip]");
    if (chip) return chip.dataset.chip === "__upload" ? fileInput.click() : send(chip.dataset.chip);
    const confirmBtn = event.target.closest("[data-confirm]");
    if (confirmBtn) return confirmAction(Number(confirmBtn.dataset.confirm));
    const cancelBtn = event.target.closest("[data-cancel]");
    if (cancelBtn) return cancelAction(Number(cancelBtn.dataset.cancel));
    const act = event.target.closest("[data-act]")?.dataset.act;
    if (act === "attach") return fileInput.click();
    if (act === "mic") return toggleMic();
    if (act === "readall") {
      await api("POST", "/api/notifications/read", { all: true }).catch(() => null);
      return pollNotifications();
    }
    if (act === "browser") {
      if (!("Notification" in window)) return alertMsg("This browser doesn't support pop-up alerts.");
      const result = await Notification.requestPermission();
      return alertMsg(result === "granted" ? "Browser alerts are on. Keep a tab open to receive them." : "Browser alerts were not allowed.");
    }
    const alertBtn = event.target.closest("[data-alert]");
    if (alertBtn) {
      await api("POST", "/api/notifications/read", { ids: [alertBtn.dataset.alert] }).catch(() => null);
      if (alertBtn.dataset.link) location.href = alertBtn.dataset.link;
      else pollNotifications();
    }
  });
  fileInput.addEventListener("change", () => upload(fileInput.files && fileInput.files[0]));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && bellMenu) closeBellMenu();
    if (event.key === "Escape" && !panel.hidden) close();
  });

  function alertMsg(text) {
    const box = panel.querySelector(".muse-alert-actions");
    let note = box.querySelector(".muse-note");
    if (!note) {
      note = document.createElement("p");
      note.className = "muse-note";
      box.appendChild(note);
    }
    note.textContent = text;
  }

  window.CCMuse = { open, close, send };
  pollNotifications();
  setInterval(() => {
    if (!document.hidden) pollNotifications();
  }, POLL_MS);
})();
