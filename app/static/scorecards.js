/*
 * Public scorecard archive: approved scorecards grouped by game date.
 * Filters: game date (date picker), club, season. Filters are kept in the URL (?date=&club=&year=).
 */
(() => {
  const listEl = document.getElementById("scList");
  const badgeEl = document.getElementById("scBadge");
  const titleEl = document.getElementById("scListTitle");
  const noticeEl = document.getElementById("scNotice");
  const dateEl = document.getElementById("scDate");
  const clubEl = document.getElementById("scClub");
  const yearEl = document.getElementById("scYear");
  const clearEl = document.getElementById("scClear");
  let all = [];

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
    const date = new Date(y, (m || 1) - 1, d || 1);
    return { y, m, d, day: DAYS[date.getDay()], month: MONTHS[(m || 1) - 1] };
  }

  function longDate(iso) {
    const p = parts(iso);
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
    const tags = [
      item.club_name ? `<span class="sc-tag">${escapeHtml(item.club_name)}</span>` : "",
      item.venue ? `<span class="sc-tag">📍 ${escapeHtml(item.venue)}</span>` : "",
      item.has_photo ? `<span class="sc-tag sc-tag-photo">📷 Photo</span>` : "",
      !item.has_details ? `<span class="sc-tag sc-tag-muted">Totals only</span>` : "",
    ].join("");
    return `
      <a class="sc-card" href="/scorecards/${encodeURIComponent(item.id)}">
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
      </a>`;
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
    if (clubEl.value) params.set("club", clubEl.value);
    if (yearEl.value) params.set("year", yearEl.value);
    const query = params.toString();
    history.replaceState(null, "", query ? `/scorecards?${query}` : "/scorecards");
  }

  function render() {
    const date = dateEl.value;
    const club = clubEl.value;
    const year = yearEl.value;
    clearEl.hidden = !(date || club || year);
    syncUrl();

    const base = all.filter((item) => (!club || item.club_id === club) && (!year || item.year === year));
    const visible = date ? base.filter((item) => item.date === date) : base;

    titleEl.textContent = date ? longDate(date) : year ? `${year} season` : "All scorecards";
    badgeEl.textContent = `${visible.length} scorecard${visible.length === 1 ? "" : "s"}`;
    noticeEl.hidden = true;

    if (!visible.length) {
      if (date && base.length) {
        const near = nearestDates(date, base);
        noticeEl.hidden = false;
        noticeEl.innerHTML =
          `No approved scorecard on ${escapeHtml(longDate(date))}. Closest game dates: ` +
          near.map((d) => `<button type="button" class="sc-chip" data-date="${d}">${escapeHtml(longDate(d))}</button>`).join(" ");
        listEl.innerHTML = "";
      } else {
        listEl.innerHTML = `<div class="live-empty">No approved scorecards yet. Scorecards appear here once an archive upload is approved.</div>`;
      }
      return;
    }

    // Group by month, newest first.
    const groups = new Map();
    visible.forEach((item) => {
      const p = parts(item.date);
      const key = `${p.y}-${String(p.m).padStart(2, "0")}`;
      if (!groups.has(key)) groups.set(key, { label: `${p.month} ${p.y}`, items: [] });
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
      const response = await fetch("/api/public/scorecards", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Unable to load scorecards.");
      const data = await response.json();
      all = Array.isArray(data.scorecards) ? data.scorecards : [];
      fillSelect(clubEl, (data.clubs || []).map((club) => [club.id, club.name]));
      const years = [...new Set(all.map((item) => item.year).filter(Boolean))].sort().reverse();
      fillSelect(yearEl, years.map((y) => [y, y]));
      const dates = all.map((item) => item.date).filter(Boolean).sort();
      if (dates.length) {
        dateEl.min = dates[0];
        dateEl.max = dates[dates.length - 1];
      }
      const params = new URLSearchParams(location.search);
      dateEl.value = params.get("date") || "";
      if (params.get("club")) clubEl.value = params.get("club");
      if (params.get("year")) yearEl.value = params.get("year");
      render();
    } catch (error) {
      badgeEl.textContent = "Unavailable";
      listEl.innerHTML = `<div class="live-empty">${escapeHtml(error.message || "Unable to load scorecards.")}</div>`;
    }
  }

  dateEl.addEventListener("change", render);
  clubEl.addEventListener("change", render);
  yearEl.addEventListener("change", () => {
    if (dateEl.value && yearEl.value && !dateEl.value.startsWith(yearEl.value)) dateEl.value = "";
    render();
  });
  clearEl.addEventListener("click", () => {
    dateEl.value = "";
    clubEl.value = "";
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
})();
