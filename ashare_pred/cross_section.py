"""横截面选股（动量轮动）。

思路：不看单只股票"明天涨不涨"，而是把一篮子股票每天横向比较，
按「动量强度」排序，定期换仓买入最强的一组（等权），弱市中空仓。
这是机构更常用的稳健思路，比"单票日频择时"可靠得多。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .config import Config, DataConfig
from .data import load_prices
from .metrics import equity_curve, strategy_metrics

#: 默认股票池（流动性好的大盘股，尽量分散行业）
DEFAULT_UNIVERSE: List[tuple] = [
    ("600519", "贵州茅台"), ("000858", "五粮液"), ("600036", "招商银行"),
    ("601318", "中国平安"), ("600900", "长江电力"), ("601012", "隆基绿能"),
    ("300750", "宁德时代"), ("002594", "比亚迪"), ("000333", "美的集团"),
    ("600276", "恒瑞医药"), ("000651", "格力电器"), ("600887", "伊利股份"),
    ("601166", "兴业银行"), ("000001", "平安银行"), ("600030", "中信证券"),
    ("601888", "中国中免"), ("600585", "海螺水泥"), ("002415", "海康威视"),
    ("300059", "东方财富"), ("601899", "紫金矿业"),
]

_NAMES = {s: n for s, n in DEFAULT_UNIVERSE}


def _emit(progress, stage: str, pct: float, detail: str = ""):
    if progress:
        progress({"stage": stage, "pct": round(pct, 1), "detail": detail})


def _load_universe(base: DataConfig, symbols: List[str], progress=None) -> Dict[str, pd.DataFrame]:
    prices: Dict[str, pd.DataFrame] = {}
    total = max(1, len(symbols))
    for i, s in enumerate(symbols):
        _emit(progress, "下载股票池数据", 5 + 70 * (i / total), f"{_NAMES.get(s, s)}")
        c = DataConfig(
            symbol=s, kind="stock", start=base.start, end=base.end,
            adjust=base.adjust, cache_dir=base.cache_dir, use_cache=base.use_cache,
            provider=base.provider, mcp_url=base.mcp_url, mcp_tool=base.mcp_tool,
            mcp_recent_n=base.mcp_recent_n,
        )
        try:
            prices[s] = load_prices(c, verbose=False)
        except Exception:  # noqa: BLE001
            pass
    return prices


def run(
    cfg: Config,
    symbols: Optional[List[str]] = None,
    top_k: int = 5,
    lookback: int = 60,
    skip: int = 5,
    rebalance: int = 20,
    ma_window: int = 120,
    verbose: bool = True,
    progress=None,
) -> Dict[str, Any]:
    syms = symbols or [s for s, _ in DEFAULT_UNIVERSE]
    _emit(progress, "准备", 3)

    prices = _load_universe(cfg.data, syms, progress)
    if not prices:
        raise RuntimeError("股票池数据全部获取失败")

    close = pd.DataFrame({s: p["close"] for s, p in prices.items()}).sort_index()
    ret = close.pct_change()
    score = close.shift(skip) / close.shift(lookback) - 1.0   # 动量：跳过近 skip 天避免短期反转
    ma = close.rolling(ma_window).mean()

    _emit(progress, "横截面轮动回测", 80)
    dates = close.index
    n = len(dates)
    daily = np.zeros(n)
    pos = np.zeros(n)
    holdings: List[str] = []
    for i in range(n):
        if i % rebalance == 0 and i >= lookback + skip:
            row = score.iloc[i].dropna()
            ok = (close.iloc[i] > ma.iloc[i]).reindex(row.index).fillna(False)
            row = row[ok]
            holdings = list(row.sort_values(ascending=False).head(top_k).index)
        if holdings:
            r = ret.iloc[i][holdings].mean()
            daily[i] = 0.0 if np.isnan(r) else r
            pos[i] = len(holdings) / top_k
    strat = pd.Series(daily, index=dates)
    bench = ret.mean(axis=1).fillna(0.0)

    _emit(progress, "计算绩效", 92)
    sm = strategy_metrics(strat, pd.Series(pos, index=dates))
    bm = strategy_metrics(bench, pd.Series(1.0, index=dates))

    # 当前最强的一批
    row = score.iloc[-1].dropna()
    ok = (close.iloc[-1] > ma.iloc[-1]).reindex(row.index).fillna(False)
    row = row[ok].sort_values(ascending=False)
    current = [
        {"symbol": s, "name": _NAMES.get(s, s), "score": round(float(row[s]), 4)}
        for s in row.head(top_k).index
    ]

    series = {
        "dates": [d.strftime("%Y-%m-%d") for d in dates],
        "strategy": [round(float(v), 4) for v in equity_curve(strat)],
        "benchmark": [round(float(v), 4) for v in equity_curve(bench)],
    }
    _emit(progress, "完成", 100)
    return {
        "metrics": {"strategy": sm, "benchmark": bm},
        "current": current,
        "series": series,
        "params": {
            "top_k": top_k, "lookback": lookback, "rebalance": rebalance,
            "universe": len(prices),
        },
    }
