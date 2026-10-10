import { useEffect, useRef, useState } from "react";
import { StockSDK } from "stock-sdk";
import {
  ShieldCheck, Scale, Zap, Play, Loader2, Search, ChevronRight, SlidersHorizontal, Sparkles, HelpCircle, Check,
} from "lucide-react";
import { MODEL_INFO } from "../glossary";

interface Props {
  config: any;
  models: string[];
  update: (path: string, value: any) => void;
  updateMany: (patch: Record<string, any>) => void;
  onRun: () => void;
  loading: boolean;
}

const STYLES: Record<string, any> = {
  steady: {
    label: "稳一点", tag: "推荐",
    desc: "亏得少、波动小，赚得也稳当。适合怕亏、想拿得安心的人。",
    Icon: ShieldCheck,
    patch: {
      "backtest.trend_filter": true, "backtest.trend_ma": 200, "backtest.vol_target": 0.08,
      "backtest.min_hold": 20, "backtest.drawdown_stop": 0.12, "backtest.drawdown_cooldown": 20,
      "backtest.prob_threshold": 0.55,
    },
  },
  balanced: {
    label: "都行", tag: "",
    desc: "收益和风险都适中，不偏不倚。拿不准就选它。",
    Icon: Scale,
    patch: {
      "backtest.trend_filter": true, "backtest.trend_ma": 120, "backtest.vol_target": 0.12,
      "backtest.min_hold": 10, "backtest.drawdown_stop": 0.18, "backtest.drawdown_cooldown": 15,
      "backtest.prob_threshold": 0.5,
    },
  },
  bold: {
    label: "搏一搏", tag: "",
    desc: "想赚得多一点，但可能亏得也多。只适合能承受大起大落的人。",
    Icon: Zap,
    patch: {
      "backtest.trend_filter": false, "backtest.trend_ma": 60, "backtest.vol_target": 0.2,
      "backtest.min_hold": 3, "backtest.drawdown_stop": 0.3, "backtest.drawdown_cooldown": 10,
      "backtest.prob_threshold": 0.5,
    },
  },
};

const HOT = [
  { name: "贵州茅台", symbol: "600519", kind: "stock" },
  { name: "宁德时代", symbol: "300750", kind: "stock" },
  { name: "比亚迪", symbol: "002594", kind: "stock" },
  { name: "五粮液", symbol: "000858", kind: "stock" },
  { name: "沪深300", symbol: "000300", kind: "index" },
];

const MODEL_LABEL: Record<string, string> = {
  xgboost: "XGBoost（综合最好）",
  lightgbm: "LightGBM（快）",
  random_forest: "随机森林（稳）",
  gradient_boosting: "梯度提升树",
  hist_gradient_boosting: "直方图提升树",
  extra_trees: "极端随机树",
  logistic: "逻辑回归（最简单）",
  svm: "支持向量机",
  knn: "K 近邻",
  gaussian_nb: "朴素贝叶斯",
};

