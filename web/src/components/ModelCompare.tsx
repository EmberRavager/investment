import { useState } from "react";
import { Layers, Loader2, AlertTriangle } from "lucide-react";
import { api } from "../api";
import { MODEL_LABEL } from "../glossary";
import { pct, num } from "../format";
import Progress from "./Progress";

interface Row {
  model: string;
  hit_rate?: number;
  auc?: number;
  total_return?: number;
  annual_return?: number;
  sharpe?: number;
  calmar?: number;
  max_drawdown?: number;
  num_trades?: number;
  exposure?: number;
  error?: string;
}

export default function ModelCompare({ config }: { config: any }) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<{ symbol: string; results: Row[]; benchmark: any } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ stage: string; pct: number; detail?: string } | null>(null);

  const run = async () => {
    setLoading(true);
    setErr(null);
    setData(null);
    setProgress({ stage: "准备中", pct: 0 });
    let result: any = null;
    let error: string | null = null;
    try {
      await api.compareStream(config, (ev: any) => {
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

  const bestHit = data?.results?.find((r) => !r.error)?.model;
  const bestSharpe = data
    ? [...data.results].filter((r) => !r.error).sort((a, b) => (b.sharpe ?? -99) - (a.sharpe ?? -99))[0]
        ?.model
    : undefined;

  return (
    <div className="step-card" style={{ borderStyle: "dashed" }}>
      <div className="step-title">
        <span className="n" style={{ background: "var(--text-2)" }}>?</span>
        <h2>
          让所有模型比一比 <span className="sub">看哪个猜得准、哪个更稳</span>
        </h2>
      </div>

      <p className="hint" style={{ marginBottom: 14 }}>
        对当前这只股票，把 10 个模型都跑一遍，按「命中率」排个榜。
        <b>命中率就是猜对涨跌的比例，50% 等于瞎猜</b>——比基准高才有意义。
      </p>

      <button className="bigbtn" onClick={run} disabled={loading}>
        {loading ? <Loader2 size={20} className="spin" /> : <Layers size={20} />}
        {loading ? "正在逐个模型对比，稍等…" : "对比所有模型"}
      </button>

      {loading && progress && (
        <div style={{ marginTop: 14 }}>
          <Progress stage={`${progress.stage}：${progress.detail ?? ""}`} pct={progress.pct} />
        </div>
      )}

      {err && (
        <div className="error" style={{ marginTop: 14, display: "flex", gap: 8 }}>
          <AlertTriangle size={16} style={{ flex: "none", marginTop: 3 }} />
          <span>对比失败：{err}</span>
        </div>
      )}

      {data && (
        <div style={{ marginTop: 18 }}>
          <div className="hint" style={{ marginBottom: 10 }}>
            {data.symbol} · 按命中率排序（绿=该列最好）：
          </div>
          <table className="metrics">
            <thead>
              <tr>
                <th style={{ textAlign: "left" }}>模型</th>
                <th>命中率</th>
                <th>预测能力</th>
                <th>总收益</th>
                <th>夏普</th>
                <th>最大亏损</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((r) => {
                if (r.error) {
                  return (
                    <tr key={r.model}>
                      <td style={{ textAlign: "left" }}>{MODEL_LABEL[r.model] ?? r.model}</td>
                      <td colSpan={5} className="muted" style={{ textAlign: "left" }}>
                        出错：{r.error.slice(0, 60)}
                      </td>
                    </tr>
                  );
                }
                const isBestHit = r.model === bestHit;
                const isBestSharpe = r.model === bestSharpe;
                return (
                  <tr key={r.model} style={isBestHit ? { background: "#eafaf1" } : undefined}>
                    <td style={{ textAlign: "left", fontWeight: isBestHit ? 700 : 500 }}>
                      {MODEL_LABEL[r.model] ?? r.model}
                      {isBestHit && <span className="tag-rec good" style={{ marginLeft: 6 }}>命中最高</span>}
                    </td>
                    <td className={`fig ${(r.hit_rate ?? 0) > 0.5 ? "up" : "down"}`}>
                      {pct(r.hit_rate)}
                    </td>
                    <td>{num(r.auc, 3)}</td>
                    <td className={isBestSharpe ? "up" : ""}>{pct(r.total_return)}</td>
                    <td className={isBestSharpe ? "up" : ""}>{num(r.sharpe, 2)}</td>
                    <td>{pct(r.max_drawdown)}</td>
                  </tr>
                );
              })}
              <tr style={{ borderTop: "2px solid var(--border)" }}>
                <td style={{ textAlign: "left", fontWeight: 600 }}>一直拿着（基准）</td>
                <td className="muted">—</td>
                <td className="muted">—</td>
                <td>{pct(data.benchmark?.total_return)}</td>
                <td>{num(data.benchmark?.sharpe, 2)}</td>
                <td>{pct(data.benchmark?.max_drawdown)}</td>
              </tr>
            </tbody>
          </table>
          <div className="hint" style={{ marginTop: 10 }}>
            提示：命中率都接近 50% 是常态——真正靠谱的模型应该 <b>命中率稳定高于 50%</b> 且
            <b>最大亏损可控</b>。若某模型命中率异常高、收益也离谱地好，反而要警惕过拟合。
          </div>
        </div>
      )}
    </div>
  );
}
