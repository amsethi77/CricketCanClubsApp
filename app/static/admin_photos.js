// Admin Center -> Scorecard tools -> "Make scorecard photos smaller" (Nov 13 2026, Amit: "in the uploads folder we
// have all the images that needs to be shrink in the size from Mb to kb"). Server: /api/admin/uploads/storage + /shrink.
// Nov 19 2026 (Dhruvika: "i want all photos in kbs"): every photo under the target (450 KB), the average shown.
(function adminPhotos() {
  const stats = document.getElementById("adminPhotoStats");
  const button = document.getElementById("adminPhotoShrink");
  const status = document.getElementById("adminPhotoStatus");
  if (!stats || !button) return;
  let token = "";
  try {
    token = localStorage.getItem("cricketClubAppAuthToken") || "";
  } catch (error) {
    token = "";
  }
  const headers = { "X-Auth-Token": token, Accept: "application/json" };
  const mb = (bytes) => `${(Number(bytes || 0) / 1048576).toFixed(1)} MB`;
  let timer = null;

  function show(text, tone = "info") {
    status.hidden = !text;
    status.className = `status-banner ${tone}`;
    status.textContent = text || "";
  }

  async function refresh() {
    const response = await fetch("/api/admin/uploads/storage", { headers }).catch(() => null);
    const data = response && response.ok ? await response.json().catch(() => null) : null;
    if (!data) {
      stats.innerHTML = "<span>Couldn't check the photos.</span>";
      return;
    }
    const job = data.job || {};
    stats.innerHTML = `
      <div><strong>${data.photos}</strong><span>photos</span></div>
      <div><strong>${mb(data.bytes)}</strong><span>in total</span></div>
      <div><strong>${Number(data.average_kb || 0).toLocaleString()} KB</strong><span>average photo</span></div>
      <div><strong>${data.big_photos}</strong><span>over ${data.target_kb || 450} KB</span></div>
      <div><strong>${mb(data.big_bytes)}</strong><span>used by those</span></div>`;
    // Nov 19 2026 (Dhruvika: "i don't want you to store duplicates"): copies left in the duplicates folder
    let dupButton = document.getElementById("adminDuplicateCopies");
    if (!dupButton) {
      dupButton = document.createElement("button");
      dupButton.type = "button";
      dupButton.id = "adminDuplicateCopies";
      dupButton.className = "secondary-button";
      button.insertAdjacentElement("afterend", dupButton);
      dupButton.addEventListener("click", removeDuplicateCopies);
    }
    dupButton.dataset.armed = "";
    dupButton.hidden = !data.duplicate_copies;
    dupButton.textContent = `🗑️ Delete ${data.duplicate_copies} duplicate photo copies (${mb(data.duplicate_bytes)})`;
    button.disabled = Boolean(job.running) || !data.big_photos;
    button.textContent = job.running ? "🗜️ Working..." : data.big_photos ? `🗜️ Compress ${data.big_photos} photos to under ${data.target_kb || 450} KB` : `✅ All photos are under ${data.target_kb || 450} KB`;
    if (job.running) {
      show(`Making photos smaller: ${job.done || 0} of ${job.total || "?"} done, ${mb(job.saved)} freed so far.`);
      clearTimeout(timer);
      timer = setTimeout(refresh, 2500);
    } else if (job.message) {
      show(job.message, job.message.startsWith("Done") ? "success" : "error");
    }
  }

  async function removeDuplicateCopies(event) {
    const dupButton = event.currentTarget;
    if (!dupButton.dataset.armed) {
      // ask once more: deleting can't be undone (the scorecards and their own photos are kept)
      dupButton.dataset.armed = "1";
      dupButton.textContent = "⚠️ Tap again to delete them for good (scorecards and their photos are kept)";
      return;
    }
    dupButton.disabled = true;
    const response = await fetch("/api/admin/uploads/remove-duplicate-copies", { method: "POST", headers }).catch(() => null);
    const data = response ? await response.json().catch(() => ({})) : {};
    show(response && response.ok ? data.message : data.detail || "Couldn't delete them. Try again.", response && response.ok ? "success" : "error");
    dupButton.disabled = false;
    refresh();
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    const response = await fetch("/api/admin/uploads/shrink", { method: "POST", headers }).catch(() => null);
    const data = response ? await response.json().catch(() => ({})) : {};
    show(response && response.ok ? data.message : data.detail || "Couldn't start. Try again.", response && response.ok ? "info" : "error");
    setTimeout(refresh, 800);
  });

  refresh();
})();
