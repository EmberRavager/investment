"""选股雷达：快照归一化与粗筛（离线）。"""

from __future__ import annotations

import pandas as pd

from ashare_pred.data import _normalize_snapshot, infer_kind
from ashare_pred.screener import _coarse, _feasibility
from ashare_pred.strategy import Condition, StrategySpec


def test_infer_kind_etf():
    assert infer_kind("510300") == "fund"
    assert infer_kind("159915") == "fund"
    assert infer_kind("588000") == "fund"
    assert infer_kind("600519") == "stock"
    assert infer_kind("000300") == "index"


def _sina_like():
    return pd.DataFrame({
        "代码": ["sh600519", "sz000001", "bj920001", "sz300750"],
        "名称": ["贵州茅台", "平安银行", "*ST某股", "宁德时代"],
        "最新价": [1600.0, 11.5, 3.2, 210.0],
        "涨跌幅": [0.5, 1.2, 0.0, 10.0],   # 最后一只涨停
        "成交额": [5e9, 3e9, 1e7, 4e9],
    })


def test_normalize_snapshot_strips_prefix_and_types():
    out = _normalize_snapshot(_sina_like())
    assert list(out["symbol"]) == ["600519", "000001", "920001", "300750"]
    assert out["amount"].dtype.kind == "f"
    assert set(["symbol", "name", "price", "pct_chg", "amount"]).issubset(out.columns)


def test_coarse_filters_st_limit_and_liquidity():
    snap = _normalize_snapshot(_sina_like())
    items = _coarse(snap, top_n=10, min_amount=1e8, max_pct=9.5)
    syms = [i["symbol"] for i in items]
    assert "600519" in syms and "000001" in syms
    assert "920001" not in syms   # 低流动性
    assert "300750" not in syms   # 涨停被剔除


def test_feasibility_position_cap_acceptance():
    # 验收：本金 3000、单股 30% -> 上限 900；某股 100 股需 1630 -> 超出单股仓位限制
    spec = StrategySpec(name="x", universe=["600519"], entry=[Condition("close", ">", "ma20")], weight=0.30)
    f = _feasibility(spec, 16.3, 3000.0, "600519")
    assert f["can_buy"] is False
    assert "超出单股仓位限制" in f["reason"]

    # 便宜到能买一手 -> 可行
    f2 = _feasibility(spec, 5.0, 3000.0, "600519")
    assert f2["can_buy"] is True and f2["qty"] == 100
