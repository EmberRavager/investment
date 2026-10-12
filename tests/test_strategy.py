"""策略规格 / 规则引擎 / NL 解析测试（离线）。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ashare_pred.strategy import (
    Condition, StrategySpec, evaluate_signals, run_spec, validate_spec,
)
from server.strategy_ai import nl_to_spec


def trending_prices(n=180, start="2023-01-01"):
    idx = pd.bdate_range(start, periods=n)
    base = 10 + np.linspace(0, 4, n) + 1.2 * np.sin(np.arange(n) / 9)
    close = pd.Series(base, index=idx)
    vol = pd.Series(1_000_000 * (1 + 0.5 * np.sin(np.arange(n) / 4)), index=idx)
    df = pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close * 1.01, "low": close * 0.99, "close": close,
        "volume": vol, "amount": close * vol,
    }, index=idx)
    return {"000001": df}


def test_validate_spec_rules():
    bad = StrategySpec(name="x", universe=["000001"], entry=[])
    with pytest.raises(ValueError):
        validate_spec(bad)
    ok = StrategySpec(
        name="t", universe=["000001"],
        entry=[Condition("close", ">", "ma20")],
        exit=[Condition("close", "<", "ma20")],
    )
    assert validate_spec(ok) == []
    # 财务字段 -> 警告而非报错
    spec = StrategySpec(
        name="t", universe=["000001"],
        filters=[Condition("profit_growth", ">", 20)],
        entry=[Condition("close", ">", "ma20")],
    )
    assert any("财务" in w for w in validate_spec(spec))


def test_evaluate_signals_and_run_spec():
    prices = trending_prices()
    spec = StrategySpec(
        name="t", universe=["000001"],
        filters=[Condition("ma20", ">", "ma60")],
        entry=[Condition("close", ">", "ma20")],
        exit=[Condition("close", "<", "ma20")],
        weight=0.5, max_position_per_stock=0.5,
    )
    sig = evaluate_signals(prices["000001"], spec)
    assert (sig > 0).sum() > 0
    res = run_spec(prices, spec, initial_cash=100000.0)
    assert len(res.trades) > 0
    assert set(t.side for t in res.trades) == {"buy", "sell"}


def test_nl_to_spec_fallback_is_valid():
    out = nl_to_spec("成长股策略，利润增长超20%，站上20日均线，放量1.3倍，单股最大仓位30%")
    assert out["source"] in ("ai", "rule")
    spec = StrategySpec.from_dict(out["spec"])
    validate_spec(spec)  # 不抛异常
    assert any(c.field == "profit_growth" for c in spec.filters)


def crash_prices(n=120):
    idx = pd.bdate_range("2023-01-01", periods=n)
    close = pd.Series(
        [10.0] * 20 + list(np.linspace(10, 14, 40)) + list(np.linspace(14, 6, n - 60)),
        index=idx,
    )
    vol = pd.Series(np.full(n, 1_000_000.0), index=idx)
    df = pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]), "high": close * 1.01,
        "low": close * 0.99, "close": close, "volume": vol, "amount": close * vol,
    }, index=idx)
    return {"000001": df}


def test_validate_rejects_invalid_rules():
    base = dict(name="x", universe=["000001"])
    with pytest.raises(ValueError):
        validate_spec(StrategySpec(**base, entry=[Condition("close", ">", "")]))
    with pytest.raises(ValueError):
        validate_spec(StrategySpec(**base, entry=[Condition("close", "~", 1)]))
    with pytest.raises(ValueError):
        validate_spec(StrategySpec(**base, entry=[Condition("nope_field", ">", 1)]))
    with pytest.raises(ValueError):
        validate_spec(StrategySpec(**base, entry=[Condition("close", ">", "not_a_field")]))
    with pytest.raises(ValueError):
        validate_spec(StrategySpec(**base, entry=[Condition("close", ">", 1)], entry_logic="xor"))


def test_and_or_logic():
    prices = trending_prices()
    spec = StrategySpec(
        name="or", universe=["000001"],
        entry=[Condition("close", ">", "ma20"), Condition("rsi14", ">", 200)],  # 后者恒假
        entry_logic="or",
        exit=[Condition("close", "<", "ma20")], weight=0.5,
    )
    res = run_spec(prices, spec, initial_cash=100000.0)
    assert len(res.trades) > 0  # OR 逻辑下 close>ma20 即可触发


def test_fundamentals_required_and_point_in_time():
    spec = StrategySpec(
        name="f", universe=["000001"],
        filters=[Condition("profit_growth", ">", 20)],
        entry=[Condition("close", ">", "ma20")],
    )
    prices = trending_prices()
    with pytest.raises(ValueError):
        evaluate_signals(prices["000001"], spec)  # 缺财务数据必须报错，不能静默忽略
    fund = pd.DataFrame({"profit_growth": [30.0]}, index=pd.to_datetime(["2023-06-30"]))
    w = evaluate_signals(prices["000001"], spec, fundamentals=fund)
    assert len(w) == len(prices["000001"])


def test_stop_loss_and_traceability():
    prices = crash_prices()
    spec = StrategySpec(
        name="t", universe=["000001"],
        entry=[Condition("close", ">", "ma20")],
        exit=[Condition("close", "<", 0)],          # 永不触发，仅靠止损退出
        weight=0.5, max_position_per_stock=0.5, stop_loss=0.05, drawdown_stop=0.0,
    )
    res = run_spec(prices, spec, initial_cash=100000.0, strategy_version=7)
    assert res.trades
    assert all(t.strategy_version == 7 for t in res.trades)
    assert any("止损" in t.reason for t in res.trades)
    assert res.trades[0].evidence is not None
    assert res.trades[0].signal_date is not None
