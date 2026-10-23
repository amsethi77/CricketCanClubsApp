/*
 * /scorecards/upload: captains, club admins and site admins upload a scorecard photo.
 * POST /api/scorecards/upload runs the smart checks (same photo, same match, mistakes, optional
 * Ollama check) and we then open the full digital scorecard (/scorecards/{id}?preview=1) with
 * "Looks right, publish" / "Something's wrong". README: "Scorecard uploads: checks, review and duplicates".
 */
(() => {
  const TOKEN_KEY = "cricketClubAppAuthToken";
  const form = document.getElementById("scuForm");
  const gate = document.getElementById("scuGate");
  const clubEl = document.getElementById("scuClub");
  const fileEl = document.getElementById("scuFile");
  const previewEl = document.getElementById("scuPreview");
  const dropText = document.getElementById("scuDropText");
  const seasonEl = document.getElementById("scuSeason");
  const msgEl = document.getElementById("scuMsg");
  const token = () => {
    try {
      return localStorage.getItem(TOKEN_KEY) || "";
    } catch (error) {
      return "";
    }
  };
  const esc = (v) =>
    String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");

  let reader = { label: "the photo reader", speed: "this can take a minute" };
  let readerToken = "";
  try {
    readerToken = localStorage.getItem("cricketClubAppAuthToken") || "";
  } catch (e) {
    readerToken = "";
  }
  fetch("/api/scorecards/reader", { headers: readerToken ? { "X-Auth-Token": readerToken } : {} })
    .then((response) => (response.ok ? response.json() : null))
    .then((data) => {
      if (!data) return;
      reader = data;
      const note = document.createElement("p");
      note.className = "scu-reader";
      note.textContent = `Photos are read by: ${data.label}`;
      form.querySelector("button[type=submit]").before(note);
    })
    .catch(() => null);

  function say(text, bad) {
    msgEl.textContent = text || "";
    msgEl.classList.toggle("bad", Boolean(bad));
  }

  fileEl.addEventListener("change", () => {
    const file = fileEl.files[0];
    if (!file) return;
    dropText.textContent = file.name;
    if (/^image\/(jpeg|png|webp|gif)$/i.test(file.type)) {
      previewEl.src = URL.createObjectURL(file);
      previewEl.hidden = false;
    } else {
      previewEl.hidden = true;
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = fileEl.files[0];
    if (!file) return say("Choose a photo first.", true);
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    // Live progress with a seconds counter, so the wait feels shorter (README "Faster photo reading").
    const started = Date.now();
    const tick = () => {
      const secs = Math.round((Date.now() - started) / 1000);
      const step = secs < 3 ? "📤 Uploading the photo" : secs < 45 ? `🤖 Reading the scorecard with ${reader.label}` : "🤖 Still reading - handwritten cards can take a little longer";
      say(`${step}… ${secs}s (${reader.speed}). Keep this page open.`);
    };
    tick();
    const timer = setInterval(tick, 1000);
    const body = new FormData();
    body.append("file", file);
    const qs = new URLSearchParams({ focus_club_id: clubEl.value || "" });
    if (seasonEl.value.trim()) qs.set("season", seasonEl.value.trim());
    try {
      const response = await fetch(`/api/scorecards/upload?${qs}`, { method: "POST", headers: { "X-Auth-Token": token() }, body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Upload failed.");
      clearInterval(timer);
      say(data.message || "Uploaded.");
      location.href = data.preview_url || `/scorecards/${encodeURIComponent(data.upload?.id || "")}?preview=1`;
    } catch (error) {
      clearInterval(timer);
      say(error.message, true);
      button.disabled = false;
    }
  });

  (async () => {
    if (!token()) {
      location.href = `/signin?next=${encodeURIComponent("/scorecards/upload")}`;
      return;
    }
    try {
      const response = await fetch("/api/auth/me", { headers: { "X-Auth-Token": token() } });
      const data = await response.json();
      const user = data.user || {};
      if (!(user.permissions || []).includes("score_matches")) {
        gate.innerHTML = "Scorecard photos are uploaded by captains and club admins. Ask your captain to upload it, or <a href=\"/scorecards\">browse scorecards</a>.";
        gate.hidden = false;
        return;
      }
      const clubs = data.visible_clubs || data.clubs || [];
      clubEl.innerHTML = clubs.map((c) => `<option value="${esc(c.id)}"${c.id === user.current_club_id ? " selected" : ""}>${esc(c.name)}</option>`).join("");
      clubEl.closest("label").hidden = clubs.length < 2;
      form.hidden = false;
    } catch (error) {
      gate.textContent = "Couldn't check your account. Please sign in again.";
      gate.hidden = false;
    }
  })();
})();
