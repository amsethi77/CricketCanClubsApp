/*
 * Cricinfo-style digital scorecard for one approved archive upload.
 * Tabs: "Scorecard" (innings tables) and "Original scorecard" (the uploaded photo).
 * ?preview=1 (signed-in scorers): the full digital scorecard of a fresh upload, with the smart
 * check results and "Looks right, publish" / "Something's wrong" buttons
 * (README: "Scorecard uploads: checks, review and duplicates").
 */
(() => {
  const headerEl = document.getElementById("scHeader");
  const cardPanel = document.getElementById("scPanelCard");
  const photoPanel = document.getElementById("scPanelPhoto");
  const backEl = document.getElementById("scBack");
  const tabs = Array.from(document.querySelectorAll(".sc-tab"));
  const id = decodeURIComponent(location.pathname.replace(/\/+$/, "").split("/").pop() || "");
  const DASH = "–";
  const preview = new URLSearchParams(location.search).get("preview") === "1";
  const token = () => {
    try {
      return localStorage.getItem("cricketClubAppAuthToken") || "";
    } catch (error) {
      return "";
    }
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function num(value) {
    return value === null || value === undefined || value === "" ? DASH : escapeHtml(value);
  }

  function showTab(name) {
    tabs.forEach((tab) => {
      const on = tab.dataset.tab === name;
      tab.classList.toggle("is-active", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
    cardPanel.hidden = name !== "card";
    photoPanel.hidden = name !== "photo";
    history.replaceState(null, "", `${location.pathname}${location.search}${name === "photo" ? "#photo" : ""}`);
  }

  function headerMarkup(sc) {
    const facts = [sc.match_type, sc.overs_limit ? `${sc.overs_limit} overs` : "", sc.venue, sc.date_label].filter(Boolean);
    const [first, second] = sc.innings;
    const winner = (sc.result || "").toLowerCase();
    const teamLine = (inn) => {
      const lost = sc.result && !winner.startsWith(String(inn.team || "").toLowerCase());
      return `
        <div class="sc-hero-team${lost ? " is-muted" : ""}">
          <span class="sc-hero-name">${escapeHtml(inn.team)}</span>
          <span class="sc-hero-score">
            ${inn.overs ? `<small>(${escapeHtml(inn.overs)} ov)</small>` : ""}
            <strong>${inn.runs === null || inn.runs === undefined ? DASH : escapeHtml(inn.score)}</strong>
          </span>
        </div>`;
    };
    return `
      <p class="sc-meta">${facts.map(escapeHtml).join(" · ")}</p>
      <h1 class="sc-title">${escapeHtml(sc.title)}</h1>
      <div class="sc-hero-teams">${teamLine(first)}${teamLine(second)}</div>
      <p class="sc-hero-result">${escapeHtml(sc.result || "Result not recorded")}</p>
    `;
  }

  function renderHeader(sc) {
    headerEl.innerHTML = headerMarkup(sc);
    document.title = `${sc.title} · ${sc.date_label} · Scorecard`;
  }

  function battingTable(inn) {
    const rows = inn.batting
      .map(
        (b) => `
        <tr>
          <td class="sc-name"${b.dismissal ? ` data-how="${escapeHtml(b.dismissal)}"` : ""}>${escapeHtml(b.name)}${b.not_out ? '<span class="sc-notout">*</span>' : ""}</td>
          <td class="sc-how">${escapeHtml(b.dismissal || "")}</td>
          <td class="sc-num sc-strong">${num(b.runs)}</td>
          <td class="sc-num">${num(b.balls)}</td>
          <td class="sc-num sc-hide-sm">${num(b.fours)}</td>
          <td class="sc-num sc-hide-sm">${num(b.sixes)}</td>
          <td class="sc-num">${num(b.strike_rate)}</td>
        </tr>`
      )
      .join("");
    const extras = `
      <tr class="sc-extras">
        <td class="sc-name"${inn.extras_detail ? ` data-how="(${escapeHtml(inn.extras_detail)})"` : ""}>Extras</td>
        <td class="sc-how">${inn.extras_detail ? `(${escapeHtml(inn.extras_detail)})` : ""}</td>
        <td class="sc-num sc-strong">${num(inn.extras)}</td>
        <td colspan="4" class="sc-fill"></td>
      </tr>`;
    const totalText =
      inn.runs === null || inn.runs === undefined
        ? DASH
        : `${escapeHtml(inn.runs)}${inn.wickets !== null && inn.wickets !== undefined ? `/${escapeHtml(inn.wickets)}` : ""}`;
    const total = `
      <tr class="sc-total">
        <td class="sc-name"${inn.overs ? ` data-how="${escapeHtml(inn.overs)} Ov"` : ""}>Total</td>
        <td class="sc-how">${inn.overs ? `${escapeHtml(inn.overs)} Ov` : ""}</td>
        <td class="sc-num sc-strong">${totalText}</td>
        <td colspan="4" class="sc-fill"></td>
      </tr>`;
    return `
      <div class="sc-table-wrap">
        <table class="sc-table sc-batting">
          <thead>
            <tr><th class="sc-name">Batting</th><th class="sc-how"></th><th class="sc-num">R</th><th class="sc-num">B</th><th class="sc-num sc-hide-sm">4s</th><th class="sc-num sc-hide-sm">6s</th><th class="sc-num">SR</th></tr>
          </thead>
          <tbody>
            ${rows || `<tr><td colspan="7" class="sc-empty-row">Batting details were not recorded for this innings.</td></tr>`}
            ${extras}
            ${total}
          </tbody>
        </table>
      </div>
      ${
        inn.did_not_bat && inn.did_not_bat.length
          ? `<p class="sc-dnb"><strong>Did not bat:</strong> ${inn.did_not_bat.map(escapeHtml).join(", ")}</p>`
          : ""
      }`;
  }

  function bowlingTable(inn) {
    if (!inn.bowling || !inn.bowling.length) {
      return `<p class="sc-dnb sc-muted">Bowling figures were not recorded for this innings.</p>`;
    }
    const rows = inn.bowling
      .map(
        (b) => `
        <tr>
          <td class="sc-name">${escapeHtml(b.name)}</td>
          <td class="sc-num">${num(b.overs)}</td>
          <td class="sc-num">${num(b.maidens)}</td>
          <td class="sc-num">${num(b.runs)}</td>
          <td class="sc-num sc-strong">${num(b.wickets)}</td>
          <td class="sc-num">${num(b.economy)}</td>
        </tr>`
      )
      .join("");
    return `
      <div class="sc-table-wrap">
        <table class="sc-table sc-bowling">
          <thead>
            <tr><th class="sc-name">Bowling</th><th class="sc-num">O</th><th class="sc-num">M</th><th class="sc-num">R</th><th class="sc-num">W</th><th class="sc-num">Econ</th></tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function inningsBlock(inn, open) {
    const score =
      inn.runs === null || inn.runs === undefined
        ? DASH
        : `${escapeHtml(inn.score)}${inn.overs ? ` <small>(${escapeHtml(inn.overs)} ov)</small>` : ""}`;
    return `
      <details class="sc-innings"${open ? " open" : ""}>
        <summary class="sc-innings-head">
          <span class="sc-innings-team">${escapeHtml(inn.team)} <small>${inn.number === 1 ? "1st" : "2nd"} innings</small></span>
          <span class="sc-innings-score">${score}</span>
        </summary>
        ${battingTable(inn)}
        ${bowlingTable(inn)}
      </details>`;
  }

  function matchInfo(sc) {
    const rows = [
      ["Match", sc.title],
      ["Date", sc.date_label],
      ["Venue", sc.venue],
      ["Toss", sc.toss],
      ["Format", sc.overs_limit ? `${sc.overs_limit} overs a side` : ""],
      ["Club", sc.club_name],
      ["Season", sc.season],
      ["Result", sc.result],
    ].filter(([, value]) => value);
    return `
      <div class="sc-info">
        <h3>Match details</h3>
        <dl>${rows.map(([k, v]) => `<div><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`).join("")}</dl>
      </div>`;
  }

  function scorecardMarkup(sc) {
    const blocks = sc.innings.filter((inn) => inn.has_data);
    return `
      ${
        sc.has_details
          ? ""
          : `<div class="sc-notice">Only the totals of this match have been digitised so far.${sc.photo_url ? ' See the <button type="button" class="sc-link" data-go-photo>original scorecard</button> for full details.' : ""}</div>`
      }
      ${(blocks.length ? blocks : sc.innings).map((inn, index) => inningsBlock(inn, index === 0 || sc.innings.length <= 2)).join("")}
      ${matchInfo(sc)}
    `;
  }

  function photoMarkup(sc) {
    return sc.photo_url
      ? `
        <figure class="sc-photo">
          <a href="${escapeHtml(sc.photo_url)}" target="_blank" rel="noopener">
            <img src="${escapeHtml(sc.photo_url)}" alt="Original scorecard photo for ${escapeHtml(sc.title)}, ${escapeHtml(sc.date_label)}" loading="lazy" />
          </a>
          <figcaption>Uploaded scorecard photo · tap to open full size</figcaption>
        </figure>`
      : `<div class="live-empty">The original scorecard photo isn't available for this match.</div>`;
  }

  function render(sc) {
    renderHeader(sc);
    cardPanel.innerHTML = scorecardMarkup(sc);
    photoPanel.innerHTML = photoMarkup(sc);
    if (location.hash === "#photo") showTab("photo");
  }

  // Shared renderer (Amit, Oct 15): Admin Center review shows the same snapshot + original image.
  function renderSnapshot(sc, root) {
    root.innerHTML = `
      <div class="scorecards-page admin-scorecard-view">
        <section class="panel onboarding-panel fixtures-hero-panel">
          <div class="stack-card sc-header">${headerMarkup(sc)}</div>
        </section>
        <section class="panel onboarding-panel fixtures-list-panel">
          <div class="stack-card">
            <div class="sc-tabs" role="tablist" aria-label="Scorecard snapshot views">
              <button class="sc-tab is-active" type="button" role="tab" aria-selected="true" data-preview-tab="card">Scorecard</button>
              <button class="sc-tab" type="button" role="tab" aria-selected="false" data-preview-tab="photo">Original scorecard</button>
            </div>
            <div class="sc-panel" role="tabpanel" data-preview-panel="card">${scorecardMarkup(sc)}</div>
            <div class="sc-panel" role="tabpanel" data-preview-panel="photo" hidden>${photoMarkup(sc)}</div>
          </div>
        </section>
      </div>
    `;
    if (root.dataset.previewBound === "true") return;
    root.dataset.previewBound = "true";
    root.addEventListener("click", (event) => {
      const tab = event.target.closest("[data-preview-tab]");
      if (tab) {
        const name = tab.dataset.previewTab;
        root.querySelectorAll("[data-preview-tab]").forEach((item) => {
          const selected = item === tab;
          item.classList.toggle("is-active", selected);
          item.setAttribute("aria-selected", selected ? "true" : "false");
        });
        root.querySelectorAll("[data-preview-panel]").forEach((panel) => {
          panel.hidden = panel.dataset.previewPanel !== name;
        });
      } else if (event.target.closest("[data-go-photo]")) {
        const photoTab = root.querySelector('[data-preview-tab="photo"]');
        if (photoTab) photoTab.click();
      }
    });
  }

  function renderOriginalImage(sc, root) {
    root.innerHTML = sc.photo_url
      ? `
        <h3>Original uploaded image</h3>
        <figure class="sc-photo">
          <img src="${escapeHtml(sc.photo_url)}" alt="Original scorecard image for ${escapeHtml(sc.title)}, ${escapeHtml(sc.date_label)}" loading="eager" decoding="async" />
          <figcaption>Original uploaded scorecard image</figcaption>
        </figure>`
      : `
        <h3>Original uploaded image</h3>
        <div class="live-empty">The original scorecard image isn't available for this match.</div>`;
  }

  window.CricketClubAppScorecardRenderer = { renderSnapshot, renderOriginalImage };
  // On the Admin Center (no scorecard page elements) only the shared renderer above is used.
  const onScorecardPage = Boolean(headerEl && cardPanel && photoPanel && backEl);

  if (onScorecardPage) {
    tabs.forEach((tab) => tab.addEventListener("click", () => showTab(tab.dataset.tab)));
    cardPanel.addEventListener("click", (event) => {
      if (event.target.closest("[data-go-photo]")) showTab("photo");
    });

    // "All scorecards" keeps the date the visitor came from.
    try {
      const ref = document.referrer ? new URL(document.referrer) : null;
      if (ref && ref.origin === location.origin && ref.pathname === "/scorecards") backEl.href = `/scorecards${ref.search}`;
    } catch (error) {
      /* ignore */
    }
  }

  // ---------- Upload preview: check results + Publish / Something's wrong ----------
  let checkEl = null;
  let lastPreview = null;
  let editorShown = false;

  // ---------- "Type in the scorecard" editor (POST /api/scorecards/{id}/manual) ----------
  // Used when the photo can't be read (handwriting) or to correct what was read.
  const HOW_OUT = ["", "not out", "caught", "bowled", "lbw", "run out", "stumped", "caught and bowled", "hit wicket", "retired out", "retired not out", "did not bat"];
  const isBlank = (v) => v === null || v === undefined || v === "";

  function splitDismissal(text, notOut) {
    const t = String(text || "").trim();
    const lower = t.toLowerCase();
    if (!t) return { how: notOut ? "not out" : "", bowler: "" };
    if (lower.startsWith("not out")) return { how: "not out", bowler: "" };
    if (lower.startsWith("retired out")) return { how: "retired out", bowler: "" };
    if (lower.startsWith("retired")) return { how: "retired not out", bowler: "" };
    if (lower.startsWith("run out")) return { how: "run out", bowler: "" };
    if (lower.startsWith("did not bat") || lower === "dnb") return { how: "did not bat", bowler: "" };
    const cb = t.match(/^c\s*(?:&|and)\s*b\s+(.+)$/i);
    if (cb) return { how: "caught and bowled", bowler: cb[1] };
    const withBowler = t.match(/\bb\s+(.+)$/);
    const bowler = withBowler ? withBowler[1].trim() : "";
    if (/^(c|caught)\b/i.test(t)) return { how: "caught", bowler };
    if (/^lbw/i.test(t)) return { how: "lbw", bowler };
    if (/^(st|stumped)\b/i.test(t)) return { how: "stumped", bowler };
    if (/^hit wicket/i.test(t)) return { how: "hit wicket", bowler };
    if (/^(b|bowled)\b/i.test(t)) return { how: "bowled", bowler };
    return { how: "", bowler };
  }

  function batRow(row = {}) {
    const d = splitDismissal(row.dismissal, row.not_out);
    return `<div class="sce-row sce-bat">
      <input data-f="name" placeholder="Batter" value="${escapeHtml(row.name || "")}" aria-label="Batter name" />
      <select data-f="how" aria-label="How out">${HOW_OUT.map((h) => `<option value="${h}"${h === d.how ? " selected" : ""}>${h || "How out"}</option>`).join("")}</select>
      <input data-f="bowler" placeholder="Bowler" value="${escapeHtml(d.bowler)}" aria-label="Bowler" />
      <input data-f="runs" type="number" min="0" inputmode="numeric" placeholder="R" value="${isBlank(row.runs) ? "" : row.runs}" aria-label="Runs" />
      <input data-f="balls" type="number" min="0" inputmode="numeric" placeholder="B" value="${isBlank(row.balls) ? "" : row.balls}" aria-label="Balls" />
      <input data-f="fours" type="number" min="0" inputmode="numeric" placeholder="4s" value="${isBlank(row.fours) ? "" : row.fours}" aria-label="Fours" />
      <input data-f="sixes" type="number" min="0" inputmode="numeric" placeholder="6s" value="${isBlank(row.sixes) ? "" : row.sixes}" aria-label="Sixes" />
      <button type="button" class="sce-x" data-sce="remove" aria-label="Remove row">✕</button>
    </div>`;
  }

  function bowlRow(row = {}) {
    return `<div class="sce-row sce-bowl">
      <input data-f="name" placeholder="Bowler" value="${escapeHtml(row.name || "")}" aria-label="Bowler name" />
      <input data-f="overs" inputmode="decimal" placeholder="Overs" value="${isBlank(row.overs) ? "" : escapeHtml(row.overs)}" aria-label="Overs" />
      <input data-f="maidens" type="number" min="0" inputmode="numeric" placeholder="M" value="${isBlank(row.maidens) ? "" : row.maidens}" aria-label="Maidens" />
      <input data-f="runs" type="number" min="0" inputmode="numeric" placeholder="R" value="${isBlank(row.runs) ? "" : row.runs}" aria-label="Runs given" />
      <input data-f="wickets" type="number" min="0" max="10" inputmode="numeric" placeholder="W" value="${isBlank(row.wickets) ? "" : row.wickets}" aria-label="Wickets" />
      <button type="button" class="sce-x" data-sce="remove" aria-label="Remove row">✕</button>
    </div>`;
  }

  function inningsEditor(inn, index, teams) {
    const batting = (inn.batting || []).filter((b) => b.name);
    const bowling = (inn.bowling || []).filter((b) => b.name);
    while (batting.length < 11) batting.push({});
    while (bowling.length < 5) bowling.push({});
    return `<fieldset class="sce-innings" data-innings="${index}">
      <legend>${index + 1}${index ? "nd" : "st"} innings: <span data-sce-team-label>${escapeHtml(teams[index] || "")}</span> batting</legend>
      <div class="sce-totals">
        <label>Total runs <input data-t="runs" type="number" min="0" inputmode="numeric" value="${isBlank(inn.runs) ? "" : inn.runs}" /></label>
        <label>Wickets <input data-t="wickets" type="number" min="0" max="10" inputmode="numeric" value="${isBlank(inn.wickets) ? "" : inn.wickets}" /></label>
        <label>Overs <input data-t="overs" inputmode="decimal" value="${isBlank(inn.overs) ? "" : escapeHtml(inn.overs)}" /></label>
        <label>Extras <input data-t="extras" type="number" min="0" inputmode="numeric" value="${isBlank(inn.extras) ? "" : inn.extras}" /></label>
      </div>
      <p class="sce-sum" data-sce-sum></p>
      <h4>Batting</h4>
      <div class="sce-head sce-bat"><span>Batter</span><span>How out</span><span>Bowler</span><span>R</span><span>B</span><span>4s</span><span>6s</span><span></span></div>
      <div data-rows="bat">${batting.map(batRow).join("")}</div>
      <button type="button" class="sc-btn ghost" data-sce="add-bat">+ Add batter</button>
      <h4>Bowling <small>(the other team's bowlers)</small></h4>
      <div class="sce-head sce-bowl"><span>Bowler</span><span>O</span><span>M</span><span>R</span><span>W</span><span></span></div>
      <div data-rows="bowl">${bowling.map(bowlRow).join("")}</div>
      <button type="button" class="sc-btn ghost" data-sce="add-bowl">+ Add bowler</button>
    </fieldset>`;
  }

  function openEditor() {
    const sc = (lastPreview && lastPreview.scorecard) || {};
    const unreadable = Boolean(lastPreview && lastPreview.unreadable);
    const innings = (sc.innings || []).slice(0, 2).map((inn) => (unreadable ? { team: inn.team } : inn));
    while (innings.length < 2) innings.push({});
    const teams = [innings[0].team || "", innings[1].team || ""].map((t) => (/^opponent$/i.test(t) ? "" : t));
    let editor = document.getElementById("scEditor");
    if (!editor) {
      editor = document.createElement("section");
      editor.id = "scEditor";
      editor.className = "panel onboarding-panel sce-panel";
      checkEl.after(editor);
    }
    editor.innerHTML = `
      <form class="stack-card sce" data-sce-form>
        <p class="section-kicker">Type in the scorecard</p>
        <h2>Enter what's written on the card</h2>
        <p class="sc-check-lede">Copy the names and numbers from the photo (open it with the button below). Leave anything you can't read empty. Batters' runs + extras must add up to the total.</p>
        ${sc.photo_url ? `<p><a class="sc-btn ghost" href="${escapeHtml(sc.photo_url)}" target="_blank" rel="noopener">📷 Open the photo in a new tab</a></p>` : ""}
        <div class="sce-match">
          <label>Team batting first <input data-m="team1" value="${escapeHtml(teams[0])}" placeholder="e.g. Heartlake Cricket Club" required /></label>
          <label>Team batting second <input data-m="team2" value="${escapeHtml(teams[1])}" placeholder="Opponent team name" required /></label>
          <label>Match date <input data-m="date" type="date" value="${escapeHtml(lastPreview && lastPreview.typed_in ? sc.date || "" : "")}" required /></label>
          <label>Venue <input data-m="venue" value="${escapeHtml(sc.venue || "")}" placeholder="Ground" /></label>
          <label>Overs per side <input data-m="overs" type="number" min="1" inputmode="numeric" value="${escapeHtml(sc.overs_limit || "")}" /></label>
          <label>Result <input data-m="result" value="${escapeHtml(sc.result && !/review|not recorded|read the handwriting|pending/i.test(sc.result) ? sc.result : "")}" placeholder="e.g. Heartlake won by 20 runs" /></label>
        </div>
        ${innings.map((inn, i) => inningsEditor(inn, i, teams)).join("")}
        <div class="sc-check-actions">
          <button type="submit" class="sc-btn primary">Save scorecard</button>
          <button type="button" class="sc-btn" data-sce="close">Cancel</button>
        </div>
        <p class="sc-check-msg" data-sce-msg role="status"></p>
      </form>`;
    editorShown = true;
    updateSums();
    editor.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  const fieldNum = (el) => (el && el.value.trim() !== "" ? Number(el.value) : null);

  function updateSums() {
    document.querySelectorAll("#scEditor [data-innings]").forEach((box) => {
      const runs = Array.from(box.querySelectorAll('[data-rows="bat"] [data-f="runs"]')).reduce((s, el) => s + (fieldNum(el) || 0), 0);
      const extras = fieldNum(box.querySelector('[data-t="extras"]')) || 0;
      const total = fieldNum(box.querySelector('[data-t="runs"]'));
      const out = box.querySelector("[data-sce-sum]");
      if (!runs && !extras && total === null) {
        out.textContent = "";
        return;
      }
      const ok = total === null || runs + extras === total;
      out.className = `sce-sum ${ok ? "ok" : "bad"}`;
      out.textContent = `Batters ${runs} + extras ${extras} = ${runs + extras}${total === null ? "" : ok ? ` ✓ matches the total ${total}` : ` ✗ but the total is ${total}`}`;
    });
    const t1 = document.querySelector('#scEditor [data-m="team1"]');
    const t2 = document.querySelector('#scEditor [data-m="team2"]');
    const labels = document.querySelectorAll("#scEditor [data-sce-team-label]");
    if (t1 && t2 && labels.length === 2) {
      labels[0].textContent = t1.value;
      labels[1].textContent = t2.value;
    }
  }

  function buildTemplate(form) {
    const val = (sel) => (form.querySelector(sel)?.value || "").trim();
    const team1 = val('[data-m="team1"]');
    const team2 = val('[data-m="team2"]');
    const innings = Array.from(form.querySelectorAll("[data-innings]")).map((box, index) => {
      const batting = Array.from(box.querySelectorAll('[data-rows="bat"] .sce-row'))
        .map((row) => {
          const name = row.querySelector('[data-f="name"]').value.trim();
          if (!name) return null;
          return {
            player: { name, normalized_name: name.toLowerCase(), member_id: null },
            runs: fieldNum(row.querySelector('[data-f="runs"]')),
            balls: fieldNum(row.querySelector('[data-f="balls"]')),
            fours: fieldNum(row.querySelector('[data-f="fours"]')),
            sixes: fieldNum(row.querySelector('[data-f="sixes"]')),
            strike_rate: null,
            dismissal: { type: row.querySelector('[data-f="how"]').value || null, fielder: null, bowler: row.querySelector('[data-f="bowler"]').value.trim() || null },
          };
        })
        .filter(Boolean);
      const bowling = Array.from(box.querySelectorAll('[data-rows="bowl"] .sce-row'))
        .map((row) => {
          const name = row.querySelector('[data-f="name"]').value.trim();
          if (!name) return null;
          const overs = row.querySelector('[data-f="overs"]').value.trim();
          return {
            player: { name, normalized_name: name.toLowerCase() },
            overs: overs === "" ? null : Number(overs),
            maidens: fieldNum(row.querySelector('[data-f="maidens"]')),
            runs_conceded: fieldNum(row.querySelector('[data-f="runs"]')),
            wickets: fieldNum(row.querySelector('[data-f="wickets"]')),
            economy: null,
          };
        })
        .filter(Boolean);
      const overs = box.querySelector('[data-t="overs"]').value.trim();
      return {
        inning_number: index + 1,
        batting_team: index ? team2 : team1,
        bowling_team: index ? team1 : team2,
        summary: { runs: fieldNum(box.querySelector('[data-t="runs"]')), wickets: fieldNum(box.querySelector('[data-t="wickets"]')), overs: overs === "" ? null : Number(overs), balls: null },
        batting,
        bowling,
        extras: { wides: null, no_balls: null, byes: null, leg_byes: null, penalties: null, total: fieldNum(box.querySelector('[data-t="extras"]')) },
      };
    });
    return {
      match: {
        match_id: null,
        match_type: "club",
        format: null,
        date: val('[data-m="date"]') || null,
        venue: val('[data-m="venue"]') || null,
        teams: { team_1: team1, team_2: team2 },
        overs_limit: fieldNum(form.querySelector('[data-m="overs"]')),
      },
      innings,
      validation: { inning_1_total: innings[0]?.summary.runs ?? null, inning_2_total: innings[1]?.summary.runs ?? null, expected_result: val('[data-m="result"]'), is_consistent: null, notes: "Typed in on the scorecard page." },
    };
  }

  document.addEventListener("input", (event) => {
    if (event.target.closest("#scEditor")) updateSums();
  });

  document.addEventListener("click", (event) => {
    if (checkEl && checkEl.contains(event.target) && event.target.closest("[data-go-photo]")) {
      showTab("photo");
      photoPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });

  document.addEventListener("click", (event) => {
    const action = event.target.closest("[data-sce]")?.dataset.sce;
    if (!action) return;
    const box = event.target.closest("[data-innings]");
    if (action === "add-bat") box.querySelector('[data-rows="bat"]').insertAdjacentHTML("beforeend", batRow());
    if (action === "add-bowl") box.querySelector('[data-rows="bowl"]').insertAdjacentHTML("beforeend", bowlRow());
    if (action === "remove") event.target.closest(".sce-row").remove();
    if (action === "close") {
      document.getElementById("scEditor")?.remove();
      editorShown = false;
    }
    updateSums();
  });

  document.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-sce-form]");
    if (!form) return;
    event.preventDefault();
    const msg = form.querySelector("[data-sce-msg]");
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    msg.textContent = "Saving…";
    try {
      const data = await previewAction(`/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/manual`, { template: buildTemplate(form) });
      document.getElementById("scEditor")?.remove();
      editorShown = true; // don't pop the editor open again after saving
      await loadPreview();
      checkEl.querySelector(".sc-check-msg").textContent = data.message || "Saved.";
      checkEl.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      msg.textContent = error.message;
      button.disabled = false;
    }
  });
  function renderChecks(data) {
    if (!checkEl) {
      checkEl = document.createElement("section");
      checkEl.className = "panel onboarding-panel sc-check-panel";
      headerEl.closest("section").before(checkEl);
    }
    const status = String(data.status || "");
    const lower = status.toLowerCase();
    const published = lower === "approved" || lower === "applied to match";
    const flags = data.flags || [];
    const tone = published ? "good" : flags.length ? "warn" : "info";
    const title = published
      ? "✅ Published"
      : lower === "rejected" || lower === "duplicate"
        ? `Not published (${status})`
        : flags.length
          ? "⚠️ A site admin will check this scorecard"
          : "Check the scorecard below";
    const lede = published
      ? "Everyone can see this scorecard. Spotted a mistake? Tell us and a site admin will fix it."
      : flags.length
        ? "We found a few things that need a second look. Players have been told it's being checked."
        : "Everything we checked looks right. If the teams, scores and players below match the photo, publish it.";
    checkEl.innerHTML = `
      <div class="stack-card sc-check sc-check-${tone}">
        <p class="section-kicker">Scorecard upload</p>
        <h2>${escapeHtml(title)}</h2>
        <p class="sc-check-lede">${escapeHtml(lede)}</p>
        ${data.ai_read ? `<p class="sc-check-lede">🤖 Read from the photo by AI. Compare it with the <button type="button" class="sc-link" data-go-photo>original scorecard</button> before publishing.</p>` : ""}
        ${data.unreadable && !data.ai_available && data.is_site_admin ? `<p class="sc-check-lede">Tip: handwriting can be read automatically. Add a free <strong>GEMINI_API_KEY</strong> to the .env file (see README "Reading handwritten scorecards automatically").</p>` : ""}
        ${flags.length ? `<ul class="sc-check-list">${flags.map((f) => `<li>${escapeHtml(f)}</li>`).join("")}</ul>` : ""}
        <div class="sc-check-actions">
          ${data.can_publish ? `<button type="button" class="sc-btn primary" data-sc="publish">✓ Looks right, publish</button>` : ""}
          ${data.can_edit && data.ai_available ? `<button type="button" class="sc-btn${data.unreadable ? " primary" : ""}" data-sc="ai-read">🤖 ${data.ai_read ? "Read again with AI" : "Read with AI"}</button>` : ""}
          ${data.can_edit && data.ai_locked ? `<a class="sc-btn" href="/pricing?feature=ai_extraction" title="AI reading of photos is part of Pro">🤖 Read with AI 🔒 Pro</a>` : ""}
          ${data.can_edit ? `<button type="button" class="sc-btn${data.unreadable && !data.ai_available ? " primary" : ""}" data-sc="edit-open">✏️ ${data.unreadable ? "Type in the scorecard" : "Edit scorecard"}</button>` : ""}
          ${data.can_report ? `<button type="button" class="sc-btn" data-sc="report-open">Something's wrong</button>` : ""}
          <a class="sc-btn ghost" href="/scorecards/upload">Upload another</a>
          ${data.can_delete ? `<button type="button" class="sc-btn sc-danger" data-sc="delete">🗑 Delete this upload</button>` : ""}
        </div>
        <form class="sc-report" data-sc-report hidden>
          <label for="scReportNote">What's wrong?</label>
          <textarea id="scReportNote" rows="3" maxlength="500" placeholder="e.g. Raj scored 34, not 24"></textarea>
          <button type="submit" class="sc-btn primary">Send to site admin</button>
        </form>
        <p class="sc-check-msg" role="status"></p>
      </div>`;
  }

  async function previewAction(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Auth-Token": token() },
      body: JSON.stringify(body || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Something went wrong.");
    return data;
  }

  async function loadPreview() {
    const response = await fetch(`/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/preview`, { headers: { Accept: "application/json", "X-Auth-Token": token() } });
    if (response.status === 401) {
      location.href = `/signin?next=${encodeURIComponent(location.pathname + location.search)}`;
      return null;
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Unable to load this scorecard.");
    render(data.scorecard);
    renderChecks(data);
    lastPreview = data;
    if (data.unreadable && data.can_edit && !data.ai_available && !editorShown) openEditor();
    backEl.href = "/scorecards";
    return data;
  }

  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-sc]");
    if (!button || !checkEl || !checkEl.contains(button)) return;
    const msg = checkEl.querySelector(".sc-check-msg");
    if (button.dataset.sc === "delete") {
      if (!window.confirm("Delete this upload and its photo? This can't be undone. You can upload the photo again afterwards.")) return;
      button.disabled = true;
      try {
        const response = await fetch(`/api/admin/archive/${encodeURIComponent(id.replace(/^a-/, ""))}`, { method: "DELETE", headers: { "X-Auth-Token": token() } });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || "Couldn't delete it.");
        location.href = "/scorecards/upload";
      } catch (error) {
        checkEl.querySelector(".sc-check-msg").textContent = error.message;
        button.disabled = false;
      }
      return;
    }
    if (button.dataset.sc === "ai-read") {
      button.disabled = true;
      button.textContent = "🤖 Reading the photo… (can take a few minutes)";
      try {
        const data = await previewAction(`/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/ai-read`);
        document.getElementById("scEditor")?.remove();
        await loadPreview();
        checkEl.querySelector(".sc-check-msg").textContent = data.message || "Read by AI.";
      } catch (error) {
        checkEl.querySelector(".sc-check-msg").textContent = error.message;
        button.disabled = false;
        button.textContent = "🤖 Read with AI";
      }
      return;
    }
    if (button.dataset.sc === "edit-open") {
      openEditor();
      return;
    }
    if (button.dataset.sc === "report-open") {
      const form = checkEl.querySelector("[data-sc-report]");
      form.hidden = !form.hidden;
      if (!form.hidden) form.querySelector("textarea").focus();
      return;
    }
    if (button.dataset.sc === "publish") {
      button.disabled = true;
      try {
        const data = await previewAction(`/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/publish`);
        await loadPreview();
        checkEl.querySelector(".sc-check-msg").textContent = data.message || "Published.";
      } catch (error) {
        msg.textContent = error.message;
        button.disabled = false;
      }
    }
  });

  document.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-sc-report]");
    if (!form) return;
    event.preventDefault();
    try {
      const data = await previewAction(`/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/report`, { note: form.querySelector("textarea").value });
      await loadPreview();
      checkEl.querySelector(".sc-check-msg").textContent = data.message || "Sent.";
    } catch (error) {
      checkEl.querySelector(".sc-check-msg").textContent = error.message;
    }
  });

  (async () => {
    if (!onScorecardPage) return;
    if (preview) {
      try {
        await loadPreview();
      } catch (error) {
        headerEl.innerHTML = `<p class="sc-meta">Scorecard</p><h1 class="sc-title">Not available</h1>`;
        cardPanel.innerHTML = `<div class="live-empty">${escapeHtml(error.message)}</div>`;
        photoPanel.innerHTML = "";
      }
      return;
    }
    try {
      const response = await fetch(`/api/public/scorecards/${encodeURIComponent(id)}`, { headers: { Accept: "application/json" } });
      if (response.status === 404) throw new Error("This scorecard isn't available. It may not be approved yet.");
      if (!response.ok) throw new Error("Unable to load this scorecard.");
      const data = await response.json();
      render(data.scorecard);
    } catch (error) {
      headerEl.innerHTML = `<p class="sc-meta">Scorecard</p><h1 class="sc-title">Not found</h1>`;
      cardPanel.innerHTML = `<div class="live-empty">${escapeHtml(error.message)}</div>`;
      photoPanel.innerHTML = "";
    }
  })();
})();
