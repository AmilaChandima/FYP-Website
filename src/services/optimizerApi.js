async function readJson(response) {
  let payload = null;
  try { payload = await response.json(); } catch { payload = null; }
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.error || `Request failed (${response.status})`);
  }
  return payload;
}

export async function checkOptimizerHealth() {
  return readJson(await fetch("/api/health"));
}

export async function startOptimizerRun(files) {
  const form = new FormData();
  form.append("pv", files.pv);
  form.append("primary_elastic", files.primaryElastic);
  form.append("grid_price", files.gridPrice);
  return readJson(await fetch("/api/optimizer/run", { method: "POST", body: form }));
}

export async function getOptimizerJob(jobId) {
  return readJson(await fetch(`/api/optimizer/jobs/${jobId}`));
}

export async function cancelOptimizerRun(jobId) {
  return readJson(await fetch(`/api/optimizer/jobs/${encodeURIComponent(jobId)}/cancel`, {
    method: "POST",
  }));
}

export async function getLatestOptimizerResult() {
  return readJson(await fetch("/api/optimizer/latest"));
}

export async function getOptimizerHistory(limit = 10) {
  return readJson(await fetch(`/api/optimizer/history?limit=${encodeURIComponent(limit)}`));
}

export async function publishTomorrowPrice(jobId) {
  return readJson(await fetch("/api/prices/publish-tomorrow", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jobId }),
  }));
}


export async function publishTomorrowPriceAndNotify(jobId) {
  return readJson(await fetch(`/api/optimizer/jobs/${encodeURIComponent(jobId)}/publish-and-notify`, { method: "POST" }));
}

export async function getPublishedPrices() {
  return readJson(await fetch("/api/prices"));
}

export async function getPrimaryElasticBaseInfo() {
  return readJson(await fetch("/api/demo/primary-elastic/base-info"));
}

export async function generatePrimaryElasticInput(targetDate, bookings) {
  return readJson(await fetch("/api/demo/primary-elastic/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ targetDate, bookings }),
  }));
}

export function downloadGeneratedPrimaryElasticInput() {
  const anchor = document.createElement("a");
  anchor.href = "/api/demo/primary-elastic/download";
  anchor.download = "Primary_Elastic_EV_Users.xlsx";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}
