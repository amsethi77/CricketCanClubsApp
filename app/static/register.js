console.log("Register page script loaded");

document.addEventListener("DOMContentLoaded", () => {
  console.log("Register page ready");

  if (!window.CricketClubAppPages) {
    console.error("❌ ClubPages not available");
    return;
  }

  const { getJson, postJson, setAuthToken, setPrimaryClubId, optionMarkup } = window.CricketClubAppPages;

  const form = document.getElementById("registerForm");
  const roleSelect = document.getElementById("registerRole");
  const clubSearchInput = document.getElementById("registerClubSearch");
  const clubSelect = document.getElementById("registerClub");
  const memberSelect = document.getElementById("registerMember");
  const memberRow = document.getElementById("registerMemberRow");
  const statusBanner = document.getElementById("registerStatus");
  const newClubNameInput = document.getElementById("registerNewClubName");
  const newClubCityInput = document.getElementById("registerNewClubCity");
  const newClubCountryInput = document.getElementById("registerNewClubCountry");

  const displayNameInput = document.getElementById("registerDisplayName");
  const mobileInput = document.getElementById("registerMobile");
  const emailInput = document.getElementById("registerEmail");
  const passwordInput = document.getElementById("registerPassword");

  console.log("Register form found");

  // Nov 25 2026 (Dhruvika: "Register club open player registration page and not club registration"): "Register your
  // club" opens /register?club=new - the same form set up for a new club: club admin, the new club's name / city /
  // country, no "find your club" or player profile pickers.
  const params = new URLSearchParams(window.location.search);
  const clubMode = params.get("club") === "new" || params.get("mode") === "club";
  let knownClubs = [];
  function setUpClubMode() {
    const show = (id, visible) => {
      const el = document.getElementById(id);
      if (el) el.hidden = !visible;
    };
    if (!clubMode) return;
    document.title = "Register your club · CricketClubApp";
    const text = (id, value) => {
      const el = document.getElementById(id);
      if (el) el.textContent = value;
    };
    text("registerKicker", "Register a club");
    text("registerTitle", "Register your club");
    text("registerLede", "Add your club and become its club admin. Your players can then register and pick your club.");
    const switchEl = document.getElementById("registerSwitch");
    if (switchEl) switchEl.innerHTML = '<a href="/register">Joining a club as a player? Register as a player →</a>';
    show("registerClubSearchRow", false);
    show("registerClubRow", false);
    show("registerClubAdminNote", true);
    if (memberRow) memberRow.hidden = true;
    const details = document.getElementById("registerNewClub");
    if (details) {
      details.open = true;
      details.classList.add("rg-club-mode");
      const summary = details.querySelector("summary");
      if (summary) summary.hidden = true;
    }
    [newClubNameInput, newClubCityInput, newClubCountryInput].forEach((input) => {
      if (input) input.required = true;
    });
    if (newClubCountryInput && !newClubCountryInput.value) newClubCountryInput.value = "Canada";
    if (roleSelect) {
      roleSelect.value = "club_admin";
      roleSelect.disabled = true;
    }
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.textContent = "Register club";
  }

  if (!form) {
    console.error("❌ registerForm NOT FOUND");
    return;
  }

  function setStatus(message, tone = "info") {
    if (!statusBanner) return;
    const show = Boolean(message) && (tone === "error" || tone === "warning");
    statusBanner.hidden = !show;
    statusBanner.textContent = show ? message : "";
    statusBanner.className = `status-banner ${tone}`;
    // Nov 17 2026 (Amit: "right now it doesn't tell anything"): the message is at the top of the form - bring it
    // into view so the person sees what went wrong
    if (show) statusBanner.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  // Nov 17 2026 (Amit: "when they register, we should show them some message ... for a few seconds. If he presses
  // okay, okay. If he doesn't, then it should go away ... and route him to the login page"): a short "You're
  // registered" box, then the Sign in page with the mobile / email filled in. The person is NOT signed in here.
  function showRegisteredBox(name, identifier) {
    const goSignIn = () => {
      window.location.href = `/signin?registered=1${identifier ? `&id=${encodeURIComponent(identifier)}` : ""}`;
    };
    const box = document.createElement("div");
    box.setAttribute("role", "alertdialog");
    box.setAttribute("aria-modal", "true");
    box.style.cssText = "position:fixed;inset:0;z-index:5000;display:grid;place-items:center;background:rgba(15,23,42,.45);padding:16px";
    box.innerHTML = `
      <div style="max-width:380px;width:100%;background:#fff;border-radius:16px;padding:22px;text-align:center;box-shadow:0 20px 50px rgba(15,23,42,.3);font-family:inherit">
        <div style="font-size:40px;line-height:1">✅</div>
        <h2 style="margin:10px 0 6px;font-size:1.25rem;color:#0f172a">You're registered${name ? `, ${String(name).replace(/[<>&"]/g, "")}` : ""}!</h2>
        <p style="margin:0 0 16px;color:#475569">Sign in with your ${identifier && identifier.includes("@") ? "email" : "mobile number"} and password to continue.</p>
        <button type="button" class="primary-button" data-ok style="min-width:140px">OK, sign in</button>
        <p style="margin:12px 0 0;font-size:.8rem;color:#94a3b8">Taking you to Sign in in <span data-left>5</span> s…</p>
      </div>`;
    document.body.appendChild(box);
    box.querySelector("[data-ok]").addEventListener("click", goSignIn);
    box.querySelector("[data-ok]").focus();
    let left = 5;
    const timer = setInterval(() => {
      left -= 1;
      const el = box.querySelector("[data-left]");
      if (el) el.textContent = String(left);
      if (left <= 0) {
        clearInterval(timer);
        goSignIn();
      }
    }, 1000);
  }

  function syncRoleVisibility() {
    if (!memberRow) return;
    memberRow.hidden = clubMode;
    if (clubMode && roleSelect) roleSelect.value = "club_admin";
  }

  function normalizeMobile(value) {
    return (value || "").replace(/\D/g, ""); // remove non-digits
  }

  function normalizeText(value) {
    return String(value || "").trim().toLowerCase();
  }

  function clubLabel(club) {
    const parts = [club?.name, club?.city, club?.country].filter(Boolean);
    return `${parts.join(" · ")}${club?.season ? ` · ${club.season}` : ""}`;
  }

  function renderClubOptions(clubs, search = "") {
    if (!clubSelect) return;
    const query = normalizeText(search);
    const filtered = query
      ? clubs.filter((club) => {
          const haystack = `${club.name || ""} ${club.short_name || ""} ${club.city || ""} ${club.country || ""} ${club.season || ""}`.toLowerCase();
          return haystack.includes(query);
        })
      : clubs;
    clubSelect.innerHTML = `<option value="">Select an existing club</option>` + optionMarkup(filtered, "id", clubLabel);
    if (clubSelect.value && !filtered.some((club) => club.id === clubSelect.value)) {
      clubSelect.value = "";
    }
  }

  async function loadOptions() {
    try {
      console.log("🔄 Loading registration options...");
      const data = await getJson("/api/auth/options");
      const clubs = Array.isArray(data.clubs) ? data.clubs : [];
      knownClubs = clubs;

      if (clubSearchInput) {
        clubSearchInput.value = "";
        clubSearchInput.addEventListener("input", () => renderClubOptions(clubs, clubSearchInput.value));
      }

      if (clubSelect) {
        renderClubOptions(clubs, clubSearchInput?.value || "");
      }

      if (memberSelect) {
        memberSelect.innerHTML =
          `<option value="">Not linked yet</option>` +
          optionMarkup(
            data.members,
            "id",
            (member) =>
              `${member.full_name || member.name} · ${member.player_id || "No Player ID"} · ${(member.club_names || []).join(", ") || member.team_name || "No team"}`
          );
      }

      const roles = (data.roles || []).filter((r) => r.role_name);

      if (roleSelect && roles.length) {
        const picked = roleSelect.value; // the page already shows Player / Captain / Club admin: keep the choice
        roleSelect.innerHTML = optionMarkup(
          roles,
          "role_name",
          (r) => r.display_name || r.role_name
        );
        roleSelect.value = roles.some((r) => r.role_name === picked) ? picked : "player";
        if (typeof syncRoleVisibility === "function") syncRoleVisibility();
      }

    } catch (error) {
      console.error("❌ Failed to load options:", error);
      setStatus("Failed to load registration options", "error");
    }
  }

  if (roleSelect) {
    roleSelect.addEventListener("change", syncRoleVisibility);
  }

  form.addEventListener("submit", async (event) => {
    console.log("Submitting registration");

    event.preventDefault();
    event.stopPropagation();



    const payload = {
    display_name: document.getElementById("registerDisplayName")?.value.trim() || "",
    mobile: document.getElementById("registerMobile")?.value.trim() || "",
    email: document.getElementById("registerEmail")?.value.trim() || "",
    password: document.getElementById("registerPassword")?.value || "",
    role: clubMode ? "club_admin" : roleSelect?.value || "player",
    primary_club_id: clubMode ? "" : clubSelect?.value || "",
    member_name: displayNameInput?.value.trim() || "",
    member_id: clubMode ? "" : memberSelect?.value || "",
    player_id: document.getElementById("registerPlayerId")?.value.trim() || "",
    aliases: document.getElementById("registerAliases")?.value.trim() || "",
    date_of_birth: document.getElementById("registerDateOfBirth")?.value || "",
    city: (document.getElementById("registerCity")?.value || "").trim(),
    country: (document.getElementById("registerCountry")?.value || "").trim(),
    club_name: newClubNameInput?.value.trim() || "",
    club_city: newClubCityInput?.value.trim() || "",
    club_country: newClubCountryInput?.value.trim() || ""
  };

    console.log("📤 Registration payload:", payload);

    // 🔥 VALIDATION
    if (!payload.display_name) {
      setStatus("❌ Display name required", "error");
      return;
    }

    if (!payload.password) {
      setStatus("❌ Password required", "error");
      return;
    }

    if (!payload.mobile && !payload.email) {
      setStatus("❌ Provide mobile or email", "error");
      return;
    }

    if (clubMode && !payload.club_name) {
      setStatus("❌ Enter your club's name", "error");
      return;
    }

    if (clubMode) {
      const same = knownClubs.find((club) => [club.name, club.short_name].some((name) => normalizeText(name) && normalizeText(name) === normalizeText(payload.club_name)));
      if (same) {
        setStatus(`❌ ${same.name} is already registered. Ask its club admin to add you, or register as a player and pick it.`, "error");
        return;
      }
    }

    if (!payload.primary_club_id && !payload.club_name) {
      setStatus("❌ Select a club or add a new one", "error");
      return;
    }

    if (!payload.primary_club_id && payload.club_name && (!payload.club_city || !payload.club_country)) {
      setStatus("❌ Add club city and country to create a new club", "error");
      return;
    }

    const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
    const submitText = submitButton ? submitButton.textContent : "";
    try {
      setStatus("", "info");
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = "Registering…";
      }

      const data = await postJson("/api/auth/register", payload);

      console.log("✅ Registration response:", data);

      // The server opens a session on register; close it so the person signs in first (and a token from an earlier
      // person on this phone isn't left behind).
      try {
        window.localStorage.removeItem("cricketClubAppAuthToken");
      } catch (storageError) {
        /* private mode */
      }
      if (data && data.token) {
        await fetch("/api/auth/signout", { method: "POST", headers: { "X-Auth-Token": data.token }, credentials: "same-origin" }).catch(() => null);
      }
      showRegisteredBox(payload.display_name, payload.mobile || payload.email);

    } catch (error) {
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = submitText;
      }
      console.error("❌ Registration failed:", error);

      const msg =
        error?.response?.detail ||
        error?.detail ||
        error?.message ||
        JSON.stringify(error);

      setStatus(`❌ ${msg}`, "error");
    }
  });

  setUpClubMode();
  loadOptions().then(syncRoleVisibility);
});
