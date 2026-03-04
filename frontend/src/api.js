const API_BASE =
  import.meta.env.VITE_API_BASE ||
  "https://stemy-hub.fly.dev";
const UI_TOKEN =
  import.meta.env.VITE_UI_TOKEN ||
  "89310a35-6420-433b-9bc5-226955510fae0d649592-61e6-4ef1-b435-8bc5223b47b4";
  
export async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export function sseUrl(runId) {
  // EventSource can't send headers → token in query param for UI SSE
  const token = encodeURIComponent(UI_TOKEN);
  return `${API_BASE}/api/stream/patches?run_id=${encodeURIComponent(
    runId
  )}&token=${token}`;
}

export function sseRunStreamUrl(runId) {
  return `${API_BASE}/api/runs/${encodeURIComponent(runId)}/stream`;
}