"""逆向策略发现：给定一只股票，反推出历史上表现稳健的策略规则。

与传统流程相反：
    传统：先定策略 -> 选股 -> 回测
    逆向：选定一只股票 -> 搜索规则空间 -> 得到在该股上稳健的策略 -> 再拿到雷达筛全市场

搜索空间（可配置）：均线快/慢、放量倍数、止损。
评价：在**样本外**（后 30%）上按夏普排序，并要求足够的成交笔数，尽量降低过拟合。
所有结果均由真实回测（事件驱动引擎）产生。
"""

from __future__ import annotations

from itertools import product
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .metrics import strategy_metrics
from .strategy import Condition, StrategySpec, run_spec

DEFAULT_SPACE: Dict[str, List[float]] = {
    "ma_fast": [5, 10, 20],
    "ma_slow": [20, 60, 120],
    "vol_ratio": [0.0, 1.2, 1.5],
    "stop_loss": [0.0, 0.05, 0.08],
}


def _build_spec(symbol: str, ma_fast: int, ma_slow: int, vol_ratio: float, stop_loss: float) -> StrategySpec:
    maF, maS = f"ma{ma_fast}", f"ma{ma_slow}"
    entry = [Condition("close", ">", maF)]
    if vol_ratio and vol_ratio > 0:
        entry.append(Condition("vol_ratio", ">", float(vol_ratio)))
    name = f"{symbol} ma{ma_fast}/{ma_slow}"
    if vol_ratio:
        name += f" 量比{vol_ratio}"
    if stop_loss:
        name += f" 止损{int(stop_loss * 100)}%"
    return StrategySpec(
        name=name,
        universe=[symbol],
        filters=[Condition(maF, ">", maS)],
        entry=entry,
        exit=[Condition("close", "<", maF)],
        weight=1.0,
        max_position_per_stock=1.0,
        max_total_exposure=1.0,
        stop_loss=stop_loss,
        drawdown_stop=0.20,
        drawdown_cooldown=10,
    )


def _split_metrics(res, frac: float = 0.7) -> Dict[str, Any]:
    n = len(res.returns)
    k = int(n * frac)
    ins = strategy_metrics(res.returns.iloc[:k], res.exposure.iloc[:k])
    oos = strategy_metrics(res.returns.iloc[k:], res.exposure.iloc[k:])
    return {"in_sample": _clean(ins), "out_sample": _clean(oos), "split_date": str(res.equity.index[k])[:10] if 0 < k < n else ""}


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (None if (isinstance(v, float) and not np.isfinite(v)) else v) for k, v in d.items()}


def discover(
    symbol: str,
    prices: Dict[str, pd.DataFrame],
    space: Optional[Dict[str, List[float]]] = None,
    initial_cash: float = 100000.0,
    top_k: int = 8,
    min_trades: int = 4,
    oos_frac: float = 0.3,
    progress=None,
) -> Dict[str, Any]:
    """在单只股票上搜索规则空间，按样本外夏普排序返回 TopK。"""
    space = {**DEFAULT_SPACE, **(space or {})}
    if symbol not in prices:
        raise ValueError(f"未提供 {symbol} 的行情数据")

    combos = [
        (mf, ms, vr, sl)
        for mf, ms, vr, sl in product(space["ma_fast"], space["ma_slow"], space["vol_ratio"], space["stop_loss"])
        if mf < ms
    ]
    total = max(1, len(combos))
    results: List[Dict[str, Any]] = []

    for i, (mf, ms, vr, sl) in enumerate(combos):
        if progress:
            progress({"stage": "搜索规则空间", "pct": round(100 * i / total, 1),
                      "detail": f"ma{mf}/{ms} 量比{vr} 止损{sl}"})
        spec = _build_spec(symbol, int(mf), int(ms), float(vr), float(sl))
        try:
            res = run_spec(prices, spec, initial_cash=initial_cash)
        except Exception:  # noqa: BLE001
            continue
        full = _clean(strategy_metrics(res.returns, res.exposure))
        if (full.get("num_trades") or 0) < min_trades:
            continue
        split = _split_metrics(res, 1 - oos_frac)
        oos = split["out_sample"] or {}
        oos_sharpe = oos.get("sharpe")
        oos_ret = oos.get("annual_return")
        full_sharpe = full.get("sharpe") or 0.0
        score = (oos_sharpe if oos_sharpe is not None else -9.0)
        results.append({
            "spec": spec.to_dict(),
            "params": {"ma_fast": int(mf), "ma_slow": int(ms),
                       "vol_ratio": float(vr), "stop_loss": float(sl)},
            "metrics": full,
            "in_sample": split["in_sample"],
            "out_sample": oos,
            "split_date": split["split_date"],
            "score": round(float(score), 4),
            "oos_annual": oos_ret,
            "full_sharpe": round(float(full_sharpe), 4),
            "rules": spec.summary_lines(),
        })

    if progress:
        progress({"stage": "完成", "pct": 100})
    results.sort(key=lambda r: (r["score"], r["full_sharpe"]), reverse=True)
    return {"symbol": symbol, "tested": len(combos), "kept": len(results), "results": results[:top_k]}
