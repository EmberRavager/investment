import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CandlestickChart, ChevronRight, BarChart3 } from "lucide-react";
import { api, downsample } from "./api";
import type { Health, RunResult } from "./types";
import Onboarding from "./components/Onboarding";
import Chooser from "./components/Chooser";
import Screener from "./components/Screener";
import BigVerdict from "./components/BigVerdict";
import MarketBoard from "./components/MarketBoard";
import Kpis from "./components/Kpis";
import NavChart from "./components/NavChart";
import ProbChart from "./components/ProbChart";
import FeatureImportance from "./components/FeatureImportance";
import MetricsTable from "./components/MetricsTable";
import ReflectionPanel from "./components/ReflectionPanel";
import Glossary from "./components/Glossary";
import Progress from "./components/Progress";
import TrackRecord from "./components/TrackRecord";

function setByPath(obj: any, path: string, value: any) {
  const keys = path.split(".");
  let cur = obj;
  for (let i = 0; i < keys.length - 1; i++) cur = cur[keys[i]];
  cur[keys[keys.length - 1]] = value;
}

export default function App() {
  const [config, setConfig] = useState<any>(null);
  const [models, setModels] = useState<string[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showIntro, setShowIntro] = useState(() => !localStorage.getItem("intro_done"));
  const [progress, setProgress] = useState<{ stage: string; pct: number } | null>(null);
  const resultRef = useRef<HTMLDivElement | null>(null);
  const configRef = useRef<any>(null);
  useEffect(() => {
    configRef.current = config;
  }, [config]);

  useEffect(() => {
    (async () => {
      try {
        const [h, m, cfg] = await Promise.all([api.health(), api.models(), api.defaultConfig()]);
        setHealth(h);
        setModels(m.models);
        setConfig(cfg);
      } catch (e: any) {
        setError(
          `没连上后台。请先在 investment 目录运行：\n  .venv/bin/uvicorn server.app:app --port 8000\n\n原因：${e.message}`
        );
      }
    })();
  }, []);

  const update = useCallback((path: string, value: any) => {
    setConfig((c: any) => {
      const n = structuredClone(c);
      setByPath(n, path, value);
      return n;
    });
  }, []);

  const updateMany = useCallback((patch: Record<string, any>) => {
    setConfig((c: any) => {
      const n = structuredClone(c);
      for (const [k, v] of Object.entries(patch)) setByPath(n, k, v);
      return n;
    });
  }, []);

  const run = useCallback(async (override?: any) => {
    const cfg = override ?? configRef.current;
    if (!cfg) return;
    setLoading(true);
    setError(null);
    setProgress({ stage: "准备中", pct: 0 });
    let result: any = null;
    let err: string | null = null;
    try {
      await api.runStream(cfg, (ev: any) => {
        if (ev.progress) setProgress(ev.progress);
        else if (ev.done) result = ev.result;
        else if (ev.error) err = ev.error;
      });
      if (err) throw new Error(err);
      setResult(result);
      setTimeout(
        () => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
        80
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
      setProgress(null);
    }
  }, []);

  // 从选股榜点某只股票，看它的详情
  const pickAndRun = useCallback(
    (symbol: string, kind: string) => {
      const n = structuredClone(configRef.current);
      setByPath(n, "data.symbol", symbol);
      setByPath(n, "data.kind", kind);
      setConfig(n);
      run(n);
    },
    [run]
  );

  const chartData = useMemo(() => (result ? downsample(result.series) : []), [result]);

  const closeIntro = () => {
    localStorage.setItem("intro_done", "1");
    setShowIntro(false);
  };

  return (
    <>
      <div className="topbar">
        <div className="brand">
          <div className="logo">
            <CandlestickChart size={22} />
          </div>
          <div className="txt">
            <h1>A 股智能助手</h1>
            <p>选只股票，看看现在该不该买</p>
          </div>
        </div>
        <div className="statusbar">
          <span className="item">
            <span className={`dot ${health ? "ok" : "bad"}`} />
            {health ? "引擎正常" : "未连接"}
          </span>
          <span className="item">
            <span className={`dot ${health?.deepseek_configured ? "ok" : "bad"}`} />
            AI 点评{health?.deepseek_configured ? "已开" : "未开"}
          </span>
        </div>
      </div>

      <div className="wrap">
        {error && <div className="error">{error}</div>}

        {loading && progress && <Progress stage={progress.stage} pct={progress.pct} />}

        {showIntro && <Onboarding onClose={closeIntro} />}

        {config ? (
          <>
            <Chooser
              config={config}
              models={models}
              update={update}
              updateMany={updateMany}
              onRun={() => run()}
              loading={loading}
            />
            <Screener config={config} onPick={pickAndRun} />
            <Glossary />
          </>
        ) : (
          !error && <div className="hint">正在加载…</div>
        )}

        <div ref={resultRef}>
          {result && (
            <>
              <BigVerdict summary={result.summary} />

              <details className="panel">
                <summary>
                  <ChevronRight size={16} className="chev" />
                  <BarChart3 size={17} />
                  看看详细数据
                  <span className="s">懂行的可以展开</span>
                </summary>
                <div className="inner">
                  <Kpis summary={result.summary} />
                  <div className="section-title">资金曲线：这套方法 vs 一直拿着</div>
                  <div className="caption">红线＝这套方法的结果，蓝线＝一直拿着不动。线越高代表钱越多。</div>
                  <NavChart data={chartData} />
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, marginTop: 20 }}>
                    <div>
                      <div className="section-title">每天的看涨把握</div>
                      <div className="caption">
                        绿线＝模型每天认为会涨的把握；超过橙色虚线（门槛）时才会考虑买入。
                      </div>
                      <ProbChart
                        data={chartData}
                        threshold={result.summary.config.backtest.prob_threshold}
                      />
                    </div>
                    <div>
                      <div className="section-title">模型最看重哪些指标</div>
                      <div className="caption">模型做判断时最依赖哪些数据，越长的越重要。</div>
                      <FeatureImportance data={result.summary.feature_importance} />
                    </div>
                  </div>
                  <div className="section-title" style={{ marginTop: 22 }}>
                    数字对比
                  </div>
                  <MetricsTable metrics={result.summary.metrics} />
                </div>
              </details>

              <TrackRecord summary={result.summary} />
              <ReflectionPanel summary={result.summary} health={health} />
            </>
          )}
        </div>

        <MarketBoard />
      </div>
    </>
  );
}
