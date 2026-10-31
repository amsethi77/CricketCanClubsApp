/*
 * Public AI Assistant for signed-out visitors (read-only).
 * Loaded by public_header.js on every public page, including Sign In and Register (Oct 2026).
 * Questions the built-in rules can't answer go to the LLM assistant on public data only.
 * Talks to POST /api/public/muse. Actions (saving scores, uploads, availability, alerts)
 * reply with Sign in / Register buttons.
 * Documented in README.md -> "AI Assistant and notifications" -> "Public AI Assistant".
 */
function startPublicMuse() {
  if (window.CCMusePublic) return;
  // Signed-in pages use the full AI Assistant (muse.js) instead.
  if (document.querySelector(".page-topbar")) return;
  const path = location.pathname.replace(/\/+$/, "") || "/";
  const onAuthPage = path === "/signin" || path === "/register";

  const HISTORY_KEY = "ccMusePublicHistory";
  const esc = (v) =>
    String(v ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  let history = [];
  try {
    history = JSON.parse(sessionStorage.getItem(HISTORY_KEY) || "[]") || [];
  } catch (e) {
    history = [];
  }
  const save = () => {
    try {
      sessionStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-30)));
    } catch (e) {
      /* ignore */
    }
  };

  const css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = "/assets/muse.css?v=20261030f";
  document.head.appendChild(css);

  const fab = document.createElement("button");
  fab.type = "button";
  fab.className = `muse-fab muse-fab-public${onAuthPage ? " muse-fab-auth" : ""}`;
  // Plans (README "Plans: what each group can use"): signed-out visitors can't use the AI Assistant;
  // the button takes them to Sign in. No button at all on the sign-in / register pages.
  let token = "";
  try {
    token = localStorage.getItem("cricketClubAppAuthToken") || "";
  } catch (e) {
    token = "";
  }
  fab.setAttribute("aria-label", token ? "Ask the AI assistant" : "AI Assistant: sign in to use it");
  fab.innerHTML = token
    ? `<span class="muse-fab-icon" aria-hidden="true">✨</span><strong>AI Assistant</strong>`
    : `<span class="muse-fab-icon" aria-hidden="true">🔒</span><strong>AI Assistant · Sign in</strong>`;
  if (!onAuthPage) document.body.appendChild(fab);

  const panel = document.createElement("aside");
  panel.className = "muse-panel";
  panel.hidden = true;
  panel.setAttribute("aria-label", "AI Assistant");
  panel.innerHTML = `
    <header class="muse-head">
      <div class="muse-title"><span aria-hidden="true">✨</span><div><strong>AI Assistant</strong><small>Ask me anything about cricket, your club or the app</small></div></div>
      <button type="button" class="muse-close" aria-label="Close">✕</button>
    </header>
    <div class="muse-body" data-view="chat">
      <div class="muse-messages" aria-live="polite"></div>
      <div class="muse-chips">
        <button type="button" data-chip="What's the live score?">🔴 Live scores</button>
        <button type="button" data-chip="Latest results">🏆 Latest results</button>
        <button type="button" data-chip="Latest scorecards">📋 Scorecards</button>
        <button type="button" data-chip="Top run scorers">🏏 Top run scorers</button>
        <button type="button" data-chip="Show club rankings">📊 Club rankings</button>
        <button type="button" data-chip="How do I register my club?">✨ Join</button>
      </div>
      <form class="muse-form muse-form-public">
        <input class="muse-input" placeholder="Ask me anything…" autocomplete="off" maxlength="300" />
        <button type="button" class="muse-icon" data-act="mic" aria-label="Speak">🎙️</button>
        <button type="submit" class="muse-send" aria-label="Send">➤</button>
      </form>
      ${token ? "" : '<p class="muse-signin-note"><a href="/signin">Sign in</a> to score matches, upload scorecards and get alerts.</p>'}
    </div>`;
  document.body.appendChild(panel);

  const messagesEl = panel.querySelector(".muse-messages");
  const input = panel.querySelector(".muse-input");
  let sending = false;
  let recognition = null;

  function render() {
    if (!history.length) {
      messagesEl.innerHTML = `<div class="muse-msg muse-bot"><div class="muse-text">Hi! I'm your AI Assistant for Cricket Canada Clubs ✨ Ask me about live scores, results, scorecards by date, club rankings, how a player is doing, or how to join. Sign in and I can also mark your availability, update scores and more.</div></div>`;
      return;
    }
    messagesEl.innerHTML = history
      .map((m) => {
        const links = (m.links || [])
          .map((l) => `<a class="muse-link${/sign in|register/i.test(l.label) ? " muse-cta" : ""}" href="${esc(l.href)}">${esc(l.label)}${/sign in|register/i.test(l.label) ? "" : " ›"}</a>`)
          .join("");
        return `<div class="muse-msg ${m.role === "user" ? "muse-user" : "muse-bot"}"><div class="muse-text">${esc(m.text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")}</div>${
          links ? `<div class="muse-actions">${links}</div>` : ""
        }</div>`;
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
    history.push({ role: "user", text: message });
    render();
    sending = true;
    messagesEl.insertAdjacentHTML("beforeend", TYPING_HTML);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    const startedAt = Date.now();
    let answered = false;
    try {
      // Signed in: the full AI Assistant (POST /api/muse), same as on the dashboard. README "AI Assistant answers (Gemini)".
      const earlier = history.slice(0, -1).slice(-8).map((m) => ({ role: m.role === "user" ? "user" : "assistant", text: m.text }));
      const response = await fetch(token ? "/api/muse" : "/api/public/muse", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json", ...(token ? { "X-Auth-Token": token } : {}) },
        body: JSON.stringify(token ? { message, history: earlier } : { message }),
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401 && token) throw new Error("please sign in again");
      if (!response.ok) throw new Error(data.detail || "Something went wrong");
      const links = (data.links || []).filter((link) => !(token && /^\/(signin|register)/.test(String(link.href || ""))));
      // Tasks that need a Confirm step are done on the dashboard's assistant.
      if (token && data.action && typeof data.action === "object") links.push({ label: "Confirm on my dashboard", href: "/dashboard" });
      await thinkAtLeast(startedAt);
      history.push({ role: "bot", text: data.reply || "…", links });
      answered = true;
    } catch (e) {
      await thinkAtLeast(startedAt);
      history.push({ role: "bot", text: `Sorry, I couldn't answer that right now (${e.message}).` });
    } finally {
      sending = false;
      save();
      render();
      if (answered) typeOutLast(messagesEl);
    }
  }

  function open(message = "") {
    panel.hidden = false;
    document.body.classList.add("muse-open");
    render();
    setTimeout(() => input.focus(), 50);
    if (message) send(message);
  }
  function close() {
    panel.hidden = true;
    document.body.classList.remove("muse-open");
  }

  function toggleMic() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const btn = panel.querySelector('[data-act="mic"]');
    if (!SR) {
      history.push({ role: "bot", text: "Voice input needs Chrome or Edge." });
      return render();
    }
    if (recognition) return recognition.stop();
    recognition = new SR();
    recognition.lang = "en-IN";
    recognition.interimResults = true;
    btn.classList.add("is-on");
    recognition.onresult = (event) => {
      input.value = Array.from(event.results).map((r) => r[0].transcript).join(" ");
      if (event.results[event.results.length - 1].isFinal) {
        const text = input.value;
        input.value = "";
        send(text);
      }
    };
    recognition.onend = () => {
      recognition = null;
      btn.classList.remove("is-on");
    };
    recognition.start();
  }

  fab.addEventListener("click", () => {
    if (!token) {
      window.location.href = `/signin?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
      return;
    }
    panel.hidden ? open() : close();
  });
  panel.querySelector(".muse-close").addEventListener("click", close);
  panel.querySelector(".muse-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value;
    input.value = "";
    send(text);
  });
  panel.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-chip]");
    if (chip) return send(chip.dataset.chip);
    if (event.target.closest('[data-act="mic"]')) toggleMic();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) close();
  });

  window.CCMusePublic = { open, close, send };
}

if (document.body) startPublicMuse();
else document.addEventListener("DOMContentLoaded", startPublicMuse);
