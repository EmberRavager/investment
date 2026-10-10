import { useEffect, useState } from "react";

interface Props {
  config: any;
  models: string[];
  update: (path: string, value: any) => void;
  onRun: () => void;
  loading: boolean;
}

function NumberField({
  label,
  value,
  step = 1,
  onChange,
}: {
  label: string;
  value: number;
  step?: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      <input
        type="number"
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
      />
    </div>
  );
}

function ParamsEditor({
  params,
  onChange,
}: {
  params: Record<string, any>;
  onChange: (p: Record<string, any>) => void;
}) {
  const [text, setText] = useState(JSON.stringify(params ?? {}, null, 2));
  const [bad, setBad] = useState(false);

  useEffect(() => {
    setText(JSON.stringify(params ?? {}, null, 2));
  }, [params]);

  return (
    <div className="field">
      <label>
        模型参数 (JSON)
        {bad && <span className="val" style={{ color: "#ff4d4f" }}>解析失败</span>}
      </label>
      <textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          try {
            const parsed = JSON.parse(e.target.value || "{}");
            setBad(false);
            onChange(parsed);
          } catch {
            setBad(true);
          }
        }}
        style={{
          width: "100%",
          minHeight: 96,
          fontFamily: "var(--mono)",
          fontSize: 11.5,
          background: "var(--bg-2)",
          color: "var(--text)",
          border: `1px solid ${bad ? "#ff4d4f" : "var(--border)"}`,
          borderRadius: 5,
          padding: 8,
          resize: "vertical",
        }}
      />
    </div>
  );
}

export default function ControlPanel({ config, models, update, onRun, loading }: Props) {
  const bt = config.backtest;
  return (
    <>
      <div className="section">
        <div className="title">标的</div>
        <div className="row2">
          <div className="field">
            <label>代码</label>
            <input value={config.data.symbol} onChange={(e) => update("data.symbol", e.target.value)} />
          </div>
          <div className="field">
            <label>类型</label>
            <select value={config.data.kind} onChange={(e) => update("data.kind", e.target.value)}>
              <option value="stock">个股</option>
              <option value="index">指数</option>
            </select>
          </div>
        </div>
        <div className="row2">
          <div className="field">
            <label>开始</label>
            <input value={config.data.start} onChange={(e) => update("data.start", e.target.value)} />
          </div>
          <div className="field">
            <label>结束</label>
            <input value={config.data.end} onChange={(e) => update("data.end", e.target.value)} />
          </div>
        </div>
        <div className="field">
          <label>复权</label>
          <select value={config.data.adjust} onChange={(e) => update("data.adjust", e.target.value)}>
            <option value="qfq">前复权</option>
            <option value="hfq">后复权</option>
            <option value="">不复权</option>
          </select>
        </div>
      </div>

      <div className="section">
        <div className="title">数据源</div>
        <div className="field">
          <label>Provider</label>
          <select
            value={config.data.provider}
            onChange={(e) => update("data.provider", e.target.value)}
          >
            <option value="akshare">akshare（默认，直连）</option>
            <option value="mcp">MCP（akshare-one-mcp）</option>
          </select>
        </div>
        {config.data.provider === "mcp" && (
          <div className="field">
            <label>MCP 端点</label>
            <input
              value={config.data.mcp_url}
              onChange={(e) => update("data.mcp_url", e.target.value)}
            />
            <div className="hint">
              需先运行：<code>uvx akshare-one-mcp --streamable-http --port 8081</code>
            </div>
          </div>
        )}
      </div>

      <div className="section">
        <div className="title">模型</div>
        <div className="field">
          <label>算法</label>
          <select value={config.model.name} onChange={(e) => update("model.name", e.target.value)}>
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <div className="toggle" style={{ marginBottom: 10 }}>
          <input
            type="checkbox"
            checked={config.model.scale}
            onChange={(e) => update("model.scale", e.target.checked)}
          />
          特征标准化 (线性/距离类模型建议开启)
        </div>
        <ParamsEditor
          key={config.model.name}
          params={config.model.params}
          onChange={(p) => update("model.params", p)}
        />
      </div>

      <div className="section">
        <div className="title">预测</div>
        <div className="row2">
          <NumberField
            label="预测跨度(天)"
            value={config.labels.horizon}
            onChange={(v) => update("labels.horizon", v)}
          />
          <NumberField
            label="上涨阈值"
            value={config.labels.threshold}
            step={0.005}
            onChange={(v) => update("labels.threshold", v)}
          />
        </div>
      </div>

      <div className="section">
        <div className="title">风控（稳定优先）</div>
        <div className="field">
          <label>
            开仓概率阈值
            <span className="val">{bt.prob_threshold}</span>
          </label>
          <input
            type="range"
            min={0}
            max={0.9}
            step={0.05}
            value={bt.prob_threshold}
            onChange={(e) => update("backtest.prob_threshold", parseFloat(e.target.value))}
            style={{ width: "100%" }}
          />
        </div>
        <div className="toggle" style={{ marginBottom: 10 }}>
          <input
            type="checkbox"
            checked={bt.trend_filter}
            onChange={(e) => update("backtest.trend_filter", e.target.checked)}
          />
          趋势过滤（仅上行趋势做多）
        </div>
        <div className="row2">
          <NumberField label="趋势均线" value={bt.trend_ma} onChange={(v) => update("backtest.trend_ma", v)} />
          <NumberField label="最少持有" value={bt.min_hold} onChange={(v) => update("backtest.min_hold", v)} />
        </div>
        <div className="row2">
          <NumberField
            label="目标波动率"
            value={bt.vol_target}
            step={0.01}
            onChange={(v) => update("backtest.vol_target", v)}
          />
          <NumberField
            label="回撤熔断"
            value={bt.drawdown_stop}
            step={0.01}
            onChange={(v) => update("backtest.drawdown_stop", v)}
          />
        </div>
      </div>

      <div className="section">
        <div className="title">训练 / 回测</div>
        <div className="row2">
          <NumberField label="训练窗口" value={bt.train_window} onChange={(v) => update("backtest.train_window", v)} />
          <NumberField label="最小训练" value={bt.min_train} onChange={(v) => update("backtest.min_train", v)} />
        </div>
        <NumberField
          label="重训频率(天)"
          value={bt.retrain_every}
          onChange={(v) => update("backtest.retrain_every", v)}
        />
      </div>

      <button className="primary" style={{ width: "100%", marginTop: 6 }} onClick={onRun} disabled={loading}>
        {loading ? "运行中…" : "运行回测"}
      </button>
    </>
  );
}
