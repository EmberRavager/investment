import { useState } from "react";
import {
  Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Sparkles, Loader2 } from "lucide-react";
import { api } from "../api";
import type { Strat } from "./QuantPilotApp";

export default function Xsec({ strat }: { strat: Strat }) {
  const [topK, setTopK] = useState(10);
  const [horizon, setHorizon] = useState(5);
  const [rebalance, setRebalance] = useState(5);
  const [trainWindow, setTrainWindow] = useState(250);
  const [retrain, setRetrain] = useState(20);
  const [universe, setUniverse] = useState<"index" | "market" | "etf" | "default" | "custom">("index");
  const [indexCode, setIndexCode] = useState("000905");
  const [uniSize, setUniSize] = useState(80);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<{ stage: string; pct: number } | null>(null);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true); setError(null); setData(null);
    setProgress({ stage: "准备中", pct: 0 });
    let result: any = null; let err: string | null = null;
    const opts: any = {
      top_k: topK, horizon, rebalance, train_window: trainWindow, retrain,
      initial_cash: strat.cash, model: "lightgbm",
      universe: universe === "custom" ? "default" : universe,
      index: indexCode,
      universe_size: uniSize,
    };
    if (universe === "custom") {
      opts.symbols = strat.form.universe.split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean);
    }
    try {
      await api.xsecStream(opts, (ev: any) => {
        if (ev.progress) setProgress(ev.progress);
        else if (ev.done) result = ev.result;
        else if (ev.error) err = ev.error;
      });
      if (err) throw new Error(err);
      setData(result);
    } catch (e: any) {
      setError(e.message);
    } finally { setLoading(false); setProgress(null); }
  };

  const curve = (() => {
    const s = data?.series;
    if (!s) return [];
    const step = Math.max(1, Math.ceil(s.dates.length / 500));
    const rows: any[] = [];
    for (let i = 0; i < s.dates.length; i += step) {
      rows.push({
        date: s.dates[i],
        strategy: s.strategy_nav[i],
        nocost: s.strategy_nav_nocost ? s.strategy_nav_nocost[i] : null,
        benchmark: s.benchmark_nav[i],
        index: s.index_nav && s.index_nav.length ? s.index_nav[i] : null,
        exposure: s.exposure[i],
      });
    }
    return rows;
  })();

  const pct = (v: any, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
  const num = (v: any, d = 2) => (v == null ? "—" : Number(v).toFixed(d));

  return (
    <div style={{ maxWidth: 1080, margin: "0 auto" }}>
      <div className="panel" style={{ marginBottom: 16, background: "var(--primary-weak)", borderColor: "#dfe7fb" }}>
        <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>横截面多因子选股（进阶）</div>
        <div className="notice" style={{ margin: 0, color: "var(--text-2)" }}>
          对一篮子股票逐日算因子 → 横截面标准化 → <b>滚动训练 LightGBM</b> 预测未来收益（打分）→ 每日选 <b>top-k</b> 等权持有 →
          交给真实撮合引擎（T+1/整手/佣金/印花税/滑点）。打分全部是 <b>walk-forward 样本外</b>，回测即样本外回测。
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div className="field" style={{ marginBottom: 0, flex: "0 0 120px" }}>
            <label>选股数 top-k</label>
            <input type="number" value={topK} onChange={(e) => setTopK(Number(e.target.value) || 10)} />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: "0 0 120px" }}>
            <label>预测周期 (日)</label>
            <input type="number" value={horizon} onChange={(e) => setHorizon(Number(e.target.value) || 5)} />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: "0 0 120px" }}>
            <label>换仓周期 (日)</label>
            <input type="number" value={rebalance} onChange={(e) => setRebalance(Number(e.target.value) || 5)} />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: "0 0 130px" }}>
            <label>训练窗口 (日)</label>
            <input type="number" value={trainWindow} onChange={(e) => setTrainWindow(Number(e.target.value) || 250)} />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: "0 0 120px" }}>
            <label>重训间隔 (日)</label>
            <input type="number" value={retrain} onChange={(e) => setRetrain(Number(e.target.value) || 20)} />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: "0 0 130px" }}>
            <label>股票池数量</label>
            <input type="number" value={uniSize} onChange={(e) => setUniSize(Number(e.target.value) || 80)} disabled={universe === "default" || universe === "custom" || universe === "index"} />
          </div>
          <button className="btn primary" onClick={run} disabled={loading}>
            {loading ? <Loader2 size={14} className="spin" /> : <Sparkles size={14} />} 开始选股回测
          </button>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 12 }}>
          <span className="notice" style={{ margin: 0 }}>股票池：</span>
          <button className={`btn ${universe === "index" ? "primary" : "ghost"} sm`} onClick={() => setUniverse("index")}>指数成分</button>
          <select value={indexCode} onChange={(e) => setIndexCode(e.target.value)} disabled={universe !== "index"}
            style={{ width: 130, padding: "5px 8px", fontSize: 13 }}>
            <option value="000300">沪深300</option>
            <option value="000905">中证500</option>
            <option value="000852">中证1000</option>
            <option value="000016">上证50</option>
          </select>
          <button className={`btn ${universe === "market" ? "primary" : "ghost"} sm`} onClick={() => setUniverse("market")}>全市场活跃</button>
          <button className={`btn ${universe === "etf" ? "primary" : "ghost"} sm`} onClick={() => setUniverse("etf")}>ETF 池</button>
          <button className={`btn ${universe === "default" ? "primary" : "ghost"} sm`} onClick={() => setUniverse("default")}>内置默认池</button>
          <button className={`btn ${universe === "custom" ? "primary" : "ghost"} sm`} onClick={() => setUniverse("custom")}>我的股票池</button>
        </div>
        {loading && progress && (
          <div style={{ marginTop: 12 }}>
            <div className="pbar"><div className="pfill" style={{ width: `${progress.pct}%` }} /></div>
            <div className="notice" style={{ marginTop: 6 }}>{progress.stage} {progress.pct ? `${progress.pct}%` : ""}</div>
          </div>
        )}
        {error && <div className="error" style={{ marginTop: 12 }}>{error}</div>}
        <div className="notice" style={{ marginTop: 10 }}>
          <b>全市场活跃</b>：按成交额取最活跃的前 N 只（剔 ST/涨停/低流动性）。截面股票越多，IC/分层越有统计意义；
          <b>我的股票池</b>用策略实验室里配置的标的。首次加载较多历史会慢一点，之后走缓存。
        </div>
      </div>

      {data && (
        <>
          {data.explanation && (
            <div className="panel" style={{ marginBottom: 16, background: "var(--surface-2)" }}>
              <div className="panel-head">
                <span className="t">自动解读</span>
                <span className={`pill ${data.verdict?.usable ? "green" : "red"}`}>{data.verdict?.label ?? "—"}</span>
              </div>
              <div style={{ fontSize: 15, fontWeight: 700, margin: "2px 0 10px", lineHeight: 1.6 }}>
                {data.explanation.headline}
              </div>
              <ul style={{ margin: "0 0 0 18px", padding: 0, color: "var(--text-2)", lineHeight: 1.9, fontSize: 13.5 }}>
                {(data.explanation.reasons || []).map((r: string, i: number) => <li key={i}>{r}</li>)}
              </ul>
              <div className="notice" style={{ marginTop: 10 }}>
                结论由真实样本外指标自动生成：<b>有效</b>看 IC/ICIR/IC-t 与分层单调性；<b>值不值</b>看相对{data.params?.index || "指数"}的超额与风险。不构成投资建议。
              </div>
            </div>
          )}

          <div className="panel" style={{ marginBottom: 16 }}>
            <div className="panel-head">
              <span className="t">最新一日选出的股票（top-{topK}）</span>
              <span className="s">{data.picks_as_of || ""} · 打分＝模型预测的相对强弱（不是涨跌概率）</span>
            </div>
            <table className="qp-table">
              <thead><tr><th>排名</th><th style={{ textAlign: "left" }}>股票</th><th>打分</th><th>同类分位</th><th>说明</th></tr></thead>
              <tbody>
                {(data.picks || []).map((p: any) => (
                  <tr key={p.symbol}>
                    <td className="mono">{p.rank}</td>
                    <td style={{ textAlign: "left" }}><span className="strong">{p.name}</span> <span className="sub mono">{p.symbol}</span></td>
                    <td className="mono strong">{p.score}</td>
                    <td className="mono">{Math.round((p.percentile ?? 0) * 100)}%</td>
                    <td style={{ textAlign: "left" }}><span className="reason">{p.rank === 1 ? "模型最看好" : p.rank <= 3 ? "模型看好" : "排名靠前"}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(!data.picks || data.picks.length === 0) && <div className="empty">暂无打分结果。</div>}
            <div className="notice" style={{ marginTop: 10 }}>
              打分高 = 模型认为它会<b>跑赢同批股票</b>（横截面排序），<b>不是涨跌概率</b>。这是"选股名单"，但**能否真赚钱取决于因子是否有效**——看下方 IC。
            </div>
          </div>

          <div className="panel" style={{ marginBottom: 16 }}>
            <div className="panel-head">
              <span className="t">因子有效性（IC）</span>
              <span className="s">样本外 {data.oos_days} 天 · 因子 {data.factor_cols?.length} 个</span>
            </div>
            <div className="stat-row">
              <div className="stat"><span className="k">IC 均值</span><span className={`v ${(data.ic.ic_mean ?? 0) >= 0 ? "up" : "down"}`}>{num(data.ic.ic_mean, 4)}</span><span className="d">打分与未来收益的相关</span></div>
              <div className="stat"><span className="k">ICIR</span><span className="v">{num(data.ic.icir)}</span><span className="d">IC均值/波动，&gt;0.3 较好</span></div>
              <div className="stat"><span className="k">IC&gt;0 占比</span><span className="v">{pct(data.ic.ic_positive_pct, 1)}</span><span className="d">方向稳定性</span></div>
              <div className="stat"><span className="k">多空(顶-底)</span><span className={`v ${(data.layered.long_short ?? 0) >= 0 ? "up" : "down"}`}>{data.layered.long_short == null ? "—" : `${data.layered.long_short}%`}</span><span className="d">每期分层多空收益</span></div>
            </div>
            {data.layered?.quantiles && Object.keys(data.layered.quantiles).length > 0 && (
              <div className="infobox" style={{ marginTop: 12 }}>
                <div className="li"><b>分层收益（每期平均 %）</b>：按打分从低到高分 5 层，看是否单调递增（越单调说明因子越有效）。</div>
                <div className="reasons" style={{ marginTop: 8 }}>
                  {Object.entries(data.layered.quantiles).map(([k, v]: any) => (
                    <span className="reason" key={k}>第 {Number(k) + 1} 层: <b className={v >= 0 ? "up" : "down"}>{v}%</b></span>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="panel" style={{ marginBottom: 16 }}>
            <div className="panel-head"><span className="t">样本外组合表现</span><span className="s">top{topK} 等权 · 换仓 {rebalance} 日 · 含成本</span></div>
            <div className="stat-row">
              <div className="stat"><span className="k">年化</span><span className={`v ${(data.metrics.annual_return ?? 0) >= 0 ? "up" : "down"}`}>{pct(data.metrics.annual_return)}</span><span className="d">累计 {pct(data.metrics.total_return)}</span></div>
              <div className="stat"><span className="k">最大回撤</span><span className="v down">{pct(data.metrics.max_drawdown)}</span><span className="d">Calmar {num(data.metrics.calmar)}</span></div>
              <div className="stat"><span className="k">夏普</span><span className="v">{num(data.metrics.sharpe)}</span><span className="d">-</span></div>
              <div className="stat"><span className="k">成交 / 费用</span><span className="v sm">{data.trade_stats?.round_trips ?? 0} 回合</span><span className="d">费用 ¥{data.trade_stats?.total_fees ?? 0}</span></div>
            </div>
            <div className="infobox" style={{ marginTop: 12 }}>
              <div className="li">
                相对 <b>{data.params?.index}</b> 超额（含成本）：
                <b className={(data.excess ?? 0) >= 0 ? "up" : "down"}> {data.excess == null ? "—" : `${(data.excess * 100).toFixed(1)}%`}</b>
                {"　"}不含成本年化：
                <b> {data.metrics_nocost?.annual_return == null ? "—" : `${(data.metrics_nocost.annual_return * 100).toFixed(1)}%`}</b>
                {"　"}成本拖累/年：<b className="down"> {data.cost_drag == null ? "—" : `${(data.cost_drag * 100).toFixed(1)}%`}</b>
              </div>
            </div>
            <div style={{ height: 240, marginTop: 12 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={curve} margin={{ top: 4, right: 8, left: -14, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--text-3)" }} minTickGap={48} tickLine={false} axisLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: "var(--text-3)" }} domain={["auto", "auto"]} tickLine={false} axisLine={false} width={48} />
                  <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid var(--border-strong)", fontSize: 12 }} />
                  <Line type="monotone" dataKey="strategy" name="多因子(含成本)" stroke="var(--up)" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="nocost" name="多因子(不含成本)" stroke="#94a3b8" strokeWidth={1.5} dot={false} />
                  <Line type="monotone" dataKey="index" name="沪深300" stroke="#2563eb" strokeWidth={1.5} strokeDasharray="4 4" dot={false} />
                  <Line type="monotone" dataKey="benchmark" name="等权基准" stroke="var(--text-3)" strokeWidth={1} strokeDasharray="2 3" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head"><span className="t">当前持仓（最后一期）</span><span className="s">{Object.keys(data.positions || {}).length} 只</span></div>
            <table className="qp-table">
              <thead><tr><th style={{ textAlign: "left" }}>标的</th><th>股数</th><th>成本</th><th>现价</th><th>盈亏</th><th>权重</th></tr></thead>
              <tbody>
                {Object.entries(data.positions || {}).map(([sym, p]: any) => (
                  <tr key={sym}>
                    <td style={{ textAlign: "left" }}><span className="strong">{p.name || sym}</span> <span className="sub mono">{sym}</span></td>
                    <td className="mono">{p.qty}</td>
                    <td className="mono">{p.cost_price?.toFixed(2)}</td>
                    <td className="mono">{p.last_price?.toFixed(2)}</td>
                    <td className={`mono ${p.pnl >= 0 ? "up" : "down"}`}>{p.pnl >= 0 ? "+" : ""}{p.pnl?.toFixed(0)}</td>
                    <td className="mono">{((data.account?.equity ? (p.market_value / data.account.equity) : 0) * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {Object.keys(data.positions || {}).length === 0 && <div className="empty">末期空仓。</div>}
          </div>
        </>
      )}
    </div>
  );
}
