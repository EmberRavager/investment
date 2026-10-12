import { Fragment, useCallback, useState } from "react";
import { Filter, Radar as RadarIcon, RefreshCw, Search, Loader2, Plus, Globe, ListChecks, BarChart3 } from "lucide-react";
import { api } from "../api";
import type { Strat } from "./QuantPilotApp";
import StrategyEditor from "./StrategyEditor";
import StrategySelector from "./StrategySelector";
import { parseUniverse } from "./strategyForm";

const STATE_CLS: Record<string, string> = { 触发买入: "blue", 持有: "green", 触发卖出: "red", 观望: "gray" };
const SOURCE_LABEL: Record<string, string> = {
  snapshot: "全市场股票快照", etf: "全市场 ETF 快照", fallback: "内置股票池（快照不可用）", custom: "自定义股票池",
};

function fmt(v: any): string {
  if (v == null) return "—";
  if (typeof v !== "number") return String(v);
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(2)}亿`;
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(2);
}

export default function Radar({
  strat, onAnalyze,
}: { strat: Strat; onAnalyze: (symbol: string, name: string) => void }) {
  const { form, setForm, spec } = strat;
  const [pool, setPool] = useState<"stock" | "etf" | "custom">("stock");
  const [q, setQ] = useState("");
  const [onlyBuy, setOnlyBuy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<{ stage: string; pct: number; detail?: string } | null>(null);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    setProgress({ stage: "准备中", pct: 0 });
    let result: any = null;
    let err: string | null = null;
    try {
      await api.strategyScreenStream(
        spec,
        {
          top_n: 25,
          universe: pool === "etf" ? "etf" : "stock",
          symbols: pool === "custom" ? parseUniverse(form.universe) : undefined,
          cash: strat.cash,
        },
        (ev: any) => {
          if (ev.progress) setProgress(ev.progress);
          else if (ev.done) result = ev.result;
          else if (ev.error) err = ev.error;
        }
      );
      if (err) throw new Error(err);
      setData(result);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
      setProgress(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec, pool]);

  const addToPool = (symbol: string) => {
    const cur = parseUniverse(form.universe);
    if (cur.includes(symbol)) return;
    setForm({ ...form, universe: [...cur, symbol].join(",") });
  };

  const candidates: any[] = data?.candidates ?? [];
  const list = candidates.filter((c) => {
    const hit = !q || c.name.includes(q) || c.symbol.includes(q);
    return hit && (!onlyBuy || c.target_weight > 0);
  });

  return (
    <>
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head">
          <span className="t">策略规则（可改）</span>
          <StrategySelector strat={strat} label="载入已保存策略" />
          <span className="s">改完点右侧「筛选」，再用同一策略去回测 / 个股分析</span>
        </div>
        <StrategyEditor form={form} onChange={setForm} hideUniverse hideName />
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 8 }}>
          <button className={`btn ${pool === "stock" ? "primary" : "ghost"}`} onClick={() => setPool("stock")}>
            <Globe size={14} /> 全市场股票
          </button>
          <button className={`btn ${pool === "etf" ? "primary" : "ghost"}`} onClick={() => setPool("etf")}>
            <Globe size={14} /> ETF 池
          </button>
          <button className={`btn ${pool === "custom" ? "primary" : "ghost"}`} onClick={() => setPool("custom")}>
            <ListChecks size={14} /> 我的股票池
          </button>
          <button className="btn primary" onClick={run} disabled={loading} style={{ marginLeft: "auto" }}>
            {loading ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />} 筛选
          </button>
        </div>
        {loading && progress && (
          <div style={{ marginTop: 12 }}>
            <div className="pbar"><div className="pfill" style={{ width: `${progress.pct}%` }} /></div>
            <div className="notice" style={{ marginTop: 6 }}>{progress.stage} {progress.detail ? `· ${progress.detail}` : ""}</div>
          </div>
        )}
        {error && <div className="error" style={{ marginTop: 12 }}>{error}</div>}
      </div>

      <div className="panel">
        <div className="panel-head">
          <span className="t"><RadarIcon size={15} style={{ verticalAlign: -2, marginRight: 6 }} />候选池</span>
          <span className="s">
            {data
              ? `来源：${SOURCE_LABEL[data.source] ?? data.source}${data.universe_size ? ` · 全市场 ${data.universe_size} 只 → 精算 ${data.shortlist_size} 只` : ` · ${data.shortlist_size} 只`}`
              : "尚未筛选"}
          </span>
        </div>

        <div className="infobox" style={{ marginTop: 0, marginBottom: 12 }}>
          <div className="li"><b>「可买」列</b>：只有 <span className="pill blue">触发买入</span> 表示今天满足买入规则；<span className="pill green">持有</span> 是已持仓继续拿；<span className="pill gray">观望</span> 是没满足；<span className="pill red">触发卖出</span> 是要卖。</div>
          <div className="li">📊 = 看这只股票的历史表现（跳到「个股分析」）；➕ = 加入你的回测股票池。</div>
        </div>

        {!data && !loading && (
          <div className="empty">
            点击右上角 <b>「筛选」</b> 开始（默认全市场约 5500 只，约 10–30 秒）。<br />
            也可以切到「我的股票池」只筛自己填的标的。
          </div>
        )}

        {data && (
          <>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
              <div style={{ position: "relative", flex: "1 1 240px", minWidth: 200 }}>
                <Search size={15} style={{ position: "absolute", left: 11, top: 11, color: "var(--text-3)" }} />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索代码或名称" style={{ paddingLeft: 34 }} />
              </div>
              <button className={`btn ${onlyBuy ? "primary" : "ghost"}`} onClick={() => setOnlyBuy((v) => !v)}>
                <Filter size={14} /> 仅看可买
              </button>
            </div>

            <div style={{ overflowX: "auto" }}>
              <table className="qp-table">
                <thead>
                  <tr>
                    <th>股票</th><th>现价</th><th>涨跌</th><th>站上MA20</th><th>量比</th>
                    <th>20日动量</th><th>成交额(亿)</th><th>评分</th><th>风险</th><th>可买</th><th>可行</th><th>操作</th>
                    <th style={{ textAlign: "left" }}>触发 / 不满足原因</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((c) => (
                    <Fragment key={c.symbol}>
                    <tr>
                      <td><div className="strong">{c.name}</div><div className="sub mono">{c.symbol} · v{c.strategy_version ?? "—"}</div></td>
                      <td className="mono">{c.price?.toFixed(2)}</td>
                      <td className={`mono ${c.change_pct >= 0 ? "up" : "down"}`}>{c.change_pct >= 0 ? "+" : ""}{c.change_pct?.toFixed(2)}%</td>
                      <td className={c.above_ma20 ? "up" : "down"}>{c.above_ma20 ? "是" : "否"}</td>
                      <td className="mono">{c.vol_ratio ?? "—"}</td>
                      <td className={`mono ${(c.ret20 ?? 0) >= 0 ? "up" : "down"}`}>{c.ret20 == null ? "—" : `${c.ret20 > 0 ? "+" : ""}${c.ret20}%`}</td>
                      <td className="mono">{c.turnover?.toFixed(1)}</td>
                      <td><div style={{ display: "flex", alignItems: "center", gap: 8 }}><div className="bar" style={{ width: 40 }}><span style={{ width: `${c.score * 100}%` }} /></div><span className="mono strong">{(c.score * 100).toFixed(0)}</span></div></td>
                      <td><span className={`risk ${c.risk}`}>{c.risk}</span></td>
                      <td><span className={`pill ${STATE_CLS[c.state] ?? "gray"}`}>{c.state}</span></td>
                      <td>
                        {c.feasible?.can_buy === true && <span className="pill green" title={c.feasible.reason}>可买</span>}
                        {c.feasible?.can_buy === false && <span className="pill red" title={c.feasible.reason}>不可买</span>}
                        {c.feasible?.can_buy == null && <span className="pill gray">—</span>}
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                          <button className="btn ghost sm" onClick={() => setExpanded((e) => ({ ...e, [c.symbol]: !e[c.symbol] }))} title="展开条件与数据">{expanded[c.symbol] ? "收起" : "详情"}</button>
                          <button className="btn ghost sm" onClick={() => onAnalyze(c.symbol, c.name)} title="分析该股票历史表现"><BarChart3 size={13} /></button>
                          <button className="btn ghost sm" onClick={() => addToPool(c.symbol)} title="加入回测股票池"><Plus size={13} /></button>
                        </div>
                      </td>
                      <td style={{ textAlign: "left", whiteSpace: "normal", minWidth: 200 }}>
                        {c.blockedBy
                          ? <span className="reason warn">{c.blockedBy}</span>
                          : <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 6 }}>{c.triggers.map((t: string, i: number) => <span className="reason" key={i}>{t}</span>)}</span>}
                      </td>
                    </tr>
                    {expanded[c.symbol] && (
                      <tr>
                        <td colSpan={13} style={{ textAlign: "left", background: "var(--surface-2)", whiteSpace: "normal" }}>
                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                            <div>
                              <div className="notice" style={{ marginBottom: 6 }}>过滤条件（命中才允许持仓）</div>
                              {c.filter_hits.map((h: any, i: number) => (
                                <div key={i} className="reason" style={{ display: "block", marginBottom: 4 }}>
                                  {h.ok ? "✓" : "✗"} {h.text}
                                  <span className="mono sub"> （{fmt(h.left)} vs {fmt(h.right)}）</span>
                                </div>
                              ))}
                              <div className="notice" style={{ margin: "8px 0 6px" }}>买入条件</div>
                              {c.entry_hits.map((h: any, i: number) => (
                                <div key={i} className="reason" style={{ display: "block", marginBottom: 4 }}>
                                  {h.ok ? "✓" : "✗"} {h.text}
                                  <span className="mono sub"> （{fmt(h.left)} vs {fmt(h.right)}）</span>
                                </div>
                              ))}
                            </div>
                            <div>
                              <div className="notice" style={{ marginBottom: 6 }}>关键数据值（{c.as_of}）</div>
                              <div className="reasons">
                                {Object.entries(c.values || {}).filter(([, v]) => v != null).map(([k, v]) => (
                                  <span className="reason" key={k}>{k}: <b className="mono">{fmt(v as number)}</b></span>
                                ))}
                              </div>
                              {c.feasible?.reason && (
                                <div className="reason warn" style={{ marginTop: 8, display: "block" }}>{c.feasible.reason}</div>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
              {list.length === 0 && <div className="empty">没有符合条件的标的。换个条件或重新筛选。</div>}
            </div>
          </>
        )}
      </div>

      <div className="notice" style={{ marginTop: 12 }}>
        候选池=「满足规则」，是否真买还要过风控（单股仓位/资金/流动性）。全市场快照走新浪源，约 5500 只。
        规则信号不构成投资建议。
      </div>
    </>
  );
}
