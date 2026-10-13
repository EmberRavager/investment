import { useEffect, useState } from "react";
import { ShieldAlert, Loader2, RefreshCw } from "lucide-react";
import { api } from "../api";
import type { Strat } from "./QuantPilotApp";
import StrategySelector from "./StrategySelector";

export default function PaperTrading({ strat }: { strat: Strat }) {
  const { result, loading, error, run } = strat;
  const [papers, setPapers] = useState<any[]>([]);
  const [resolving, setResolving] = useState(false);
  const [liveReady, setLiveReady] = useState<any>(null);
  const loadPapers = () => api.paperList().then((r) => setPapers(r.papers)).catch(() => {});
  useEffect(() => {
    loadPapers();
    api.liveReadiness().then(setLiveReady).catch(() => {});
  }, []);
  const resolvePaper = async () => {
    setResolving(true);
    try { await api.paperResolve(); await loadPapers(); } catch { /* ignore */ } finally { setResolving(false); }
  };

  if (loading && !result) return <div className="panel"><div style={{ display: "flex", gap: 8, color: "var(--text-3)" }}><Loader2 size={16} className="spin" /> 生成模拟盘…</div></div>;
  if (error) return <div className="error">模拟盘失败：{error}</div>;
  if (!result) return <div className="empty">暂无数据。</div>;

  const acct = result.account || {};
  const positions = result.positions || {};
  const posList = Object.entries(positions).map(([symbol, p]: any) => ({ symbol, ...p }));
  const initial = result.initial_cash ?? 0;
  const equity = acct.equity ?? initial;
  const nav = result.series?.strategy_nav ?? [];
  const dayPnl = nav.length >= 2 ? (nav[nav.length - 1] - nav[nav.length - 2]) * initial : 0;
  const todayOrders: any[] = result.today_orders || [];
  const recent: any[] = (result.trades || []).slice(-10).reverse();
  const spec = result.spec || {};

  const ordersToShow = todayOrders.length ? todayOrders : recent;
  const isToday = todayOrders.length > 0;

  return (
    <>
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head">
          <span className="t">模拟账户 · {spec.name}</span>
          <StrategySelector strat={strat} label="切换策略" />
          <span className="s">数据截至 {result.as_of} · A 股规则：T+1 · 100 股整手 · 涨跌停</span>
          <button className="link" onClick={() => run()} disabled={loading}>
            {loading ? <Loader2 size={13} className="spin" style={{ verticalAlign: -2 }} /> : <RefreshCw size={13} style={{ verticalAlign: -2, marginRight: 4 }} />}
            重新运行
          </button>
        </div>
        <div className="stat-row">
          <div className="stat"><span className="k">初始本金</span><span className="v">¥{initial.toLocaleString()}</span><span className="d">模拟</span></div>
          <div className="stat"><span className="k">总权益</span><span className="v">¥{equity.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span><span className="d up">{(equity - initial >= 0 ? "+" : "") + (equity - initial).toFixed(0)}</span></div>
          <div className="stat"><span className="k">可用资金</span><span className="v">¥{(acct.cash ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span><span className="d">仓位 {((acct.exposure ?? 0) * 100).toFixed(1)}%</span></div>
          <div className="stat"><span className="k">最近一日盈亏</span><span className={`v ${dayPnl >= 0 ? "up" : "down"}`}>{dayPnl >= 0 ? "+" : ""}¥{dayPnl.toFixed(0)}</span><span className="d">{posList.length} 只持仓</span></div>
        </div>
      </div>

      <div className="qp-grid side">
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="panel">
            <div className="panel-head"><span className="t">当前持仓</span><span className="s">{posList.length} 只</span></div>
            <table className="qp-table">
              <thead>
                <tr><th>标的</th><th>数量</th><th>可卖</th><th>成本</th><th>现价</th><th>盈亏</th></tr>
              </thead>
              <tbody>
                {posList.map((p: any) => (
                  <tr key={p.symbol}>
                    <td><div className="strong">{p.name || p.symbol}</div><div className="sub mono">{p.symbol}</div></td>
                    <td className="mono">{p.qty}</td>
                    <td className="mono">{p.available_qty}{p.available_qty === 0 && <span className="sub"> (T+1)</span>}</td>
                    <td className="mono">{p.cost_price?.toFixed(3)}</td>
                    <td className="mono">{p.last_price?.toFixed(3)}</td>
                    <td className={`mono ${p.pnl >= 0 ? "up" : "down"}`}>{p.pnl >= 0 ? "+" : ""}{p.pnl?.toFixed(1)}（{(p.pnl_pct * 100).toFixed(1)}%）</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {posList.length === 0 && <div className="empty">期末空仓（策略在最新交易日无持仓）。</div>}
          </div>

          <div className="panel">
            <div className="panel-head">
              <span className="t">{isToday ? "今日订单" : "近期成交"}</span>
              <span className="s">{isToday ? "含被风控拒绝的订单" : "最近 10 笔成交"}</span>
            </div>
            <table className="qp-table">
              <thead>
                <tr><th>日期</th><th>标的</th><th>方向</th><th>数量</th><th>价格</th><th>状态</th><th style={{ textAlign: "left" }}>原因</th></tr>
              </thead>
              <tbody>
                {ordersToShow.map((o: any, i: number) => (
                  <tr key={i}>
                    <td className="mono">{String(o.date).slice(0, 10)}</td>
                    <td><span className="strong">{o.name || o.symbol}</span> <span className="sub mono">{o.symbol}</span></td>
                    <td className={o.side === "buy" || o.side === "买入" ? "up" : "down"}>{o.side === "buy" ? "买入" : o.side === "sell" ? "卖出" : o.side}</td>
                    <td className="mono">{o.qty || "—"}</td>
                    <td className="mono">{o.price ? Number(o.price).toFixed(2) : "—"}</td>
                    <td><span className={`pill ${o.status === "已拒绝" ? "red" : "green"}`}>{o.status || "已成交"}</span></td>
                    <td style={{ textAlign: "left", whiteSpace: "normal", minWidth: 160 }}>
                      {o.status === "已拒绝" ? <span className="reason warn">{o.reason}</span> : <span className="reason">{o.reason}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {ordersToShow.length === 0 && <div className="empty">暂无订单。</div>}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="panel">
            <div className="panel-head"><span className="t">运行时风控</span><span className="pill green">已校验</span></div>
            <div className="rule-list">
              {[["单股最大仓位", `${(spec.max_position_per_stock * 100).toFixed(0)}%`],
                ["止损", `${(spec.stop_loss * 100).toFixed(0)}%`],
                ["回撤熔断", `${(spec.drawdown_stop * 100).toFixed(0)}%`],
                ["最小申报", "100 股整手（科创板 200 起）"],
                ["被拒订单", `${result.skips?.length ?? 0} 次`]].map(([k, v]) => (
                <div className="rule-item" key={k as string}>
                  <ShieldAlert size={14} style={{ color: "var(--text-3)" }} />
                  <span>{k}</span>
                  <b className="mono" style={{ marginLeft: "auto", fontSize: 12.5 }}>{v}</b>
                </div>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-head"><span className="t">期末快照</span></div>
            <div className="rule-list">
              <div className="rule-item"><span>现金</span><b className="mono" style={{ marginLeft: "auto" }}>¥{(acct.cash ?? 0).toFixed(2)}</b></div>
              <div className="rule-item"><span>持仓市值</span><b className="mono" style={{ marginLeft: "auto" }}>¥{(acct.market_value ?? 0).toFixed(2)}</b></div>
              <div className="rule-item"><span>总权益</span><b className="mono" style={{ marginLeft: "auto" }}>¥{(acct.equity ?? 0).toFixed(2)}</b></div>
            </div>
            <div className="notice" style={{ marginTop: 12 }}>
              这是用真实历史行情跑出的模拟账户期末状态，不是实时委托；实盘接入后同一引擎负责撮合。
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <span className="t">实盘接入</span>
              <span className={`pill ${liveReady?.ready ? "green" : "red"}`}>{liveReady?.ready ? "已就绪" : "未就绪"}</span>
            </div>
            <div className="rule-list">
              {(liveReady?.blockers || []).map((b: string, i: number) => (
                <div className="rule-item" key={i}><ShieldAlert size={14} style={{ color: "var(--text-3)" }} /><span>{b}</span></div>
              ))}
            </div>
            <div className="notice" style={{ marginTop: 12 }}>{liveReady?.note || "实盘尚未接入。"}</div>
          </div>
        </div>
      </div>
      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head">
          <span className="t">模拟盘跟踪（长期验证）</span>
          <span className="s">{papers.length} 条记录 · 用真实行情事后结算</span>
          <button className="link" onClick={resolvePaper} disabled={resolving}>
            {resolving ? <Loader2 size={13} className="spin" style={{ verticalAlign: -2, marginRight: 4 }} /> : null}结算待定记录
          </button>
        </div>
        <table className="qp-table">
          <thead><tr><th>记录日</th><th>持有期</th><th style={{ textAlign: "left" }}>标的</th><th>组合收益</th><th>指数</th><th>超额</th><th>命中率</th></tr></thead>
          <tbody>
            {papers.map((p) => (
              <tr key={p.id}>
                <td className="mono">{p.as_of}</td>
                <td className="mono">{p.horizon}日</td>
                <td style={{ textAlign: "left", whiteSpace: "normal", maxWidth: 320 }}>
                  {(p.picks || []).map((x: any) => x.name || x.symbol).join("、") || "—"}
                </td>
                <td className={`mono ${(p.result?.pick_return ?? 0) >= 0 ? "up" : "down"}`}>
                  {p.result ? `${(p.result.pick_return * 100).toFixed(1)}%` : "待结算"}
                </td>
                <td className="mono">{p.result?.index_return != null ? `${(p.result.index_return * 100).toFixed(1)}%` : "—"}</td>
                <td className={`mono ${(p.result?.excess ?? 0) >= 0 ? "up" : "down"}`}>
                  {p.result?.excess != null ? `${(p.result.excess * 100).toFixed(1)}%` : "—"}
                </td>
                <td className="mono">{p.result?.hit_rate != null ? `${(p.result.hit_rate * 100).toFixed(0)}%` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {papers.length === 0 && <div className="empty">还没有模拟盘记录。在「多因子选股」页点「记录到模拟盘」即可。</div>}
        <div className="notice" style={{ marginTop: 10 }}>
          记录选股快照 → 持有期结束后「结算」用真实行情算收益/超额/命中率，累积成判断"能不能用"的样本外证据。
        </div>
      </div>
    </>
  );
}
