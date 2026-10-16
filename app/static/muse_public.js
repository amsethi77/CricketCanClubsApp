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
  css.href = "/assets/muse.css?v=20261005a";
  document.head.appendChild(css);

  const fab = document.createElement("button");
  fab.type = "button";
  fab.className = `muse-fab muse-fab-public${onAuthPage ? " muse-fab-auth" : ""}`;
  fab.setAttribute("aria-label", "Ask the AI assistant");
  fab.innerHTML = `<span class="muse-fab-icon" aria-hidden="true">✨</span><strong>AI Assistant</strong>`;
  document.body.appendChild(fab);

  const panel = document.createElement("aside");
  panel.className = "muse-panel";
  panel.hidden = true;
  panel.setAttribute("aria-label", "AI Assistant");
  panel.innerHTML = `
    <header class="muse-head">
      <div class="muse-title"><span aria-hidden="true">✨</span><div><strong>AI Assistant</strong><small>Ask about scores, results, players and clubs</small></div></div>
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
        <input class="muse-input" placeholder="Ask about scores, players, clubs…" autocomplete="off" maxlength="300" />
        <button type="button" class="muse-icon" data-act="mic" aria-label="Speak">🎙️</button>
        <button type="submit" class="muse-send" aria-label="Send">➤</button>
      </form>
      <p class="muse-signin-note"><a href="/signin">Sign in</a> to score matches, upload scorecards and get alerts.</p>
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
        return `<div class="muse-msg ${m.role === "user" ? "muse-user" : "muse-bot"}"><div class="muse-text">${esc(m.text)}</div>${
          links ? `<div class="muse-actions">${links}</div>` : ""
        }</div>`;
      })
      .join("");
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  async function send(text) {
    const message = String(text || "").trim();
    if (!message || sending) return;
    history.push({ role: "user", text: message });
    render();
    sending = true;
    messagesEl.insertAdjacentHTML("beforeend", `<div class="muse-msg muse-bot muse-typing"><div class="muse-text">…</div></div>`);
    try {
      const response = await fetch("/api/public/muse", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Something went wrong");
      history.push({ role: "bot", text: data.reply || "…", links: data.links || [] });
    } catch (e) {
      history.push({ role: "bot", text: `Sorry, I couldn't answer that right now (${e.message}).` });
    } finally {
      sending = false;
      save();
      render();
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

  fab.addEventListener("click", () => (panel.hidden ? open() : close()));
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
