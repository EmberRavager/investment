"""FastAPI 服务：把量化引擎暴露成 API，供前端调用。

启动：
    cd investment
    DEEPSEEK_API_KEY=sk-xxx .venv/bin/uvicorn server.app:app --reload --port 8000
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ashare_pred import cross_section  # noqa: E402
from ashare_pred.config import Config, DataConfig, apply_overrides  # noqa: E402
from ashare_pred.data import infer_kind, load_code_name_map, load_etf_snapshot, load_market_snapshot, load_prices  # noqa: E402
from ashare_pred.discovery import discover  # noqa: E402
from ashare_pred.metrics import round_trip_metrics, strategy_metrics  # noqa: E402
from ashare_pred.models import list_models  # noqa: E402
from ashare_pred.pipeline import analyze, compare, rank, run, screen  # noqa: E402
from ashare_pred.rotation import run_rotation  # noqa: E402
from ashare_pred.screener import screen_rules  # noqa: E402
from ashare_pred.store import Store  # noqa: E402
from ashare_pred.strategy import StrategySpec, describe_spec, explain_last, run_spec, uses_fundamentals, validate_spec  # noqa: E402
from ashare_pred.xsec import explain_narrative, run_xsec  # noqa: E402
from server.reflect import reflect, reflect_panel  # noqa: E402
from server.strategy_ai import nl_to_spec  # noqa: E402

CONFIG_PATH = os.getenv("ASHARE_CONFIG", str(PROJECT_ROOT / "configs" / "default.yaml"))

#: 选股榜默认股票池（可被请求覆盖）
DEFAULT_UNIVERSE = [
    {"name": "贵州茅台", "symbol": "600519", "kind": "stock"},
    {"name": "宁德时代", "symbol": "300750", "kind": "stock"},
    {"name": "比亚迪", "symbol": "002594", "kind": "stock"},
    {"name": "五粮液", "symbol": "000858", "kind": "stock"},
    {"name": "招商银行", "symbol": "600036", "kind": "stock"},
    {"name": "中国平安", "symbol": "601318", "kind": "stock"},
    {"name": "长江电力", "symbol": "600900", "kind": "stock"},
    {"name": "东方财富", "symbol": "300059", "kind": "stock"},
    {"name": "隆基绿能", "symbol": "601012", "kind": "stock"},
    {"name": "沪深300", "symbol": "000300", "kind": "index"},
]

app = FastAPI(title="A 股量化预测系统 API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None      # 完整配置（可选）
    overrides: Optional[Dict[str, Any]] = None   # 点路径覆盖，如 {"backtest.prob_threshold": 0.6}
    persist: bool = False                        # 是否落盘到 outputs


class ReflectRequest(BaseModel):
    summary: Dict[str, Any]
    question: Optional[str] = None
    mode: str = "single"   # single | panel


class RankRequest(BaseModel):
    symbols: Optional[List[Dict[str, Any]]] = None   # 自定义股票池
    config: Optional[Dict[str, Any]] = None
    overrides: Optional[Dict[str, Any]] = None


class ScreenRequest(BaseModel):
    top_n: int = 20
    min_amount: float = 1e8
    config: Optional[Dict[str, Any]] = None
    overrides: Optional[Dict[str, Any]] = None


class CompareRequest(BaseModel):
    models: Optional[List[str]] = None
    config: Optional[Dict[str, Any]] = None
    overrides: Optional[Dict[str, Any]] = None


class SelectRequest(BaseModel):
    symbols: Optional[List[str]] = None
    top_k: int = 5
    lookback: int = 60
    rebalance: int = 20
    config: Optional[Dict[str, Any]] = None
    overrides: Optional[Dict[str, Any]] = None


class StrategyParseRequest(BaseModel):
    text: str


class StrategyRunRequest(BaseModel):
    spec: Dict[str, Any]
    initial_cash: float = 3000.0
    start: str = "2018-01-01"
    end: str = ""
    strategy_id: Optional[int] = None
    persist: bool = True


class StrategyScreenRequest(BaseModel):
    spec: Dict[str, Any]
    top_n: int = 20
    min_amount: float = 1e8
    symbols: Optional[List[str]] = None
    universe: str = "stock"          # stock | etf
    start: str = "2018-01-01"
    end: str = ""
    cash: float = 0.0
    strategy_version: Optional[int] = None


class SignalsRequest(BaseModel):
    spec: Dict[str, Any]
    symbols: List[str]
    start: str = "2018-01-01"
    end: str = ""


class XsecRequest(BaseModel):
    symbols: Optional[List[str]] = None
    universe: str = "default"        # default | market | etf | index | custom(symbols)
    index: str = "000905"            # universe=index 时的指数（如 000300/000905/000852）
    include_delisted: bool = True    # index 池是否并入退市名单（缓解幸存者偏差）
    universe_size: int = 80
    min_amount: float = 1e8
    top_k: int = 10
    horizon: int = 5
    rebalance: int = 5
    train_window: int = 250
    retrain: int = 20
    initial_cash: float = 100000.0
    model: str = "lightgbm"
    target: str = "rank"
    neutralize_size: bool = True
    neutralize_industry: bool = True
    risk_aversion: float = 0.0        # 组合风险厌恶（对角风险模型）
    impact: float = 0.0               # 冲击成本系数
    stop_loss: float = 0.0
    drawdown_stop: float = 0.20
    start: str = "2018-01-01"
    end: str = ""


class RotationRequest(BaseModel):
    symbols: List[str]
    top_n: int = 5
    rebalance: int = 5
    lookback: int = 20
    initial_cash: float = 100000.0
    start: str = "2018-01-01"
    end: str = ""
    stop_loss: float = 0.0
    drawdown_stop: float = 0.15


class DiscoveryRequest(BaseModel):
    symbol: str
    initial_cash: float = 100000.0
    start: str = "2018-01-01"
    end: str = ""
    top_k: int = 8
    space: Optional[Dict[str, List[float]]] = None


class SaveStrategyRequest(BaseModel):
    spec: Dict[str, Any]
    name: Optional[str] = None
    description: str = ""
    source: str = "manual"


class PaperRecordRequest(BaseModel):
    as_of: str = ""
    picks: List[Dict[str, Any]] = []
    horizon: int = 5
    index_symbol: str = "000300"
    strategy_id: Optional[int] = None
    params: Optional[Dict[str, Any]] = None
    initial_cash: float = 0.0


class UpdateStrategyRequest(BaseModel):
    spec: Dict[str, Any]
    note: str = ""


_store: Optional[Store] = None


def get_store() -> Store:
    global _store
    if _store is None:
        db = os.getenv("QUANTPILOT_DB", str(PROJECT_ROOT / "data" / "quantpilot.db"))
        _store = Store(db)
    return _store


def _infer_kind(symbol: str) -> str:
    return infer_kind(symbol)


def _load_universe(symbols: List[str], start: str, end: str):
    prices: Dict[str, Any] = {}
    warnings: List[str] = []
    for sym in symbols:
        try:
            cfg = DataConfig(symbol=sym, kind=_infer_kind(sym), start=start, end=end, adjust="qfq")
            prices[sym] = load_prices(cfg, verbose=False)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{sym} 行情加载失败：{type(exc).__name__}: {str(exc)[:80]}")
    return prices, warnings


def _clean(obj: Any) -> Any:
    """把 NaN / Inf 转成 None，保证 JSON 合法。"""
    import math

    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    return obj


@app.get("/api/live/readiness")
def live_readiness_endpoint():
    from ashare_pred.engine import live_readiness
    return live_readiness()


@app.post("/api/paper/record")
def paper_record(req: PaperRecordRequest):
    try:
        from ashare_pred.paper import record_snapshot
        picks = req.picks or []
        if not picks:
            raise HTTPException(status_code=400, detail="picks 为空")
        as_of = req.as_of or datetime.date.today().isoformat()
        pid = record_snapshot(get_store(), as_of=as_of, picks=picks, horizon=req.horizon,
                              index_symbol=req.index_symbol, strategy_id=req.strategy_id,
                              params=req.params, initial_cash=req.initial_cash)
        return {"paper_id": pid}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/paper/resolve")
def paper_resolve():
    try:
        from ashare_pred.paper import resolve_pending
        return {"resolved": resolve_pending(get_store())}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.get("/api/paper")
def paper_list():
    return {"papers": get_store().list_papers()}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "deepseek_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
        "config": CONFIG_PATH,
    }


@app.get("/api/models")
def models():
    return {"models": list_models()}


@app.get("/api/default-config")
def default_config():
    return Config.load(CONFIG_PATH).to_dict()


def _build_config(req: RunRequest) -> Config:
    if req.config:
        cfg = Config.from_dict(req.config)
    else:
        cfg = Config.load(CONFIG_PATH)
    if req.overrides:
        # 切换模型但未显式给出参数时，清空上一个模型的遗留参数
        if "model.name" in req.overrides and "model.params" not in req.overrides:
            cfg.model.params = {}
        apply_overrides(cfg, req.overrides)
    return cfg


@app.post("/api/run")
def run_endpoint(req: RunRequest):
    try:
        cfg = _build_config(req)
        if req.persist:
            summary = run(cfg, verbose=True)
            return {"summary": summary}
        return analyze(cfg, verbose=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/screen")
def screen_endpoint(req: ScreenRequest):
    try:
        cfg = _build_config(RunRequest(config=req.config, overrides=req.overrides))
        return screen(cfg, top_n=req.top_n, min_amount=req.min_amount)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/rank")
def rank_endpoint(req: RankRequest):
    try:
        cfg = _build_config(RunRequest(config=req.config, overrides=req.overrides))
        items = req.symbols or DEFAULT_UNIVERSE
        return {"results": rank(cfg, items)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


def _stream(runner):
    """把 runner(progress) 放到线程里执行，以 NDJSON 流式返回进度与最终结果。"""
    q: "queue.Queue" = queue.Queue()

    def worker():
        try:
            result = runner(lambda ev: q.put({"progress": ev}))
            q.put({"done": True, "result": result})
        except Exception as exc:  # noqa: BLE001
            q.put({"error": f"{type(exc).__name__}: {exc}"})
        finally:
            q.put(None)

    def gen():
        threading.Thread(target=worker, daemon=True).start()
        while True:
            ev = q.get()
            if ev is None:
                break
            yield json.dumps(ev, ensure_ascii=False) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/api/run/stream")
def run_stream(req: RunRequest):
    try:
        cfg = _build_config(req)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")
    return _stream(lambda progress: analyze(cfg, verbose=True, progress=progress))


@app.post("/api/screen/stream")
def screen_stream(req: ScreenRequest):
    try:
        cfg = _build_config(RunRequest(config=req.config, overrides=req.overrides))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")
    return _stream(
        lambda progress: screen(cfg, top_n=req.top_n, min_amount=req.min_amount, progress=progress)
    )


@app.post("/api/compare/stream")
def compare_stream(req: CompareRequest):
    try:
        cfg = _build_config(RunRequest(config=req.config, overrides=req.overrides))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")
    return _stream(lambda progress: compare(cfg, models=req.models, progress=progress))


@app.post("/api/select/stream")
def select_stream(req: SelectRequest):
    try:
        cfg = _build_config(RunRequest(config=req.config, overrides=req.overrides))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")
    return _stream(
        lambda progress: cross_section.run(
            cfg, symbols=req.symbols, top_k=req.top_k,
            lookback=req.lookback, rebalance=req.rebalance, progress=progress,
        )
    )


@app.post("/api/reflect")
def reflect_endpoint(req: ReflectRequest):
    try:
        if req.mode == "panel":
            return {"panel": reflect_panel(req.summary, question=req.question)}
        text = reflect(req.summary, question=req.question)
        return {"reflection": text}
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


# ---------------- QuantPilot：策略规格 / 回测 / 持久化 ----------------

@app.post("/api/strategy/parse")
def strategy_parse(req: StrategyParseRequest):
    try:
        return nl_to_spec(req.text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/strategy/run")
def strategy_run(req: StrategyRunRequest):
    try:
        spec = StrategySpec.from_dict(req.spec)
        warnings = validate_spec(spec)
        start = req.start or Config.load(CONFIG_PATH).data.start
        end = req.end or datetime.date.today().isoformat()

        prices, load_warnings = _load_universe(spec.universe, start, end)
        warnings.extend(load_warnings)
        if not prices:
            raise HTTPException(status_code=400, detail="无法加载任何标的行情数据")

        try:
            name_map = load_code_name_map(verbose=False)
        except Exception:  # noqa: BLE001
            name_map = {}
        names = {sym: name_map.get(sym, sym) for sym in spec.universe}

        # 财务因子：使用则必须加载（按公告日对齐），失败直接拒绝，不静默忽略
        fundamentals_map = {}
        if uses_fundamentals(spec):
            try:
                from ashare_pred.fundamentals import load_fundamentals
                for sym in spec.universe:
                    if sym in prices:
                        fundamentals_map[sym] = load_fundamentals(sym, verbose=False)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=400,
                    detail=f"该策略使用财务因子，但财务数据不可用：{type(exc).__name__}: {str(exc)[:120]}",
                )

        # 版本号：新建=1，已有策略=当前版本
        version = 1
        if req.strategy_id is not None:
            existing = get_store().get_strategy(req.strategy_id)
            if existing:
                version = existing["current_version"]

        res = run_spec(prices, spec, initial_cash=req.initial_cash, names=names,
                       fundamentals_map=fundamentals_map, strategy_version=version)
        metrics = _clean(strategy_metrics(res.returns, res.exposure))

        # 样本内 / 样本外
        n = len(res.returns)
        k = int(n * 0.7)
        splits = {
            "in_sample": _clean(strategy_metrics(res.returns.iloc[:k], res.exposure.iloc[:k])),
            "out_sample": _clean(strategy_metrics(res.returns.iloc[k:], res.exposure.iloc[k:])),
            "split_date": res.equity.index[k].strftime("%Y-%m-%d") if 0 < k < n else "",
            "in_sample_end": res.equity.index[k - 1].strftime("%Y-%m-%d") if 0 < k <= n else "",
        }

        first = prices[spec.universe[0]] if spec.universe[0] in prices else next(iter(prices.values()))
        bench = first["close"].reindex(res.equity.index).ffill()
        bench_nav = (bench / bench.iloc[0]).fillna(1.0)

        series = {
            "dates": [d.strftime("%Y-%m-%d") for d in res.equity.index],
            "strategy_nav": [round(float(v), 4) for v in res.equity.values],
            "benchmark_nav": [round(float(v), 4) for v in bench_nav.values],
            "exposure": [round(float(v), 4) for v in res.exposure.values],
        }

        as_of = series["dates"][-1] if series["dates"] else ""
        last_snap = res.snapshots[-1] if res.snapshots else None

        today_orders = []
        for t in res.trades:
            if t.date.strftime("%Y-%m-%d") == as_of:
                d = t.as_dict()
                d["status"] = "已成交"
                today_orders.append(d)
        for s in res.skips:
            if str(s.get("date", ""))[:10] == as_of:
                today_orders.append({
                    "date": s.get("date", ""), "symbol": s.get("symbol", ""),
                    "name": s.get("name", ""), "side": "买入", "qty": 0,
                    "price": 0.0, "amount": 0.0, "status": "已拒绝", "reason": s.get("reason", ""),
                })

        signals = []
        for sym in spec.universe:
            if sym not in prices:
                continue
            info = explain_last(prices[sym], spec, fundamentals_map.get(sym))
            target, prev = info["target"], info["prev"]
            if target > 0 and prev <= 0:
                state = "触发买入"
            elif target > 0:
                state = "持有"
            elif prev > 0:
                state = "触发卖出"
            else:
                state = "观望"
            signals.append({
                "symbol": sym, "name": names.get(sym, sym), "state": state,
                "target_weight": target,
                "score": round(len(info["passed"]) / max(1, len(info["passed"]) + len(info["failed"])), 3),
                "reasons": info["passed"], "block": info["failed"],
            })

        run_id = None
        strategy_id = req.strategy_id
        if req.persist:
            try:
                store = get_store()
                if strategy_id is None:
                    strategy_id = store.create_strategy(
                        spec.name, spec.to_dict(),
                        description=describe_spec(spec), source="ai",
                    )
                    version = 1
                else:
                    existing = store.get_strategy(strategy_id)
                    version = existing["current_version"] if existing else 1
                run_id = store.create_run(
                    "backtest", strategy_id=strategy_id, version=version,
                    symbol=",".join(spec.universe), start=start, end=end,
                    initial_cash=req.initial_cash,
                )
                store.persist_engine_result(run_id, res)
                store.finish_run(run_id, metrics)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"结果落库失败：{type(exc).__name__}: {exc}")

        return {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "as_of": as_of,
            "initial_cash": req.initial_cash,
            "strategy_version": version,
            "splits": splits,
            "metrics": metrics,
            "series": series,
            "trades": [t.as_dict() for t in res.trades],
            "skips": res.skips[:200],
            "risk_events": res.risk_events,
            "spec": spec.to_dict(),
            "account": _clean(last_snap),
            "positions": _clean(last_snap["positions"] if last_snap else {}),
            "today_orders": _clean(today_orders),
            "signals": _clean(signals),
            "trade_stats": _clean(round_trip_metrics(res.trades, req.initial_cash)),
            "warnings": warnings,
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/strategy/signals")
def strategy_signals(req: SignalsRequest):
    try:
        spec = StrategySpec.from_dict(req.spec)
        validate_spec(spec)
        end = req.end or datetime.date.today().isoformat()
        prices, warnings = _load_universe(req.symbols, req.start, end)
        try:
            nm = load_code_name_map(verbose=False)
        except Exception:  # noqa: BLE001
            nm = {}
        out = []
        for sym in req.symbols:
            name = nm.get(sym, sym)
            if sym not in prices:
                out.append({"symbol": sym, "name": name, "state": "无数据",
                            "target_weight": 0.0, "price": None, "reasons": [], "block": []})
                continue
            try:
                info = explain_last(prices[sym], spec)
            except Exception as exc:  # noqa: BLE001 — 如缺失财务数据
                out.append({"symbol": sym, "name": name, "state": "—", "target_weight": 0.0,
                            "price": None, "reasons": [], "block": [str(exc)[:100]]})
                continue
            target, prev = info["target"], info["prev"]
            if target > 0 and prev <= 0:
                state = "触发买入"
            elif target > 0:
                state = "持有"
            elif prev > 0:
                state = "触发卖出"
            else:
                state = "观望"
            out.append({
                "symbol": sym, "name": name, "state": state,
                "target_weight": target, "price": info["price"],
                "change_pct": round(info["change_pct"] * 100, 2),
                "reasons": info["passed"], "block": info["failed"],
            })
        return _clean({"signals": out, "warnings": warnings})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/strategy/rotation")
def strategy_rotation(req: RotationRequest):
    try:
        end = req.end or datetime.date.today().isoformat()
        prices, warnings = _load_universe(req.symbols, req.start, end)
        if not prices:
            raise HTTPException(status_code=400, detail="无法加载行情数据")
        try:
            nm = load_code_name_map(verbose=False)
        except Exception:  # noqa: BLE001
            nm = {}
        names = {s: nm.get(s, s) for s in prices}

        res = run_rotation(
            prices, top_n=req.top_n, rebalance=req.rebalance, lookback=req.lookback,
            initial_cash=req.initial_cash, names=names,
            stop_loss=req.stop_loss, drawdown_stop=req.drawdown_stop,
        )
        metrics = _clean(strategy_metrics(res.returns, res.exposure))
        first = prices[req.symbols[0]] if req.symbols[0] in prices else next(iter(prices.values()))
        bench = first["close"].reindex(res.equity.index).ffill()
        bench_nav = (bench / bench.iloc[0]).fillna(1.0)
        series = {
            "dates": [d.strftime("%Y-%m-%d") for d in res.equity.index],
            "strategy_nav": [round(float(v), 4) for v in res.equity.values],
            "benchmark_nav": [round(float(v), 4) for v in bench_nav.values],
            "exposure": [round(float(v), 4) for v in res.exposure.values],
        }
        n = len(res.returns)
        k = int(n * 0.7)
        splits = {
            "in_sample": _clean(strategy_metrics(res.returns.iloc[:k], res.exposure.iloc[:k])),
            "out_sample": _clean(strategy_metrics(res.returns.iloc[k:], res.exposure.iloc[k:])),
            "split_date": res.equity.index[k].strftime("%Y-%m-%d") if 0 < k < n else "",
        }
        last = res.snapshots[-1] if res.snapshots else None
        return _clean({
            "params": {"top_n": req.top_n, "rebalance": req.rebalance, "lookback": req.lookback},
            "metrics": metrics,
            "series": series,
            "splits": splits,
            "trades": [t.as_dict() for t in res.trades],
            "skips": res.skips[:200],
            "account": last,
            "positions": last["positions"] if last else {},
            "trade_stats": round_trip_metrics(res.trades, req.initial_cash),
            "warnings": warnings,
        })
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


def _xsec_membership(req: "XsecRequest"):
    if req.universe != "index":
        return None
    try:
        from ashare_pred.xsec_data import membership_months
        return membership_months(req.index, req.start, req.end or datetime.date.today().isoformat())
    except Exception:  # noqa: BLE001
        return None


def _xsec_symbols(req: "XsecRequest") -> List[str]:
    """确定多因子选股的股票池。"""
    if req.symbols:
        return req.symbols
    if req.universe == "index":
        try:
            from ashare_pred.xsec_data import build_pit_universe
            syms = build_pit_universe(req.index, req.start,
                                      req.end or datetime.date.today().isoformat(),
                                      include_delisted=req.include_delisted)
            if syms:
                return syms
        except Exception:  # noqa: BLE001
            pass
    if req.universe in ("market", "etf"):
        try:
            from ashare_pred.screener import _coarse
            snap = load_etf_snapshot(verbose=False) if req.universe == "etf" else load_market_snapshot(verbose=False)
            items = _coarse(snap, top_n=req.universe_size, min_amount=req.min_amount, max_pct=9.5)
            syms = [it["symbol"] for it in items]
            if syms:
                return syms
        except Exception:  # noqa: BLE001
            pass
    return [d["symbol"] for d in DEFAULT_UNIVERSE]


def _xsec_payload(out, prices, initial_cash, warnings, req, names=None):
    import pandas as pd

    res = out["result"]
    res_free = out.get("result_free", res)
    names = names or {}
    metrics = _clean(strategy_metrics(res.returns, res.exposure))
    metrics_free = _clean(strategy_metrics(res_free.returns, res_free.exposure))

    # 指数基准（直接买指数）
    index_name = "沪深300"
    idx_nav = None
    index_metrics = {}
    try:
        from ashare_pred.config import DataConfig as _DC
        icfg = _DC(symbol="000300", kind="index", start=req.start,
                   end=req.end or datetime.date.today().isoformat(), adjust="qfq")
        idx = load_prices(icfg, verbose=False)
        idx_close = idx["close"].reindex(res.equity.index).ffill()
        idx_ret = idx_close.pct_change().fillna(0.0)
        index_metrics = _clean(strategy_metrics(idx_ret, pd.Series(1.0, index=idx_ret.index)))
        idx_nav = (idx_close / idx_close.iloc[0]).fillna(1.0)
    except Exception:  # noqa: BLE001
        index_name = "等权基准"

    # 等权基准
    closes = pd.DataFrame({s: prices[s]["close"] for s in prices}).reindex(res.equity.index).ffill()
    bench = (closes / closes.iloc[0]).mean(axis=1)

    excess = None
    if index_metrics.get("total_return") is not None and metrics.get("total_return") is not None:
        excess = round(float(metrics["total_return"] - index_metrics["total_return"]), 4)
    cost_drag = round(float((metrics_free.get("annual_return") or 0) - (metrics.get("annual_return") or 0)), 4)

    explanation = explain_narrative(
        ic=out["ic"], layered=out["layered"], verdict=out["verdict"],
        metrics=metrics, metrics_free=metrics_free, index_metrics=index_metrics,
        excess=excess, cost_drag=cost_drag, index_name=index_name,
    )

    series = {
        "dates": [d.strftime("%Y-%m-%d") for d in res.equity.index],
        "strategy_nav": [round(float(v), 4) for v in res.equity.values],
        "strategy_nav_nocost": [round(float(v), 4) for v in res_free.equity.values],
        "benchmark_nav": [round(float(v), 4) for v in bench.values],
        "index_nav": [round(float(v), 4) for v in idx_nav.values] if idx_nav is not None else [],
        "exposure": [round(float(v), 4) for v in res.exposure.values],
    }

    picks = []
    scores = out.get("scores")
    as_of = None
    if scores is not None and len(scores):
        last = scores["date"].max()
        as_of = str(pd.Timestamp(last))[:10]
        g = scores[scores["date"] == last].dropna(subset=["score"]).sort_values("score", ascending=False).head(req.top_k)
        total = int(len(g))
        for rank, (_, r) in enumerate(g.iterrows(), 1):
            sym = str(r["symbol"])
            picks.append({"rank": rank, "symbol": sym, "name": names.get(sym, sym),
                          "score": round(float(r["score"]), 4),
                          "percentile": round(1 - (rank - 1) / max(1, total), 3)})

    last_snap = res.snapshots[-1] if res.snapshots else None
    return _clean({
        "params": {"top_k": req.top_k, "horizon": req.horizon, "rebalance": req.rebalance,
                   "train_window": req.train_window, "retrain": req.retrain, "model": req.model,
                   "target": req.target, "universe": req.universe, "universe_size": req.universe_size,
                   "index_universe": req.index, "n_symbols": len(prices), "index": index_name},
        "picks": picks, "picks_as_of": as_of,
        "explanation": explanation,
        "verdict": out["verdict"],
        "metrics": metrics, "metrics_nocost": metrics_free, "index_metrics": index_metrics,
        "excess": excess, "cost_drag": cost_drag,
        "ic": out["ic"], "layered": out["layered"],
        "factor_cols": out["factor_cols"], "factor_importance": out.get("factor_importance", []),
        "oos_days": out["n_factor_days"],
        "series": series,
        "trades": [t.as_dict() for t in res.trades],
        "skips": res.skips[:200],
        "account": last_snap,
        "positions": last_snap["positions"] if last_snap else {},
        "trade_stats": round_trip_metrics(res.trades, initial_cash),
        "warnings": warnings,
    })


@app.post("/api/xsec/run")
def xsec_run(req: XsecRequest):
    try:
        symbols = _xsec_symbols(req)
        end = req.end or datetime.date.today().isoformat()
        prices, warnings = _load_universe(symbols, req.start, end)
        if len(prices) < 5:
            raise HTTPException(status_code=400, detail=f"有效标的不足（{len(prices)} 只，至少 5 只）")
        try:
            nm = load_code_name_map(verbose=False)
        except Exception:  # noqa: BLE001
            nm = {}
        names = {s: nm.get(s, s) for s in prices}
        out = run_xsec(prices, top_k=req.top_k, horizon=req.horizon, rebalance=req.rebalance,
                       train_window=req.train_window, retrain=req.retrain, model_name=req.model,
                       target=req.target, neutralize_size=req.neutralize_size,
                       neutralize_industry=req.neutralize_industry,
                       membership=_xsec_membership(req),
                       risk_aversion=req.risk_aversion, impact=req.impact,
                       initial_cash=req.initial_cash, names=names,
                       drawdown_stop=req.drawdown_stop)
        return _xsec_payload(out, prices, req.initial_cash, warnings, req, names)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/xsec/stream")
def xsec_stream(req: XsecRequest):
    def runner(progress):
        progress({"stage": "确定股票池", "pct": 2})
        symbols = _xsec_symbols(req)
        end = req.end or datetime.date.today().isoformat()
        progress({"stage": f"加载行情（{len(symbols)} 只）", "pct": 5})
        prices, warnings = _load_universe(symbols, req.start, end)
        if len(prices) < 5:
            raise RuntimeError(f"有效标的不足（{len(prices)} 只，至少 5 只）")
        try:
            nm = load_code_name_map(verbose=False)
        except Exception:  # noqa: BLE001
            nm = {}
        names = {s: nm.get(s, s) for s in prices}

        def p2(ev):
            progress({"stage": ev.get("stage", "训练中"), "pct": 15 + 0.85 * float(ev.get("pct", 0))})

        out = run_xsec(prices, top_k=req.top_k, horizon=req.horizon, rebalance=req.rebalance,
                       train_window=req.train_window, retrain=req.retrain, model_name=req.model,
                       target=req.target, neutralize_size=req.neutralize_size,
                       neutralize_industry=req.neutralize_industry,
                       membership=_xsec_membership(req),
                       risk_aversion=req.risk_aversion, impact=req.impact,
                       initial_cash=req.initial_cash, names=names,
                       drawdown_stop=req.drawdown_stop, progress=p2)
        return _xsec_payload(out, prices, req.initial_cash, warnings, req, names)

    return _stream(runner)


@app.post("/api/strategy/screen")
def strategy_screen(req: StrategyScreenRequest):
    try:
        spec = StrategySpec.from_dict(req.spec)
        warnings = validate_spec(spec)
        result = screen_rules(
            spec, top_n=req.top_n, min_amount=req.min_amount,
            symbols=req.symbols, universe=req.universe, start=req.start, end=req.end,
            cash=req.cash, strategy_version=req.strategy_version,
        )
        result["warnings"] = warnings
        return _clean(result)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/strategy/screen/stream")
def strategy_screen_stream(req: StrategyScreenRequest):
    try:
        spec = StrategySpec.from_dict(req.spec)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")
    return _stream(
        lambda progress: screen_rules(
            spec, top_n=req.top_n, min_amount=req.min_amount,
            symbols=req.symbols, universe=req.universe, start=req.start, end=req.end,
            cash=req.cash, strategy_version=req.strategy_version, progress=progress,
        )
    )


@app.get("/api/stock/names")
def stock_names(symbols: str = ""):
    """按代码查名称，返回 {symbol: name}。symbols 为逗号分隔。"""
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    if not syms:
        return {"names": {}}
    try:
        m = load_code_name_map(verbose=False)
    except Exception:  # noqa: BLE001
        m = {}
    return {"names": {s: m.get(s, s) for s in syms}}


@app.get("/api/stock/search")
def stock_search(q: str = "", limit: int = 20):
    """按代码前缀或名称关键字搜索全市场股票。"""
    qq = q.strip()
    if not qq:
        return {"results": []}
    try:
        m = load_code_name_map(verbose=False)
    except Exception:  # noqa: BLE001
        m = {}
    matches = [(code, name) for code, name in m.items() if code.startswith(qq) or qq in name]
    matches.sort(key=lambda x: (0 if x[0].startswith(qq) else 1, x[0]))
    return {"results": [{"symbol": c, "name": n} for c, n in matches[: max(1, limit)]]}


@app.get("/api/strategies")
def list_strategies_endpoint():
    store = get_store()
    out = []
    for r in store.list_strategies():
        d = dict(r)
        if not d.get("description") or d["description"] in (d["name"], "—", "逆向发现"):
            full = store.get_strategy(r["id"])
            if full and full.get("config"):
                try:
                    d["description"] = describe_spec(StrategySpec.from_dict(full["config"]))
                except Exception:  # noqa: BLE001
                    pass
        out.append(d)
    return {"strategies": out}


@app.get("/api/presets")
def presets_endpoint():
    from ashare_pred.presets import PRESETS
    return {"presets": PRESETS}


@app.post("/api/strategies/seed")
def seed_presets_endpoint():
    from ashare_pred.presets import PRESETS
    return {"added": get_store().seed_presets(PRESETS)}


@app.post("/api/strategies/dedupe")
def dedupe_strategies_endpoint():
    return {"removed": get_store().dedupe_by_name()}


@app.delete("/api/strategies/{strategy_id}")
def delete_strategy_endpoint(strategy_id: int):
    get_store().delete_strategy(strategy_id)
    return {"ok": True}


@app.put("/api/strategies/{strategy_id}")
def update_strategy_endpoint(strategy_id: int, req: UpdateStrategyRequest):
    try:
        spec = StrategySpec.from_dict(req.spec)
        validate_spec(spec)
        version = get_store().add_version(strategy_id, spec.to_dict(), note=req.note or "更新")
        return {"version": version}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/strategies/delete")
def delete_many_strategies_endpoint(ids: List[int]):
    n = 0
    for sid in ids:
        get_store().delete_strategy(sid)
        n += 1
    return {"deleted": n}


@app.post("/api/strategies")
def save_strategy_endpoint(req: SaveStrategyRequest):
    try:
        spec = StrategySpec.from_dict(req.spec)
        validate_spec(spec)
        sid = get_store().create_strategy(
            req.name or spec.name, spec.to_dict(),
            description=req.description or describe_spec(spec), source=req.source,
        )
        return {"strategy_id": sid}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/strategy/discover")
def strategy_discover(req: DiscoveryRequest):
    try:
        end = req.end or datetime.date.today().isoformat()
        prices, warnings = _load_universe([req.symbol], req.start, end)
        if not prices:
            raise HTTPException(status_code=400, detail=f"无法加载 {req.symbol} 行情数据")
        try:
            nm = load_code_name_map(verbose=False)
        except Exception:  # noqa: BLE001
            nm = {}
        out = discover(req.symbol, prices, space=req.space,
                       initial_cash=req.initial_cash, top_k=req.top_k)
        out["name"] = nm.get(req.symbol, req.symbol)
        out["warnings"] = warnings
        return _clean(out)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/strategy/discover/stream")
def strategy_discover_stream(req: DiscoveryRequest):
    try:
        end = req.end or datetime.date.today().isoformat()
        prices, _w = _load_universe([req.symbol], req.start, end)
        if not prices:
            raise HTTPException(status_code=400, detail=f"无法加载 {req.symbol} 行情数据")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}")
    return _stream(
        lambda progress: discover(req.symbol, prices, space=req.space,
                                  initial_cash=req.initial_cash, top_k=req.top_k, progress=progress)
    )


@app.get("/api/strategies/{strategy_id}")
def get_strategy_endpoint(strategy_id: int):
    s = get_store().get_strategy(strategy_id)
    if s is None:
        raise HTTPException(status_code=404, detail="策略不存在")
    return {"strategy": s, "runs": get_store().list_runs(strategy_id)}


@app.get("/api/runs")
def list_runs_endpoint(strategy_id: Optional[int] = None):
    return {"runs": get_store().list_runs(strategy_id)}


@app.get("/api/runs/{run_id}")
def get_run_endpoint(run_id: int):
    detail = get_store().get_run_detail(run_id)
    if detail["run"] is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    return detail
