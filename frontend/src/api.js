const API_BASE = import.meta.env.VITE_API_BASE || "";
const UI_TOKEN = import.meta.env.VITE_UI_TOKEN || "";

export async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "X-UI-Token": UI_TOKEN },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-UI-Token": UI_TOKEN,
    },
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