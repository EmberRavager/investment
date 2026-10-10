import { ShieldCheck, Scale, Zap, ChevronRight, Play, Sparkles, SlidersHorizontal, Loader2 } from "lucide-react";

interface Props {
  config: any;
  models: string[];
  update: (path: string, value: any) => void;
  updateMany: (patch: Record<string, any>) => void;
  onRun: () => void;
  loading: boolean;
}

const PRESETS: Record<string, any> = {
  steady: {
    label: "稳健",
    desc: "波动小、亏损少，收益也较平缓",
    Icon: ShieldCheck,
    patch: {
      "backtest.trend_filter": true,
      "backtest.trend_ma": 200,
      "backtest.vol_target": 0.08,
      "backtest.min_hold": 20,
      "backtest.drawdown_stop": 0.12,
      "backtest.drawdown_cooldown": 20,
      "backtest.prob_threshold": 0.55,
    },
  },
  balanced: {
    label: "均衡",
    desc: "收益和风险兼顾",
    Icon: Scale,
    patch: {
      "backtest.trend_filter": true,
      "backtest.trend_ma": 120,
      "backtest.vol_target": 0.12,
      "backtest.min_hold": 10,
      "backtest.drawdown_stop": 0.18,
      "backtest.drawdown_cooldown": 15,
      "backtest.prob_threshold": 0.5,
    },
  },
  bold: {
    label: "进取",
    desc: "追求更高收益，波动和亏损更大",
    Icon: Zap,
    patch: {
      "backtest.trend_filter": false,
      "backtest.trend_ma": 60,
      "backtest.vol_target": 0.2,
      "backtest.min_hold": 3,
      "backtest.drawdown_stop": 0.3,
      "backtest.drawdown_cooldown": 10,
      "backtest.prob_threshold": 0.5,
    },
  },
};

const MODEL_LABEL: Record<string, string> = {
  xgboost: "XGBoost · 综合推荐",
  lightgbm: "LightGBM · 快而稳",
  random_forest: "随机森林 · 不易过拟合",
  gradient_boosting: "梯度提升树",
  hist_gradient_boosting: "直方图提升树",
  extra_trees: "极端随机树",
  logistic: "逻辑回归 · 最简单可解释",
  svm: "支持向量机",
  knn: "K 近邻",
  gaussian_nb: "朴素贝叶斯",
};

const STOCK_CHIPS = [
  { name: "贵州茅台", symbol: "600519", kind: "stock" },
  { name: "沪深300", symbol: "000300", kind: "index" },
  { name: "宁德时代", symbol: "300750", kind: "stock" },
  { name: "比亚迪", symbol: "002594", kind: "stock" },
  { name: "五粮液", symbol: "000858", kind: "stock" },
];

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

