console.error("🚨 REGISTER JS FINAL LOADED - 20260428");

document.addEventListener("DOMContentLoaded", () => {
  console.error("🚨 DOM READY");

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

  console.error("FORM FOUND:", form);

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
  }

  function syncRoleVisibility() {
    if (!memberRow || !roleSelect) return;
    memberRow.hidden = roleSelect.value !== "player";
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
            "name",
            (member) => `${member.full_name || member.name} · ${member.team_name || "No team"}`
          );
      }

      const roles = (data.roles || []).filter((r) => r.role_name);

      if (roleSelect) {
        roleSelect.innerHTML = optionMarkup(
          roles,
          "role_name",
          (r) => r.display_name || r.role_name
        );

        if (!roleSelect.value) roleSelect.value = "player";
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
    console.error("🚨 SUBMIT HANDLER TRIGGERED");

    event.preventDefault();
    event.stopPropagation();



    const payload = {
    display_name: document.getElementById("registerDisplayName")?.value.trim() || "",
    mobile: document.getElementById("registerMobile")?.value.trim() || "",
    email: document.getElementById("registerEmail")?.value.trim() || "",
    password: document.getElementById("registerPassword")?.value || "",
    role: roleSelect?.value || "player",
    primary_club_id: clubSelect?.value || "",
    member_name: memberSelect?.value || "",
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

    if (!payload.primary_club_id && !payload.club_name) {
      setStatus("❌ Select a club or add a new one", "error");
      return;
    }

    if (!payload.primary_club_id && payload.club_name && (!payload.club_city || !payload.club_country)) {
      setStatus("❌ Add club city and country to create a new club", "error");
      return;
    }

    try {
      setStatus("Registering...", "info");

      const data = await postJson("/api/auth/register", payload);

      console.log("✅ Registration response:", data);

      setStatus("✅ Registration successful! Redirecting...", "success");

      setAuthToken(data.token);
      setPrimaryClubId(
        data.user?.current_club_id ||
        data.user?.primary_club_id ||
        ""
      );

      setTimeout(() => {
        window.location.href = "/clubs";
      }, 1200);

    } catch (error) {
      console.error("❌ Registration failed:", error);

      const msg =
        error?.response?.detail ||
        error?.detail ||
        error?.message ||
        JSON.stringify(error);

      setStatus(`❌ ${msg}`, "error");
    }
  });

  loadOptions().then(syncRoleVisibility);
});
