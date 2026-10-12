"""横截面短线轮动：每 K 个交易日按短周期动量排序，买入最强的前 N 只，等权持有，到期换仓。

这是"低频短线(1~7天)"更稳健的做法——不预测单票方向，而是在一篮子股票里做排序轮动，
分散单票噪声；配合最长持有、止损、熔断与真实成本约束（T+1、整手、佣金/印花税/滑点）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .engine import Broker, EngineConfig, EngineResult, TradingCost
from .risk.engine import RiskConfig


def rotation_targets(
    prices: Dict[str, pd.DataFrame],
    top_n: int = 5,
    rebalance: int = 5,
    lookback: int = 20,
) -> tuple:
    """生成 ({换仓日: {symbol: 权重}}, {(换仓日, symbol): 证据})。按 lookback 日动量取前 top_n。"""
    syms = [s for s in prices if "close" in prices[s].columns]
    if not syms:
        return {}, {}
    close = pd.DataFrame({s: prices[s]["close"] for s in syms}).sort_index()
    mom = close.pct_change(lookback)
    cal = list(close.index)
    weight = 1.0 / max(1, top_n)

    targets: Dict[Any, Dict[str, float]] = {}
    evidence: Dict[Any, Dict[str, Any]] = {}
    for i, day in enumerate(cal):
        if i % max(1, rebalance) != 0 or i < lookback:
            continue
        row = mom.loc[day].dropna()
        if len(row) == 0:
            continue
        ranked = row.sort_values(ascending=False)
        top = ranked.head(top_n)
        targets[day] = {s: weight for s in top.index}
        for rank, (s, v) in enumerate(top.items(), 1):
            evidence[(day, s)] = {
                "action": "rebalance",
                "reason": f"{lookback}日动量排名 第{rank}",
                "momentum": round(float(v), 4),
                "rank": rank,
            }
    return targets, evidence


def run_rotation(
    prices: Dict[str, pd.DataFrame],
    top_n: int = 5,
    rebalance: int = 5,
    lookback: int = 20,
    initial_cash: float = 100000.0,
    names: Optional[Dict[str, str]] = None,
    stop_loss: float = 0.0,
    drawdown_stop: float = 0.15,
    drawdown_cooldown: int = 5,
    cost: Optional[TradingCost] = None,
    strategy_version: Optional[int] = None,
) -> EngineResult:
    targets, evidence = rotation_targets(prices, top_n=top_n, rebalance=rebalance, lookback=lookback)
    weight = 1.0 / max(1, top_n)
    cfg = EngineConfig(
        initial_cash=initial_cash,
        cost=cost or TradingCost(),
        risk=RiskConfig(
            max_position_per_stock=max(weight * 1.1, weight),
            max_total_exposure=1.0,
            max_drawdown_stop=drawdown_stop,
            drawdown_cooldown_days=drawdown_cooldown,
        ),
        names=dict(names or {}),
        stop_loss=stop_loss,
        strategy_version=strategy_version,
        strategy_name=f"轮动 top{top_n}/{lookback}日",
    )
    return Broker(cfg).run(prices, targets, evidence=evidence)
