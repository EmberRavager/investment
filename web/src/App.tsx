import { useCallback, useEffect, useMemo, useState } from "react";
import { api, downsample } from "./api";
import type { Health, RunResult } from "./types";
import ControlPanel from "./components/ControlPanel";
import MarketBoard from "./components/MarketBoard";
import Kpis from "./components/Kpis";
import NavChart from "./components/NavChart";
import ProbChart from "./components/ProbChart";
import FeatureImportance from "./components/FeatureImportance";
import MetricsTable from "./components/MetricsTable";
import ReflectionPanel from "./components/ReflectionPanel";

export default function App() {
  const [config, setConfig] = useState<any>(null);
  const [models, setModels] = useState<string[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [h, m, cfg] = await Promise.all([
          api.health(),
          api.models(),
          api.defaultConfig(),
        ]);
        setHealth(h);
        setModels(m.models);
        setConfig(cfg);
      } catch (e: any) {
        setError(`无法连接后端 API：${e.message}\n请先在 investment 目录运行：\n  .venv/bin/uvicorn server.app:app --port 8000`);
      }
    })();
  }, []);

  const update = useCallback((path: string, value: any) => {
    setConfig((c: any) => {
      const n = structuredClone(c);
      const keys = path.split(".");
      let cur = n;
      for (let i = 0; i < keys.length - 1; i++) cur = cur[keys[i]];
      cur[keys[keys.length - 1]] = value;
      return n;
    });
  }, []);

  const run = useCallback(async () => {
    if (!config) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.run(config);
      setResult(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [config]);

  const chartData = useMemo(
    () => (result ? downsample(result.series) : []),
    [result]
  );

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <h1>A 股量化预测终端</h1>
          <span className="tag">v0.1</span>
        </div>
        {config ? (
          <ControlPanel
            config={config}
            models={models}
            update={update}
            onRun={run}
            loading={loading}
          />
        ) : (
          <div className="hint">加载配置中…</div>
        )}
      </aside>

      <main className="main">
        <div className="status-bar">
          <span>
            <span className={`dot ${health ? "ok" : "bad"}`} />
            引擎 {health ? "在线" : "离线"}
          </span>
          <span>
            <span className={`dot ${health?.deepseek_configured ? "ok" : "bad"}`} />
            反思模型 {health?.deepseek_configured ? "已配置" : "未配置 DEEPSEEK_API_KEY"}
          </span>
          {loading && (
            <span>
              <span className="dot busy" />
              回测运行中…
            </span>
          )}
          {result && (
            <span>
              样本 {result.summary.metrics.classification.n_samples} · 特征{" "}
              {result.summary.n_features}
            </span>
          )}
        </div>

        {error && <div className="error">{error}</div>}

        <MarketBoard />

        {!result ? (
          <div className="empty">
            <div style={{ fontSize: 40 }}>◧</div>
            <div>在左侧配置标的与模型，然后点击「运行回测」</div>
          </div>
        ) : (
          <>
            <Kpis summary={result.summary} />
            <div className="card">
              <div className="head">
                <span className="t">净值曲线 · 策略 vs 买入持有</span>
                <span className="s">
                  {result.summary.symbol} · {result.summary.model}
                </span>
              </div>
              <NavChart data={chartData} />
            </div>
            <div className="grid-2">
              <div className="card">
                <div className="head">
                  <span className="t">预测概率</span>
                  <span className="s">
                    阈值 {result.summary.config.backtest.prob_threshold}
                  </span>
                </div>
                <ProbChart
                  data={chartData}
                  threshold={result.summary.config.backtest.prob_threshold}
                />
              </div>
              <div className="card">
                <div className="head">
                  <span className="t">特征重要性 Top20</span>
                </div>
                <FeatureImportance data={result.summary.feature_importance} />
              </div>
            </div>
            <div className="card">
              <div className="head">
                <span className="t">绩效对比</span>
                <span className="s">红=优 · 风险调整后收益优先</span>
              </div>
              <MetricsTable metrics={result.summary.metrics} />
            </div>
            <ReflectionPanel summary={result.summary} health={health} />
          </>
        )}
      </main>
    </div>
  );
}
