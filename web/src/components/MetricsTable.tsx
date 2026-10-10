import { pct, num, upDown } from "../format";

const ROWS: { key: string; label: string; fmt: (v: number) => string }[] = [
  { key: "total_return", label: "总收益", fmt: (v) => pct(v) },
  { key: "annual_return", label: "年化收益", fmt: (v) => pct(v) },
  { key: "sharpe", label: "夏普比率", fmt: (v) => num(v, 2) },
  { key: "calmar", label: "Calmar", fmt: (v) => num(v, 2) },
  { key: "max_drawdown", label: "最大回撤", fmt: (v) => pct(v) },
  { key: "win_rate", label: "胜率", fmt: (v) => pct(v) },
  { key: "num_trades", label: "进场次数", fmt: (v) => Math.round(v).toString() },
  { key: "exposure", label: "持仓占比", fmt: (v) => pct(v) },
];

export default function MetricsTable({ metrics }: { metrics: any }) {
  const clf = metrics.classification;
  const st = metrics.strategy;
  const bm = metrics.benchmark;

  return (
    <>
      <table className="metrics">
        <thead>
          <tr>
            <th>指标</th>
            <th>策略</th>
            <th>买入持有</th>
            <th>差异</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => {
            const a = st[r.key];
            const b = bm[r.key];
            const diff = (a ?? 0) - (b ?? 0);
            return (
              <tr key={r.key}>
                <td>{r.label}</td>
                <td className={upDown(a)}>{r.fmt(a)}</td>
                <td>{r.fmt(b)}</td>
                <td className={upDown(diff)}>
                  {r.key === "num_trades" ? `${Math.round(diff) > 0 ? "+" : ""}${Math.round(diff)}` : pct(diff)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="section" style={{ marginTop: 18, marginBottom: 0 }}>
        <div className="title">预测能力（分类）</div>
        <div className="row2" style={{ gap: 12 }}>
          <div className="kpi">
            <div className="k">准确率</div>
            <div className={`v ${clf.accuracy > clf.base_rate_up ? "up" : "down"}`}>{pct(clf.accuracy)}</div>
            <div className="sub">基准率 {pct(clf.base_rate_up)}</div>
          </div>
          <div className="kpi">
            <div className="k">AUC</div>
            <div className={`v ${clf.roc_auc > 0.5 ? "up" : "down"}`}>{num(clf.roc_auc, 3)}</div>
            <div className="sub">{clf.roc_auc > 0.5 ? "优于随机" : "不优于随机 (≤0.5)"}</div>
          </div>
          <div className="kpi">
            <div className="k">精确率 / 召回率</div>
            <div className="v" style={{ fontSize: 16 }}>
              {pct(clf.precision, 1)} / {pct(clf.recall, 1)}
            </div>
            <div className="sub">样本 {clf.n_samples}</div>
          </div>
        </div>
      </div>
    </>
  );
}
