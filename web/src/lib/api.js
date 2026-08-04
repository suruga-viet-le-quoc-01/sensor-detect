// Thin client for src/web_api (docs/web-dashboard/api-contract.md). Read-only, GET-only --
// mirrors the backend's own read-only contract. Uses relative paths so the Vite dev proxy
// (vite.config.js) and a same-origin production reverse proxy both work without CORS.
const API_BASE = "/api";

const ERROR_MESSAGES = {
  db_unavailable: "データベースに接続できません。",
  invalid_date: "日付の形式が正しくありません。",
};

// GET one JSON endpoint. Always throws a clean Japanese-message Error on failure -- never a raw
// Response or {error: code} shape -- so every caller can just try/catch and show err.message.
async function getJson(path) {
  let response;
  try {
    response = await fetch(API_BASE + path);
  } catch {
    throw new Error("サーバーに接続できません。ネットワークを確認してください。");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(ERROR_MESSAGES[body?.error] ?? "通信エラーが発生しました。");
  }

  return response.json();
}

// GET /api/machines/status -- current presence + sensor health for every machine.
export function fetchMachineStatus() {
  return getJson("/machines/status");
}

// GET /api/machines/{machineId}/sessions?date=YYYY-MM-DD -- one machine's sessions for one day.
export function fetchSessions(machineId, date) {
  return getJson(`/machines/${encodeURIComponent(machineId)}/sessions?date=${encodeURIComponent(date)}`);
}

// GET /api/fte?date=YYYY-MM-DD&machine_id=... -- FTE + occupancy per machine. machineId omitted
// (null/undefined) means every machine, per api-contract.md.
export function fetchFte(date, machineId) {
  const query = new URLSearchParams({ date });
  if (machineId) query.set("machine_id", machineId);
  return getJson(`/fte?${query.toString()}`);
}
