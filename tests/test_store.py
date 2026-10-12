"""持久化层测试。"""

from __future__ import annotations

import pytest

from ashare_pred.engine import Broker, EngineConfig
from ashare_pred.risk import RiskConfig
from ashare_pred.store import Store
from tests.test_engine import make_prices


def test_strategy_versioning_and_persistence():
    s = Store(":memory:")
    sid = s.create_strategy("趋势跟随", {"type": "rule", "ma": 20}, source="ai")
    got = s.get_strategy(sid)
    assert got["name"] == "趋势跟随" and got["config"]["ma"] == 20
    assert got["current_version"] == 1
    v2 = s.add_version(sid, {"type": "rule", "ma": 60}, note="参数调整")
    assert v2 == 2
    assert s.get_strategy(sid)["config"]["ma"] == 60

    # 运行 + 结果落库
    prices = make_prices(price=5.0)
    idx = list(prices["600519"].index)
    targets = {idx[0]: {"600519": 0.30}, idx[5]: {"600519": 0.0}}
    run_id = s.create_run("backtest", strategy_id=sid, version=2, symbol="600519",
                          start=str(idx[0]), end=str(idx[-1]), initial_cash=3000.0)
    res = Broker(EngineConfig(initial_cash=3000.0, risk=RiskConfig(max_position_per_stock=0.30))).run(prices, targets)
    s.persist_engine_result(run_id, res)
    s.finish_run(run_id, {"total_return": float(res.equity.iloc[-1] - 1.0)})

    detail = s.get_run_detail(run_id)
    assert detail["run"]["status"] == "done"
    assert len(detail["trades"]) == 2          # 买入 + 卖出
    assert len(detail["equity_curve"]) == len(idx)
    assert detail["positions"]                # 有持仓记录


def test_cannot_validate_without_backtest():
    s = Store(":memory:")
    sid = s.create_strategy("未验证策略", {"type": "rule"})
    with pytest.raises(ValueError):
        s.set_status(sid, "validated")

    # 完成一次回测后可标记
    prices = make_prices(price=5.0)
    idx = list(prices["600519"].index)
    res = Broker(EngineConfig(initial_cash=3000.0)).run(prices, {idx[0]: {"600519": 0.30}})
    run_id = s.create_run("backtest", strategy_id=sid, symbol="600519")
    s.persist_engine_result(run_id, res)
    s.finish_run(run_id, {"total_return": 0.0})
    s.set_status(sid, "validated")
    assert s.get_strategy(sid)["status"] == "validated"
