import { useEffect, useMemo, useState } from "react";
import {
  Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Loader2, TrendingUp, TrendingDown } from "lucide-react";
import { api } from "../api";
import StockPicker from "./StockPicker";
import StrategySelector from "./StrategySelector";
import type { Strat } from "./QuantPilotApp";

const MONTHS = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];

function yearlyRet(dates: string[], nav: number[]) {
  const out: { year: string; ret: number }[] = [];
  let ys = nav[0] ?? 1;
  let year = dates[0]?.slice(0, 4);
  for (let i = 1; i < dates.length; i++) {
    const y = dates[i].slice(0, 4);
    if (y !== year) { out.push({ year, ret: (nav[i - 1] / ys - 1) * 100 }); ys = nav[i - 1]; year = y; }
  }
  if (dates.length) out.push({ year, ret: (nav[nav.length - 1] / ys - 1) * 100 });
  return out;
}

function monthlyByYear(dates: string[], nav: number[]) {
  const lastOfMonth: Record<string, number> = {};
  for (let i = 0; i < dates.length; i++) lastOfMonth[dates[i].slice(0, 7)] = nav[i];
  const keys = Object.keys(lastOfMonth);
  const byYear: Record<string, (number | null)[]> = {};
  keys.forEach((ym, i) => {
    const prev = i > 0 ? lastOfMonth[keys[i - 1]] : nav[0];
    const [y, m] = ym.split("-");
    const ret = lastOfMonth[ym] / prev - 1;
    (byYear[y] ||= Array(12).fill(null))[Number(m) - 1] = ret * 100;
  });
  return byYear;
}

function Sign({ v }: { v: number | null }) {
  if (v == null) return <span className="muted">—</span>;
  const up = v >= 0;
  return <span className={up ? "up" : "down"}>{up ? "+" : ""}{v.toFixed(1)}%</span>;
}

