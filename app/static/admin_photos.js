// Admin Center -> Scorecard tools -> "Make scorecard photos smaller" (Nov 13 2026, Amit: "in the uploads folder we
// have all the images that needs to be shrink in the size from Mb to kb"). Server: /api/admin/uploads/storage + /shrink.
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
      <div><strong>${data.big_photos}</strong><span>can be made smaller</span></div>
      <div><strong>${mb(data.big_bytes)}</strong><span>used by those</span></div>`;
    button.disabled = Boolean(job.running) || !data.big_photos;
    button.textContent = job.running ? "🗜️ Working..." : data.big_photos ? `🗜️ Make ${data.big_photos} photos smaller` : "✅ All photos are small";
    if (job.running) {
      show(`Making photos smaller: ${job.done || 0} of ${job.total || "?"} done, ${mb(job.saved)} freed so far.`);
      clearTimeout(timer);
      timer = setTimeout(refresh, 2500);
    } else if (job.message) {
      show(job.message, job.message.startsWith("Done") ? "success" : "error");
    }
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
