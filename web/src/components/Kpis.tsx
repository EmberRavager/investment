import type { Summary } from "../types";
import { pct, num, upDown } from "../format";
import Info from "./Info";

export default function Kpis({ summary }: { summary: Summary }) {
  const st = summary.metrics.strategy;
  const bm = summary.metrics.benchmark;
  const isBuy = summary.signal === "买入";

  return (
    <div className="kpis">
      <div className="kpi">
        <div className="k">现在该不该买？</div>
        <span className={`signal-pill ${isBuy ? "buy" : "hold"}`}>
          {isBuy ? "建议买入" : "建议观望"}
        </span>
        <div className="sub">
          {summary.last_date} · 看涨概率 <b>{pct(summary.last_prob, 0)}</b>
        </div>
      </div>

      <div className="kpi">
        <div className="k">总收益</div>
        <div className={`v ${upDown(st.total_return)}`}>{pct(st.total_return)}</div>
        <div className="sub">
          一直拿着是 <b>{pct(bm.total_return)}</b>
        </div>
      </div>

      <div className="kpi">
        <div className="k">最大亏损</div>
        <div className="v">{pct(st.max_drawdown)}</div>
        <div className="sub">
          一直拿着 <b>{pct(bm.max_drawdown)}</b>
        </div>
      </div>

      <div className="kpi">
        <div className="k">
          风险性价比 <Info text="夏普比率：每承担一份风险能换来多少收益。>1 优秀，>0.5 尚可，<0 说明还不如不冒险。" />
        </div>
        <div className={`v ${upDown(st.sharpe)}`}>{num(st.sharpe, 2)}</div>
        <div className="sub">
          一直拿着 <b>{num(bm.sharpe, 2)}</b>
        </div>
      </div>

      <div className="kpi">
        <div className="k">
          收益回撤比 <Info text="Calmar 比率：年化收益 ÷ 最大回撤。衡量赚的钱是否值得承受的亏损，越高越好。" />
        </div>
        <div className={`v ${upDown(st.calmar)}`}>{num(st.calmar, 2)}</div>
        <div className="sub">
          一直拿着 <b>{num(bm.calmar, 2)}</b>
        </div>
      </div>

      <div className="kpi">
        <div className="k">
          持仓时间 <Info text="有仓位的天数占比。越高说明越常在场内，交易越少越省成本。" />
        </div>
        <div className="v">{pct(st.exposure, 0)}</div>
        <div className="sub">
          出手 <b>{Math.round(st.num_trades ?? 0)}</b> 次
        </div>
      </div>
    </div>
  );
}