export default function StockAnalysis({
  strat, selected, onPick,
}: {
  strat: Strat;
  selected: { symbol: string; name: string } | null;
  onPick?: (s: { symbol: string; name: string }) => void;
}) {
  const [pick, setPick] = useState<{ symbol: string; name: string } | null>(selected);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [year, setYear] = useState<string>("");

  useEffect(() => { if (selected) setPick(selected); }, [selected?.symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!pick) return;
    setResult(null); setError(null); setLoading(true);
    api.strategyRun({ ...strat.spec, universe: [pick.symbol] }, { initial_cash: strat.cash, persist: false })
      .then((r) => setResult(r))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pick?.symbol, JSON.stringify(strat.spec), strat.cash]);

  const curve = useMemo(() => {
    const s = result?.series;
    if (!s) return [];
    const step = Math.max(1, Math.ceil(s.dates.length / 500));
    const rows: any[] = [];
    for (let i = 0; i < s.dates.length; i += step) {
      rows.push({ date: s.dates[i], strategy: s.strategy_nav[i], benchmark: s.benchmark_nav[i], exposure: s.exposure[i] });
    }
    return rows;
  }, [result]);

  const years = useMemo(() => (result?.series ? yearlyRet(result.series.dates, result.series.strategy_nav) : []), [result]);
  const months = useMemo(() => (result?.series ? monthlyByYear(result.series.dates, result.series.strategy_nav) : {}), [result]);
  const yearKeys = Object.keys(months).sort();
  useEffect(() => { if (yearKeys.length && !yearKeys.includes(year)) setYear(yearKeys[yearKeys.length - 1]); }, [yearKeys, year]);

  const m = result?.metrics || {};
  const pct = (v: any, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
  const trades: any[] = result?.trades || [];
  const lastNav = result?.series?.strategy_nav?.slice(-1)[0];
  const benchLast = result?.series?.benchmark_nav?.slice(-1)[0];

  return (
    <>
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-head">
          <span className="t">选择股票</span>
          <StrategySelector strat={strat} label="使用策略" />
          <span className="s">全市场任意一只 · 用当前策略「{strat.spec.name}」分析</span>
        </div>
        <StockPicker onPick={(s) => { setPick(s); onPick?.(s); }} />
        {pick && (
          <div className="selected-bar" style={{ marginTop: 12 }}>
            正在分析：<b>{pick.name}</b> <span className="mono muted">{pick.symbol}</span>
          </div>
        )}
      </div>

      {!pick && (
        <div className="panel"><div className="empty">在上方搜索并选择一只股票，即可看到该策略在它身上的历史表现。</div></div>
      )}

      {pick && (
        <>
          <div className="panel" style={{ marginBottom: 16 }}>
            <div className="panel-head">
              <span className="t">{pick.name} <span className="mono sub">{pick.symbol}</span></span>
              <span className="s">策略「{strat.spec.name}」· 本金 ¥{strat.cash.toLocaleString()} · 信号次日开盘</span>
            </div>
            <div className="notice" style={{ margin: 0 }}>
              单独针对该股票的完整回测：含 T+1、100 股整手、佣金/印花税/滑点。
            </div>
          </div>

          {loading && !result && <div className="panel" style={{ display: "flex", gap: 8, color: "var(--text-3)" }}><Loader2 size={16} className="spin" /> 正在回测该股票历史…</div>}
          {error && <div className="error">{error}</div>}

          {result && (
            <>
              <div className="panel" style={{ marginBottom: 16 }}>
                <div className="panel-head"><span className="t">总览指标</span><span className="s">数字含义见下方说明</span></div>
                {(() => {
                  const initial = result.initial_cash ?? 0;
                  const nav = result.series?.strategy_nav ?? [];
                  const navEnd = nav.length ? nav[nav.length - 1] : 1;
                  const equityEnd = navEnd * initial;
                  const profit = equityEnd - initial;
                  const ts = result.trade_stats || {};
                  return (
                    <div className="selected-bar" style={{ marginBottom: 14, display: "block" }}>
                      用本金 <b>¥{initial.toLocaleString()}</b>，这套策略在这只股票历史期末约 <b>¥{equityEnd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</b>，
                      即 <b className={profit >= 0 ? "up" : "down"}>{profit >= 0 ? "赚" : "亏"} ¥{Math.abs(profit).toLocaleString(undefined, { maximumFractionDigits: 0 })}（{pct(navEnd - 1)}）</b>
                      {ts.round_trips ? <> ｜ 共 {ts.round_trips} 个完整交易回合，每笔平均 <b className={((ts.avg_return ?? 0) >= 0) ? "up" : "down"}>{(ts.avg_return ?? 0) >= 0 ? "+" : ""}{((ts.avg_return ?? 0) * 100).toFixed(2)}%</b>（约 ¥{((ts.total_pnl ?? 0) / ts.round_trips).toFixed(0)}/笔）</> : null}
                    </div>
                  );
                })()}
                <div className="stat-row">
                  <div className="stat"><span className="k">年化收益</span><span className={`v ${(m.annual_return ?? 0) >= 0 ? "up" : "down"}`}>{pct(m.annual_return)}</span><span className="d">累计 {pct(m.total_return)}</span></div>
                  <div className="stat"><span className="k">最大回撤</span><span className="v down">{pct(m.max_drawdown)}</span><span className="d">Calmar {m.calmar == null ? "—" : Number(m.calmar).toFixed(2)}</span></div>
                  <div className="stat"><span className="k">夏普比率</span><span className="v">{m.sharpe == null ? "—" : Number(m.sharpe).toFixed(2)}</span><span className="d">仓位均值 {pct(m.exposure, 0)}</span></div>
                  <div className="stat"><span className="k">胜率 / 成交</span><span className="v sm">{pct(m.win_rate, 0)}</span><span className="d">{m.num_trades ?? trades.length} 笔</span></div>
                </div>
                <div className="infobox">
                  <div className="li"><b>年化收益</b>：把总收益折算成"每年平均赚多少"。</div>
                  <div className="li"><b>最大回撤</b>：历史上从最高点跌下来最多的幅度。</div>
                  <div className="li"><b>夏普比率</b>：每承担一份波动换来多少收益，&gt;1 算不错。</div>
                  <div className="li"><b>胜率</b>：盈利的持仓期占比；趋势策略胜率常不高，靠"亏小赚大"。</div>
                </div>
              </div>

              <div className="panel" style={{ marginBottom: 16 }}>
                <div className="panel-head">
                  <span className="t">资金曲线（时间维度）</span>
                  <span className="s">期末：策略 {lastNav?.toFixed(0)} vs 买入持有 {benchLast?.toFixed(0)}（初始 1000）</span>
                </div>
                <div style={{ height: 240 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={curve} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
                      <CartesianGrid stroke="var(--border)" vertical={false} />
                      <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--text-3)" }} minTickGap={48} tickLine={false} axisLine={false} />
                      <YAxis tick={{ fontSize: 11, fill: "var(--text-3)" }} domain={["auto", "auto"]} tickLine={false} axisLine={false} width={48} />
                      <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid var(--border-strong)", fontSize: 12 }} />
                      <Line type="monotone" dataKey="strategy" name="策略" stroke="var(--up)" strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="benchmark" name="买入持有" stroke="var(--text-3)" strokeWidth={1.5} strokeDasharray="4 4" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="notice" style={{ marginTop: 8 }}>
                  实线＝按策略规则买卖；虚线＝一开始就买入一直拿着。红线在上说明这套规则比死拿更好。
                </div>
              </div>

              <div className="qp-grid side" style={{ marginBottom: 16 }}>
                <div className="panel">
                  <div className="panel-head"><span className="t">分年度收益</span></div>
                  <table className="qp-table">
                    <thead><tr><th>年份</th><th>收益</th><th>结果</th></tr></thead>
                    <tbody>
                      {years.map((y) => (
                        <tr key={y.year}>
                          <td className="mono">{y.year}</td>
                          <td className="mono strong"><Sign v={y.ret} /></td>
                          <td>{y.ret >= 0 ? <TrendingUp size={14} className="up" /> : <TrendingDown size={14} className="down" />}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="panel">
                  <div className="panel-head">
                    <span className="t">分月度收益</span>
                    <select value={year} onChange={(e) => setYear(e.target.value)} style={{ width: 110, padding: "5px 8px", fontSize: 13 }}>
                      {yearKeys.map((y) => <option key={y} value={y}>{y} 年</option>)}
                    </select>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
                    {MONTHS.map((label, i) => {
                      const v = months[year]?.[i] ?? null;
                      return (
                        <div key={i} style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "8px 10px", background: "var(--surface-2)" }}>
                          <div className="notice" style={{ margin: 0 }}>{label}</div>
                          <div className="mono strong" style={{ fontSize: 14 }}><Sign v={v} /></div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              <div className="panel" style={{ marginBottom: 16 }}>
                <div className="panel-head"><span className="t">仓位（时间维度）</span><span className="s">1=满仓，0=空仓</span></div>
                <div style={{ height: 100 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={curve} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
                      <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--text-3)" }} minTickGap={48} tickLine={false} axisLine={false} />
                      <YAxis hide domain={[0, 1]} />
                      <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid var(--border-strong)", fontSize: 12 }} />
                      <Area type="stepAfter" dataKey="exposure" name="仓位" stroke="var(--primary)" fill="var(--primary-weak)" strokeWidth={1.5} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="panel">
                <div className="panel-head"><span className="t">交易记录</span><span className="s">{trades.length} 笔</span></div>
                <table className="qp-table">
                  <thead><tr><th>日期</th><th>方向</th><th>数量</th><th>价格</th><th>金额</th><th>费用</th><th style={{ textAlign: "left" }}>依据</th></tr></thead>
                  <tbody>
                    {trades.slice().reverse().map((t, i) => (
                      <tr key={i}>
                        <td className="mono">{t.date?.slice(0, 10)}</td>
                        <td className={t.side === "buy" ? "up" : "down"}>{t.side === "buy" ? "买入" : "卖出"}</td>
                        <td className="mono">{t.qty}</td>
                        <td className="mono">{t.price?.toFixed(2)}</td>
                        <td className="mono">{t.amount?.toFixed(0)}</td>
                        <td className="mono">{t.total_fee?.toFixed(1)}</td>
                        <td style={{ textAlign: "left" }}><span className="reason">{t.reason}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {trades.length === 0 && <div className="empty">该股票在历史中没有触发成交（可能不满足规则，或本金不足一手）。</div>}
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}
