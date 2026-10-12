"""横截面多因子选股（离线，合成数据）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ashare_pred.xsec import (
    build_panel, ic_metrics, layered_returns, optimize_weights, run_xsec, verdict_of,
)


def make_universe(n_sym=12, n=520, seed=0):
    idx = pd.bdate_range("2020-01-01", periods=n)
    rng = np.random.default_rng(seed)
    out = {}
    for k in range(n_sym):
        ret = rng.normal(0, 0.018, n) + 0.02 * np.sin(np.arange(n) / 30 + k)
        close = pd.Series(100 * np.exp(np.cumsum(ret)), index=idx)
        vol = pd.Series(1e6 * (1 + rng.random(n)), index=idx)
        out[f"{k:06d}"] = pd.DataFrame({
            "open": close.shift(1).fillna(close.iloc[0]), "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": vol, "amount": close * vol,
        }, index=idx)
    return out


def test_panel_and_run_xsec():
    prices = make_universe()
    panel, factor_cols = build_panel(prices, horizon=5)
    assert not panel.empty
    assert len(factor_cols) >= 50, f"因子应>=50，实际 {len(factor_cols)}"
    assert "size" in panel.columns and "label" in panel.columns

    out = run_xsec(prices, top_k=3, horizon=5, rebalance=5,
                   train_window=150, retrain=20, initial_cash=100000.0)
    assert out["ic"]["n_days"] > 0
    assert out["result"].trades, "应产生成交"
    assert "usable" in out["verdict"]
    assert isinstance(out["factor_importance"], list)


def test_ic_metrics_signal_with_variation():
    dates = pd.bdate_range("2021-01-01", periods=10)
    rows = []
    rng = np.random.default_rng(1)
    for d in dates:
        scale = rng.uniform(0.2, 1.0)
        for s in range(8):
            v = float(rng.normal())
            rows.append({"date": d, "symbol": f"{s:06d}", "score": v,
                         "label": 0.9 * v + rng.normal(0, scale)})
    ic = ic_metrics(pd.DataFrame(rows))
    assert ic["n_days"] == 10
    assert ic["ic_mean"] > 0.5
    assert ic["ic_t"] is not None


def test_layered_and_verdict():
    dates = pd.bdate_range("2021-01-01", periods=20)
    rows = []
    rng = np.random.default_rng(2)
    for d in dates:
        for s in range(20):
            sc = float(rng.normal())
            rows.append({"date": d, "symbol": f"{s:06d}", "score": sc, "label": sc + rng.normal(0, 0.3)})
    lay = layered_returns(pd.DataFrame(rows), q=5)
    assert lay["monotonic"] is not None and lay["monotonic"] > 0
    ic = ic_metrics(pd.DataFrame(rows))
    assert verdict_of(ic)["usable"] is True


def test_optimize_weights_constraints():
    scores = {f"{i:06d}": float(10 - i) for i in range(10)}
    industry = {f"{i:06d}": ("A" if i < 5 else "B") for i in range(10)}
    w = optimize_weights(scores, {}, industry, cap=0.3, turnover_penalty=0.05, ind_limit=0.6, top_k=5)
    assert w, "应返回权重"
    assert sum(w.values()) <= 1.0 + 1e-6
    assert all(0 <= v <= 0.3 + 1e-6 for v in w.values())
    for ind in ("A", "B"):
        exp = sum(v for k, v in w.items() if industry[k] == ind)
        assert exp <= 0.6 + 1e-6
