"""撮合引擎与风险引擎的单元测试（纯离线，用合成数据）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ashare_pred.engine import Broker, EngineConfig, TradingCost, rules
from ashare_pred.engine.account import Account
from ashare_pred.risk import RiskConfig, RiskContext, RiskEngine


def make_prices(symbol="600519", n=12, price=5.0, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=n)
    df = pd.DataFrame(
        {
            "open": price,
            "high": price * 1.02,
            "low": price * 0.98,
            "close": price,
            "volume": 1_000_000.0,
            "amount": 1_000_000.0 * price,
        },
        index=idx,
    )
    return {symbol: df}


# ---- 规则 ----
def test_board_and_lot():
    assert rules.detect_board("600519") == "main"
    assert rules.detect_board("300750") == "gem"
    assert rules.detect_board("688981") == "star"
    assert rules.detect_board("159338") == "fund"
    assert rules.round_lot(199, "600519") == 100
    assert rules.round_lot(199, "688981") == 0
    assert rules.round_lot(250, "688981") == 250
    assert rules.round_lot(90, "300750") == 0


def test_price_limits():
    assert rules.limit_up_price(10.0, "600519") == 11.0
    assert rules.limit_down_price(10.0, "600519") == 9.0
    assert rules.limit_up_price(10.0, "300750") == 12.0
    assert rules.limit_up_price(10.0, "600519", is_st=True) == 10.5


# ---- 账户 T+1 ----
def test_t_plus_1_settlement():
    acc = Account(initial_cash=100000.0)
    acc.apply_buy("600519", 100, 10.0, fee=5.0)
    assert acc.positions["600519"].qty == 100
    assert acc.positions["600519"].available_qty == 0   # 当日买入不可卖
    acc.settle()
    assert acc.positions["600519"].available_qty == 100  # 次日可卖


# ---- 风险引擎 ----
def test_risk_rejects_insufficient_cash_and_cap():
    eng = RiskEngine(RiskConfig(max_position_per_stock=0.30))
    ctx = RiskContext(equity=3000, peak_equity=3000, cash=3000, weight=0.0)
    d = eng.check_order("600519", "buy", 100, 100.0, ctx)  # 需 10000 元
    assert not d.approved and "资金不足" in d.reason
    d2 = eng.check_order("600519", "buy", 1000, 1.0, ctx)  # 拟仓位 33% > 30%
    assert not d2.approved and "仓位上限" in d2.reason


def test_risk_drawdown_halt_and_resume():
    eng = RiskEngine(RiskConfig(max_drawdown_stop=0.10, drawdown_cooldown_days=2))
    assert not eng.monitor("d1", 100.0, 100.0)
    assert eng.monitor("d2", 85.0, 100.0)   # 回撤 15% -> 熔断
    assert eng.monitor("d3", 84.0, 100.0)   # 冷却中
    assert not eng.monitor("d4", 84.0, 100.0)  # 冷却结束


# ---- 端到端撮合 ----
def test_engine_skips_when_position_cap_too_small():
    # 3000 元本金、单股 30% -> 上限 900 元；100 股 @100 元 = 10000 元 > 上限
    prices = make_prices(price=100.0)
    idx = list(prices["600519"].index)
    targets = {idx[0]: {"600519": 0.30}}
    cfg = EngineConfig(initial_cash=3000.0, risk=RiskConfig(max_position_per_stock=0.30))
    res = Broker(cfg).run(prices, targets)
    assert len(res.trades) == 0
    assert any("超出单股仓位限制" in s["reason"] for s in res.skips)


def test_engine_buys_within_capital_and_cap():
    prices = make_prices(price=5.0)
    idx = list(prices["600519"].index)
    targets = {idx[0]: {"600519": 0.30}}
    cfg = EngineConfig(initial_cash=3000.0, risk=RiskConfig(max_position_per_stock=0.30))
    res = Broker(cfg).run(prices, targets)
    assert len(res.trades) == 1
    tr = res.trades[0]
    assert tr.side == "buy" and tr.qty == 100
    assert tr.amount <= 0.30 * 3000 + 1e-6
    assert res.account.positions["600519"].qty == 100
    # 成本必须被扣掉：权益略低于成交额对应净值
    assert res.equity.iloc[-1] < 1.0 + 1e-9


def test_engine_blocks_buy_at_limit_up():
    prices = make_prices(price=10.0)
    df = prices["600519"]
    df.loc[df.index[1], "open"] = 11.0   # 次日一字涨停开盘
    target_idx = df.index[0]
    cfg = EngineConfig(initial_cash=100000.0, risk=RiskConfig(max_position_per_stock=1.0))
    res = Broker(cfg).run(prices, {target_idx: {"600519": 1.0}})
    assert len(res.trades) == 0
    assert any("涨跌停" in s["reason"] for s in res.skips)


def test_stamp_tax_only_on_sell():
    cost = TradingCost()
    buy_fee, _ = cost.fee("buy", 10000)
    sell_fee, _ = cost.fee("sell", 10000)
    assert sell_fee > buy_fee   # 卖出多印花税


def test_impact_cost():
    from ashare_pred.engine.costs import TradingCost as TC
    c = TC(impact_coef=1.0)
    assert c.impact(1_000_000, 10_000_000) > 0
    assert c.impact(0, 10_000_000) == 0
    assert TC(impact_coef=0.0).impact(1_000_000, 1_000_000) == 0


def test_live_not_ready():
    import pytest
    from ashare_pred.engine import LiveBroker, LiveNotReadyError, live_readiness
    r = live_readiness()
    assert r["ready"] is False and r["blockers"]
    with pytest.raises(LiveNotReadyError):
        LiveBroker()
