(() => {
  const listEl = document.getElementById("publicClubsList");
  const countEl = document.getElementById("publicClubsCount");
  const upcomingEl = document.getElementById("publicClubsUpcoming");
  const badgeEl = document.getElementById("publicClubsBadge");
  const searchEl = document.getElementById("publicClubsSearch");
  let clubs = [];

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function clubCard(club) {
    const place = [club.city, club.country].filter(Boolean).join(", ") || "Location TBD";
    const fixtures = Number(club.fixture_count || 0);
    const upcoming = Number(club.upcoming_count || 0);
    return `
      <article class="live-card fixtures-card">
        <div class="live-card-head">
          <div>
            <h4>${escapeHtml(club.name || "Club")}</h4>
            <p>${escapeHtml(place)}${club.short_name ? ` · ${escapeHtml(club.short_name)}` : ""}</p>
          </div>
          <span class="signin-widget-pill">${escapeHtml(club.season || "Season TBD")}</span>
        </div>
        <p>${fixtures} fixture${fixtures === 1 ? "" : "s"} · ${upcoming} upcoming</p>
        <div class="live-cta-row">
          <a class="live-action secondary" href="/fixtures">View fixtures</a>
        </div>
      </article>
    `;
  }

  function render() {
    const query = String(searchEl?.value || "").trim().toLowerCase();
    const visible = clubs.filter((club) =>
      !query ||
      [club.name, club.short_name, club.city, club.country].some((value) =>
        String(value || "").toLowerCase().includes(query)
      )
    );
    if (badgeEl) badgeEl.textContent = query ? `${visible.length} match` : `${clubs.length} clubs`;
    listEl.innerHTML = visible.length
      ? visible.map(clubCard).join("")
      : `<div class="live-empty">No clubs match that search.</div>`;
  }

  async function load() {
    try {
      const response = await fetch("/api/public/clubs", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Unable to load clubs.");
      const data = await response.json();
      clubs = Array.isArray(data.clubs) ? data.clubs : [];
      if (countEl) countEl.textContent = String(clubs.length);
      if (upcomingEl) {
        upcomingEl.textContent = String(clubs.reduce((sum, club) => sum + Number(club.upcoming_count || 0), 0));
      }
      render();
    } catch (error) {
      console.error("[Public Clubs]", error);
      listEl.innerHTML = `<div class="live-empty">Clubs could not be loaded right now.</div>`;
      if (badgeEl) badgeEl.textContent = "Unavailable";
    }
  }

  // Opened from the navbar search (e.g. /clubs?q=Heartlake): start with that filter.
  const initialQuery = new URLSearchParams(window.location.search).get("q") || "";
  if (searchEl && initialQuery) searchEl.value = initialQuery;
  searchEl?.addEventListener("input", render);
  load();
})();
