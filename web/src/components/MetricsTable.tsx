import { pct, num, upDown } from "../format";
import Info from "./Info";

const ROWS: {
  key: string;
  label: string;
  info?: string;
  fmt: (v: number) => string;
  higherBetter: boolean;
}[] = [
  { key: "total_return", label: "总收益", fmt: (v) => pct(v), higherBetter: true },
  { key: "annual_return", label: "平均每年", fmt: (v) => pct(v), higherBetter: true },
  {
    key: "sharpe",
    label: "风险性价比",
    info: "夏普比率，越高越好",
    fmt: (v) => num(v, 2),
    higherBetter: true,
  },
  {
    key: "calmar",
    label: "收益回撤比",
    info: "年化收益 ÷ 最大亏损，越高越好",
    fmt: (v) => num(v, 2),
    higherBetter: true,
  },
  {
    key: "max_drawdown",
    label: "最大亏损",
    info: "从最高点回落到最低点的幅度，越浅越好",
    fmt: (v) => pct(v),
    higherBetter: true,
  },
  { key: "win_rate", label: "盈利天数占比", fmt: (v) => pct(v), higherBetter: true },
  { key: "num_trades", label: "出手次数", fmt: (v) => Math.round(v).toString(), higherBetter: true },
  { key: "exposure", label: "持仓时间", fmt: (v) => pct(v), higherBetter: true },
];

export default function MetricsTable({ metrics }: { metrics: any }) {
  const clf = metrics.classification;
  const st = metrics.strategy;
  const bm = metrics.benchmark;
  const auc = clf.roc_auc ?? 0.5;

  return (
    <>
      <table className="metrics">
        <thead>
          <tr>
            <th>指标</th>
            <th>这套策略</th>
            <th>一直拿着</th>
            <th>对比</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => {
            const a = st[r.key];
            const b = bm[r.key];
            const better = r.higherBetter ? a > b : a < b;
            return (
              <tr key={r.key}>
                <td>
                  {r.label} {r.info && <Info text={r.info} />}
                </td>
                <td className={`fig ${upDown(r.key.includes("drawdown") || r.key.includes("return") || r.key === "sharpe" || r.key === "calmar" ? a : undefined)}`}>
                  {r.fmt(a)}
                </td>
                <td>{r.fmt(b)}</td>
                <td>
                  <span className={`tag-rec ${better ? "good" : "bad"}`}>
                    {better ? "更好" : "略逊"}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div style={{ marginTop: 20 }}>
        <div className="section-title" style={{ fontSize: 14 }}>
          模型的“眼力”怎么样？
        </div>
        <div className="kpis" style={{ marginBottom: 0 }}>
          <div className="kpi">
            <div className="k">
              猜对涨跌的比例{" "}
              <Info text="模型预测方向正确的比例。要跟“上涨天数占比”比较才有意义。" />
            </div>
            <div className={`v ${upDown(clf.accuracy - clf.base_rate_up)}`}>{pct(clf.accuracy)}</div>
            <div className="sub">
              随便猜的基准是 <b>{pct(clf.base_rate_up)}</b>
            </div>
          </div>
          <div className="kpi">
            <div className="k">
              预测能力{" "}
              <Info text="AUC：0.50 = 和瞎猜一样；>0.55 才算有一点真本事；<0.50 说明还不如瞎猜。" />
            </div>
            <div className={`v ${auc > 0.5 ? "up" : "down"}`}>{num(auc, 2)}</div>
            <div className="sub">{auc > 0.55 ? "有一定优势" : auc > 0.5 ? "只有微弱优势" : "基本等于瞎猜"}</div>
          </div>
          <div className="kpi">
            <div className="k">
              抓上涨的准头 <Info text="精确率：模型说涨时，真的涨的比例。" />
            </div>
            <div className="v">{pct(clf.precision, 0)}</div>
            <div className="sub">样本数 {clf.n_samples}</div>
          </div>
        </div>
      </div>
    </>
  );
}
