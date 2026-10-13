import { useCallback, useEffect, useMemo, useState } from "react";
import {
  LayoutDashboard, Radar as RadarIcon, FlaskConical, LineChart, Wallet, CandlestickChart, BarChart3, Compass, Boxes, BookOpen,
} from "lucide-react";
import { api } from "../api";
import type { Health } from "../types";
import { NAV } from "./data";
import { DEFAULT_CASH } from "./spec";
import { DEFAULT_FORM, formToSpec, type StrategyForm } from "./strategyForm";
import { useStrategyRun } from "./useStrategy";
import Overview from "./Overview";
import Radar from "./Radar";
import StockAnalysis from "./StockAnalysis";
import Discovery from "./Discovery";
import Xsec from "./Xsec";
import StrategyLab from "./StrategyLab";
import Backtest from "./Backtest";
import PaperTrading from "./PaperTrading";
import Guide from "./Guide";
import ResearchBanner from "./ResearchBanner";
import "./quantpilot.css";

const ICONS: Record<string, any> = {
  overview: LayoutDashboard,
  radar: RadarIcon,
  stock: BarChart3,
  discovery: Compass,
  xsec: Boxes,
  lab: FlaskConical,
  backtest: LineChart,
  paper: Wallet,
  guide: BookOpen,
};

const PAGE_KEYS = NAV.map((n) => n.key);

export interface Strat {
  form: StrategyForm;
  setForm: (f: StrategyForm) => void;
  cash: number;
  setCash: (c: number) => void;
  spec: any;
  result: any | null;
  loading: boolean;
  error: string | null;
  run: () => void;
}

/** 解析 #/page/param 形式的 URL。 */
function parseHash(): { page: string; param: string } {
  const raw = (typeof location !== "undefined" ? location.hash : "").replace(/^#\/?/, "");
  const [page, param = ""] = raw.split("/");
  return { page: PAGE_KEYS.includes(page) ? page : "overview", param: decodeURIComponent(param) };
}

function hashFor(page: string, param = ""): string {
  return `#/${page}${param ? "/" + encodeURIComponent(param) : ""}`;
}

export default function QuantPilotApp() {
  const [route, setRoute] = useState(parseHash);
  const [health, setHealth] = useState<Health | null>(null);
  const [form, setForm] = useState<StrategyForm>(DEFAULT_FORM);
  const [cash, setCash] = useState(DEFAULT_CASH);
  const [selected, setSelected] = useState<{ symbol: string; name: string } | null>(null);

  const page = route.page;
  const spec = useMemo(() => formToSpec(form), [form]);
  const stratRun = useStrategyRun();
  const started = useMemo(() => ({ done: false }), []);

  // 路由：同步 URL hash 与前进/后退
  useEffect(() => {
    if (!location.hash) location.replace(hashFor("overview"));
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = useCallback((key: string, param = "") => {
    const h = hashFor(key, param);
    if (location.hash === h) setRoute(parseHash());
    else location.hash = h; // 触发 hashchange -> setRoute
  }, []);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    if (started.done) return;
    started.done = true;
    stratRun.run(spec, cash);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 个股分析：从 URL 恢复选中的股票（刷新/分享都不丢）
  useEffect(() => {
    if (page !== "stock" || !route.param) return;
    if (selected?.symbol !== route.param) setSelected({ symbol: route.param, name: route.param });
    api.stockNames(route.param)
      .then((r) => setSelected({ symbol: route.param, name: r.names[route.param] || route.param }))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, route.param]);

  const strat: Strat = {
    form, setForm, cash, setCash, spec,
    result: stratRun.result, loading: stratRun.loading, error: stratRun.error,
    run: () => stratRun.run(spec, cash),
  };

  const current = NAV.find((n) => n.key === page)!;

  return (
    <div className="qp">
      <aside className="qp-side">
        <div className="qp-logo">
          <div className="mark"><CandlestickChart size={18} /></div>
          <div>
            <div className="name">QuantPilot</div>
            <div className="sub">AI 量化策略平台</div>
          </div>
        </div>

        <div className="qp-nav-label">工作台</div>
        <nav className="qp-nav">
          {NAV.map((n) => {
            const Icon = ICONS[n.key];
            return (
              <button key={n.key} className={page === n.key ? "on" : ""} onClick={() => go(n.key)}>
                <Icon size={16} className="ico" />
                <span className="lbl">{n.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="qp-side-foot">
          <div className="st"><span className={`dot ${health ? "ok" : "bad"}`} />引擎<span className="v">{health ? "正常" : "未连接"}</span></div>
          <div className="st"><span className={`dot ${health?.deepseek_configured ? "ok" : "bad"}`} />AI 解析<span className="v">{health?.deepseek_configured ? "已开" : "关键词"}</span></div>
        </div>
      </aside>

      <main className="qp-main">
        <header className="qp-top">
          <div className="ttl">
            <h1>{current.label}</h1>
            <p>{current.hint}</p>
          </div>
          <div className="right">
            <span className="item">当前策略：{spec.name}</span>
            <span className="item">本金 ¥{cash.toLocaleString()}</span>
          </div>
        </header>

        <div className="qp-body">
          <ResearchBanner />
          {page === "overview" && <Overview strat={strat} onGo={go} />}
          {page === "radar" && (
            <Radar
              strat={strat}
              onAnalyze={(symbol, name) => { setSelected({ symbol, name }); go("stock", symbol); }}
            />
          )}
          {page === "stock" && <StockAnalysis strat={strat} selected={selected} onPick={(s) => go("stock", s.symbol)} />}
          {page === "discovery" && <Discovery strat={strat} onAdopt={(k) => go(k)} />}
          {page === "xsec" && <Xsec strat={strat} />}
          {page === "lab" && <StrategyLab strat={strat} />}
          {page === "backtest" && <Backtest strat={strat} />}
          {page === "paper" && <PaperTrading strat={strat} />}
          {page === "guide" && <Guide />}

          <div className="notice" style={{ marginTop: 22 }}>
            全站共用同一套「策略 + 风控」；总览/回测/模拟交易基于真实历史行情与确定性规则引擎
            （含 T+1、涨跌停、整手、佣金/印花税/滑点）。历史回测不代表未来，不构成投资建议。
          </div>
        </div>
      </main>
    </div>
  );
}
