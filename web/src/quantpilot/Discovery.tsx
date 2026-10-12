import { useState } from "react";
import { Sparkles, Loader2, Check, ArrowRight } from "lucide-react";
import { api } from "../api";
import StockPicker from "./StockPicker";
import type { Strat } from "./QuantPilotApp";
import { specToForm } from "./strategyForm";

const OP_LBL: Record<string, string> = { ">": ">", "<": "<", ">=": "≥", "<=": "≤", "==": "=", cross_above: "上穿", cross_below: "下穿" };

export default function Discovery({ strat, onAdopt }: { strat: Strat; onAdopt: (kind: string) => void }) {
  const [pick, setPick] = useState<{ symbol: string; name: string } | null>(null);
  const [cash, setCash] = useState(100000);
  const [topK, setTopK] = useState(8);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<{ stage: string; pct: number; detail?: string } | null>(null);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  const run = async () => {
    if (!pick) { setError("请先选择一只股票"); return; }
    setLoading(true); setError(null); setSavedMsg(null); setData(null);
    setProgress({ stage: "准备中", pct: 0 });
    let result: any = null; let err: string | null = null;
    try {
      await api.strategyDiscoverStream({ symbol: pick.symbol, initial_cash: cash, top_k: topK }, (ev: any) => {
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

  const adopt = (r: any) => {
    strat.setForm(specToForm(r.spec));
    setSavedMsg(`已采用：${r.spec.name}（可在下方回测，或去「股票雷达」用它筛选全市场）`);
  };

  const save = async (r: any) => {
    try {
      const res = await api.strategySave(r.spec, { source: "discovery" });
      setSavedMsg(`已保存为策略 #${res.strategy_id}`);
    } catch (e: any) { setError(e.message); }
  };

  const pct = (v: any, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
  const num = (v: any, d = 2) => (v == null ? "—" : Number(v).toFixed(d));

  return (
    <div style={{ maxWidth: 1080, margin: "0 auto" }}>
      <div className="panel" style={{ marginBottom: 16, background: "var(--primary-weak)", borderColor: "#dfe7fb" }}>
        <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>逆向策略发现</div>
        <div className="notice" style={{ margin: 0, color: "var(--text-2)" }}>
          反过来做：<b>先选一只股票</b>，系统在这只股票上涨回搜索规则空间（均线/放量/止损），
          按<b>样本外</b>夏普挑出稳健的策略 → 采用后可去「股票雷达」用它筛选全市场。
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div className="field" style={{ marginBottom: 0, flex: "1 1 320px", minWidth: 260 }}>
            <label>选择股票</label>
            <StockPicker onPick={setPick} />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: "0 0 160px" }}>
            <label>回测本金（元）</label>
            <input type="number" value={cash} onChange={(e) => setCash(Number(e.target.value) || 0)} />
          </div>
          <div className="field" style={{ marginBottom: 0, flex: "0 0 120px" }}>
            <label>返回前 N 个</label>
            <input type="number" value={topK} onChange={(e) => setTopK(Number(e.target.value) || 8)} />
          </div>
          <button className="btn primary" onClick={run} disabled={loading || !pick}>
            {loading ? <Loader2 size={14} className="spin" /> : <Sparkles size={14} />} 开始发现
          </button>
        </div>
        {pick && (
          <div className="selected-bar" style={{ marginTop: 12 }}>
            目标股票：<b>{pick.name}</b> <span className="mono muted">{pick.symbol}</span>
          </div>
        )}
        {loading && progress && (
          <div style={{ marginTop: 12 }}>
            <div className="pbar"><div className="pfill" style={{ width: `${progress.pct}%` }} /></div>
            <div className="notice" style={{ marginTop: 6 }}>{progress.stage} {progress.detail ? `· ${progress.detail}` : ""}</div>
          </div>
        )}
        {error && <div className="error" style={{ marginTop: 12 }}>{error}</div>}
      </div>

      {data && (
        <div className="panel">
          <div className="panel-head">
            <span className="t">{data.name || data.symbol} 的发现结果</span>
            <span className="s">测试 {data.tested} 种组合 · 保留 {data.kept} 个（成交≥4笔）· 按样本外夏普排序</span>
          </div>
          {savedMsg && <div className="selected-bar" style={{ marginBottom: 12 }}><Check size={15} /> {savedMsg}</div>}
          <div style={{ overflowX: "auto" }}>
            <table className="qp-table">
              <thead>
                <tr>
                  <th>#</th><th style={{ textAlign: "left" }}>规则</th>
                  <th>样本外年化</th><th>样本外夏普</th><th>全样本年化</th><th>全样本夏普</th><th>最大回撤</th><th>成交</th><th>操作</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((r: any, i: number) => (
                  <tr key={i}>
                    <td className="mono">{i + 1}</td>
                    <td style={{ textAlign: "left" }}>
                      <div className="strong">{r.spec.name}</div>
                      <div className="sub">{r.rules.map((x: any) => x.text).join(" 且 ")}</div>
                    </td>
                    <td className={`mono ${(r.out_sample?.annual_return ?? 0) >= 0 ? "up" : "down"}`}>{pct(r.out_sample?.annual_return)}</td>
                    <td className="mono strong">{num(r.out_sample?.sharpe)}</td>
                    <td className={`mono ${(r.metrics?.annual_return ?? 0) >= 0 ? "up" : "down"}`}>{pct(r.metrics?.annual_return)}</td>
                    <td className="mono">{num(r.metrics?.sharpe)}</td>
                    <td className="mono down">{pct(r.metrics?.max_drawdown)}</td>
                    <td className="mono">{r.metrics?.num_trades ?? "—"}</td>
                    <td>
                      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                        <button className="btn primary sm" onClick={() => adopt(r)}>采用</button>
                        <button className="btn ghost sm" onClick={() => save(r)}>保存</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="notice" style={{ marginTop: 10 }}>
            样本外＝后 30% 时间段，策略没"见过"这段历史，更能反映是否真稳健。
            {data.results[0] && (
              <button className="link" style={{ marginLeft: 8 }} onClick={() => { adopt(data.results[0]); onAdopt("radar"); }}>
                采用最优并去雷达筛选 <ArrowRight size={12} style={{ verticalAlign: -2 }} />
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
