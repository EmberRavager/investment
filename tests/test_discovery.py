"""逆向策略发现（离线）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ashare_pred.discovery import discover


def oscillating_prices(n=420):
    idx = pd.bdate_range("2022-01-01", periods=n)
    close = pd.Series(50 + 10 * np.sin(np.arange(n) / 12) + np.linspace(0, 6, n), index=idx)
    vol = pd.Series(1_000_000 * (1 + 0.6 * np.sin(np.arange(n) / 5)), index=idx)
    df = pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]), "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": vol, "amount": close * vol,
    }, index=idx)
    return {"000001": df}


def test_discover_returns_ranked_strategies():
    prices = oscillating_prices()
    out = discover("000001", prices, initial_cash=100000.0, top_k=3, min_trades=3)
    assert out["tested"] > 0
    assert out["results"], "应至少发现一个策略"
    top = out["results"][0]
    assert "spec" in top and "metrics" in top and "params" in top
    assert top["spec"]["universe"] == ["000001"]
    # 按样本外夏普排序
    scores = [r["score"] for r in out["results"]]
    assert scores == sorted(scores, reverse=True)


def test_discover_missing_symbol_raises():
    prices = oscillating_prices()
    try:
        discover("999999", prices)
        assert False, "缺少行情应报错"
    except ValueError:
        pass
