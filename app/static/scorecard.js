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
  const tabs = Array.from(document.querySelectorAll(".pm-tabbar [data-tab]"));
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

  function showTab(name) {
    tabs.forEach((tab) => {
      const on = tab.dataset.tab === name;
      tab.classList.toggle("is-active", on);
      tab.classList.toggle("on", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
    cardPanel.hidden = name !== "card";
    photoPanel.hidden = name !== "photo";
    history.replaceState(null, "", `${location.pathname}${location.search}${name === "photo" ? "#photo" : ""}`);
  }

  // ---------- Same look as a scored match's page (/live/{id}, public_match.css) - Dhruvika, Oct 30 ----------
  // "make same like for manual one is made, no different": the uploaded scorecard uses the live page's markup.
  function shortCode(name) {
    let words = String(name || "").replace(/[^A-Za-z0-9 ]/g, " ").split(/\s+/).filter(Boolean);
    if (!words.length) return "?";
    // Nov 7 2026: "Imran XI" showed as "IX" - a trailing XI / 11 isn't part of the code ("IMR", "CCXI")
    const xi = words.length > 1 && /^(xi|11)$/i.test(words[words.length - 1]);
    if (xi) {
      words = words.slice(0, -1);
      if (words.length === 1) return words[0].slice(0, 3).toUpperCase();
      return `${words.map((w) => w[0]).join("").slice(0, 2).toUpperCase()}XI`;
    }
    if (words.length === 1) return words[0].length <= 4 && words[0] === words[0].toUpperCase() ? words[0] : words[0].slice(0, 3).toUpperCase();
    return words.map((w) => w[0]).join("").slice(0, 3).toUpperCase();
  }

  function flagHue(name) {
    let h = 0;
    for (const ch of String(name || "")) h = (h * 31 + ch.charCodeAt(0)) % 360;
    return h;
  }

  function headerMarkup(sc) {
    const winner = (sc.result || "").toLowerCase();
    const row = (inn) => {
      if (!inn) return "";
      const won = sc.result && winner.startsWith(String(inn.team || "").toLowerCase());
      const has = !(inn.runs === null || inn.runs === undefined);
      return `<div class="pm-trow${won ? " bat" : ""}">
          <span class="pm-badge pm-flag" style="--h:${flagHue(inn.team)}" aria-hidden="true"></span>
          <span class="pm-tname" title="${escapeHtml(inn.team)}">${escapeHtml(shortCode(inn.team))}</span>
          <span class="pm-tscore">${has && inn.overs ? `<small>(${escapeHtml(inn.overs)} ov) </small>` : ""}<b>${has ? escapeHtml(inn.score) : DASH}</b></span></div>`;
    };
    const info = [sc.title, sc.match_type, sc.overs_limit ? `${sc.overs_limit} overs` : "", sc.venue, sc.date_label].filter(Boolean).map(escapeHtml).join(", ");
    const [first, second] = sc.innings;
    return `
      <div class="pm-head-top">${sc.result ? '<span class="pm-state done">RESULT</span>' : '<span class="pm-state">SCORECARD</span>'}</div>
      <div class="pm-teams">${row(first)}${row(second)}</div>
      <p class="pm-status done">${escapeHtml(sc.result || "Result not recorded")}</p>
      ${peopleLine(sc)}
      <p class="pm-info">${info}</p>
      ${sc.match_code ? `<p class="pm-info sc-match-id">Match ID <b>${escapeHtml(sc.match_code)}</b></p>` : ""}
      ${(sc.innings_ids || []).length ? `<ul class="sc-innings-ids" aria-label="Innings of this match">${sc.innings_ids
        .map((i) => `<li class="${i.status === "missing" ? "missing" : "ok"}"><b>${escapeHtml(i.id)}</b> ${escapeHtml(i.team || `Innings ${i.number}`)} ${i.status === "missing" ? "· <em>missing</em>" : `· ${escapeHtml(i.score || "")}`}</li>`)
        .join("")}</ul>` : ""}`;
  }

  // Nov 11 2026 (Amit: "add the captains from each side and the man of the match in the match Result Summary")
  function manOfMatch(sc) {
    if (sc.man_of_match) return sc.man_of_match;
    return sc.man_of_match_auto ? `${sc.man_of_match_auto} (auto pick)` : "";
  }
  function peopleLine(sc) {
    const caps = (sc.captains || []).map((c) => `${c.name ? escapeHtml(c.name) : "<em>not picked</em>"}${c.team ? ` <small>(${escapeHtml(shortCode(c.team))})</small>` : ""}${c.captain_auto ? ' <small title="The club\'s usual captain - pick one below to change it">· usual captain</small>' : ""}`).join(" · ");
    const mom = manOfMatch(sc);
    if (!caps && !mom) return "";
    return `<p class="pm-info sc-people">${caps ? `<span>🧢 Captains: ${caps}</span>` : ""}${caps && mom ? " &nbsp;|&nbsp; " : ""}${mom ? `<span>🏅 Man of the match: <b>${escapeHtml(mom)}</b></span>` : ""}</p>`;
  }

  function renderHeader(sc) {
    headerEl.innerHTML = headerMarkup(sc);
    document.title = `${sc.title} · ${sc.date_label} · Scorecard`;
  }

  // Nov 17 2026 (Cricbuzz "INFO" box): Match, Series, Date, Toss, Venue, Result, captains, man of the match, then
  // each side's squad (the players on this card).
  function matchInfo(sc) {
    const sidePlayers = (team) =>
      [...new Set((sc.innings || []).flatMap((inn) => (inn.team === team ? [...(inn.batting || []).map((r) => r.name), ...(inn.did_not_bat || [])] : (inn.bowling || []).map((r) => r.name))).filter(Boolean))];
    const tagged = (c, name) => `${name}${[c.name === name ? "c" : "", c.vice_captain === name ? "vc" : "", c.keeper === name ? "wk" : ""].filter(Boolean).length ? ` (${[c.name === name ? "c" : "", c.vice_captain === name ? "vc" : "", c.keeper === name ? "wk" : ""].filter(Boolean).join(" & ")})` : ""}`;
    const rows = [
      ["Match", sc.title + (sc.match_type ? ` · ${sc.match_type}` : "")],
      ["Series", sc.season],
      ["Date", sc.date_label],
      ["Toss", sc.toss],
      ["Venue", sc.venue],
      ["Format", sc.overs_limit ? `${sc.overs_limit} overs a side` : ""],
      ["Result", sc.result],
      ["Captains", (sc.captains || []).filter((c) => c.name || c.team).map((c) => `${c.name || "not picked"}${c.team ? ` (${c.team})` : ""}`).join(" · ")],
      ["Vice-captains", (sc.captains || []).filter((c) => c.vice_captain).map((c) => `${c.vice_captain}${c.team ? ` (${c.team})` : ""}`).join(" · ")],
      ["Wicket keepers", (sc.captains || []).filter((c) => c.keeper).map((c) => `${c.keeper}${c.team ? ` (${c.team})` : ""}`).join(" · ")],
      ["Man of the match", manOfMatch(sc)],
      ...(sc.captains || [])
        .filter((c) => c.team && sidePlayers(c.team).length)
        .map((c) => [`${c.team} squad`, sidePlayers(c.team).map((name) => tagged(c, name)).join(", ")]),
    ].filter(([, value]) => value);
    return `<div class="pm-info-box"><div class="pm-info-head">INFO</div>
      <dl class="pm-details pm-info-rows">${rows.map(([k, v]) => `<div><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`).join("")}</dl></div>`;
  }

  function scorecardMarkup(sc) {
    return `
      ${
        sc.has_details
          ? ""
          : `<p class="pm-note">Only the totals of this match have been digitised so far.${sc.photo_url ? ' See the <button type="button" class="pm-link" data-go-photo>original scorecard</button> for full details.' : ""}</p>`
      }
      ${window.CricketClubAppScorecardView.inningsSections(sc)}
      ${matchInfo(sc)}
      ${preview || !sc.id ? "" : `<p class="sc-pdf-row"><a class="pm-download" href="/api/public/scorecards/${encodeURIComponent(sc.id)}/scorecard.pdf" download>⬇️ Download PDF scorecard</a></p>`}
    `;
  }

  function photoMarkup(sc) {
    // Nov 2 2026: a card photographed on two pages has two photos (1st innings, 2nd innings)
    const urls = (Array.isArray(sc.photo_urls) && sc.photo_urls.length ? sc.photo_urls : [sc.photo_url]).filter(Boolean);
    if (!urls.length) return `<div class="live-empty">The original scorecard photo isn't available for this match.</div>`;
    return urls
      .map(
        (url, index) => `
        <figure class="sc-photo">
          <a href="${escapeHtml(url)}" target="_blank" rel="noopener">
            <img src="${escapeHtml(url)}" alt="Original scorecard photo${urls.length > 1 ? ` ${index + 1}` : ""} for ${escapeHtml(sc.title)}, ${escapeHtml(sc.date_label)}" loading="lazy" />
          </a>
          <figcaption>${urls.length > 1 ? `${index === 0 ? "1st" : "2nd"} innings photo` : "Uploaded scorecard photo"} · tap to open full size</figcaption>
        </figure>`
      )
      .join("");
  }

  function render(sc) {
    renderHeader(sc);
    cardPanel.innerHTML = scorecardMarkup(sc);
    photoPanel.innerHTML = photoMarkup(sc);
    if (location.hash === "#photo") showTab("photo");
    offerManOfMatchPicker(sc);
  }

  // Nov 11 2026: a playing club's captain / club admin (or the superadmin) picks each side's captain and the man of the match of a
  // live-scored match; the same check as editing its ball-by-ball (/api/quick-score/<id>).
  async function offerManOfMatchPicker(sc) {
    const matchId = sc.fixture_id || (String(sc.id || "").startsWith("f-") ? String(sc.id).slice(2) : "");
    const uploadId = String(sc.id || "").startsWith("a-") ? String(sc.id).slice(2) : "";
    if (!token() || !(sc.source === "fixture" ? matchId : uploadId)) return;
    // live-scored match: whoever may edit its ball-by-ball; uploaded card: whoever may fix it
    const allowed =
      sc.source === "fixture"
        ? await fetch(`/api/quick-score/${encodeURIComponent(matchId)}`, { headers: { "X-Auth-Token": token(), Accept: "application/json" } }).then((r) => r.ok).catch(() => false)
        : await fetch(`/api/scorecards/${encodeURIComponent(uploadId)}/preview`, { headers: { "X-Auth-Token": token(), Accept: "application/json" } })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => Boolean(d && d.can_edit))
            .catch(() => false);
    if (!allowed) return;
    const names = [...new Set([
      ...(sc.innings || []).flatMap((inn) => [...(inn.batting || []), ...(inn.bowling || [])].map((row) => row.name)),
      ...(sc.captains || []).flatMap((c) => c.squad || []),
    ].filter(Boolean))].sort();
    if (!names.length) return;
    // players of one team: its batters, and the bowlers of the other team's innings
    const teamPlayers = (team) =>
      [...new Set((sc.innings || []).flatMap((inn) => (inn.team === team ? inn.batting || [] : inn.bowling || []).map((row) => row.name)).filter(Boolean))].sort();
    const options = (list, current, blank) => ["", ...list].map((n) => `<option value="${escapeHtml(n)}"${n === (current || "") ? " selected" : ""}>${n ? escapeHtml(n) : blank}</option>`).join("");
    const caps = sc.captains || [];
    const box = document.createElement("form");
    box.className = "sc-mom-picker";
    // Nov 17 2026 (Dhruvika: "where is the captain and vice caption"): captain, vice-captain and wicket keeper of each
    // side, picked from that side's players in this match; shown as (c) (vc) (wk) after the names.
    const sidePlayers = (c, extra) => [...new Set([...(c.squad || []), ...teamPlayers(c.team), ...extra.filter(Boolean)])].sort();
    box.innerHTML = `${caps
      .map((c) => {
        const list = sidePlayers(c, [c.name, c.vice_captain, c.keeper]);
        return `<fieldset class="sc-side-roles"><legend>${escapeHtml(c.team)}</legend>
          <label>🧢 Captain (c)<select data-captain="${escapeHtml(c.side || "")}">${options(list, c.captain_auto ? "" : c.name, c.captain_auto ? `Not picked (usual: ${escapeHtml(c.name)})` : "Not picked")}</select></label>
          <label>Vice-captain (vc)<select data-vice="${escapeHtml(c.side || "")}">${options(list, c.vice_captain_auto ? "" : c.vice_captain, c.vice_captain_auto ? `Not picked (usual: ${escapeHtml(c.vice_captain)})` : "Not picked")}</select></label>
          <label>🧤 Wicket keeper (wk)<select data-keeper="${escapeHtml(c.side || "")}">${options(list, c.keeper, "Not picked")}</select></label>
        </fieldset>`;
      })
      .join("")}
      <label>🏅 Man of the match
        <select data-mom>${options(names, sc.man_of_match, "Not picked (show the auto pick)")}</select>
      </label>
      <button class="sc-btn primary" type="submit">Save</button>
      <span class="sc-mom-msg" role="status"></span>`;
    cardPanel.appendChild(box);
    // Nov 20 2026 (Dhruvika: "c and vc cannot be same person"): the player picked as captain can't be picked as
    // vice-captain of the same side (and the other way round) - greyed out in the other list, and checked on Save
    const sameName = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();
    const syncCaptainVice = (side) => {
      const cap = box.querySelector(`[data-captain="${side}"]`);
      const vice = box.querySelector(`[data-vice="${side}"]`);
      if (!cap || !vice) return;
      [...vice.options].forEach((o) => { o.disabled = Boolean(o.value) && sameName(o.value, cap.value); });
      [...cap.options].forEach((o) => { o.disabled = Boolean(o.value) && sameName(o.value, vice.value); });
    };
    caps.forEach((c) => {
      const side = c.side || "";
      syncCaptainVice(side);
      box.querySelector(`[data-captain="${side}"]`)?.addEventListener("change", () => syncCaptainVice(side));
      box.querySelector(`[data-vice="${side}"]`)?.addEventListener("change", () => syncCaptainVice(side));
    });
    box.addEventListener("submit", async (event) => {
      event.preventDefault();
      const msg = box.querySelector(".sc-mom-msg");
      const clash = caps.find((c) => {
        const cap = box.querySelector(`[data-captain="${c.side || ""}"]`)?.value;
        const vice = box.querySelector(`[data-vice="${c.side || ""}"]`)?.value;
        return cap && vice && sameName(cap, vice);
      });
      if (clash) {
        msg.textContent = `${clash.team}: the captain and the vice-captain can't be the same player. Pick someone else as vice-captain.`;
        return;
      }
      // Nov 20 2026 (Dhruvika: Save "takes long time"): the button shows it is working and can't be pressed twice
      const saveButton = box.querySelector('button[type="submit"]');
      const saveLabel = saveButton ? saveButton.textContent : "";
      if (saveButton) {
        if (saveButton.disabled) return;
        saveButton.disabled = true;
        saveButton.textContent = "Saving…";
      }
      msg.textContent = "";
      const pick = (side) => box.querySelector(`[data-captain="${side}"]`)?.value ?? null;
      const vice = (side) => box.querySelector(`[data-vice="${side}"]`)?.value ?? null;
      const keeper = (side) => box.querySelector(`[data-keeper="${side}"]`)?.value ?? null;
      const response = await fetch(
        sc.source === "fixture" ? `/api/matches/${encodeURIComponent(matchId)}/man-of-match` : `/api/scorecards/${encodeURIComponent(uploadId)}/people`,
        {
          method: "POST",
          headers: { "X-Auth-Token": token(), "Content-Type": "application/json" },
          body: JSON.stringify(
            sc.source === "fixture"
              ? {
                  name: box.querySelector("[data-mom]").value,
                  club_captain: pick("club"), opponent_captain: pick("opponent"),
                  club_vice_captain: vice("club"), opponent_vice_captain: vice("opponent"),
                  club_keeper: keeper("club"), opponent_keeper: keeper("opponent"),
                }
              : {
                  man_of_match: box.querySelector("[data-mom]").value,
                  team_1_captain: pick("team_1"), team_2_captain: pick("team_2"),
                  team_1_vice_captain: vice("team_1"), team_2_vice_captain: vice("team_2"),
                  team_1_keeper: keeper("team_1"), team_2_keeper: keeper("team_2"),
                }
          ),
        }
      ).catch(() => null);
      const data = response ? await response.json().catch(() => ({})) : {};
      if (saveButton) {
        saveButton.disabled = false;
        saveButton.textContent = saveLabel;
      }
      msg.textContent = response && response.ok ? data.message || "Saved." : data.detail || "Couldn't save.";
      if (response && response.ok) {
        sc.man_of_match = data.man_of_match ?? box.querySelector("[data-mom]").value;
        (sc.captains || []).forEach((c) => {
          const picked = box.querySelector(`[data-captain="${c.side}"]`);
          if (picked) c.name = picked.value;
          c.vice_captain = box.querySelector(`[data-vice="${c.side}"]`)?.value || "";
          c.keeper = box.querySelector(`[data-keeper="${c.side}"]`)?.value || "";
        });
        // (c) (vc) (wk) next to the names, without reloading the page
        const sameName = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();
        (sc.innings || []).forEach((inn) => {
          [["batting", inn.team], ["bowling", inn.bowling_team]].forEach(([key, team]) => {
            (inn[key] || []).forEach((row) => {
              const side = (sc.captains || []).find((c) => c.team === team);
              if (!side) return;
              const keep = (row.tags || []).filter((tag) => !["C", "VC", "WK"].includes(tag));
              if (sameName(side.name, row.name)) keep.push("C");
              if (sameName(side.vice_captain, row.name)) keep.push("VC");
              if (sameName(side.keeper, row.name)) keep.push("WK");
              row.tags = keep;
            });
          });
        });
        if (sc.man_of_match) sc.man_of_match_auto = "";
        renderHeader(sc);
        cardPanel.innerHTML = scorecardMarkup(sc);
        cardPanel.appendChild(box);
      }
    });
  }

  // Shared renderer (Amit, Oct 15): Admin Center review shows the same snapshot + original image.
  function renderSnapshot(sc, root) {
    if (!document.querySelector('link[href*="public_match.css"]')) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "/assets/public_match.css?v=20261114a";
      document.head.appendChild(link);
    }
    root.innerHTML = `
      <div class="pm-app sc-app admin-scorecard-view">
        <div class="pm-head">${headerMarkup(sc)}</div>
        <nav class="pm-tabbar" role="tablist" aria-label="Scorecard snapshot views">
          <button class="on" type="button" role="tab" aria-selected="true" data-preview-tab="card">Scorecard</button>
          <button type="button" role="tab" aria-selected="false" data-preview-tab="photo">Original scorecard</button>
        </nav>
        <div class="pm-body sc-panel" role="tabpanel" data-preview-panel="card">${scorecardMarkup(sc)}</div>
        <div class="pm-body sc-panel" role="tabpanel" data-preview-panel="photo" hidden>${photoMarkup(sc)}</div>
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
          item.classList.toggle("on", selected);
          item.setAttribute("aria-selected", selected ? "true" : "false");
        });
        root.querySelectorAll("[data-preview-panel]").forEach((panel) => {
          panel.hidden = panel.dataset.previewPanel !== name;
        });
      } else if (event.target.closest("[data-sc-inn]")) {
        const box = event.target.closest(".pm-inn");
        box.classList.toggle("open");
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
      const bar = event.target.closest("[data-sc-inn]");
      if (bar) {
        const box = bar.closest(".pm-inn");
        box.classList.toggle("open");
        bar.setAttribute("aria-expanded", box.classList.contains("open") ? "true" : "false");
      }
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
      <input data-f="name" placeholder="Batter" value="${escapeHtml(row.name || "")}" data-orig="${escapeHtml(row.name || "")}" aria-label="Batter name" />
      <select data-f="how" aria-label="How out">${HOW_OUT.map((h) => `<option value="${h}"${h === d.how ? " selected" : ""}>${h || "How out"}</option>`).join("")}</select>
      <input data-f="bowler" placeholder="Bowler" value="${escapeHtml(d.bowler)}" aria-label="Bowler" />
      <label class="sce-num"><span>R</span><input data-f="runs" type="number" min="0" inputmode="numeric" placeholder="R" value="${isBlank(row.runs) ? "" : row.runs}" aria-label="Runs" /></label>
      <label class="sce-num"><span>B</span><input data-f="balls" type="number" min="0" inputmode="numeric" placeholder="B" value="${isBlank(row.balls) ? "" : row.balls}" aria-label="Balls" /></label>
      <label class="sce-num"><span>4s</span><input data-f="fours" type="number" min="0" inputmode="numeric" placeholder="4s" value="${isBlank(row.fours) ? "" : row.fours}" aria-label="Fours" /></label>
      <label class="sce-num"><span>6s</span><input data-f="sixes" type="number" min="0" inputmode="numeric" placeholder="6s" value="${isBlank(row.sixes) ? "" : row.sixes}" aria-label="Sixes" /></label>
      <label class="sce-num"><span>0s</span><input data-f="dots" type="number" min="0" inputmode="numeric" placeholder="0s" value="${isBlank(row.dots) ? "" : row.dots}" aria-label="Dot balls" /></label>
      <label class="sce-num"><span>1s</span><input data-f="ones" type="number" min="0" inputmode="numeric" placeholder="1s" value="${isBlank(row.ones) ? "" : row.ones}" aria-label="Ones" /></label>
      <label class="sce-num"><span>2s</span><input data-f="twos" type="number" min="0" inputmode="numeric" placeholder="2s" value="${isBlank(row.twos) ? "" : row.twos}" aria-label="Twos" /></label>
      <label class="sce-num"><span>3s</span><input data-f="threes" type="number" min="0" inputmode="numeric" placeholder="3s" value="${isBlank(row.threes) ? "" : row.threes}" aria-label="Threes" /></label>
      <button type="button" class="sce-x" data-sce="remove" aria-label="Remove row">✕</button>
    </div>`;
  }

  function bowlRow(row = {}) {
    return `<div class="sce-row sce-bowl">
      <input data-f="name" placeholder="Bowler" value="${escapeHtml(row.name || "")}" data-orig="${escapeHtml(row.name || "")}" aria-label="Bowler name" />
      <label class="sce-num"><span>O</span><input data-f="overs" inputmode="decimal" placeholder="Overs" value="${isBlank(row.overs) ? "" : escapeHtml(row.overs)}" aria-label="Overs" /></label>
      <label class="sce-num"><span>M</span><input data-f="maidens" type="number" min="0" inputmode="numeric" placeholder="M" value="${isBlank(row.maidens) ? "" : row.maidens}" aria-label="Maidens" /></label>
      <label class="sce-num"><span>R</span><input data-f="runs" type="number" min="0" inputmode="numeric" placeholder="R" value="${isBlank(row.runs) ? "" : row.runs}" aria-label="Runs given" /></label>
      <label class="sce-num"><span>W</span><input data-f="wickets" type="number" min="0" max="10" inputmode="numeric" placeholder="W" value="${isBlank(row.wickets) ? "" : row.wickets}" aria-label="Wickets" /></label>
      <label class="sce-num"><span>Wd</span><input data-f="wides" type="number" min="0" inputmode="numeric" placeholder="Wd" value="${isBlank(row.wides) ? "" : row.wides}" aria-label="Wides" /></label>
      <label class="sce-num"><span>Nb</span><input data-f="no_balls" type="number" min="0" inputmode="numeric" placeholder="Nb" value="${isBlank(row.no_balls) ? "" : row.no_balls}" aria-label="No balls" /></label>
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
      <div class="sce-totals sce-extras">
        ${[["wides", "Wides"], ["no_balls", "No balls"], ["byes", "Byes"], ["leg_byes", "Leg byes"]]
          .map(([key, label]) => `<label>${label} <input data-x="${key}" type="number" min="0" inputmode="numeric" value="${isBlank((inn.extras_parts || {})[key]) ? "" : inn.extras_parts[key]}" /></label>`)
          .join("")}
      </div>
      <p class="sce-sum" data-sce-sum></p>
      <h4>Batting</h4>
      <div class="sce-head sce-bat"><span>Batter</span><span>How out</span><span>Bowler</span><span>R</span><span>B</span><span>4s</span><span>6s</span><span>0s</span><span>1s</span><span>2s</span><span>3s</span><span></span></div>
      <div data-rows="bat">${batting.map(batRow).join("")}</div>
      <button type="button" class="sc-btn ghost" data-sce="add-bat">+ Add batter</button>
      <h4>Bowling <small>(the other team's bowlers)</small></h4>
      <div class="sce-head sce-bowl"><span>Bowler</span><span>O</span><span>M</span><span>R</span><span>W</span><span>Wd</span><span>Nb</span><span></span></div>
      <div data-rows="bowl">${bowling.map(bowlRow).join("")}</div>
      <button type="button" class="sc-btn ghost" data-sce="add-bowl">+ Add bowler</button>
    </fieldset>`;
  }

  // Nov 12 2026 (Amit: "make it same as ai read"): the editor shows everything the AI reads - captains, man of the
  // match, extras by kind, bowlers' wides / no balls - so saving an edit keeps the card as complete as the read
  function capOf(sc, team) {
    const same = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();
    return ((sc.captains || []).find((c) => same(c.team, team)) || {}).name || "";
  }

  let editorSwapped = false;
  function openEditor(swap) {
    if (swap === true) editorSwapped = !editorSwapped;
    const sc = (lastPreview && lastPreview.scorecard) || {};
    const unreadable = Boolean(lastPreview && lastPreview.unreadable);
    let innings = (sc.innings || []).slice(0, 2).map((inn) => (unreadable ? { team: inn.team } : inn));
    while (innings.length < 2) innings.push({});
    // Nov 10 2026 (Amit: "This is second innings"): the innings written as "(2nd)" on the card is the 2nd innings here
    const written = (inn) => Number(inn.written_inning_number || inn.number || 0);
    if (written(innings[0]) === 2 && !innings[1].has_data && !(innings[1].batting || []).some((b) => b.name)) innings = [innings[1], innings[0]];
    // Nov 11 2026 (Amit, again "This is second innings"): the reader called it the 1st innings - one tap swaps them
    if (editorSwapped) innings = [innings[1], innings[0]];
    editorSource = innings;
    const teams = [innings[0].team || "", innings[1].team || ""].map((t) => (/^opponent$/i.test(t) ? "" : t));
    let editor = document.getElementById("scEditor");
    if (!editor) {
      editor = document.createElement("section");
      editor.id = "scEditor";
      editor.className = "panel onboarding-panel sce-panel";
      checkEl.after(editor);
    }
    editor.innerHTML = `
      <form class="stack-card sce" data-sce-form novalidate>
        <p class="section-kicker">Type in the scorecard</p>
        <h2>Enter what's written on the card</h2>
        <p class="sc-check-lede">Copy the names and numbers from the photo (open it with the button below). Leave anything you can't read empty. Batters' runs + extras must add up to the total.</p>
        ${sc.photo_url ? `<p><a class="sc-btn ghost" href="${escapeHtml(sc.photo_url)}" target="_blank" rel="noopener">📷 Open the photo in a new tab</a></p>` : ""}
        <!-- Nov 14 2026 (Amit: "Editing the match innings is not an easy job. We should allow it to be edited
             separately"): one part at a time - match details, 1st innings, 2nd innings. Save keeps all of them. -->
        <nav class="sce-tabs" role="tablist" aria-label="Part of the scorecard to edit">
          <button type="button" role="tab" data-sce-tab="match" class="on" aria-selected="true">📋 Match details</button>
          <button type="button" role="tab" data-sce-tab="inn0" aria-selected="false">🏏 1st innings <small data-sce-tab-team="0">${escapeHtml(teams[0])}</small> <i data-sce-tab-ok="0"></i></button>
          <button type="button" role="tab" data-sce-tab="inn1" aria-selected="false">🏏 2nd innings <small data-sce-tab-team="1">${escapeHtml(teams[1])}</small> <i data-sce-tab-ok="1"></i></button>
        </nav>
        <div class="sce-step" data-sce-step="match">
        <p><button type="button" class="sc-btn ghost" data-sce="swap">⇅ Wrong order? Swap 1st and 2nd innings</button> <small>(do this first - it starts the form again)</small></p>
        <div class="sce-match">
          <label>Team batting first <input data-m="team1" value="${escapeHtml(teams[0])}" placeholder="e.g. Heartlake Cricket Club" required /></label>
          <label>Team batting second <input data-m="team2" value="${escapeHtml(teams[1])}" placeholder="Opponent team name" required /></label>
          ${(() => {
            const cardDate = /^\d{4}-\d{2}-\d{2}$/.test(String(sc.date || "")) ? sc.date : "";
            const photoDate = !cardDate && lastPreview && /^\d{4}-\d{2}-\d{2}$/.test(String(lastPreview.photo_date || "")) ? lastPreview.photo_date : "";
            return `<label>Match date ${photoDate ? "<small>(not on the card - this is the day the photo was taken, check it)</small>" : cardDate ? "" : "<small>(not on the card - enter it)</small>"}
              <input data-m="date" type="date" value="${escapeHtml(cardDate || photoDate)}" required /></label>`;
          })()}
          <label>Venue <input data-m="venue" value="${escapeHtml(sc.venue || "")}" placeholder="Ground" /></label>
          <label>Overs per side <input data-m="overs" type="number" min="1" inputmode="numeric" value="${escapeHtml(sc.overs_limit || "")}" /></label>
          <label>Captain - team batting first <input data-m="cap1" value="${escapeHtml(capOf(sc, teams[0]))}" placeholder="Captain" /></label>
          <label>Captain - team batting second <input data-m="cap2" value="${escapeHtml(capOf(sc, teams[1]))}" placeholder="Captain" /></label>
          <label>Man of the match <input data-m="mom" value="${escapeHtml(sc.man_of_match || "")}" placeholder="Player" /></label>
          <label>Result <input data-m="result" value="${escapeHtml(sc.result && !/review|not recorded|read the handwriting|pending/i.test(sc.result) ? sc.result : "")}" placeholder="e.g. Heartlake won by 20 runs" /></label>
        </div>
        <p class="sce-next"><button type="submit" class="sc-btn ghost">💾 Save</button> <button type="button" class="sc-btn" data-sce-go="inn0">Next: 1st innings →</button></p>
        </div>
        ${innings.map((inn, i) => `<div class="sce-step" data-sce-step="inn${i}" hidden>${inningsEditor(inn, i, teams)}
          <p class="sce-next">${i === 0 ? '<button type="button" class="sc-btn ghost" data-sce-go="match">← Match details</button> <button type="submit" class="sc-btn ghost">💾 Save</button> <button type="button" class="sc-btn" data-sce-go="inn1">Next: 2nd innings →</button>' : '<button type="button" class="sc-btn ghost" data-sce-go="inn0">← 1st innings</button> <button type="submit" class="sc-btn">💾 Save</button>'}</p>
        </div>`).join("")}
        <div class="sc-check-actions sce-save-bar">
          <button type="submit" class="sc-btn primary">Save scorecard</button>
          <button type="button" class="sc-btn" data-sce="close">Cancel</button>
        </div>
        <p class="sc-check-msg" data-sce-msg role="status"></p>
      </form>`;
    editorShown = true;
    updateSums();
    wireRenameEverywhere(editor);
    wireEditorSteps(editor);
    editor.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function showEditorStep(editor, name) {
    editor.querySelectorAll("[data-sce-step]").forEach((step) => (step.hidden = step.dataset.sceStep !== name));
    editor.querySelectorAll("[data-sce-tab]").forEach((tab) => {
      const on = tab.dataset.sceTab === name;
      tab.classList.toggle("on", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  function wireEditorSteps(editor) {
    if (editor.dataset.stepsWired) return;
    editor.dataset.stepsWired = "1";
    editor.addEventListener("click", (event) => {
      const target = event.target.closest("[data-sce-tab], [data-sce-go]");
      if (!target) return;
      showEditorStep(editor, target.dataset.sceTab || target.dataset.sceGo);
      editor.querySelector(".sce-tabs")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  // Nov 7 2026 (Amit: "if we update at 1 place then it should replace in other places while editing the scorecard
  // manually"): changing a player's name changes the same name everywhere on the card - batting, bowling and the
  // bowler in How out, in both innings.
  function wireRenameEverywhere(editor) {
    if (editor.dataset.renameWired) return;
    editor.dataset.renameWired = "1";
    const nameFields = '[data-f="name"], [data-f="bowler"]';
    editor.addEventListener("focusin", (event) => {
      const input = event.target.closest(nameFields);
      if (input) input.dataset.prev = input.value.trim();
    });
    editor.addEventListener("change", (event) => {
      const input = event.target.closest(nameFields);
      if (!input) return;
      const before = (input.dataset.prev || "").trim();
      const after = input.value.trim();
      input.dataset.prev = after;
      if (!before || !after || before.toLowerCase() === after.toLowerCase()) return;
      // Nov 17 2026 (Amit: "it should only change to the same club where I have changed it"): only the places of the
      // SAME side change - its batters in the innings it batted, its bowlers and the bowler in How out in the innings
      // it fielded. Rafa of the other team keeps his name. Exact same name only (Rafa never changes Rafael).
      const sideOf = (field) => {
        const box = field.closest("[data-innings]");
        const index = box ? Number(box.dataset.innings) : 0;
        const inBatting = Boolean(field.closest('[data-rows="bat"]')) && field.matches('[data-f="name"]');
        return inBatting ? index : 1 - index;
      };
      const side = sideOf(input);
      let changed = 0;
      editor.querySelectorAll(nameFields).forEach((other) => {
        if (other !== input && sideOf(other) === side && other.value.trim().toLowerCase() === before.toLowerCase()) {
          other.value = after;
          other.dataset.prev = after;
          changed += 1;
        }
      });
      const msg = editor.querySelector("[data-sce-msg]");
      if (msg && changed) msg.textContent = `'${before}' was also changed to '${after}' in ${changed} other place${changed === 1 ? "" : "s"} of the same team on this card.`;
    });
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
      const mark = document.querySelector(`#scEditor [data-sce-tab-ok="${box.dataset.innings}"]`);
      if (mark) mark.textContent = ok ? "✓" : "!";
      out.textContent = `Batters ${runs} + extras ${extras} = ${runs + extras}${total === null ? "" : ok ? ` ✓ matches the total ${total}` : ` ✗ but the total is ${total}`}`;
    });
    const t1 = document.querySelector('#scEditor [data-m="team1"]');
    const t2 = document.querySelector('#scEditor [data-m="team2"]');
    const labels = document.querySelectorAll("#scEditor [data-sce-team-label]");
    if (t1 && t2 && labels.length === 2) {
      labels[0].textContent = t1.value;
      labels[1].textContent = t2.value;
    }
    document.querySelectorAll("#scEditor [data-sce-tab-team]").forEach((small) => {
      small.textContent = (small.dataset.sceTabTeam === "0" ? t1 : t2)?.value || "";
    });
  }

  // Nov 10 2026: saving an edit keeps what the form doesn't show - 1s/2s/3s/dots, runs per over, wides, no balls,
  // captains and man of the match - for every row whose player is the same (renamed rows keep them too).
  let editorSource = [];
  function sourceRow(index, kind, original) {
    const key = String(original || "").trim().toLowerCase();
    if (!key) return {};
    const lists = [editorSource[index], ...editorSource.filter((_, i) => i !== index)].map((inn) => (inn && inn[kind]) || []);
    for (const list of lists) {
      const found = list.find((row) => String(row.name || "").trim().toLowerCase() === key);
      if (found) return found;
    }
    return {};
  }
  function kept(row, keys) {
    const out = {};
    keys.forEach((key) => {
      if (row[key] !== null && row[key] !== undefined && row[key] !== "") out[key] = row[key];
    });
    return out;
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
            // Nov 12 2026 (Amit: "1s, 2s missing" in Edit): 0s / 1s / 2s / 3s are typed in the form now
            dots: fieldNum(row.querySelector('[data-f="dots"]')),
            ones: fieldNum(row.querySelector('[data-f="ones"]')),
            twos: fieldNum(row.querySelector('[data-f="twos"]')),
            threes: fieldNum(row.querySelector('[data-f="threes"]')),
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
            ...kept(sourceRow(index, "bowling", row.querySelector('[data-f="name"]').dataset.orig || name), ["over_runs", "dots", "fours", "sixes"]),
            wides: fieldNum(row.querySelector('[data-f="wides"]')),
            no_balls: fieldNum(row.querySelector('[data-f="no_balls"]')),
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
        extras: (() => {
          const part = (key) => fieldNum(box.querySelector(`[data-x="${key}"]`));
          const parts = { wides: part("wides"), no_balls: part("no_balls"), byes: part("byes"), leg_byes: part("leg_byes") };
          const typed = fieldNum(box.querySelector('[data-t="extras"]'));
          const sum = Object.values(parts).reduce((total, value) => total + (value || 0), 0);
          return { ...parts, penalties: null, total: typed ?? (Object.values(parts).some((value) => value !== null) ? sum : null) };
        })(),
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
        captains: { team_1: val('[data-m="cap1"]') || null, team_2: val('[data-m="cap2"]') || null },
        man_of_match: val('[data-m="mom"]') || null,
      },
      innings,
      validation: { inning_1_total: innings[0]?.summary.runs ?? null, inning_2_total: innings[1]?.summary.runs ?? null, expected_result: val('[data-m="result"]'), is_consistent: null, notes: "Typed in on the scorecard page." },
    };
  }

  document.addEventListener("input", (event) => {
    const part = event.target.closest("#scEditor [data-x]");
    if (part) {
      const box = part.closest("[data-innings]");
      const values = Array.from(box.querySelectorAll("[data-x]")).map((el) => fieldNum(el));
      if (values.some((value) => value !== null)) box.querySelector('[data-t="extras"]').value = values.reduce((total, value) => total + (value || 0), 0);
    }
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
      editorSwapped = false;
    }
    if (action === "swap") {
      openEditor(true);
      return;
    }
    updateSums();
  });

  document.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-sce-form]");
    if (!form) return;
    event.preventDefault();
    const msg = form.querySelector("[data-sce-msg]");
    const button = form.querySelector('button[type="submit"]');
    // the form is in parts: a missing required box (team, date) may be on a part that is not showing
    const missing = form.querySelector(":invalid");
    if (missing) {
      const step = missing.closest("[data-sce-step]");
      if (step) showEditorStep(form.closest("#scEditor") || document, step.dataset.sceStep);
      missing.reportValidity();
      return;
    }
    const allSave = Array.from(form.querySelectorAll('button[type="submit"]'));
    allSave.forEach((b) => (b.disabled = true));
    msg.textContent = "Saving…";
    form.querySelector(".sce-save-bar")?.scrollIntoView({ behavior: "smooth", block: "center" });
    try {
      const data = await previewAction(`/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/manual`, { template: buildTemplate(form) }).catch((error) => {
        // Nov 14 2026: iPhones say only "Load failed" when the connection drops; say what happened
        if (error instanceof TypeError) throw new Error("The connection dropped while saving (weak signal or the site was restarting). Your changes are still here - tap Save scorecard again.");
        throw error;
      });
      document.getElementById("scEditor")?.remove();
      editorShown = true; // don't pop the editor open again after saving
      await loadPreview();
      checkEl.querySelector(".sc-check-msg").textContent = data.message || "Saved.";
      checkEl.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      msg.textContent = error.message;
      allSave.forEach((b) => (b.disabled = false));
    }
  });
  function nameMatchesHtml(matches) {
    return matches.map((match) => {
      const label = (m) => `<b>${escapeHtml(m.name)}</b>${(m.clubs || []).length ? ` <span class="sc-name-club">${escapeHtml(m.clubs.join(", "))}</span>` : ""}`;
      if (match.kind === "recognised") {
        // Nov 16 2026 (Amit: "once it has learnt that Amit is Amit S then it should not question again"): a club admin /
        // the superadmin confirms who the name is; it is remembered for the club and written on the card.
        const best = match.members[0];
        const why = (best.reasons || match.reasons || []).join(" · ");
        const nameAttrs = `data-card-name="${escapeHtml(match.card_name)}" data-club="${escapeHtml(match.club_id || "")}"`;
        const choices = match.can_confirm
          ? `<div class="sc-check-actions">
              ${match.members.map((m, i) => `<button type="button" class="sc-btn${i === 0 ? " primary" : ""}" data-sc="name-identity" data-member="${escapeHtml(m.id)}" ${nameAttrs}>✓ ${i === 0 ? "Yes, " : "It's "}${escapeHtml(m.name)}${m.full_name && m.full_name !== m.name ? ` (${escapeHtml(m.full_name)})` : ""}</button>`).join("")}
              <button type="button" class="sc-btn ghost" data-sc="name-identity-no" data-members="${escapeHtml(match.members.map((m) => m.id).join(","))}" ${nameAttrs}>✗ None of these</button>
            </div>`
          : `<p class="sc-check-lede"><small>A club admin of this club or the superadmin confirms it once - then it isn't asked again.</small></p>`;
        return `<div class="sc-name-match sc-name-info">
          <p class="sc-check-lede">🔎 <b>${escapeHtml(match.card_name)}</b> on this card is most likely ${label(best)}${best.full_name && best.full_name !== best.name ? ` (${escapeHtml(best.full_name)})` : ""} - ${best.confidence ?? match.match_percent}% sure${match.members.length > 1 ? `, ${match.members.slice(1).map((m) => `${escapeHtml(m.name)} ${m.confidence}%`).join(", ")}` : ""}.</p>
          ${why ? `<p class="sc-check-lede"><small>${escapeHtml(why)}</small></p>` : ""}
          ${choices}
          <p class="sc-name-merge-msg" role="status"></p>
        </div>`;
      }
      const [older, newer] = match.members;
      const pair = `data-first="${escapeHtml(older.id)}" data-second="${escapeHtml(newer.id)}"`;
      const actions = match.can_merge
        ? `<button type="button" class="sc-btn primary" data-sc="name-merge" data-keep="older" ${pair}>Merge into older record (${escapeHtml(older.name)})</button>
          <button type="button" class="sc-btn" data-sc="name-merge" data-keep="newer" ${pair}>Merge into newer record (${escapeHtml(newer.name)})</button>`
        : `<p class="sc-check-lede">Ask a club admin to merge these players.</p>`;
      return `<div class="sc-name-match sc-name-dup">
        <p class="sc-check-lede">🔎 <b>${escapeHtml(match.card_name)}</b> may be the same player as ${label(older)} and ${label(newer)} (${match.match_percent}% match).</p>
        <div class="sc-check-actions">${actions}<button type="button" class="sc-btn ghost" data-sc="name-ignore" ${match.can_merge ? pair : ""}>Not the same, ignore</button></div>
        <p class="sc-name-merge-msg" role="status"></p>
      </div>`;
    }).join("");
  }
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
        ${nameMatchesHtml(data.name_matches || [])}
        ${new URLSearchParams(location.search).get("joined") === "1" ? `<p class="sc-check-lede sc-joined-note">🔗 This photo was the other innings of a match already uploaded, so both innings are now one scorecard.</p>` : ""}
        ${data.match_code ? `<p class="sc-check-lede">Match ID <b>${escapeHtml(data.match_code)}</b>${data.innings_count < 2 ? " · if the other team has their innings, give them this ID so they can link it" : ""}.</p>` : ""}
        ${(data.duplicate_candidates || []).length && data.can_delete ? `<div class="sc-second-photo">
          <p class="sc-check-lede"><strong>The same innings was uploaded twice.</strong> Keep this one and delete the duplicate?</p>
          ${data.duplicate_candidates.map((c) => `<button type="button" class="sc-btn sc-danger" data-sc="remove-dup" data-other="${escapeHtml(c.id)}" data-published="${c.is_published ? "1" : "0"}">🗑 Delete duplicate ${escapeHtml(c.match_code)}${c.file_name ? ` (${escapeHtml(c.file_name)})` : ""}</button>`).join(" ")}
        </div>` : ""}
        ${(data.link_candidates || []).length && !data.other_half ? `<div class="sc-second-photo">
          <p class="sc-check-lede"><strong>Is one of these the other team's innings of the same match?</strong> Link it and the match gets both innings.</p>
          ${data.link_candidates.map((c) => `<button type="button" class="sc-btn" data-sc="link" data-code="${escapeHtml(c.match_code)}">🔗 Link with ${escapeHtml(c.match_code)}${c.file_name ? ` (${escapeHtml(c.file_name)})` : ""}</button>`).join(" ")}
        </div>` : ""}
        ${data.innings_count < 2 && data.can_edit ? `<form class="sc-link-form" data-sc-link>
          <label for="scLinkCode">Other team already uploaded their innings? Enter their Match ID</label>
          <div class="sc-link-row"><input id="scLinkCode" placeholder="e.g. M-8A311D9B" autocomplete="off" /><button type="submit" class="sc-btn">🔗 Link</button></div>
        </form>` : ""}
        ${data.other_half ? `<div class="sc-second-photo">
          <p class="sc-check-lede"><strong>The other innings of this match was uploaded separately</strong> ('${escapeHtml(data.other_half.file_name)}'${data.other_half.uploaded_by ? ` by ${escapeHtml(data.other_half.uploaded_by)}` : ""}): same date and teams. Join them into one scorecard?</p>
          <button type="button" class="sc-btn primary" data-sc="join" data-other="${escapeHtml(data.other_half.id)}">🔗 Join the two innings</button>
        </div>` : ""}
        ${data.can_add_second_photo && !data.other_half ? `<div class="sc-second-photo">
          <p class="sc-check-lede"><strong>Only ${data.innings_count === 1 ? "one innings" : "part of the match"} is on this photo.</strong> Is the other team's batting on a second page? Add its photo and it is joined to this scorecard.</p>
          <label class="sc-btn primary sc-second-btn">📷 Add the ${missingInningsLabel(data)} innings photo
            <input type="file" accept="image/*,.jpg,.jpeg,.png,.webp,.heic,.heif" data-sc-second hidden />
          </label>
        </div>` : ""}
        <div class="sc-check-actions">
          ${data.can_publish ? `<button type="button" class="sc-btn primary" data-sc="publish">✓ Looks right, publish</button>` : ""}
          ${data.can_edit && data.ai_available ? `<button type="button" class="sc-btn${data.unreadable ? " primary" : ""}" data-sc="ai-read">🤖 ${data.ai_read ? "Read again with AI" : "Read with AI"}</button>` : ""}
          ${data.can_edit && data.ai_locked ? `<a class="sc-btn" href="/pricing?feature=ai_extraction" title="AI reading of photos is part of Pro">🤖 Read with AI 🔒 Pro</a>` : ""}
          ${data.can_edit ? `<button type="button" class="sc-btn${data.unreadable && !data.ai_available ? " primary" : ""}" data-sc="edit-open">✏️ ${data.unreadable ? "Type in the scorecard" : "Edit scorecard"}</button>` : ""}
          ${data.can_report ? `<button type="button" class="sc-btn" data-sc="report-open">Something's wrong</button>` : ""}
          <a class="sc-btn ghost" href="/scorecards/upload">Upload another</a>
          ${data.can_delete ? `<button type="button" class="sc-btn sc-danger" data-sc="delete">🗑 ${data.is_published ? "Delete this scorecard" : "Delete this upload"}</button>` : ""}
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

  // Nov 14 2026 (Amit): uploads are read in the background. While this one is, show where it is and look again
  // every 5 seconds; the uploader also gets a notification (and a WhatsApp) when it's done, so he can leave.
  let processingStarted = 0;
  async function stillProcessing() {
    const response = await fetch(`/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/processing`, { headers: { Accept: "application/json", "X-Auth-Token": token() } }).catch(() => null);
    const data = response && response.ok ? await response.json().catch(() => null) : null;
    if (!data || !data.processing) return false;
    processingStarted = processingStarted || Date.now();
    const secs = Math.round((Date.now() - processingStarted) / 1000);
    const where = data.state === "queued" && data.ahead ? `${data.ahead} scorecard${data.ahead === 1 ? "" : "s"} ahead of yours` : data.state === "queued" ? "starting" : "reading the photo";
    headerEl.innerHTML = `
      <div class="sc-processing" role="status">
        <p class="sc-processing-title">📄 Reading your scorecard… <small>(${escapeHtml(where)}, ${secs}s)</small></p>
        <p>Match ID <b>${escapeHtml(data.match_code || "")}</b> is saved with the photo. You'll get a notification (and a WhatsApp) when it's ready to check - you can close this page or <a href="/scorecards/upload">upload another one</a>.</p>
      </div>`;
    cardPanel.innerHTML = "";
    setTimeout(() => loadPreview().catch(() => null), 5000);
    return true;
  }

  async function loadPreview() {
    if (await stillProcessing()) return null;
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
    const msg = checkEl.querySelector(":scope > .sc-check > .sc-check-msg");
    if (button.dataset.sc === "name-ignore") {
      // Nov 16 2026: remembered (same as Admin Center -> Name Matches -> "Not the same player"), so it isn't asked again
      if (button.dataset.first && button.dataset.second) {
        fetch("/api/admin/name-matches/reject", {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-Auth-Token": token() },
          body: JSON.stringify({ first_member_id: button.dataset.first, second_member_id: button.dataset.second }),
        }).catch(() => null);
      }
      button.closest(".sc-name-match")?.remove();
      return;
    }
    if (button.dataset.sc === "name-identity" || button.dataset.sc === "name-identity-no") {
      const box = button.closest(".sc-name-match");
      const msg = box.querySelector(".sc-name-merge-msg");
      box.querySelectorAll("button").forEach((b) => (b.disabled = true));
      const yes = button.dataset.sc === "name-identity";
      try {
        const data = await previewAction(`/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/${yes ? "name-identity" : "name-identity-reject"}`, {
          card_name: button.dataset.cardName,
          club_id: button.dataset.club,
          ...(yes ? { member_id: button.dataset.member } : { member_ids: String(button.dataset.members || "").split(",").filter(Boolean) }),
        });
        if (yes && data.changed) {
          await loadPreview();
          const note = checkEl?.querySelector(":scope > .sc-check > .sc-check-msg");
          if (note) note.textContent = data.message;
        } else {
          box.innerHTML = `<p class="sc-check-lede">✓ ${escapeHtml(data.message || "Saved.")}</p>`;
        }
      } catch (error) {
        msg.textContent = error.message;
        box.querySelectorAll("button").forEach((b) => (b.disabled = false));
      }
      return;
    }
    if (button.dataset.sc === "name-merge") {
      const keep = button.dataset.keep;
      if (!window.confirm("Merge these players? Their stats are added together and the other name becomes an alias of the kept player.")) return;
      const matchMsg = button.closest(".sc-name-match").querySelector(".sc-name-merge-msg");
      matchMsg.textContent = "";
      document.querySelectorAll(".sc-name-match [data-sc='name-merge']").forEach((b) => (b.disabled = true));
      let data;
      try {
        data = await previewAction(`/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/name-merge`, {
          first_id: button.dataset.first,
          second_id: button.dataset.second,
          keep,
        });
      } catch (error) {
        document.querySelectorAll(".sc-name-match [data-sc='name-merge']").forEach((b) => (b.disabled = false));
        matchMsg.textContent = error.message;
        return;
      }
      try {
        await loadPreview();
        const note = checkEl?.querySelector(":scope > .sc-check > .sc-check-msg");
        if (note) note.textContent = data.message || "Players merged.";
      } catch (error) {
        matchMsg.textContent = `${data.message || "Players merged."} Could not refresh the scorecard: ${error.message} Reload the page.`;
      }
      return;
    }
    if (button.dataset.sc === "delete") {
      const isPublished = Boolean(lastPreview && lastPreview.is_published);
      const ask = isPublished
        ? "This scorecard is PUBLISHED and everyone can see it. Delete it and its photo for everyone? This can't be undone. You can upload the photo again afterwards."
        : "Delete this upload and its photo? This can't be undone. You can upload the photo again afterwards.";
      if (!window.confirm(ask)) return;
      button.disabled = true;
      try {
        const response = await fetch(`/api/admin/archive/${encodeURIComponent(id.replace(/^a-/, ""))}${isPublished ? "?published=1" : ""}`, { method: "DELETE", headers: { "X-Auth-Token": token() } });
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
    if (button.dataset.sc === "link") {
      linkTo(button.dataset.code, button);
      return;
    }
    if (button.dataset.sc === "join") {
      button.disabled = true;
      button.textContent = "🔗 Joining…";
      try {
        const data = await previewAction(`/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/join/${encodeURIComponent(button.dataset.other)}`);
        if (data.preview_url && !data.preview_url.startsWith(location.pathname)) {
          location.href = data.preview_url;
          return;
        }
        document.getElementById("scEditor")?.remove();
        await loadPreview();
        checkEl.querySelector(".sc-check-msg").textContent = data.message || "Joined.";
      } catch (error) {
        msg.textContent = error.message;
        button.disabled = false;
        button.textContent = "🔗 Join the two innings";
      }
      return;
    }
    if (button.dataset.sc === "remove-dup") {
      const ask = button.dataset.published === "1"
        ? "That duplicate is PUBLISHED. Delete it and its photo? This can't be undone."
        : "Delete the duplicate upload and its photo? This scorecard is kept. This can't be undone.";
      if (!window.confirm(ask)) return;
      button.disabled = true;
      try {
        const data = await previewAction(
          `/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/remove-duplicate/${encodeURIComponent(button.dataset.other)}`,
          { confirm_published: button.dataset.published === "1" }
        );
        document.getElementById("scEditor")?.remove();
        await loadPreview();
        checkEl.querySelector(".sc-check-msg").textContent = data.message || "Deleted.";
      } catch (error) {
        msg.textContent = error.message;
        button.disabled = false;
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

  // Nov 6 2026: when the uploaded photo is the 2nd innings, the missing one is the 1st.
  function missingInningsLabel(data) {
    const ids = ((data && data.scorecard && data.scorecard.innings_ids) || []).filter((item) => item.status === "missing");
    return ids.length && Number(ids[0].number) === 1 ? "1st" : "2nd";
  }

  // "Add the 2nd innings photo" (POST /api/scorecards/{id}/second-photo)
  document.addEventListener("change", async (event) => {
    const input = event.target.closest("[data-sc-second]");
    if (!input || !checkEl || !checkEl.contains(input) || !input.files[0]) return;
    const msg = checkEl.querySelector(".sc-check-msg");
    const label = input.closest("label");
    label.classList.add("is-busy");
    const started = Date.now();
    const tick = () => {
      msg.textContent = `📤 Adding the other innings photo and reading it… ${Math.round((Date.now() - started) / 1000)}s. Keep this page open.`;
    };
    tick();
    const timer = setInterval(tick, 1000);
    const body = new FormData();
    body.append("file", input.files[0]);
    try {
      const response = await fetch(`/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/second-photo`, { method: "POST", headers: { "X-Auth-Token": token() }, body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Couldn't add the photo.");
      clearInterval(timer);
      document.getElementById("scEditor")?.remove();
      editorShown = false;
      await loadPreview();
      checkEl.querySelector(".sc-check-msg").textContent = data.message || "Innings photo added.";
    } catch (error) {
      clearInterval(timer);
      msg.textContent = error.message;
      label.classList.remove("is-busy");
      input.value = "";
    }
  });

  // Link by Match ID (POST /api/scorecards/{id}/link)
  async function linkTo(code, button) {
    const msg = checkEl.querySelector(".sc-check-msg");
    if (button) button.disabled = true;
    msg.textContent = "🔗 Linking…";
    try {
      const data = await previewAction(`/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/link`, { match_code: code });
      if (data.preview_url && !data.preview_url.startsWith(location.pathname)) {
        location.href = data.preview_url;
        return;
      }
      document.getElementById("scEditor")?.remove();
      await loadPreview();
      checkEl.querySelector(".sc-check-msg").textContent = data.message || "Linked.";
    } catch (error) {
      msg.textContent = error.message;
      if (button) button.disabled = false;
    }
  }

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-sc-link]");
    if (!form) return;
    event.preventDefault();
    const code = form.querySelector("input").value.trim();
    if (!code) return;
    linkTo(code, form.querySelector("button"));
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

  // Nov 2 2026 (Amit): captains, club admins and superadmins can fix or delete a published uploaded scorecard
  async function offerFix() {
    if (!token() || !/^a-/.test(id)) return;
    try {
      const response = await fetch(`/api/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}/preview`, { headers: { Accept: "application/json", "X-Auth-Token": token() } });
      if (!response.ok) return;
      const data = await response.json();
      if (!data.can_edit && !data.can_delete) return;
      const bar = document.createElement("p");
      bar.className = "sc-fix-bar";
      bar.innerHTML = `<a class="sc-btn" href="/scorecards/${encodeURIComponent(id.replace(/^a-/, ""))}?preview=1">✏️ Fix or delete this scorecard</a>`;
      headerEl.after(bar);
    } catch (error) {
      /* signed out or not allowed: no button */
    }
  }

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
      const response = await fetch(`/api/public/scorecards/${encodeURIComponent(id)}`, {
        headers: { Accept: "application/json", "X-Auth-Token": token() },
      });
      if (response.status === 404) throw new Error("This scorecard isn't available. It may not be approved yet.");
      if (!response.ok) throw new Error("Unable to load this scorecard.");
      const data = await response.json();
      render(data.scorecard);
      offerFix();
    } catch (error) {
      headerEl.innerHTML = `<p class="sc-meta">Scorecard</p><h1 class="sc-title">Not found</h1>`;
      cardPanel.innerHTML = `<div class="live-empty">${escapeHtml(error.message)}</div>`;
      photoPanel.innerHTML = "";
    }
  })();
})();
