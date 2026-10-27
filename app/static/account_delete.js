/*
 * "Delete my account" card at the bottom of the Profile page (README "Privacy policy and Delete my account").
 * Apple requires apps where people can sign up to let them delete their account in the app.
 * The member types DELETE, the account is removed (POST /api/account/delete) and they are signed out.
 */
(() => {
  const shell = document.querySelector(".page-shell");
  if (!shell || document.getElementById("deleteAccountCard")) return;

  const card = document.createElement("section");
  card.id = "deleteAccountCard";
  card.className = "panel";
  card.style.cssText = "margin-top:20px;border:1.5px solid #fecaca;";
  card.innerHTML = `
    <div class="stack-card" style="display:grid;gap:10px;">
      <h2 style="margin:0;font-size:1.15rem;">Delete my account</h2>
      <p class="lede" style="margin:0;">This deletes your sign-in account and settings and signs you out on every device.
        Your name in published scorecards stays as part of your club's match history.
        <a href="/privacy">Privacy policy</a></p>
      <label style="display:grid;gap:6px;">
        <span>Type <strong>DELETE</strong> to confirm</span>
        <input id="deleteAccountConfirm" type="text" autocomplete="off" autocapitalize="characters" placeholder="DELETE" style="max-width:260px;" />
      </label>
      <div><button id="deleteAccountButton" type="button" class="secondary-button" disabled
        style="background:#dc2626;border-color:#dc2626;color:#fff;">Delete my account</button></div>
      <p id="deleteAccountStatus" class="status-banner" hidden></p>
    </div>`;
  shell.appendChild(card);

  const input = card.querySelector("#deleteAccountConfirm");
  const button = card.querySelector("#deleteAccountButton");
  const status = card.querySelector("#deleteAccountStatus");
  input.addEventListener("input", () => {
    button.disabled = input.value.trim().toUpperCase() !== "DELETE";
  });

  button.addEventListener("click", async () => {
    button.disabled = true;
    status.hidden = false;
    status.textContent = "Deleting…";
    let token = "";
    try {
      token = localStorage.getItem("cricketClubAppAuthToken") || "";
    } catch (error) {
      token = "";
    }
    try {
      const response = await fetch("/api/account/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Auth-Token": token },
        body: JSON.stringify({ confirmation: input.value.trim() }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Couldn't delete the account.");
      status.textContent = data.message || "Your account has been deleted.";
      try {
        localStorage.removeItem("cricketClubAppAuthToken");
        sessionStorage.clear();
      } catch (error) {
        /* ignore */
      }
      setTimeout(() => {
        window.location.href = "/live";
      }, 1500);
    } catch (error) {
      status.textContent = error.message;
      button.disabled = false;
    }
  });
})();
