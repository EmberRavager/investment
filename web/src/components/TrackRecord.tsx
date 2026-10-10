import type { Summary } from "../types";
import { pct } from "../format";

interface Rec {
  date: string;
  pred: string;
  actual: string;
  correct: boolean;
}

export default function TrackRecord({ summary }: { summary: Summary }) {
  const tr = (summary as any).track_record;
  if (!tr || !tr.recent) return null;
  const recent: Rec[] = tr.recent;
  const correctCount = recent.filter((r) => r.correct).length;

  return (
    <div className="card">
      <div className="head">
        <span className="t">预测战绩</span>
        <span className="s">每天预测的方向 vs 实际结果，逐条核对</span>
      </div>

      <div className="kpis" style={{ marginBottom: 16 }}>
        <div className="kpi">
          <div className="k">历史命中率</div>
          <div className={`v ${(tr.hit_rate ?? 0) > 0.5 ? "up" : "down"}`}>{pct(tr.hit_rate)}</div>
          <div className="sub">共 {tr.n} 个交易日 · 50% 就是瞎猜</div>
        </div>
        <div className="kpi">
          <div className="k">最近 {recent.length} 次</div>
          <div className="v">
            {correctCount}
            <span style={{ fontSize: 16, color: "var(--text-3)" }}> / {recent.length} 次猜对</span>
          </div>
          <div className="sub">下表绿=对，红=错</div>
        </div>
      </div>

      <div className="caption">最近 {recent.length} 个交易日的逐条记录（最新在上）：</div>
      <table className="metrics">
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>日期</th>
            <th>模型预测</th>
            <th>实际结果</th>
            <th>对/错</th>
          </tr>
        </thead>
        <tbody>
          {recent
            .slice()
            .reverse()
            .map((r) => (
              <tr key={r.date}>
                <td style={{ textAlign: "left" }}>{r.date}</td>
                <td className={r.pred === "涨" ? "up" : "down"} style={{ fontWeight: 600 }}>
                  {r.pred}
                </td>
                <td className={r.actual === "涨" ? "up" : "down"}>{r.actual}</td>
                <td className={r.correct ? "up" : "down"} style={{ fontWeight: 700 }}>
                  {r.correct ? "✓ 对" : "✗ 错"}
                </td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}