export default function ControlPanel({ config, models, update, updateMany, onRun, loading }: Props) {
  const activePreset =
    (Object.entries(PRESETS).find(([, p]) => p.patch["backtest.drawdown_stop"] === config.backtest.drawdown_stop) ?? ["balanced"])[0];

  return (
    <>
      {/* ① 选股票 */}
      <div className="step">
        <div className="step-head">
          <span className="n">1</span> 想看哪只股票 / 指数？
        </div>
        <input
          value={config.data.symbol}
          onChange={(e) => update("data.symbol", e.target.value)}
          placeholder="输入 6 位代码，如 600519"
        />
        <div className="chips">
          {STOCK_CHIPS.map((c) => (
            <button
              key={c.symbol}
              className="chip"
              onClick={() =>
                updateMany({ "data.symbol": c.symbol, "data.kind": c.kind })
              }
            >
              {c.name}
            </button>
          ))}
        </div>
      </div>

      {/* ② 投资风格 */}
      <div className="step">
        <div className="step-head">
          <span className="n">2</span> 你偏好哪种风格？
        </div>
        <div className="presets">
          {Object.entries(PRESETS).map(([key, p]) => (
            <button
              key={key}
              className={`preset ${activePreset === key ? "on" : ""}`}
              onClick={() => updateMany(p.patch)}
            >
              <div className="ttl">
                <p.Icon size={15} /> {p.label}
                {key === "steady" && (
                  <span style={{ fontSize: 11, color: "var(--primary)", marginLeft: 2 }}>推荐</span>
                )}
              </div>
              <div className="desc">{p.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* ③ 模型 */}
      <div className="step">
        <div className="step-head">
          <span className="n">3</span> 用哪个预测模型？
          <Sparkles size={14} style={{ color: "var(--primary)" }} />
        </div>
        <select value={config.model.name} onChange={(e) => update("model.name", e.target.value)}>
          {models.map((m) => (
            <option key={m} value={m}>
              {MODEL_LABEL[m] ?? m}
            </option>
          ))}
        </select>
        <div className="hint">不确定就保持默认，先跑一次看看结果。</div>
      </div>

      <button className="primary" style={{ width: "100%", marginTop: 2 }} onClick={onRun} disabled={loading}>
        {loading ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
        {loading ? "正在分析…" : "开始分析"}
      </button>

      {/* 高级设置 */}
      <details className="advanced" style={{ marginTop: 20 }}>
        <summary>
          <ChevronRight size={15} className="chev" />
          <SlidersHorizontal size={15} />
          高级设置（不懂可以不用改）
        </summary>
        <div className="body">
          <div className="row2">
            <Field label="开始日期">
              <input value={config.data.start} onChange={(e) => update("data.start", e.target.value)} />
            </Field>
            <Field label="结束日期">
              <input value={config.data.end} onChange={(e) => update("data.end", e.target.value)} />
            </Field>
          </div>

          <Field label="价格处理">
            <select value={config.data.adjust} onChange={(e) => update("data.adjust", e.target.value)}>
              <option value="qfq">前复权（推荐，看走势）</option>
              <option value="hfq">后复权（算收益）</option>
              <option value="">不复权</option>
            </select>
          </Field>

          <Field label="数据来源" hint="MCP 需先运行 akshare-one-mcp 服务">
            <select
              value={config.data.provider}
              onChange={(e) => update("data.provider", e.target.value)}
            >
              <option value="akshare">akshare（直连，推荐）</option>
              <option value="mcp">MCP 服务</option>
            </select>
          </Field>
          {config.data.provider === "mcp" && (
            <Field label="MCP 地址">
              <input value={config.data.mcp_url} onChange={(e) => update("data.mcp_url", e.target.value)} />
            </Field>
          )}

          <div className="row2">
            <Field label="预测未来几天" hint="1=明天">
              <input
                type="number"
                value={config.labels.horizon}
                onChange={(e) => update("labels.horizon", parseInt(e.target.value || "1"))}
              />
            </Field>
            <Field label="涨多少算上涨">
              <input
                type="number"
                step={0.005}
                value={config.labels.threshold}
                onChange={(e) => update("labels.threshold", parseFloat(e.target.value || "0"))}
              />
            </Field>
          </div>

          <Field label="出手门槛" hint="越高越谨慎，出手越少">
            <input
              type="range"
              min={0}
              max={0.9}
              step={0.05}
              value={config.backtest.prob_threshold}
              onChange={(e) => update("backtest.prob_threshold", parseFloat(e.target.value))}
            />
            <div className="hint">当前：{config.backtest.prob_threshold}</div>
          </Field>

          <div className="switch">
            <input
              type="checkbox"
              checked={config.backtest.trend_filter}
              onChange={(e) => update("backtest.trend_filter", e.target.checked)}
            />
            只在上涨趋势时才买入
          </div>

          <div className="row2">
            <Field label="趋势判断天数">
              <input
                type="number"
                value={config.backtest.trend_ma}
                onChange={(e) => update("backtest.trend_ma", parseInt(e.target.value || "120"))}
              />
            </Field>
            <Field label="最短持有天数">
              <input
                type="number"
                value={config.backtest.min_hold}
                onChange={(e) => update("backtest.min_hold", parseInt(e.target.value || "10"))}
              />
            </Field>
          </div>

          <div className="row2">
            <Field label="仓位大小（控波动）" hint="越小越稳">
              <input
                type="number"
                step={0.01}
                value={config.backtest.vol_target}
                onChange={(e) => update("backtest.vol_target", parseFloat(e.target.value || "0.1"))}
              />
            </Field>
            <Field label="亏损保护线" hint="亏损超过就停手">
              <input
                type="number"
                step={0.01}
                value={config.backtest.drawdown_stop}
                onChange={(e) => update("backtest.drawdown_stop", parseFloat(e.target.value || "0.15"))}
              />
            </Field>
          </div>

          <div className="row2">
            <Field label="训练历史天数">
              <input
                type="number"
                value={config.backtest.train_window}
                onChange={(e) => update("backtest.train_window", parseInt(e.target.value || "500"))}
              />
            </Field>
            <Field label="重新学习频率（天）">
              <input
                type="number"
                value={config.backtest.retrain_every}
                onChange={(e) => update("backtest.retrain_every", parseInt(e.target.value || "20"))}
              />
            </Field>
          </div>
        </div>
      </details>
    </>
  );
}
