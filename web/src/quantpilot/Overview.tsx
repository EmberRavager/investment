import { useCallback, useEffect, useState } from "react";
import { Plus, Trash2, RefreshCw, TrendingUp, Loader2 } from "lucide-react";
import { api } from "../api";
import MarketBoard from "../components/MarketBoard";
import StockPicker from "./StockPicker";
import { fetchQuotes, type Quote } from "./quotes";
import { loadHoldings, saveHoldings, uid, type Holding } from "./holdings";
import StrategySelector from "./StrategySelector";
import type { Strat } from "./QuantPilotApp";

const STATE_CLS: Record<string, string> = { 触发买入: "blue", 持有: "green", 触发卖出: "red", 观望: "gray" };
const STATE_LABEL: Record<string, string> = {
  触发买入: "今天买入", 持有: "策略已持有", 触发卖出: "今天卖出", 观望: "暂不参与", "无数据": "无数据", "—": "—",
};

export default function Overview({ strat, onGo }: { strat: Strat; onGo: (k: string) => void }) {
  const [holdings, setHoldings] = useState<Holding[]>(loadHoldings);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [pending, setPending] = useState<{ symbol: string; name: string } | null>(null);
  const [qty, setQty] = useState("");
  const [cost, setCost] = useState("");
  const [signals, setSignals] = useState<any[]>([]);
  const [loadingSignals, setLoadingSignals] = useState(false);
  const [quoteErr, setQuoteErr] = useState(false);

  useEffect(() => { saveHoldings(holdings); }, [holdings]);

  const refreshQuotes = useCallback(async () => {
    const syms = holdings.map((h) => h.symbol);
    if (!syms.length) { setQuotes({}); return; }
    const q = await fetchQuotes(syms);
    setQuotes(q);
    setQuoteErr(Object.keys(q).length === 0);
  }, [holdings]);
  useEffect(() => { refreshQuotes(); }, [refreshQuotes]);

  const loadSignals = useCallback(async () => {
    const syms = holdings.map((h) => h.symbol);
    if (!syms.length) { setSignals([]); return; }
    setLoadingSignals(true);
    try {
      const r = await api.strategySignals(strat.spec, syms);
      setSignals(r.signals || []);
    } catch { setSignals([]); } finally { setLoadingSignals(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [holdings, JSON.stringify(strat.spec)]);
  useEffect(() => { loadSignals(); }, [loadSignals]);

  const add = () => {
    if (!pending) return;
    const q = Number(qty), c = Number(cost);
    if (!(q > 0) || !(c > 0)) return;
    setHoldings((h) => [...h, { id: uid(), symbol: pending.symbol, name: pending.name, qty: q, cost: c }]);
    setPending(null); setQty(""); setCost("");
  };
  const remove = (id: string) => setHoldings((h) => h.filter((x) => x.id !== id));
  const update = (id: string, patch: Partial<Holding>) => setHoldings((h) => h.map((x) => (x.id === id ? { ...x, ...patch } : x)));

  let totalCost = 0, totalValue = 0, dayPnl = 0, covered = 0;
  holdings.forEach((h) => {
    const q = quotes[h.symbol];
    const px = q ? q.price : h.cost;
    totalCost += h.qty * h.cost;
    totalValue += h.qty * px;
    if (q) { covered += 1; const prev = q.price / (1 + q.changePercent / 100); dayPnl += h.qty * (q.price - prev); }
  });
  const pnl = totalValue - totalCost;
  const pnlPct = totalCost ? (pnl / totalCost) * 100 : 0;

  return (
    <>
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head">
          <span className="t">我的持仓</span>
          <StrategySelector strat={strat} label="按策略看信号" />
          <button className="link" onClick={refreshQuotes}>刷新现价</button>
        </div>

        {/* 添加 */}
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap", marginBottom: 14 }}>
          <div className="field" style={{ marginBottom: 0, flex: "1 1 300px", minWidth: 240 }}>
            <label>添加股票（搜索代码或名称）</label>
            <StockPicker onPick={setPending} />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: "0 0 110px" }}>
            <label>股数</label>
            <input type="number" value={qty} onChange={(e) => setQty(e.target.value)} placeholder="100" />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: "0 0 130px" }}>
            <label>买入价（每股）</label>
            <input type="number" value={cost} onChange={(e) => setCost(e.target.value)} placeholder="如 12.5" />
          </div>
          <button className="btn primary" onClick={add} disabled={!pending || !(Number(qty) > 0) || !(Number(cost) > 0)}>
            <Plus size={14} /> 添加
          </button>
        </div>
        {pending && (
          <div className="selected-bar" style={{ marginBottom: 14 }}>
            待添加：<b>{pending.name}</b> <span className="mono muted">{pending.symbol}</span>
          </div>
        )}

        {/* 汇总 */}
        <div className="stat-row">
          <div className="stat"><span className="k">总成本</span><span className="v">¥{totalCost.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span><span className="d">{holdings.length} 只</span></div>
          <div className="stat"><span className="k">总市值</span><span className="v">¥{totalValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span><span className="d">{quoteErr ? "现价取不到，按成本计" : "按最新价"}</span></div>
          <div className="stat"><span className="k">总盈亏</span><span className={`v ${pnl >= 0 ? "up" : "down"}`}>{pnl >= 0 ? "+" : ""}¥{pnl.toFixed(0)}</span><span className="d">{pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%</span></div>
          <div className="stat"><span className="k">今日盈亏</span><span className={`v ${dayPnl >= 0 ? "up" : "down"}`}>{dayPnl >= 0 ? "+" : ""}¥{dayPnl.toFixed(0)}</span><span className="d">已覆盖 {covered} 只行情</span></div>
        </div>

        {/* 持仓表 */}
        <div style={{ overflowX: "auto", marginTop: 14 }}>
          <table className="qp-table">
            <thead>
              <tr><th style={{ textAlign: "left" }}>股票</th><th>股数</th><th>成本价</th><th>现价</th><th>市值</th><th>盈亏</th><th>盈亏%</th><th>操作</th></tr>
            </thead>
            <tbody>
              {holdings.map((h) => {
                const q = quotes[h.symbol];
                const px = q ? q.price : h.cost;
                const mv = h.qty * px;
                const pl = (px - h.cost) * h.qty;
                const plPct = h.cost ? (px / h.cost - 1) * 100 : 0;
                return (
                  <tr key={h.id}>
                    <td style={{ textAlign: "left" }}>
                      <div className="strong">{h.name}</div>
                      <div className="sub mono">{h.symbol}</div>
                    </td>
                    <td><input type="number" value={h.qty} onChange={(e) => update(h.id, { qty: Number(e.target.value) || 0 })} style={{ width: 80, padding: "5px 8px", fontSize: 13 }} /></td>
                    <td><input type="number" step="0.001" value={h.cost} onChange={(e) => update(h.id, { cost: Number(e.target.value) || 0 })} style={{ width: 90, padding: "5px 8px", fontSize: 13 }} /></td>
                    <td className="mono">{q ? px.toFixed(2) : "—"}</td>
                    <td className="mono">¥{mv.toFixed(0)}</td>
                    <td className={`mono ${pl >= 0 ? "up" : "down"}`}>{pl >= 0 ? "+" : ""}{pl.toFixed(0)}</td>
                    <td className={`mono ${plPct >= 0 ? "up" : "down"}`}>{plPct >= 0 ? "+" : ""}{plPct.toFixed(2)}%</td>
                    <td><button className="btn ghost sm" onClick={() => remove(h.id)} title="删除"><Trash2 size={13} /></button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {holdings.length === 0 && (
            <div className="empty">
              还没有持仓。上面搜索股票、填股数和买入价即可添加。
              <div style={{ marginTop: 12, display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
                <button className="btn primary sm" onClick={() => onGo("radar")}>去股票雷达选股</button>
                <button className="btn ghost sm" onClick={() => onGo("lab")}>去策略实验室</button>
                <button className="btn ghost sm" onClick={() => onGo("guide")}>看使用说明</button>
              </div>
            </div>
          )}
        </div>
        <div className="notice" style={{ marginTop: 10 }}>
          现价来自浏览器实时行情（stock-sdk）；取不到时按成本价计。持仓保存在本机浏览器。
        </div>
      </div>

      {/* 我的股票 · 今日策略信号 */}
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head">
          <span className="t">我的股票 · 今日策略信号</span>
          <span className="s">用当前策略「{strat.spec.name}」判断你持仓的买卖状态</span>
          {loadingSignals && <Loader2 size={14} className="spin" />}
        </div>
        {holdings.length === 0 ? (
          <div className="empty">添加持仓后，这里显示每只股票今天该买/该卖/该拿。</div>
        ) : (
          <div className="qp-grid c3">
            {signals.map((s) => (
              <div className="signal-card" key={s.symbol}>
                <div className="top">
                  <span className="name">{s.name}</span>
                  <span className="code">{s.symbol}</span>
                  <span className={`pill ${STATE_CLS[s.state] ?? "gray"}`} style={{ marginLeft: "auto" }}>{STATE_LABEL[s.state] ?? s.state}</span>
                </div>
                <div className="reasons">
                  {(s.reasons?.length ? s.reasons : s.block || []).map((r: string, i: number) => (
                    <span className={`reason ${s.block?.length ? "warn" : ""}`} key={i}>{r}</span>
                  ))}
                  {!s.reasons?.length && !s.block?.length && <span className="reason">无触发条件</span>}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "var(--text-3)" }}>
                  {s.price != null && <span>现价 <b className="mono" style={{ color: "var(--text)" }}>{Number(s.price).toFixed(2)}</b></span>}
                  <span>目标仓位 <b className="mono" style={{ color: "var(--text)" }}>{(s.target_weight * 100).toFixed(0)}%</b></span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "4px 2px 12px", fontSize: 12.5, color: "var(--text-3)" }}>
        <TrendingUp size={14} /> 实时行情（浏览器直连）
      </div>
      <MarketBoard />

      <div className="notice" style={{ marginTop: 16 }}>
        想看策略整体回测/模拟账户，去 <button className="link" onClick={() => onGo("backtest")}>回测中心</button>
        {" "}或 <button className="link" onClick={() => onGo("paper")}>模拟交易</button>。
      </div>
    </>
  );
}
