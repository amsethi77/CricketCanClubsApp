/*
 * Public scorecard archive: approved uploads and played fixture scorebooks grouped by game date.
 * Filters: game date (date picker), club, season. Filters are kept in the URL (?date=&club=&year=).
 */
(() => {
  const listEl = document.getElementById("scList");
  const badgeEl = document.getElementById("scBadge");
  const titleEl = document.getElementById("scListTitle");
  const noticeEl = document.getElementById("scNotice");
  const actionStatusEl = document.getElementById("scActionStatus");
  const dateEl = document.getElementById("scDate");
  const clubEl = document.getElementById("scClub");
  const yearEl = document.getElementById("scYear");
  const clearEl = document.getElementById("scClear");
  let all = [];
  let manager = null;
  let fixedClubId = "";
  let canSelectClub = false;

  const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function parts(iso) {
    const [y, m, d] = String(iso || "").split("-").map(Number);
    // Nov 5 2026: an upload whose date wasn't read showed "January 0" / "MON undefined JAN".
    if (!y || !m || !d) return { y: 0, m: 0, d: "?", day: "", month: "", none: true };
    const date = new Date(y, (m || 1) - 1, d || 1);
    return { y, m, d, day: DAYS[date.getDay()], month: MONTHS[(m || 1) - 1] };
  }

  function longDate(iso) {
    const p = parts(iso);
    if (p.none) return "Date not set";
    return `${p.day} ${p.d} ${p.month} ${p.y}`;
  }

  function teamRow(team) {
    const score = team.score
      ? `<strong>${escapeHtml(team.score)}</strong>${team.overs ? ` <small>(${escapeHtml(team.overs)} ov)</small>` : ""}`
      : `<span class="sc-dash">–</span>`;
    return `<div class="sc-team-row"><span class="sc-team-name">${escapeHtml(team.name)}</span><span class="sc-team-score">${score}</span></div>`;
  }

  function card(item) {
    const p = parts(item.date);
    const canDelete = Boolean(
      manager &&
      item.source === "fixture" &&
      item.is_incomplete &&
      (manager.role === "superadmin" || (
        manager.role === "club_admin" &&
        String(item.club_id || "") === manager.clubId
      ))
    );
    const tags = [
      item.pending ? `<span class="sc-tag sc-tag-missing">⏳ Waiting for review</span>` : "",
      item.club_name ? `<span class="sc-tag">${escapeHtml(item.club_name)}</span>` : "",
      item.venue ? `<span class="sc-tag">📍 ${escapeHtml(item.venue)}</span>` : "",
      item.has_photo ? `<span class="sc-tag sc-tag-photo">📷 Photo</span>` : "",
      item.match_code ? `<span class="sc-tag sc-tag-muted">${escapeHtml(item.match_code)}</span>` : "",
      (item.innings_ids || []).some((i) => i.status === "missing") && item.source !== "fixture"
        ? `<span class="sc-tag sc-tag-missing">⚠ ${(item.innings_ids || []).filter((i) => i.status === "missing").map((i) => `Innings ${i.number}`).join(", ")} missing</span>`
        : "",
      item.source === "fixture" && item.is_incomplete ? `<span class="sc-tag sc-tag-muted">Incomplete</span>` : "",
      !item.has_details ? `<span class="sc-tag sc-tag-muted">Totals only</span>` : "",
    ].join("");
    return `
      <article class="sc-card-wrap">
        <a class="sc-card${item.pending ? " sc-card-pending" : ""}" href="${escapeHtml(item.url || `/scorecards/${encodeURIComponent(item.id)}`)}">
          <div class="sc-card-date" aria-hidden="true">
            <span>${escapeHtml(p.day)}</span>
            <strong>${p.d}</strong>
            <span>${escapeHtml(p.month.slice(0, 3))}</span>
          </div>
          <div class="sc-card-body">
            <div class="sc-card-teams">${(item.teams || []).map(teamRow).join("")}</div>
            <p class="sc-card-result">${escapeHtml(item.result || "Result not recorded")}</p>
            <div class="sc-card-tags">${tags}</div>
          </div>
          <span class="sc-card-go" aria-hidden="true">›</span>
        </a>
        ${canDelete ? `<button type="button" class="sc-delete-incomplete" data-delete-fixture="${escapeHtml(item.fixture_id)}" data-club-id="${escapeHtml(item.club_id)}">Delete incomplete scorecard</button>` : ""}
      </article>`;
  }

  function nearestDates(target, pool, count = 3) {
    const dates = [...new Set(pool.map((item) => item.date))];
    const t = new Date(target).getTime();
    return dates
      .map((d) => ({ d, gap: Math.abs(new Date(d).getTime() - t) }))
      .sort((a, b) => a.gap - b.gap)
      .slice(0, count)
      .map((x) => x.d)
      .sort()
      .reverse();
  }

  function syncUrl() {
    const params = new URLSearchParams();
    if (dateEl.value) params.set("date", dateEl.value);
    if (canSelectClub && clubEl.value) params.set("club", clubEl.value);
    if (yearEl.value) params.set("year", yearEl.value);
    const query = params.toString();
    history.replaceState(null, "", query ? `/scorecards?${query}` : "/scorecards");
  }

  function render() {
    const date = dateEl.value;
    const club = clubEl.value;
    const year = yearEl.value;
    clearEl.hidden = !(date || year || (canSelectClub && club));
    syncUrl();

    const base = all.filter((item) => {
      const clubIds = Array.isArray(item.club_ids) ? item.club_ids : [item.club_id];
      return (!club || clubIds.includes(club)) && (!year || item.year === year);
    });
    const visible = date ? base.filter((item) => item.date === date) : base;

    const selectedClubName = clubEl.selectedOptions?.[0]?.textContent || "";
    titleEl.textContent = date ? longDate(date) : year ? `${year} season` : club ? `${selectedClubName} scorecards` : "All scorecards";
    badgeEl.textContent = `${visible.length} scorecard${visible.length === 1 ? "" : "s"}`;
    noticeEl.hidden = true;

    if (!visible.length) {
      if (date && base.length) {
        const near = nearestDates(date, base);
        noticeEl.hidden = false;
        noticeEl.innerHTML =
          `No scorecard on ${escapeHtml(longDate(date))}. Closest game dates: ` +
          near.map((d) => `<button type="button" class="sc-chip" data-date="${d}">${escapeHtml(longDate(d))}</button>`).join(" ");
        listEl.innerHTML = "";
      } else {
        listEl.innerHTML = `<div class="live-empty">No scorecards match these filters. Scored past fixtures and approved uploads appear here.</div>`;
      }
      return;
    }

    // Group by month, newest first.
    const groups = new Map();
    visible.forEach((item) => {
      const p = parts(item.date);
      const key = p.none ? "0000-00" : `${p.y}-${String(p.m).padStart(2, "0")}`;
      if (!groups.has(key)) groups.set(key, { label: p.none ? "Date not set - add it with ✏️ Edit scorecard" : `${p.month} ${p.y}`, items: [] });
      groups.get(key).items.push(item);
    });
    listEl.innerHTML = [...groups.values()]
      .map(
        (group) => `
        <section class="sc-month">
          <h3 class="sc-month-title">${escapeHtml(group.label)}</h3>
          <div class="sc-month-items">${group.items.map(card).join("")}</div>
        </section>`
      )
      .join("");
  }

  function fillSelect(select, options) {
    const current = select.value;
    select.innerHTML = select.options[0].outerHTML + options.map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join("");
    select.value = options.some(([value]) => value === current) ? current : "";
  }

  async function load() {
    try {
      let token = "";
      try {
        token = localStorage.getItem("cricketClubAppAuthToken") || "";
      } catch (error) {
        token = "";
      }
      const headers = { Accept: "application/json" };
      if (token) headers["X-Auth-Token"] = token;
      const response = await fetch("/api/public/scorecards", { headers });
      if (!response.ok) throw new Error("Unable to load scorecards.");
      const data = await response.json();
      all = Array.isArray(data.scorecards) ? data.scorecards : [];
      canSelectClub = Boolean(data.can_select_club);
      fixedClubId = String(data.selected_club_id || "");
      fillSelect(clubEl, (data.clubs || []).map((club) => [club.id, club.name]));
      clubEl.parentElement.hidden = !canSelectClub;
      clubEl.disabled = !canSelectClub;
      clubEl.value = canSelectClub
        ? (new URLSearchParams(location.search).get("club") || fixedClubId)
        : fixedClubId;
      // Nov 2: the current season is always listed, even before its first scorecard
      const thisYear = String(new Date().getFullYear());
      const years = [...new Set([thisYear, ...all.map((item) => item.year).filter(Boolean)])].sort().reverse();
      fillSelect(yearEl, years.map((y) => [y, y]));
      // Nov 2: no from / to limit on the date picker (it stopped at the last uploaded card)
      dateEl.removeAttribute("min");
      dateEl.removeAttribute("max");

      const params = new URLSearchParams(location.search);
      dateEl.value = params.get("date") || "";
      if (canSelectClub && params.get("club")) clubEl.value = params.get("club");
      if (params.get("year")) yearEl.value = params.get("year");
      render();
    } catch (error) {
      badgeEl.textContent = "Unavailable";
      listEl.innerHTML = `<div class="live-empty">${escapeHtml(error.message || "Unable to load scorecards.")}</div>`;
    }
  }

  async function loadManager() {
    let token = "";
    try {
      token = localStorage.getItem("cricketClubAppAuthToken") || "";
    } catch (error) {
      return;
    }
    if (!token) return;
    try {
      const response = await fetch("/api/auth/me", { headers: { "X-Auth-Token": token } });
      if (!response.ok) return;
      const data = await response.json();
      const user = data.user || {};
      manager = {
        role: String(user.effective_role || user.role || ""),
        clubId: String(user.current_club_id || user.primary_club_id || ""),
      };
      render();
    } catch (error) {
      manager = null;
    }
  }

  listEl.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete-fixture]");
    if (!button) return;
    const fixtureId = button.dataset.deleteFixture;
    const clubId = button.dataset.clubId;
    if (!window.confirm("Delete this incomplete scorecard and its fixture? Completed matches cannot be deleted.")) return;
    button.disabled = true;
    try {
      const token = localStorage.getItem("cricketClubAppAuthToken") || "";
      const response = await fetch(`/api/admin/clubs/${encodeURIComponent(clubId)}/fixtures/${encodeURIComponent(fixtureId)}`, {
        method: "DELETE",
        headers: { "X-Auth-Token": token },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Couldn't delete this incomplete scorecard.");
      all = all.filter((item) => String(item.fixture_id || "") !== fixtureId);
      render();
      actionStatusEl.textContent = "Incomplete scorecard deleted.";
    } catch (error) {
      actionStatusEl.textContent = error.message || "Couldn't delete this incomplete scorecard.";
      button.disabled = false;
    }
  });

  const onDate = () => {
    // keep Season in step with the picked date (a 2026 date while "2025" was picked showed nothing)
    if (dateEl.value) {
      const y = dateEl.value.slice(0, 4);
      if ([...yearEl.options].some((o) => o.value === y)) yearEl.value = y;
    }
    render();
  };
  dateEl.addEventListener("change", onDate);
  dateEl.addEventListener("input", onDate);
  clubEl.addEventListener("change", render);
  yearEl.addEventListener("change", () => {
    if (dateEl.value && yearEl.value && !dateEl.value.startsWith(yearEl.value)) dateEl.value = "";
    render();
  });
  clearEl.addEventListener("click", () => {
    dateEl.value = "";
    clubEl.value = canSelectClub ? "" : fixedClubId;
    yearEl.value = "";
    render();
  });
  noticeEl.addEventListener("click", (event) => {
    const chip = event.target.closest("[data-date]");
    if (!chip) return;
    dateEl.value = chip.dataset.date;
    render();
  });

  load();
  loadManager();
  // Captains, club admins and site admins see "Upload a scorecard" (README: "Scorecard uploads: checks, review and duplicates").
  (async () => {
    let token = "";
    try {
      token = localStorage.getItem("cricketClubAppAuthToken") || "";
    } catch (error) {
      token = "";
    }
    if (!token) return;
    try {
      const response = await fetch("/api/auth/me", { headers: { "X-Auth-Token": token } });
      if (!response.ok) return;
      const data = await response.json();
      if ((data.user?.permissions || []).includes("score_matches")) document.getElementById("scUploadCta").hidden = false;
      const role = String(data.user?.effective_role || data.user?.role || "");
      if (role === "superadmin") document.getElementById("scChecksCta").hidden = false;
    } catch (error) {
      /* signed out or offline: no upload button */
    }
  })();
})();
