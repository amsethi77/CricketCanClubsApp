/*
 * Insights panel on the Assistant page: your form, a next-innings prediction,
 * your club's outlook, improvement tips, and one-tap questions for the chat.
 * Data: GET /api/insights/me (computed from the club's own stored stats).
 */
(() => {
  if (document.body.dataset.dashboardWidget !== "assistant") return;
  const section = document.getElementById("assistant");
  const chatMessages = document.getElementById("chatMessages");
  const chatInput = document.getElementById("chatInput");
  const chatForm = document.getElementById("chatForm");
  if (!section || !chatMessages) return;

  const esc = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const panel = document.createElement("div");
  panel.id = "insightsPanel";
  panel.className = "ins-panel";
  panel.innerHTML = `<div class="ins-loading">Loading your insights…</div>`;
  chatMessages.insertAdjacentElement("beforebegin", panel);

  function ask(question) {
    if (!chatInput || !chatForm) return;
    chatInput.value = question;
    if (typeof chatForm.requestSubmit === "function") chatForm.requestSubmit();
    else chatForm.dispatchEvent(new Event("submit", { cancelable: true }));
    chatMessages.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const FORM_CLASS = { hot: "hot", cold: "cold", steady: "steady", unknown: "unknown" };

  function tipsHtml(tips) {
    if (!tips || !tips.length) return `<p class="ins-muted">No clear improvement areas in the recorded data yet.</p>`;
    return `<ul class="ins-tips">${tips
      .slice(0, 4)
      .map((tip) => `<li><span class="ins-tip-area">${esc(tip.area)}</span><strong>${esc(tip.title)}</strong><span>${esc(tip.why)}</span></li>`)
      .join("")}</ul>`;
  }

  function render(data) {
    const player = data.player;
    const club = data.club;
    const cards = [];

    if (player) {
      const f = player.form || {};
      const p = player.prediction || {};
      const c = player.career || {};
      const recent = (f.recent_runs || []).map((r) => `<span class="ins-run">${esc(r)}</span>`).join("");
      cards.push(`
        <article class="ins-card">
          <p class="ins-kicker">Your form</p>
          <div class="ins-form-row">
            <span class="ins-form ${FORM_CLASS[f.key] || "unknown"}">${esc(f.label || "–")}</span>
            <span class="ins-muted">trend ${esc(f.trend || "flat")}</span>
          </div>
          ${recent ? `<div class="ins-runs" title="Last innings, oldest to newest">${recent}</div>` : ""}
          <p class="ins-muted">${esc(c.runs)} runs · avg ${esc(c.average)} · best ${esc(c.highest)}${c.strike_rate ? ` · SR ${esc(c.strike_rate)}` : ""}</p>
        </article>`);
      cards.push(`
        <article class="ins-card">
          <p class="ins-kicker">Next innings prediction</p>
          <p class="ins-big">${esc(p.expected_runs ?? "–")}<small> runs</small></p>
          <p class="ins-muted">Likely ${esc((p.range || [])[0])}–${esc((p.range || [])[1])} · ${esc(p.chance_25_plus)}% chance of 25+</p>
          <p class="ins-conf">Confidence: ${esc(p.confidence)} (${esc(p.based_on_innings)} innings)</p>
        </article>`);
    }

    if (club) {
      const r = club.record || {};
      const next = club.next_match;
      cards.push(`
        <article class="ins-card">
          <p class="ins-kicker">${esc(club.club?.name || "Your club")}</p>
          ${
            r.played
              ? `<p class="ins-big">${esc(r.win_rate)}%<small> wins</small></p><p class="ins-muted">Won ${esc(r.won)} of ${esc(r.played)} · ranked ${esc(r.rank)} of ${esc(r.clubs_ranked)}</p>`
              : `<p class="ins-muted">No results recorded yet, so no ranking.</p>`
          }
          ${
            next
              ? `<p class="ins-conf">Next: ${esc(next.date)} vs ${esc(next.opponent)} · ${esc(next.win_chance)}% win chance</p>`
              : `<p class="ins-conf">No upcoming fixture on record.</p>`
          }
        </article>`);
    }

    const xi = data.best_xi;
    const outlook = data.outlook;
    let xiHtml = "";
    if (xi && xi.xi && xi.xi.length) {
      xiHtml = `
        <div class="ins-block">
          <p class="ins-kicker">Suggested playing XI${xi.fixture ? ` · vs ${esc(xi.fixture.opponent)} (${esc(xi.fixture.date)})` : ""}</p>
          ${xi.fixture ? "" : `<p class="ins-muted">No upcoming fixture on record, so this is the strongest XI on current stats.</p>`}
          <ol class="ins-xi">${xi.xi
            .map(
              (p) => `<li><strong>${esc(p.name)}</strong><span>${esc(p.reason)}</span>${
                p.status !== "available" ? `<em class="ins-pill ${p.status === "maybe" ? "maybe" : "noresp"}">${esc(p.status)}</em>` : ""
              }</li>`
            )
            .join("")}</ol>
          ${(xi.notes || []).map((n) => `<p class="ins-conf">${esc(n)}</p>`).join("")}
        </div>`;
    }
    let outlookHtml = "";
    if (outlook) {
      const pr = outlook.projected || {};
      outlookHtml = `
        <div class="ins-block">
          <p class="ins-kicker">Season outlook</p>
          ${
            outlook.remaining_games
              ? `<p class="ins-big">${esc(pr.wins)}<small> projected wins from ${esc(pr.played)}</small></p>
                 <p class="ins-muted">${esc(outlook.remaining_games)} games left · projected ${esc(pr.win_rate)}%${pr.rank ? ` · around #${esc(pr.rank)} of ${esc(pr.clubs)}` : ""}</p>
                 <ul class="ins-mini">${(outlook.fixtures || [])
                   .slice(0, 5)
                   .map((g) => `<li><span>${esc(g.date)} vs ${esc(g.opponent)}</span><strong>${esc(g.win_chance)}%</strong></li>`)
                   .join("")}</ul>`
              : `<p class="ins-muted">No remaining fixtures on record. Add the rest of the season's fixtures to see a projection.</p>`
          }
        </div>`;
    }

    const playerName = player?.player?.name || "";
    const clubName = club?.club?.name || "";
    const chips = [
      playerName && `How can ${playerName} improve?`,
      playerName && `Predict ${playerName} next match`,
      clubName && `How can ${clubName} improve its ranking?`,
      clubName && `Suggest the best playing XI for ${clubName}`,
      clubName && `Season outlook for ${clubName}`,
      clubName && `Tell me about ${clubName}`,
      "Who is the top run scorer?",
      "Show club rankings",
    ].filter(Boolean);

    panel.innerHTML = `
      <div class="ins-head">
        <div>
          <p class="section-kicker">Insights</p>
          <h3>Predictions and tips from your stats</h3>
        </div>
        <span class="ins-note">Updates as more matches are scored</span>
      </div>
      ${cards.length ? `<div class="ins-grid">${cards.join("")}</div>` : `<p class="ins-muted">Link your account to a player profile to see personal insights.</p>`}
      <div class="ins-columns">
        ${player ? `<div class="ins-block"><p class="ins-kicker">How you can improve</p>${tipsHtml(player.recommendations)}</div>` : ""}
        ${club ? `<div class="ins-block"><p class="ins-kicker">How ${esc(clubName)} can climb the rankings</p>${tipsHtml(club.recommendations)}</div>` : ""}
      </div>
      ${xiHtml || outlookHtml ? `<div class="ins-columns">${xiHtml}${outlookHtml}</div>` : ""}
      <div class="ins-chips" aria-label="Ask the assistant">
        ${chips.map((q) => `<button type="button" class="ins-chip" data-ask="${esc(q)}">${esc(q)}</button>`).join("")}
      </div>`;
  }

  panel.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-ask]");
    if (chip) ask(chip.dataset.ask);
  });

  (async () => {
    try {
      const token = localStorage.getItem("cricketClubAppAuthToken") || "";
      const response = await fetch("/api/insights/me", { headers: { Accept: "application/json", "X-Auth-Token": token } });
      if (!response.ok) throw new Error("Insights unavailable");
      render(await response.json());
    } catch (error) {
      panel.innerHTML = `<p class="ins-muted">Insights couldn't be loaded right now. You can still ask the assistant below.</p>`;
    }
  })();
})();