export default function Chooser({ config, models, update, updateMany, onRun, loading }: Props) {
  const sdkRef = useRef<StockSDK | null>(null);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [selName, setSelName] = useState("");
  const timer = useRef<any>(null);
  const skipSearch = useRef(false);
  const chosenSymbol = useRef(config.data.symbol);

  const activeStyle =
    (Object.entries(STYLES).find(
      ([, s]) => s.patch["backtest.drawdown_stop"] === config.backtest.drawdown_stop
    ) ?? ["balanced"])[0];

  // 外部（如选股榜）改了标的时，清空搜索框，避免显示不一致
  useEffect(() => {
    if (config.data.symbol !== chosenSymbol.current) {
      chosenSymbol.current = config.data.symbol;
      skipSearch.current = true;
      setQ("");
      setSelName("");
    }
  }, [config.data.symbol]);

  useEffect(() => {
    if (skipSearch.current) {
      skipSearch.current = false;
      return;
    }
    if (timer.current) clearTimeout(timer.current);
    if (q.trim().length < 1) {
      setHits([]);
      setOpen(false);
      return;
    }
    timer.current = setTimeout(async () => {
      try {
        if (!sdkRef.current) sdkRef.current = new StockSDK();
        const r: any[] = await sdkRef.current.search(q.trim());
        setHits((r || []).slice(0, 8));
        setOpen(true);
      } catch {
        setHits([]);
      }
    }, 250);
    return () => timer.current && clearTimeout(timer.current);
  }, [q]);

  const choose = (symbol: string, kind: string, name: string) => {
    chosenSymbol.current = symbol;
    updateMany({ "data.symbol": symbol, "data.kind": kind });
    setSelName(name);
    skipSearch.current = true;
    setQ(name);
    setHits([]);
    setOpen(false);
  };

  const pick = (h: any) => {
    const symbol = String(h.code).replace(/^(sh|sz|bj)/i, "");
    const kind = h.category === "index" ? "index" : "stock";
    choose(symbol, kind, h.name);
  };

  const displayName = selName && chosenSymbol.current === config.data.symbol ? selName : "";

  return (
    <>
      {/* 第 1 步：选股票 */}
      <div className="step-card">
        <div className="step-title">
          <span className="n">1</span>
          <h2>
            想看哪只股票？ <span className="sub">打名字或代码都行</span>
          </h2>
        </div>
        <div className="search-wrap">
          <div style={{ position: "relative" }}>
            <Search size={18} style={{ position: "absolute", left: 14, top: 15, color: "var(--text-3)" }} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onFocus={() => hits.length && setOpen(true)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && /^\d{6}$/.test(q.trim())) {
                  choose(q.trim(), config.data.kind, q.trim());
                }
              }}
              placeholder="例如：茅台、宁德时代、600519"
              style={{ paddingLeft: 42 }}
            />
          </div>
          {open && hits.length > 0 && (
            <div className="search-results">
              {hits.map((h) => (
                <div className="row" key={h.code} onClick={() => pick(h)}>
                  <span className="nm">{h.name}</span>
                  <span className="cd">{String(h.code).toUpperCase()}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="chips">
          <span className="lead">不知道选啥？试试：</span>
          {HOT.map((c) => (
            <button key={c.symbol} className="chip" onClick={() => choose(c.symbol, c.kind, c.name)}>
              {c.name}
            </button>
          ))}
        </div>

        <div className="selected-bar">
          <Check size={16} style={{ color: "var(--down)" }} />
          当前已选：
          <b>
            {displayName ? `${displayName}　${config.data.symbol}` : config.data.symbol}
          </b>
          <span className="muted">{config.data.kind === "index" ? "指数" : "个股"}</span>
        </div>
      </div>

      {/* 第 2 步：选风格 */}
      <div className="step-card">
        <div className="step-title">
          <span className="n">2</span>
          <h2>
            你想要哪种？ <span className="sub">决定了承受多大风险</span>
          </h2>
        </div>
        <div className="style-grid">
          {Object.entries(STYLES).map(([key, s]) => (
            <button
              key={key}
              className={`style-card ${activeStyle === key ? "on" : ""}`}
              onClick={() => updateMany(s.patch)}
            >
              <s.Icon className="icon" size={24} />
              <div className="ttl">
                {s.label}
                {s.tag && <span className="tag-rec good">{s.tag}</span>}
              </div>
              <div className="desc">{s.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* 第 3 步：开始 */}
      <div className="step-card">
        <div className="step-title">
          <span className="n">3</span>
          <h2>开始分析</h2>
        </div>
        <button className="bigbtn" onClick={onRun} disabled={loading}>
          {loading ? <Loader2 size={20} className="spin" /> : <Play size={20} />}
          {loading ? "正在分析，请稍等…" : "开始分析"}
        </button>

        <details className="panel" style={{ marginTop: 18, marginBottom: 0, boxShadow: "none" }}>
          <summary>
            <ChevronRight size={16} className="chev" />
            <SlidersHorizontal size={16} />
            想自己调？点这里（看不懂就别动）
          </summary>
          <div className="inner" style={{ paddingTop: 6 }}>
            <div className="field">
              <label>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                  <Sparkles size={14} /> 用哪种预测方法
                </span>
              </label>
              <select value={config.model.name} onChange={(e) => update("model.name", e.target.value)}>
                {models.map((m) => (
                  <option key={m} value={m}>
                    {MODEL_LABEL[m] ?? m}
                  </option>
                ))}
              </select>
            </div>

            {MODEL_INFO[config.model.name] && (
              <div className="infobox">
                <div style={{ fontWeight: 700, marginBottom: 5 }}>
                  {(MODEL_LABEL[config.model.name] ?? config.model.name).split("（")[0]} 是什么？
                </div>
                <div className="li"><b>做法：</b>{MODEL_INFO[config.model.name].what}</div>
                <div className="li"><b>优点：</b>{MODEL_INFO[config.model.name].good}</div>
                <div className="li"><b>缺点：</b>{MODEL_INFO[config.model.name].bad}</div>
                <div className="li"><b>何时用：</b>{MODEL_INFO[config.model.name].use}</div>
              </div>
            )}

            <details className="panel" style={{ marginTop: 16, marginBottom: 4, boxShadow: "none" }}>
              <summary style={{ fontSize: 14, padding: "10px 0" }}>
                <HelpCircle size={15} />
                10 个模型分别是什么？
              </summary>
              <div style={{ fontSize: 13.5, color: "var(--text-2)", lineHeight: 1.7 }}>
                {models.map((m) => (
                  <div key={m} style={{ marginBottom: 8 }}>
                    <b>{MODEL_LABEL[m] ?? m}</b> —— {MODEL_INFO[m]?.what ?? ""}
                  </div>
                ))}
              </div>
            </details>

            <div className="row2" style={{ marginTop: 12 }}>
              <div className="field">
                <label>开始日期</label>
                <input value={config.data.start} onChange={(e) => update("data.start", e.target.value)} />
              </div>
              <div className="field">
                <label>结束日期</label>
                <input value={config.data.end} onChange={(e) => update("data.end", e.target.value)} />
              </div>
            </div>

            <div className="field">
              <label>
                <span>出手门槛（越高越谨慎，出手越少）</span>
                <span>{config.backtest.prob_threshold}</span>
              </label>
              <input
                type="range"
                min={0}
                max={0.9}
                step={0.05}
                value={config.backtest.prob_threshold}
                onChange={(e) => update("backtest.prob_threshold", parseFloat(e.target.value))}
              />
            </div>

            <div className="field">
              <label>数据来源</label>
              <select value={config.data.provider} onChange={(e) => update("data.provider", e.target.value)}>
                <option value="akshare">普通（akshare，推荐）</option>
                <option value="mcp">MCP 服务</option>
              </select>
            </div>
            {config.data.provider === "mcp" && (
              <div className="field">
                <label>MCP 地址</label>
                <input value={config.data.mcp_url} onChange={(e) => update("data.mcp_url", e.target.value)} />
              </div>
            )}
          </div>
        </details>
      </div>
    </>
  );
}
