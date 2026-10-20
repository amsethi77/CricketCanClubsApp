/*
 * Cricinfo-style digital scorecard for one approved archive upload.
 * Tabs: "Scorecard" (innings tables) and "Original scorecard" (the uploaded photo).
 */
(() => {
  const headerEl = document.getElementById("scHeader");
  const cardPanel = document.getElementById("scPanelCard");
  const photoPanel = document.getElementById("scPanelPhoto");
  const backEl = document.getElementById("scBack");
  const tabs = Array.from(document.querySelectorAll(".sc-tab"));
  const id = decodeURIComponent(location.pathname.replace(/\/+$/, "").split("/").pop() || "");
  const DASH = "–";

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

  function showTab(name) {
    tabs.forEach((tab) => {
      const on = tab.dataset.tab === name;
      tab.classList.toggle("is-active", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
    cardPanel.hidden = name !== "card";
    photoPanel.hidden = name !== "photo";
    history.replaceState(null, "", name === "photo" ? "#photo" : location.pathname);
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

  if (headerEl && cardPanel && photoPanel && backEl) {
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

    (async () => {
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
  }
})();
