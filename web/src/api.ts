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

async function delJSON<T>(url: string): Promise<T> {
  const r = await fetch(url, { method: "DELETE" });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function putJSON<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = await r.text();
    try { msg = JSON.parse(msg).detail ?? msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return r.json();
}

async function streamNDJSON(url: string, body: unknown, onEvent: (ev: any) => void) {
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
  const reader = r.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let nl: number;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
  if (buf.trim()) onEvent(JSON.parse(buf));
}

export const api = {
  health: () => getJSON<Health>(`${BASE}/api/health`),
  models: () => getJSON<{ models: string[] }>(`${BASE}/api/models`),
  defaultConfig: () => getJSON<any>(`${BASE}/api/default-config`),
  run: (config: any) => postJSON<RunResult>(`${BASE}/api/run`, { config }),
  // 流式：边跑边回报进度 {progress:{stage,pct}}，结束回报 {done,result}
  runStream: (config: any, onEvent: (ev: any) => void) =>
    streamNDJSON(`${BASE}/api/run/stream`, { config }, onEvent),
  screenStream: (config: any, topN: number, onEvent: (ev: any) => void) =>
    streamNDJSON(`${BASE}/api/screen/stream`, { config, top_n: topN }, onEvent),
  compareStream: (config: any, onEvent: (ev: any) => void) =>
    streamNDJSON(`${BASE}/api/compare/stream`, { config }, onEvent),
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
  strategyParse: (text: string) =>
    postJSON<{
      spec: any;
      warnings: string[];
      source: "ai" | "rule";
      rationale: string;
      rules: { kind: string; text: string }[];
    }>(`${BASE}/api/strategy/parse`, { text }),
  strategyRun: (spec: any, opts: { initial_cash?: number; start?: string; persist?: boolean } = {}) =>
    postJSON<any>(`${BASE}/api/strategy/run`, { spec, persist: false, ...opts }),
  strategies: () => getJSON<{ strategies: any[] }>(`${BASE}/api/strategies`),
  paperRecord: (opts: { as_of: string; picks: any[]; horizon?: number; index_symbol?: string; initial_cash?: number }) =>
    postJSON<{ paper_id: number }>(`${BASE}/api/paper/record`, opts),
  paperList: () => getJSON<{ papers: any[] }>(`${BASE}/api/paper`),
  paperResolve: () => postJSON<{ resolved: number }>(`${BASE}/api/paper/resolve`, {}),
  liveReadiness: () => getJSON<{ ready: boolean; blockers: string[]; note: string }>(`${BASE}/api/live/readiness`),
  strategySignals: (spec: any, symbols: string[]) =>
    postJSON<{ signals: any[]; warnings: string[] }>(`${BASE}/api/strategy/signals`, { spec, symbols }),
  strategyDetail: (id: number) => getJSON<{ strategy: any; runs: any[] }>(`${BASE}/api/strategies/${id}`),
  strategySave: (spec: any, opts: { name?: string; description?: string; source?: string } = {}) =>
    postJSON<{ strategy_id: number }>(`${BASE}/api/strategies`, { spec, ...opts }),
  presets: () => getJSON<{ presets: any[] }>(`${BASE}/api/presets`),
  seedPresets: () => postJSON<{ added: number }>(`${BASE}/api/strategies/seed`, {}),
  dedupeStrategies: () => postJSON<{ removed: number }>(`${BASE}/api/strategies/dedupe`, {}),
  deleteStrategy: (id: number) => delJSON<{ ok: boolean }>(`${BASE}/api/strategies/${id}`),
  updateStrategy: (id: number, spec: any, note = "") =>
    putJSON<{ version: number }>(`${BASE}/api/strategies/${id}`, { spec, note }),
  deleteStrategies: (ids: number[]) => postJSON<{ deleted: number }>(`${BASE}/api/strategies/delete`, ids),
  strategyDiscoverStream: (
    opts: { symbol: string; initial_cash?: number; top_k?: number; start?: string },
    onEvent: (ev: any) => void
  ) => streamNDJSON(`${BASE}/api/strategy/discover/stream`, opts, onEvent),
  xsecStream: (
    opts: { symbols?: string[]; universe?: string; index?: string; universe_size?: number; top_k?: number; horizon?: number; rebalance?: number; train_window?: number; retrain?: number; initial_cash?: number; model?: string },
    onEvent: (ev: any) => void
  ) => streamNDJSON(`${BASE}/api/xsec/stream`, opts, onEvent),
  stockNames: (symbols: string) =>
    getJSON<{ names: Record<string, string> }>(`${BASE}/api/stock/names?symbols=${encodeURIComponent(symbols)}`),
  stockSearch: (q: string, limit = 20) =>
    getJSON<{ results: { symbol: string; name: string }[] }>(
      `${BASE}/api/stock/search?q=${encodeURIComponent(q)}&limit=${limit}`
    ),
  strategyScreen: (spec: any, opts: { top_n?: number; min_amount?: number; symbols?: string[]; cash?: number; universe?: string } = {}) =>
    postJSON<any>(`${BASE}/api/strategy/screen`, { spec, ...opts }),
  strategyScreenStream: (
    spec: any,
    opts: { top_n?: number; min_amount?: number; symbols?: string[]; cash?: number; universe?: string },
    onEvent: (ev: any) => void
  ) => streamNDJSON(`${BASE}/api/strategy/screen/stream`, { spec, ...opts }, onEvent),
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
