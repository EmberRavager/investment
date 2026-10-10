import type { Summary } from "../types";
import { pct, num, upDown } from "../format";

export default function Kpis({ summary }: { summary: Summary }) {
  const st = summary.metrics.strategy;
  const bm = summary.metrics.benchmark;
  const isBuy = summary.signal === "买入";
  const excessDD = (st.max_drawdown ?? 0) - (bm.max_drawdown ?? 0);

  const card = (k: string, v: string, cls = "", sub?: string) => (
    <div className="kpi">
      <div className="k">{k}</div>
      <div className={`v ${cls}`}>{v}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );

  return (
    <div className="kpis">
      <div className="kpi">
        <div className="k">最新信号 · {summary.last_date}</div>
        <span className={`signal-badge ${isBuy ? "buy" : "hold"}`}>{summary.signal}</span>
        <div className="sub">多头概率 {num(summary.last_prob, 3)}</div>
      </div>
      {card("策略总收益", pct(st.total_return), upDown(st.total_return), `基准 ${pct(bm.total_return)}`)}
      {card("年化收益", pct(st.annual_return), upDown(st.annual_return), `基准 ${pct(bm.annual_return)}`)}
      {card("夏普比率", num(st.sharpe, 2), upDown(st.sharpe), `基准 ${num(bm.sharpe, 2)}`)}
      {card("Calmar", num(st.calmar, 2), upDown(st.calmar), `基准 ${num(bm.calmar, 2)}`)}
      {card("最大回撤", pct(st.max_drawdown), upDown(st.max_drawdown), `较基准 ${pct(excessDD)}`)}
      {card("持仓占比", pct(st.exposure), "", `进场 ${Math.round(st.num_trades ?? 0)} 次`)}
    </div>
  );
}
