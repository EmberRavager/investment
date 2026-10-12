import { useMemo } from "react";
import {
  Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Loader2 } from "lucide-react";
import type { Strat } from "./QuantPilotApp";
import StrategySelector from "./StrategySelector";
import { verdictOf } from "./verdict";

export default function Backtest({ strat }: { strat: Strat }) {
  const { result, loading, error } = strat;

  const curve = useMemo(() => {
    const s = result?.series;
    if (!s) return [];
    let peak = -Infinity;
    const rows: any[] = [];
    const step = Math.max(1, Math.ceil(s.dates.length / 400));
    for (let i = 0; i < s.dates.length; i += step) {
      const nav = s.strategy_nav[i];
      peak = Math.max(peak, nav);
      rows.push({
        date: s.dates[i], strategy: nav, benchmark: s.benchmark_nav[i],
        drawdown: Number(((nav / peak - 1) * 100).toFixed(2)),
      });
    }
    return rows;
  }, [result]);

  if (loading && !result) return <div className="panel"><div style={{ display: "flex", gap: 8, color: "var(--text-3)" }}><Loader2 size={16} className="spin" /> 回测中…</div></div>;
  if (error) return <div className="error">回测失败：{error}</div>;
  if (!result) return <div className="empty">暂无数据。</div>;

  const m = result.metrics || {};
  const spec = result.spec || {};
  const verdict = verdictOf(m, result.splits);
  const trades: any[] = result.trades || [];
  const fees = trades.reduce((a, t) => a + (t.total_fee || 0), 0);
  const slip = trades.reduce((a, t) => a + (t.slippage_cost || 0), 0);
  const pct = (v: any, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
  const num = (v: any, d = 2) => (v == null ? "—" : Number(v).toFixed(d));

  return (
    <>
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head">
          <span className="t">{spec.name} · 回测</span>
          <span className={`pill ${verdict.usable ? "green" : "red"}`} title={(verdict.reasons || []).join("；")}>{verdict.label}</span>
          <StrategySelector strat={strat} label="切换策略" />
          <span className="s">区间 {curve[0]?.date ?? ""} ~ {result.as_of} · 初始 ¥{(result.initial_cash ?? 0).toLocaleString()} · 信号次日开盘撮合</span>
        </div>
        <div className="stat-row">
          <div className="stat"><span className="k">年化收益</span><span className={`v ${(m.annual_return ?? 0) >= 0 ? "up" : "down"}`}>{pct(m.annual_return)}</span><span className="d">累计 {pct(m.total_return)}</span></div>
          <div className="stat"><span className="k">最大回撤</span><span className="v down">{pct(m.max_drawdown)}</span><span className="d">Calmar {m.calmar == null ? "—" : m.calmar.toFixed(2)}</span></div>
          <div className="stat"><span className="k">夏普比率</span><span className="v">{m.sharpe == null ? "—" : m.sharpe.toFixed(2)}</span><span className="d">仓位均值 {pct(m.exposure, 0)}</span></div>
          <div className="stat"><span className="k">胜率</span><span className="v sm">{pct(m.win_rate, 0)}</span><span className="d">成交 {m.num_trades ?? trades.length} 笔</span></div>
        </div>
      </div>

      <div className="qp-grid side" style={{ marginBottom: 16 }}>
        <div className="panel">
          <div className="panel-head"><span className="t">净值 vs 基准</span></div>
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={curve} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--text-3)" }} minTickGap={48} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "var(--text-3)" }} domain={["auto", "auto"]} tickLine={false} axisLine={false} width={48} />
                <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid var(--border-strong)", fontSize: 12 }} />
                <Line type="monotone" dataKey="strategy" name="策略净值" stroke="var(--up)" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="benchmark" name="基准(首只标的)" stroke="var(--text-3)" strokeWidth={1.5} strokeDasharray="4 4" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head"><span className="t">回撤 (%)</span></div>
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={curve} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--text-3)" }} minTickGap={48} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "var(--text-3)" }} tickLine={false} axisLine={false} width={48} />
                <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid var(--border-strong)", fontSize: 12 }} />
                <Area type="monotone" dataKey="drawdown" name="回撤%" stroke="#b42318" fill="#fdeeee" strokeWidth={1.5} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {result.splits && (
        <div className="panel" style={{ marginBottom: 16 }}>
          <div className="panel-head">
            <span className="t">样本内 / 样本外</span>
            <span className="s">前 70% 为样本内（策略设计区间），后 30% 为样本外（独立验证）· 切分点 {result.splits.split_date}</span>
          </div>
          <div className="stat-row">
            <div className="stat"><span className="k">样本内 年化</span><span className={`v sm ${(result.splits.in_sample?.annual_return ?? 0) >= 0 ? "up" : "down"}`}>{pct(result.splits.in_sample?.annual_return)}</span><span className="d">夏普 {num(result.splits.in_sample?.sharpe)}</span></div>
            <div className="stat"><span className="k">样本外 年化</span><span className={`v sm ${(result.splits.out_sample?.annual_return ?? 0) >= 0 ? "up" : "down"}`}>{pct(result.splits.out_sample?.annual_return)}</span><span className="d">夏普 {num(result.splits.out_sample?.sharpe)}</span></div>
            <div className="stat"><span className="k">样本外 回撤</span><span className="v sm down">{pct(result.splits.out_sample?.max_drawdown)}</span><span className="d">Calmar {num(result.splits.out_sample?.calmar)}</span></div>
            <div className="stat"><span className="k">样本外 胜率</span><span className="v sm">{pct(result.splits.out_sample?.win_rate, 0)}</span><span className="d">成交 {result.splits.out_sample?.num_trades ?? "—"}</span></div>
          </div>
          <div className="notice" style={{ marginTop: 8 }}>
            样本外是策略从未"见过"的时间段，更接近真实使用；若样本外明显变差，说明规则可能过拟合。
          </div>
        </div>
      )}

      <div className="qp-grid side">
        <div className="panel">
          <div className="panel-head"><span className="t">交易明细</span><span className="s">{trades.length} 笔（含方向、数量、费用、依据）</span></div>
          <div style={{ maxHeight: 420, overflowY: "auto" }}>
            <table className="qp-table">
              <thead>
                <tr><th>成交日</th><th>信号日</th><th>版本</th><th>标的</th><th>方向</th><th>数量</th><th>价格</th><th>费用</th><th style={{ textAlign: "left" }}>依据</th></tr>
              </thead>
              <tbody>
                {trades.slice(-80).reverse().map((t, i) => (
                  <tr key={i}>
                    <td className="mono">{t.date?.slice(0, 10)}</td>
                    <td className="mono sub">{String(t.signal_date || "").slice(0, 10)}</td>
                    <td className="mono sub">v{t.strategy_version ?? "—"}</td>
                    <td><span className="strong">{t.name}</span> <span className="sub mono">{t.symbol}</span></td>
                    <td className={t.side === "buy" ? "up" : "down"}>{t.side === "buy" ? "买入" : "卖出"}</td>
                    <td className="mono">{t.qty}</td>
                    <td className="mono">{t.price?.toFixed(2)}</td>
                    <td className="mono">{t.total_fee?.toFixed(1)}</td>
                    <td style={{ textAlign: "left" }}><span className="reason" title={t.evidence ? JSON.stringify(t.evidence) : ""}>{t.reason}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {trades.length === 0 && <div className="empty">此策略在当前标的与本金下没有产生成交（可能被资金/整手约束跳过）。</div>}
          </div>
        </div>

        <div className="panel">
          <div className="panel-head"><span className="t">成本与真实性</span></div>
          <div className="rule-list">
            <div className="rule-item"><span>累计交易费用</span><b className="mono" style={{ marginLeft: "auto" }}>¥{fees.toFixed(2)}</b></div>
            <div className="rule-item"><span>其中滑点成本</span><b className="mono" style={{ marginLeft: "auto" }}>¥{slip.toFixed(2)}</b></div>
            <div className="rule-item"><span>费用占初始本金</span><b className="mono" style={{ marginLeft: "auto" }}>{((fees / (result.initial_cash || 1)) * 100).toFixed(2)}%</b></div>
            <div className="rule-item"><span>被风控跳过次数</span><b className="mono" style={{ marginLeft: "auto" }}>{result.skips?.length ?? 0}</b></div>
          </div>
          <div className="ai-box" style={{ marginTop: 14 }}>
            <div className="who">真实性说明</div>
            <p>已计入佣金（最低 5 元）、印花税（卖出）、滑点；T+1 交收；信号与执行时点分离。</p>
            <p>仅在收盘确认信号、次日开盘成交，不使用未来信息。历史回测不代表未来，不构成投资建议。</p>
          </div>
        </div>
      </div>
    </>
  );
}
