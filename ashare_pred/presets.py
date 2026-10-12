"""预设策略（模板）：彼此规则不同，覆盖趋势/交叉/突破/超跌/指数择时。

供「策略实验室」一键载入，也可作为初始策略库种子。
"""

from __future__ import annotations

from typing import Any, Dict, List

from .strategy import Condition, StrategySpec

_DEFAULT_UNIVERSE = ["600519", "000858", "600036", "601318", "600900", "300750", "002594", "000001"]


def _spec(**kw) -> Dict[str, Any]:
    base = dict(
        universe=list(_DEFAULT_UNIVERSE), weight=0.30, max_position_per_stock=0.30,
        max_total_exposure=1.0, stop_loss=0.08, drawdown_stop=0.15, drawdown_cooldown=20,
    )
    base.update(kw)
    return base


PRESETS: List[Dict[str, Any]] = [
    {
        "key": "trend",
        "name": "趋势跟随（默认）",
        "description": "中短均线多头 + 放量确认；跌破快线卖出。稳健基准，适合作为起点。",
        "spec": _spec(
            name="趋势跟随（默认）",
            filters=[{"field": "ma20", "op": ">", "value": "ma60"}],
            entry=[{"field": "close", "op": ">", "value": "ma20"}, {"field": "vol_ratio", "op": ">", "value": 1.3}],
            exit=[{"field": "close", "op": "<", "value": "ma20"}],
        ),
    },
    {
        "key": "cross",
        "name": "双均线交叉",
        "description": "快线上穿慢线买入（5 上穿 20），下穿卖出。经典择时，信号明确。",
        "spec": _spec(
            name="双均线交叉",
            weight=0.50, max_position_per_stock=0.50,
            entry=[{"field": "ma5", "op": "cross_above", "value": "ma20"}],
            exit=[{"field": "ma5", "op": "cross_below", "value": "ma20"}],
        ),
    },
    {
        "key": "breakout",
        "name": "突破20日新高",
        "description": "收盘创过去 20 日新高买入，跌破 10 日线卖出。动量突破型。",
        "spec": _spec(
            name="突破20日新高",
            stop_loss=0.10,
            entry=[{"field": "close", "op": ">", "value": "high20"}],
            exit=[{"field": "close", "op": "<", "value": "ma10"}],
        ),
    },
    {
        "key": "oversold",
        "name": "超跌反弹",
        "description": "RSI(14) 低于 30 买入，高于 60 卖出。逆势低吸，需承受继续下跌风险。",
        "spec": _spec(
            name="超跌反弹",
            entry=[{"field": "rsi14", "op": "<", "value": 30}],
            exit=[{"field": "rsi14", "op": ">", "value": 60}],
        ),
    },
    {
        "key": "index",
        "name": "指数趋势（宽基/ETF）",
        "description": "宽基或 ETF 均线择时：站上 20 日线且 20 日线在 60 日线上方才持有。低换手、低频。",
        "spec": _spec(
            name="指数趋势（宽基/ETF）",
            weight=1.0, max_position_per_stock=1.0, stop_loss=0.0,
            filters=[{"field": "ma20", "op": ">", "value": "ma60"}],
            entry=[{"field": "close", "op": ">", "value": "ma20"}],
            exit=[{"field": "close", "op": "<", "value": "ma20"}],
        ),
    },
]


def preset_specs() -> List[StrategySpec]:
    return [StrategySpec.from_dict(p["spec"]) for p in PRESETS]
