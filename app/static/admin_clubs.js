// Admin Center -> Clubs (Nov 13 2026, Amit): "only club admins or superadmin can change the name of their club or
// merge into another ... Provide list of all the clubs to admins and then they can select. Once the club is merged it
// should use either name of the club and other name becomes alias."
// Club admins see their own club(s) to edit and every club to pick from when merging; the superadmin sees all.
(function adminClubs() {
  const root = document.getElementById("clubManager");
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
  let data = { clubs: [], managed_club_ids: [], is_superadmin: false };
  let query = "";

  async function api(url, options = {}) {
    const response = await fetch(url, { ...options, headers: { ...headers, ...(options.body ? { "Content-Type": "application/json" } : {}) } }).catch(() => null);
    const body = response ? await response.json().catch(() => ({})) : {};
    if (!response || !response.ok) throw new Error(body.detail || "Something went wrong. Try again.");
    return body;
  }

  const managed = (id) => data.managed_club_ids.includes(id);
  const byId = (id) => data.clubs.find((club) => club.id === id);
  const place = (club) => [club.city, club.country].filter(Boolean).join(", ");

  function clubOptions(list, selected, placeholder) {
    return `<option value="">${esc(placeholder)}</option>` + list.map((club) => `<option value="${esc(club.id)}"${club.id === selected ? " selected" : ""}>${esc(club.name)}${place(club) ? " · " + esc(place(club)) : ""}</option>`).join("");
  }

  function render() {
    const mine = data.clubs.filter((club) => managed(club.id));
    const ordered = data.is_superadmin ? data.clubs : [...mine, ...data.clubs.filter((club) => !managed(club.id))];
    const shown = ordered.filter((club) => {
      if (!query) return true;
      const text = [club.name, club.short_name, club.city, club.country, ...(club.aliases || [])].join(" ").toLowerCase();
      return text.includes(query);
    });
    root.innerHTML = `
      <div class="acm-grid">
        <section class="acm-card">
          <header class="acm-card-head">
            <div><p class="acm-kicker">${data.is_superadmin ? "All clubs" : "Your club" + (mine.length > 1 ? "s" : "")}</p>
            <h2>${data.is_superadmin ? `${data.clubs.length} clubs` : mine.map((c) => esc(c.name)).join(", ")}</h2></div>
            <input class="acm-search" type="search" placeholder="Search clubs, city, old names..." value="${esc(query)}" aria-label="Search clubs" />
          </header>
          <div class="acm-list">
            ${shown.map((club) => clubRow(club)).join("") || '<p class="acm-empty">No club matches.</p>'}
          </div>
        </section>
        <section class="acm-card acm-merge" id="acmMerge">
          <header class="acm-card-head"><div><p class="acm-kicker">Merge clubs</p><h2>Join a duplicate club into ${data.is_superadmin ? "another" : "yours"}</h2></div></header>
          <p class="acm-help">Both clubs become one. Every player keeps all his matches and stats, now under one club. You choose which name stays; the other name becomes an alias, so old scorecards and links still find the club.</p>
          <div class="acm-merge-pick">
            <label>Club to merge away<select id="acmSource">${clubOptions(data.clubs, "", "Pick a club from the list")}</select></label>
            <span class="acm-arrow" aria-hidden="true">→</span>
            <label>Merge into${data.is_superadmin || mine.length > 1 ? `<select id="acmTarget">${clubOptions(data.is_superadmin ? data.clubs : mine, mine.length === 1 ? mine[0].id : "", "Pick the club that stays")}</select>` : `<select id="acmTarget">${clubOptions(mine, mine[0]?.id || "", "Your club")}</select>`}</label>
          </div>
          <div id="acmPreview"></div>
        </section>
      </div>`;
    root.querySelector(".acm-search").addEventListener("input", (event) => {
      query = event.target.value.trim().toLowerCase();
      const list = root.querySelector(".acm-list");
      const position = event.target.selectionStart;
      render();
      const box = root.querySelector(".acm-search");
      box.focus();
      box.setSelectionRange(position, position);
      void list;
    });
    root.querySelector("#acmSource").addEventListener("change", preview);
    root.querySelector("#acmTarget").addEventListener("change", preview);
  }

  function clubRow(club) {
    const editable = managed(club.id);
    const aliases = (club.aliases || []).map((alias) => `<span class="acm-chip" title="Old name / alias">${esc(alias)}</span>`).join("");
    return `
      <article class="acm-club${editable && !data.is_superadmin ? " is-mine" : ""}" data-club="${esc(club.id)}">
        <div class="acm-club-main">
          <div class="acm-avatar" aria-hidden="true">${esc((club.short_name || club.name || "?").slice(0, 2).toUpperCase())}</div>
          <div>
            <strong>${esc(club.name)}</strong>${club.disabled ? ' <span class="acm-chip is-off">disabled</span>' : ""}
            <small>${esc(place(club) || "No city yet")}${club.short_name && club.short_name !== club.name ? " · short name " + esc(club.short_name) : ""}</small>
            ${aliases ? `<div class="acm-chips">${aliases}</div>` : ""}
          </div>
        </div>
        <div class="acm-club-stats">
          <span><b>${club.players}</b> players</span><span><b>${club.matches}</b> match${club.matches === 1 ? "" : "es"}</span><span><b>${club.admins}</b> admin${club.admins === 1 ? "" : "s"}</span>
        </div>
        <div class="acm-club-actions">
          ${editable ? `<button class="acm-btn" type="button" data-edit="${esc(club.id)}">Edit details</button>` : ""}
          ${!editable || data.is_superadmin ? `<button class="acm-btn is-ghost" type="button" data-merge="${esc(club.id)}">Merge…</button>` : ""}
        </div>
        <form class="acm-edit" data-form="${esc(club.id)}" hidden>
          <label>Club name<input name="name" required maxlength="80" value="${esc(club.name)}" /></label>
          <label>Short name<input name="short_name" maxlength="40" value="${esc(club.short_name)}" placeholder="e.g. Heartlake" /></label>
          <label>City<input name="city" maxlength="80" value="${esc(club.city)}" placeholder="e.g. Brampton" /></label>
          <label>Country<input name="country" maxlength="80" value="${esc(club.country)}" placeholder="e.g. Canada" /></label>
          <div class="acm-edit-actions"><button class="acm-btn is-primary" type="submit">Save</button><button class="acm-btn is-ghost" type="button" data-cancel>Cancel</button></div>
          <p class="acm-note">Renaming keeps the old name as an alias, so old scorecards still count for this club.</p>
          <p class="acm-msg" role="status"></p>
        </form>
      </article>`;
  }

  root.addEventListener("click", (event) => {
    const edit = event.target.closest("[data-edit]");
    if (edit) {
      const form = root.querySelector(`[data-form="${CSS.escape(edit.dataset.edit)}"]`);
      form.hidden = !form.hidden;
      if (!form.hidden) form.querySelector("input").focus();
      return;
    }
    if (event.target.closest("[data-cancel]")) {
      event.target.closest("form").hidden = true;
      return;
    }
    const merge = event.target.closest("[data-merge]");
    if (merge) {
      const source = root.querySelector("#acmSource");
      const target = root.querySelector("#acmTarget");
      if (managed(merge.dataset.merge) && data.is_superadmin && !target.value) {
        target.value = merge.dataset.merge;
      } else {
        source.value = merge.dataset.merge;
      }
      root.querySelector("#acmMerge").scrollIntoView({ behavior: "smooth", block: "start" });
      preview();
    }
  });

  root.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-form]");
    if (!form) return;
    event.preventDefault();
    const msg = form.querySelector(".acm-msg");
    msg.textContent = "Saving...";
    msg.className = "acm-msg";
    try {
      const body = Object.fromEntries(new FormData(form).entries());
      const result = await api(`/api/clubs/${encodeURIComponent(form.dataset.form)}/settings`, { method: "POST", body: JSON.stringify(body) });
      await load();
      flash(result.message || "Saved.", "success");
    } catch (error) {
      msg.textContent = error.message;
      msg.className = "acm-msg is-error";
    }
  });

  async function preview() {
    const box = root.querySelector("#acmPreview");
    const sourceId = root.querySelector("#acmSource").value;
    const targetId = root.querySelector("#acmTarget").value;
    if (!sourceId || !targetId) {
      box.innerHTML = "";
      return;
    }
    if (sourceId === targetId) {
      box.innerHTML = '<p class="acm-msg is-error">Pick two different clubs.</p>';
      return;
    }
    box.innerHTML = '<p class="acm-empty">Checking both clubs...</p>';
    let plan;
    try {
      plan = await api(`/api/admin/clubs/merge-preview?source_id=${encodeURIComponent(sourceId)}&target_id=${encodeURIComponent(targetId)}`);
    } catch (error) {
      box.innerHTML = `<p class="acm-msg is-error">${esc(error.message)}</p>`;
      return;
    }
    const s = plan.source;
    const t = plan.target;
    const common = plan.common_players || [];
    const look = plan.look_alike_players || [];
    box.innerHTML = `
      <div class="acm-compare">
        <div class="acm-side"><p class="acm-kicker">Goes away</p><strong>${esc(s.name)}</strong><small>${s.players} players · ${s.matches} match${s.matches === 1 ? "" : "es"}</small></div>
        <div class="acm-side is-stays"><p class="acm-kicker">Stays</p><strong>${esc(t.name)}</strong><small>${t.players} players · ${t.matches} match${t.matches === 1 ? "" : "es"}</small></div>
      </div>
      <ul class="acm-facts">
        <li><b>${plan.players_after}</b> players in the merged club${common.length ? ` - ${common.length} already played for both and are counted once: ${esc(common.slice(0, 12).join(", "))}${common.length > 12 ? "…" : ""}` : ""}.</li>
        <li>All matches, scorecards and stats of both clubs move to the merged club. No player's runs, wickets or matches change.</li>
        ${look.length ? `<li class="is-warn">Same name in both clubs but saved as two players: ${esc(look.join(", "))}. They stay two players - join them later in <b>Name Matches</b> if they are the same person.</li>` : ""}
        ${plan.matches_between ? `<li class="is-warn">${plan.matches_between} scorecard(s) are ${esc(s.name)} v ${esc(t.name)}. After merging, both sides of those games belong to one club.</li>` : ""}
      </ul>
      <fieldset class="acm-name-choice">
        <legend>Name of the merged club</legend>
        <label><input type="radio" name="acmKeep" value="target" checked /> <span><b>${esc(t.name)}</b> <small>(${esc(s.name)} becomes an alias)</small></span></label>
        <label><input type="radio" name="acmKeep" value="source" /> <span><b>${esc(s.name)}</b> <small>(${esc(t.name)} becomes an alias)</small></span></label>
      </fieldset>
      <div class="acm-confirm">
        <label><span>Type <b>MERGE</b> to confirm</span><input id="acmConfirm" autocomplete="off" placeholder="MERGE" /></label>
        <button class="acm-btn is-danger" type="button" id="acmGo" disabled>Merge clubs</button>
      </div>
      <p class="acm-note">This can't be undone from here - check the two clubs above first.</p>
      <p class="acm-msg" id="acmMergeMsg" role="status"></p>`;
    const confirmBox = box.querySelector("#acmConfirm");
    const go = box.querySelector("#acmGo");
    confirmBox.addEventListener("input", () => {
      go.disabled = confirmBox.value.trim().toUpperCase() !== "MERGE";
    });
    go.addEventListener("click", async () => {
      const msg = box.querySelector("#acmMergeMsg");
      go.disabled = true;
      msg.className = "acm-msg";
      msg.textContent = "Merging... this can take a minute while every player's stats are recalculated.";
      try {
        const keep = box.querySelector('input[name="acmKeep"]:checked').value;
        const result = await api("/api/admin/clubs/merge", {
          method: "POST",
          body: JSON.stringify({ source_id: sourceId, target_id: targetId, keep_name: keep, confirmation: confirmBox.value }),
        });
        await load();
        flash(result.message, "success");
      } catch (error) {
        msg.textContent = error.message;
        msg.className = "acm-msg is-error";
        go.disabled = false;
      }
    });
  }

  function flash(text, tone) {
    let bar = root.querySelector(".acm-flash");
    if (!bar) {
      bar = document.createElement("p");
      root.prepend(bar);
    }
    bar.className = `acm-flash is-${tone}`;
    bar.textContent = text;
    bar.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  async function load() {
    try {
      data = await api("/api/admin/club-management");
      render();
    } catch (error) {
      root.innerHTML = `<p class="acm-msg is-error">${esc(error.message)}</p>`;
    }
  }

  load();
})();
