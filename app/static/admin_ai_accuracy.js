// Admin Center -> "AI accuracy" (Nov 18 2026, Amit: "accuracy is 60-70% today, it should keep learning and be 90%+").
// Every card a person fixed after the AI read it is compared with the AI's own reading. Server: GET
// /api/admin/ai-accuracy. README "AI accuracy (Admin Center)".
(function adminAiAccuracy() {
  const root = document.getElementById("adminAiAccuracy");
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
  const FIELD = {
    "batter name": "Batter names",
    "bowler name": "Bowler names",
    "batter runs": "Batter runs",
    "batter balls": "Balls faced",
    "batter fours": "4s",
    "batter sixes": "6s",
    "batter ones": "1s",
    "batter twos": "2s",
    "batter threes": "3s",
    "batter dots": "Dot balls",
    "bowler overs": "Bowler overs",
    "bowler maidens": "Maidens",
    "bowler runs_conceded": "Bowler runs",
    "bowler wickets": "Bowler wickets",
    "innings runs": "Innings total",
    "innings wickets": "Innings wickets",
    "innings overs": "Innings overs",
    "innings number": "Innings 1 or 2",
    "batting team": "Batting team",
    extras: "Extras",
    "match date": "Match date",
    captain: "Captains",
    "man of the match": "Man of the match",
  };
  const label = (field) => FIELD[field] || field;
  const tone = (percent, target) => (percent >= target ? "is-good" : percent >= target - 15 ? "is-mid" : "is-bad");
  const bar = (percent, target) =>
    `<span class="aac-bar ${tone(percent, target)}"><i style="width:${Math.max(2, Math.min(100, percent))}%"></i></span>`;
  const monthName = (month) => {
    const [y, m] = String(month).split("-").map(Number);
    return y && m ? new Date(y, m - 1, 1).toLocaleString([], { month: "short", year: "numeric" }) : esc(month);
  };
  let loaded = false;

  async function load() {
    const response = await fetch("/api/admin/ai-accuracy", { headers }).catch(() => null);
    const data = response && response.ok ? await response.json().catch(() => null) : null;
    if (!data) {
      root.innerHTML = '<p class="empty-state">Couldn\'t work out the accuracy. Only the superadmin can see this.</p>';
      return;
    }
    loaded = true;
    render(data);
  }

  function render(data) {
    const target = Number(data.target || 90);
    const overall = data.overall || {};
    if (!overall.checked) {
      root.innerHTML = `<p class="empty-state">No scorecard has been fixed by a person after the AI read it yet, so there is nothing to compare. Each time someone fixes an AI-read card with ✏️ Edit and saves it, it is counted here.</p>`;
      return;
    }
    const pct = Number(overall.percent || 0);
    const head = `
      <div class="aac-head ${tone(pct, target)}">
        <strong>${pct.toFixed(1)}%</strong>
        <div><b>of the fields the AI read were right</b><small>${Number(overall.right).toLocaleString()} of ${Number(overall.checked).toLocaleString()} fields on ${overall.cards} fixed card${overall.cards === 1 ? "" : "s"} · goal ${target}%</small></div>
      </div>
      <div class="aac-learn">🧠 The AI has learned <b>${data.learned.names}</b> name fix${data.learned.names === 1 ? "" : "es"} and keeps <b>${data.learned.examples}</b> fixed card${data.learned.examples === 1 ? "" : "s"} as worked examples. ${data.published_as_read ? `${data.published_as_read} card${data.published_as_read === 1 ? " was" : "s were"} published exactly as the AI read ${data.published_as_read === 1 ? "it" : "them"} (not counted - nobody checked them line by line).` : ""}</div>`;
    const groups = (data.groups || [])
      .map((g) => `<div class="aac-group"><span>${esc(g.group)}</span>${bar(g.percent, target)}<b>${g.percent.toFixed(1)}%</b><small>${g.right}/${g.checked}</small></div>`)
      .join("");
    const fields = (data.fields || [])
      .map((f) => `<tr><td>${esc(label(f.field))}</td><td class="aac-barcell">${bar(f.percent, target)}</td><td><b>${f.percent.toFixed(1)}%</b></td><td>${f.right}/${f.checked}</td></tr>`)
      .join("");
    const months = (data.months || [])
      .map((m) => `<tr><td>${monthName(m.month)}</td><td>${m.cards}</td><td class="aac-barcell">${bar(m.percent, target)}</td><td><b>${m.percent.toFixed(1)}%</b></td></tr>`)
      .join("");
    const cards = (data.cards || [])
      .map((c) => {
        const misses = (c.misses || [])
          .map((m) => `<li>${esc(m.where)} · <b>${esc(label(m.field))}</b>: card <code>${esc(m.card)}</code>, AI <code>${esc(m.ai || "—")}</code></li>`)
          .join("");
        return `<details class="aac-card"><summary><span class="aac-pill ${tone(c.percent, target)}">${c.percent.toFixed(0)}%</span><span class="aac-title">${esc(c.title)}</span><small>${esc(c.date)}${c.model ? ` · ${esc(c.model)}` : ""} · ${c.right}/${c.checked}</small></summary>${misses ? `<ul>${misses}</ul>${c.more_misses ? `<p class="aac-more">+ ${c.more_misses} more</p>` : ""}` : "<p>Everything the AI read was right.</p>"}<a href="/scorecards/a-${encodeURIComponent(c.id)}">Open the card</a></details>`;
      })
      .join("");
    root.innerHTML = `
      ${head}
      <div class="aac-groups">${groups}</div>
      <h3>By month (when the card was uploaded)</h3>
      <div class="aac-scroll"><table class="aac-table"><thead><tr><th>Month</th><th>Cards</th><th></th><th>Right</th></tr></thead><tbody>${months}</tbody></table></div>
      <h3>Every field (weakest first)</h3>
      <div class="aac-scroll"><table class="aac-table"><thead><tr><th>Field</th><th></th><th>Right</th><th>Fields</th></tr></thead><tbody>${fields}</tbody></table></div>
      <h3>Card by card (tap one to see what the AI got wrong)</h3>
      <div class="aac-cards">${cards}</div>`;
  }

  document.addEventListener("click", (event) => {
    if (event.target.closest('[data-admin-section="ai-accuracy"]') && !loaded) load();
  });
  if (!document.getElementById("adminSectionAiAccuracy")?.hidden) load();
})();
