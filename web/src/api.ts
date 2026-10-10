import type { Health, RunResult, Series } from "./types";

const BASE = "";

async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = await r.text();
    try {
      msg = JSON.parse(msg).detail ?? msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return r.json();
}

export const api = {
  health: () => getJSON<Health>(`${BASE}/api/health`),
  models: () => getJSON<{ models: string[] }>(`${BASE}/api/models`),
  defaultConfig: () => getJSON<any>(`${BASE}/api/default-config`),
  run: (config: any) => postJSON<RunResult>(`${BASE}/api/run`, { config }),
  screen: (config: any, topN = 15) =>
    postJSON<{ universe_size: number; shortlist_size: number; results: any[] }>(
      `${BASE}/api/screen`,
      { config, top_n: topN }
    ),
  reflect: (summary: any, question?: string, mode: "single" | "panel" = "single") =>
    postJSON<{ reflection?: string; panel?: Record<string, string> }>(
      `${BASE}/api/reflect`,
      { summary, question, mode }
    ),
};

/** 图表点太多会拖慢渲染，按步长抽稀（保留首尾）。 */
export function downsample(s: Series, maxPoints = 700): any[] {
  const n = s.dates.length;
  const step = Math.max(1, Math.ceil(n / maxPoints));
  const rows: any[] = [];
  for (let i = 0; i < n; i += step) {
    rows.push({
      date: s.dates[i],
      close: s.close[i],
      proba: s.proba[i],
      position: s.position[i],
      strategy: s.strategy_nav[i],
      benchmark: s.benchmark_nav[i],
    });
  }
  const last = n - 1;
  if (rows.length && rows[rows.length - 1].date !== s.dates[last]) {
    rows.push({
      date: s.dates[last],
      close: s.close[last],
      proba: s.proba[last],
      position: s.position[last],
      strategy: s.strategy_nav[last],
      benchmark: s.benchmark_nav[last],
    });
  }
  return rows;
}
