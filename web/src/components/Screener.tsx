import { useState } from "react";
import { Radar, Loader2, ChevronRight, AlertTriangle } from "lucide-react";
import { api } from "../api";
import Progress from "./Progress";

interface Row {
  symbol: string;
  kind: string;
  name: string;
  prob?: number;
  action?: string;
  position_pct?: number;
  error?: string;
}

const ACTION_CLS: Record<string, string> = {
  买入: "up",
  持有: "up",
  卖出: "down",
  观望: "muted",
};

export default function Screener({
  config,
  onPick,
}: {
  config: any;
  onPick: (symbol: string, kind: string) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<{ universe_size: number; shortlist_size: number; results: Row[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ stage: string; pct: number } | null>(null);

  const run = async () => {
    setLoading(true);
    setErr(null);
    setData(null);
    setProgress({ stage: "准备中", pct: 0 });
    let result: any = null;
    let error: string | null = null;
    try {
      await api.screenStream(config, 15, (ev: any) => {
        if (ev.progress) setProgress(ev.progress);
        else if (ev.done) result = ev.result;
        else if (ev.error) error = ev.error;
      });
      if (error) throw new Error(error);
      setData(result);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
      setProgress(null);
    }
  };

  return (
    <div className="step-card" style={{ borderStyle: "dashed" }}>
      <div className="step-title">
        <span className="n" style={{ background: "var(--text-2)" }}>
          ?
        </span>
        <h2>
          不知道买啥？让系统扫一遍全市场 <span className="sub">从 5000 多只里帮你挑</span>
        </h2>
      </div>

      <p className="hint" style={{ marginBottom: 14 }}>
        先按活跃度粗筛一遍，再对挑出来的十几只跑模型，按「看涨概率」排个榜。
        看到感兴趣的，<b>点一下就能看它的详细分析</b>。
      </p>

      <button className="bigbtn" onClick={run} disabled={loading}>
        {loading ? <Loader2 size={20} className="spin" /> : <Radar size={20} />}
        {loading ? "正在扫描全市场，稍等…" : "扫一遍，看看有哪些机会"}
      </button>

      {loading && progress && (
        <div style={{ marginTop: 14 }}>
          <Progress stage={progress.stage} pct={progress.pct} />
        </div>
      )}

      {err && (
        <div className="error" style={{ marginTop: 14, display: "flex", gap: 8 }}>
          <AlertTriangle size={16} style={{ flex: "none", marginTop: 3 }} />
          <span>选股失败：{err}</span>
        </div>
      )}

      {data && (
        <div style={{ marginTop: 18 }}>
          <div className="hint" style={{ marginBottom: 10 }}>
            全市场 <b>{data.universe_size}</b> 只 → 粗筛出 <b>{data.shortlist_size}</b> 只 →
            按模型看涨概率排序：
          </div>
          <table className="metrics">
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>#</th>
                <th style={{ textAlign: "left" }}>名称</th>
                <th>看涨概率</th>
                <th>建议</th>
                <th>建议仓位</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((r, i) => (
                <tr
                  key={r.symbol}
                  onClick={() => !r.error && onPick(r.symbol, r.kind)}
                  style={{ cursor: r.error ? "default" : "pointer" }}
                  title={r.error ? r.error : "点击查看详细分析"}
                >
                  <td style={{ textAlign: "left" }} className="muted">
                    {i + 1}
                  </td>
                  <td style={{ textAlign: "left", fontWeight: 600 }}>
                    {r.name} <span className="muted" style={{ fontSize: 12 }}>{r.symbol}</span>
                  </td>
                  <td className="fig">{r.error ? "—" : `${(100 * (r.prob ?? 0)).toFixed(0)}%`}</td>
                  <td className={ACTION_CLS[r.action ?? ""] ?? ""}>{r.error ? "取数失败" : r.action}</td>
                  <td>
                    {r.error ? "—" : r.position_pct ? `${(r.position_pct * 100).toFixed(0)}%` : "不投"}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {!r.error && <ChevronRight size={15} className="muted" />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
