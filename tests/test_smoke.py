"""离线冒烟测试：数据归一化、模型注册表、风控因果性、配置不变量。

运行：
    .venv/bin/pytest -q
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ashare_pred.backtest import build_strategy
from ashare_pred.config import BacktestConfig, Config, CostConfig
from ashare_pred.models import build_model, list_models
from ashare_pred.providers.base import normalize


def test_normalize_chinese_columns():
    df = pd.DataFrame({
        "日期": ["2024-01-02", "2024-01-03"],
        "开盘": [1, 2], "最高": [2, 3], "最低": [0.5, 1.5],
        "收盘": [1.5, 2.5], "成交量": [100, 200],
    })
    out = normalize(df)
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert out.index[0] == pd.Timestamp("2024-01-02")
    assert out.index.is_monotonic_increasing


def test_normalize_timestamp_is_beijing_date():
    # 2024-12-16 00:00 +08:00 == 1734278400000 ms；应还原为 2024-12-16 零点
    df = pd.DataFrame({
        "timestamp": [1734278400000],
        "open": [1], "high": [1], "low": [1], "close": [1], "volume": [1],
    })
    out = normalize(df)
    assert out.index[0] == pd.Timestamp("2024-12-16")
    assert out.index[0].hour == 0


def test_model_registry_and_fit():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 5))
    y = (X[:, 0] + rng.normal(scale=0.5, size=200) > 0).astype(int)
    assert "xgboost" in list_models() and "logistic" in list_models()
    for name in ["logistic", "random_forest", "xgboost", "lightgbm"]:
        m = build_model(name)
        m.fit(X, y)
        p = m.predict_proba(X)
        assert p.shape == (200, 2)
        assert np.all((p >= 0) & (p <= 1))


def test_config_embargo_not_less_than_horizon():
    cfg = Config.from_dict({"labels": {"horizon": 5}})
    assert cfg.backtest.embargo >= 5


def test_drawdown_stop_caps_drawdown():
    idx = pd.date_range("2020-01-01", periods=320, freq="B")
    proba = pd.Series(1.0, index=idx)             # 始终给多头信号
    fwd = pd.Series(np.r_[np.full(220, 0.001), np.full(100, -0.02)], index=idx)  # 末端暴跌
    bt = BacktestConfig(
        prob_threshold=0.0, trend_filter=False, vol_target=0.0,
        min_hold=1, drawdown_stop=0.10, drawdown_cooldown=20,
        cost=CostConfig(commission=0, stamp_tax=0, slippage=0),
    )
    pos, strat = build_strategy(proba, fwd, None, None, bt)
    eq = (1 + strat).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    assert (pos == 0).any(), "回撤熔断应触发空仓"
    assert dd > -0.6, "熔断应显著压制回撤"


def test_trend_filter_reduces_exposure():
    idx = pd.date_range("2020-01-01", periods=100, freq="B")
    proba = pd.Series(1.0, index=idx)
    fwd = pd.Series(0.001, index=idx)
    trend = pd.Series(np.r_[np.zeros(50), np.ones(50)], index=idx)  # 前 50 天空头趋势
    bt = BacktestConfig(prob_threshold=0.0, trend_filter=True, vol_target=0.0,
                        min_hold=1, drawdown_stop=0.0,
                        cost=CostConfig(commission=0, stamp_tax=0, slippage=0))
    pos, _ = build_strategy(proba, fwd, trend, None, bt)
    assert pos[:45].sum() == 0, "下行趋势期不应持仓"
    assert pos[55:].sum() > 0, "上行趋势期应持仓"
