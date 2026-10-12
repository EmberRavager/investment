"""规则选股雷达：全市场快照粗筛 + 规则精算。

流程（两级漏斗，与旧 ML 版 screen 保持一致的结构，但精算用确定性规则）：
1) 粗筛：拉全市场快照，剔除 ST/退市/涨跌停/低流动性，按成交额取最活跃 top_n；
2) 精算：对候选逐只加载历史行情，用 StrategySpec 的规则评估最新一根 K 线的信号，
   输出每只股票的「触发条件 / 不满足原因 / 目标仓位 / 信号」。

网络不可用或未提供快照时，自动回退到内置股票池，保证接口始终可用。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .config import DataConfig
from .cross_section import DEFAULT_UNIVERSE
from .data import infer_kind, load_code_name_map, load_etf_snapshot, load_market_snapshot, load_prices
from .engine import rules as trading_rules
from .strategy import StrategySpec, explain_last

#: ETF 快照不可用时的兜底池
_DEFAULT_ETFS = [
    ("510300", "沪深300ETF"), ("510500", "中证500ETF"), ("159915", "创业板ETF"),
    ("588000", "科创50ETF"), ("512880", "证券ETF"), ("512480", "半导体ETF"),
    ("515000", "科技ETF"), ("159949", "创业板50ETF"),
]


def _emit(progress, stage: str, pct: float, detail: str = ""):
    if progress:
        progress({"stage": stage, "pct": round(pct, 1), "detail": detail})


def _coarse(snapshot: pd.DataFrame, top_n: int, min_amount: float, max_pct: float):
    snap = snapshot.rename(
        columns={"代码": "symbol", "名称": "name", "成交额": "amount", "涨跌幅": "pct_chg"}
    ).copy()
    snap["amount"] = pd.to_numeric(snap.get("amount"), errors="coerce")
    snap["pct_chg"] = pd.to_numeric(snap.get("pct_chg"), errors="coerce")
    snap = snap.dropna(subset=["symbol", "name"])
    snap = snap[~snap["name"].astype(str).str.contains("ST|退", regex=True, na=False)]
    snap = snap[snap["pct_chg"].abs() < max_pct]
    snap = snap[snap["amount"] >= min_amount]
    snap = snap.sort_values("amount", ascending=False).head(top_n)
    items = []
    for r in snap.itertuples():
        s = "".join(ch for ch in str(r.symbol) if ch.isdigit())
        if not s:
            continue
        items.append({"symbol": s.zfill(6), "name": str(r.name)})
    return items


def _feasibility(spec: StrategySpec, price: float, cash: float, sym: str) -> Dict[str, Any]:
    if price is None or price <= 0:
        return {"can_buy": False, "reason": "无有效价格"}
    lot = trading_rules.lot_size(sym)
    one_lot_cost = price * lot
    if cash <= 0:
        return {"can_buy": None, "reason": "未提供本金", "one_lot_cost": round(one_lot_cost, 1)}
    cap_value = spec.weight * cash
    if cap_value < one_lot_cost - 1e-9:
        return {
            "can_buy": False,
            "reason": f"超出单股仓位限制：单股上限 {cap_value:.0f} 元 < 一手约 {one_lot_cost:.0f} 元",
            "cap_value": round(cap_value, 1), "one_lot_cost": round(one_lot_cost, 1), "qty": 0,
        }
    qty = trading_rules.round_lot(cap_value / price, sym)
    if qty <= 0:
        return {
            "can_buy": False, "reason": "不足一手",
            "cap_value": round(cap_value, 1), "one_lot_cost": round(one_lot_cost, 1), "qty": 0,
        }
    return {
        "can_buy": True, "reason": "",
        "cap_value": round(cap_value, 1), "one_lot_cost": round(one_lot_cost, 1), "qty": qty,
    }


def _vol_risk(df: pd.DataFrame) -> str:
    ret = df["close"].pct_change().tail(60)
    vol = float(ret.std() * np.sqrt(252)) if len(ret) > 5 else float("nan")
    if not np.isfinite(vol):
        return "中"
    return "低" if vol < 0.25 else ("高" if vol > 0.45 else "中")


def screen_rules(
    spec: StrategySpec,
    top_n: int = 20,
    min_amount: float = 1e8,
    max_pct: float = 9.5,
    symbols: Optional[List[str]] = None,
    snapshot: Optional[pd.DataFrame] = None,
    universe: str = "stock",          # stock | etf
    start: str = "2018-01-01",
    end: str = "",
    cash: float = 0.0,
    strategy_version: Optional[int] = None,
    progress=None,
) -> Dict[str, Any]:
    import datetime

    end = end or datetime.date.today().isoformat()

    universe_size: Optional[int] = None
    source = "fallback"
    items: List[Dict[str, str]] = []

    if symbols:
        items = [{"symbol": s, "name": s} for s in symbols]
        source = "custom"
        universe_size = len(items)
    else:
        snap = snapshot
        if snap is None:
            try:
                _emit(progress, "拉取" + ("ETF" if universe == "etf" else "全市场") + "快照", 5)
                snap = load_etf_snapshot(verbose=False) if universe == "etf" else load_market_snapshot(verbose=False)
            except Exception:  # noqa: BLE001 — 网络不可用时回退
                snap = None
        if snap is not None and len(snap) > 0:
            _emit(progress, "粗筛候选", 20)
            universe_size = int(len(snap))
            items = _coarse(snap, top_n, min_amount, max_pct)
            source = "etf" if universe == "etf" else "snapshot"
        if not items:
            source = "fallback"
            pool = _DEFAULT_ETFS if universe == "etf" else DEFAULT_UNIVERSE
            items = [{"symbol": s, "name": n} for s, n in pool[:top_n]]

    total = max(1, len(items))
    if any(it.get("name") in ("", None, it["symbol"]) for it in items):
        try:
            nm = load_code_name_map(verbose=False)
            for it in items:
                it["name"] = nm.get(it["symbol"], it.get("name") or it["symbol"])
        except Exception:  # noqa: BLE001
            pass

    candidates: List[Dict[str, Any]] = []
    for i, it in enumerate(items):
        sym = it["symbol"]
        _emit(progress, "规则精算", 25 + 70 * (i / total), sym)
        try:
            df = load_prices(
                DataConfig(symbol=sym, kind=infer_kind(sym), start=start, end=end, adjust="qfq"),
                verbose=False,
            )
        except Exception:  # noqa: BLE001
            continue
        info = explain_last(df, spec)
        target, prev = info["target"], info["prev"]
        if target > 0 and prev <= 0:
            state = "触发买入"
        elif target > 0:
            state = "持有"
        elif prev > 0:
            state = "触发卖出"
        else:
            state = "观望"

        conds = info.get("conditions", [])
        filter_hits = [c for c in conds if c["group"] == "filter"]
        entry_hits = [c for c in conds if c["group"] == "entry"]
        blockers = [c for c in conds if c["group"] in ("filter", "entry") and not c["ok"]]
        passed_cnt = sum(1 for c in conds if c["group"] in ("filter", "entry") and c["ok"])
        total_cnt = max(1, passed_cnt + len(blockers))
        score = round(passed_cnt / total_cnt, 3)

        price = info["price"]
        feasible = _feasibility(spec, price, cash, sym)

        candidates.append({
            "symbol": sym,
            "name": it.get("name", sym),
            "as_of": str(info["date"])[:10],
            "price": round(price, 3),
            "change_pct": round(info["change_pct"] * 100, 2),
            "above_ma20": info["above_ma20"],
            "vol_ratio": round(info["vol_ratio"], 2) if info["vol_ratio"] is not None else None,
            "ret20": round(info["ret20"] * 100, 2) if info["ret20"] is not None else None,
            "turnover": round((info["turnover"] or 0) / 1e8, 2),
            "target_weight": target,
            "state": state,
            "score": score,
            "risk": _vol_risk(df),
            "strategy_version": strategy_version,
            "filter_hits": filter_hits,
            "entry_hits": entry_hits,
            "failed": [{"text": c["text"], "left": c["left"], "right": c["right"]} for c in blockers],
            "values": info.get("values", {}),
            "feasible": feasible,
            "triggers": info["passed"],
            "blockedBy": "；".join(c["text"] for c in blockers),
        })

    candidates.sort(
        key=lambda c: (c["target_weight"] > 0, c["score"], c["vol_ratio"] or 0), reverse=True
    )
    _emit(progress, "完成", 100)
    return {
        "universe_size": universe_size,
        "shortlist_size": len(candidates),
        "source": source,
        "filters": {"top_n": top_n, "min_amount": min_amount, "max_pct": max_pct},
        "candidates": candidates,
    }
