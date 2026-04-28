console.error("🚨 REGISTER JS FINAL LOADED - 20260428");

document.addEventListener("DOMContentLoaded", () => {
  console.error("🚨 DOM READY");

  if (!window.HeartlakePages) {
    console.error("❌ ClubPages not available");
    return;
  }

  const { getJson, postJson, setAuthToken, setPrimaryClubId, optionMarkup } = window.HeartlakePages;

  const form = document.getElementById("registerForm");
  const roleSelect = document.getElementById("registerRole");
  const clubSelect = document.getElementById("registerClub");
  const memberSelect = document.getElementById("registerMember");
  const memberRow = document.getElementById("registerMemberRow");
  const statusBanner = document.getElementById("registerStatus");

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
    statusBanner.hidden = !message;
    statusBanner.textContent = message || "";
    statusBanner.className = `status-banner ${tone}`;
  }

  function syncRoleVisibility() {
    if (!memberRow || !roleSelect) return;
    memberRow.hidden = roleSelect.value !== "player";
  }

  function normalizeMobile(value) {
    return (value || "").replace(/\D/g, ""); // remove non-digits
  }

  async function loadOptions() {
    try {
      console.log("🔄 Loading registration options...");
      const data = await getJson("/api/auth/options");

      if (clubSelect) {
        clubSelect.innerHTML = optionMarkup(
          data.clubs,
          "id",
          (club) => `${club.name} · ${club.season || "Season TBD"}`
        );
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
    member_name: memberSelect?.value || ""   // 🔥 FIXED
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

    if (!payload.primary_club_id) {
      setStatus("❌ Select a club", "error");
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