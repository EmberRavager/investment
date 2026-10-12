"""A 股交易规则（确定性、无未来函数）。

集中定义撮合所需的交易所规则，回测 / 模拟盘 / 未来实盘必须共用同一套：

- 板块识别：主板 / 创业板 / 科创板 / 北交所 / 基金(ETF)
- 最小申报单位（100 股整手；科创板 200 股起、之后可零股递增）
- 涨跌停幅度（主板 10%、创业板/科创板 20%、北交所 30%、ST 5%、ETF 10%）
- 价格最小变动单位（股票 0.01、基金 0.001）
- 停牌判定
- 涨跌停下的可成交性（涨停买不进、跌停卖不出）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

# 价格最小变动单位
_TICK_STOCK = 0.01
_TICK_FUND = 0.001


@dataclass(frozen=True)
class Board:
    name: str
    lot_size: int          # 最小申报股数
    limit_pct: float       # 涨跌停幅度
    tick: float            # 最小价格变动单位


_BOARDS = {
    "main": Board("主板", 100, 0.10, _TICK_STOCK),
    "gem": Board("创业板", 100, 0.20, _TICK_STOCK),
    "star": Board("科创板", 200, 0.20, _TICK_STOCK),
    "bse": Board("北交所", 100, 0.30, _TICK_STOCK),
    "fund": Board("基金/ETF", 100, 0.10, _TICK_FUND),
}

_ST_LIMIT = 0.05


def normalize_symbol(symbol: str) -> str:
    """去掉 sh/sz/bj 前缀并补齐 6 位。"""
    s = str(symbol).strip().lower()
    for pre in ("sh", "sz", "bj", "s"):
        if s.startswith(pre) and s[len(pre):].isdigit():
            s = s[len(pre):]
            break
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits.zfill(6) if digits else str(symbol)


def detect_board(symbol: str) -> str:
    """根据代码前缀判断板块。"""
    s = normalize_symbol(symbol)
    if s.startswith("688"):
        return "star"
    if s.startswith(("300", "301")):
        return "gem"
    if s.startswith(("43", "83", "87", "88", "92")):
        return "bse"
    if s.startswith(("15", "16", "51", "52", "56", "58", "159", "510", "512", "513", "515", "588")):
        return "fund"
    return "main"


def board_of(symbol: str) -> Board:
    return _BOARDS[detect_board(symbol)]


def lot_size(symbol: str) -> int:
    return board_of(symbol).lot_size


def limit_pct(symbol: str, is_st: bool = False) -> float:
    if is_st and detect_board(symbol) not in ("fund",):
        return _ST_LIMIT
    return board_of(symbol).limit_pct


def round_lot(qty: float, symbol: str) -> int:
    """按最小申报单位取整（买入向下取整）。

    科创板规则特殊：最低 200 股，200 股以上可按 1 股递增。
    """
    q = int(np.floor(max(0.0, float(qty))))
    if detect_board(symbol) == "star":
        return q if q >= 200 else 0
    lot = lot_size(symbol)
    return (q // lot) * lot


def round_price(price: float, symbol: str) -> float:
    tick = board_of(symbol).tick
    return round(float(price) / tick) * tick


def limit_up_price(prev_close: float, symbol: str, is_st: bool = False) -> float:
    return round_price(prev_close * (1.0 + limit_pct(symbol, is_st)), symbol)


def limit_down_price(prev_close: float, symbol: str, is_st: bool = False) -> float:
    return round_price(prev_close * (1.0 - limit_pct(symbol, is_st)), symbol)


def is_suspended(row) -> bool:
    """停牌判定：成交量<=0 或关键价格缺失。"""
    if row is None:
        return True
    if bool(getattr(row, "suspended", False)):
        return True
    vol = getattr(row, "volume", np.nan)
    o = getattr(row, "open", np.nan)
    if vol is None or (isinstance(vol, float) and np.isnan(vol)) or float(vol) <= 0:
        return True
    if o is None or (isinstance(o, float) and np.isnan(o)) or float(o) <= 0:
        return True
    return False


def fillable_open(
    row,
    prev_close: Optional[float],
    symbol: str,
    side: str,
    is_st: bool = False,
) -> Optional[float]:
    """给出以开盘价成交的实际可成交价；不可成交返回 None。

    规则：
    - 停牌 -> None
    - 买入：开盘价触及涨停（>= 涨停价）时买不进 -> None
    - 卖出：开盘价触及跌停（<= 跌停价）时卖不出 -> None
    """
    if is_suspended(row):
        return None
    o = float(getattr(row, "open"))
    if prev_close is None or not np.isfinite(prev_close) or prev_close <= 0:
        return round_price(o, symbol)
    if side == "buy" and o >= limit_up_price(prev_close, symbol, is_st) - 1e-9:
        return None
    if side == "sell" and o <= limit_down_price(prev_close, symbol, is_st) + 1e-9:
        return None
    return round_price(o, symbol)
