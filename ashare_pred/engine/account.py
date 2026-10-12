"""模拟账户：现金、持仓（含 T+1 可卖量）、成交记录与净值。

同一份账户模型供回测与模拟盘复用；是否加入 T+1 结算由调用方控制。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np


@dataclass
class Trade:
    date: object
    symbol: str
    name: str
    side: str                # buy | sell
    qty: int
    price: float
    amount: float            # 成交额（不含费用）
    commission: float
    stamp_tax: float
    slippage_cost: float
    total_fee: float
    reason: str = ""
    signal_date: object = None       # 信号产生日（T，收盘）
    strategy_version: object = None  # 策略版本号（可追溯）
    strategy_name: str = ""
    evidence: object = None          # 触发依据（条件+实际值）

    def as_dict(self) -> Dict[str, object]:
        return {
            "date": str(self.date),
            "signal_date": str(self.signal_date) if self.signal_date is not None else "",
            "symbol": self.symbol,
            "name": self.name,
            "side": self.side,
            "qty": self.qty,
            "price": round(self.price, 4),
            "amount": round(self.amount, 2),
            "commission": round(self.commission, 2),
            "stamp_tax": round(self.stamp_tax, 2),
            "slippage_cost": round(self.slippage_cost, 2),
            "total_fee": round(self.total_fee, 2),
            "strategy_version": self.strategy_version,
            "strategy_name": self.strategy_name,
            "reason": self.reason,
            "evidence": self.evidence,
        }


@dataclass
class Position:
    symbol: str
    name: str = ""
    qty: int = 0                 # 总持股
    available_qty: int = 0       # T+1 可卖
    cost_price: float = 0.0      # 摊薄成本
    last_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.qty * self.last_price

    @property
    def pnl(self) -> float:
        return (self.last_price - self.cost_price) * self.qty

    @property
    def pnl_pct(self) -> float:
        if self.cost_price <= 0:
            return 0.0
        return self.last_price / self.cost_price - 1.0


@dataclass
class Account:
    initial_cash: float = 3000.0
    cash: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)
    trades: List[Trade] = field(default_factory=list)
    names: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.cash == 0.0:
            self.cash = self.initial_cash

    # ---- 结算 ----
    def settle(self) -> None:
        """新交易日开盘前：T+1 结算，昨日买入今日可卖。"""
        for pos in self.positions.values():
            pos.available_qty = pos.qty

    # ---- 估值 ----
    def market_value(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    def equity(self) -> float:
        return self.cash + self.market_value()

    def mark_to_market(self, prices: Dict[str, float]) -> None:
        for sym, pos in self.positions.items():
            px = prices.get(sym)
            if px is not None and np.isfinite(px):
                pos.last_price = float(px)

    def weight(self, symbol: str) -> float:
        eq = self.equity()
        if eq <= 0:
            return 0.0
        pos = self.positions.get(symbol)
        return (pos.market_value / eq) if pos else 0.0

    def exposure(self) -> float:
        eq = self.equity()
        if eq <= 0:
            return 0.0
        return self.market_value() / eq

    # ---- 持仓变更 ----
    def apply_buy(self, symbol: str, qty: int, price: float, fee: float) -> None:
        if qty <= 0:
            return
        cost = qty * price + fee
        self.cash -= cost
        pos = self.positions.get(symbol)
        if pos is None:
            pos = Position(symbol=symbol, name=self.names.get(symbol, ""))
            self.positions[symbol] = pos
        new_qty = pos.qty + qty
        pos.cost_price = (pos.cost_price * pos.qty + cost) / new_qty if new_qty else 0.0
        pos.qty = new_qty
        # T+1：当日买入不增加可卖量
        pos.last_price = price

    def apply_sell(self, symbol: str, qty: int, price: float, fee: float) -> None:
        pos = self.positions.get(symbol)
        if pos is None or qty <= 0:
            return
        qty = min(qty, pos.qty)
        self.cash += qty * price - fee
        pos.qty -= qty
        pos.available_qty = max(0, pos.available_qty - qty)
        pos.last_price = price
        if pos.qty <= 0:
            self.positions.pop(symbol, None)

    def snapshot(self, date, prices: Optional[Dict[str, float]] = None) -> Dict[str, object]:
        if prices:
            self.mark_to_market(prices)
        return {
            "date": str(date),
            "cash": round(self.cash, 2),
            "market_value": round(self.market_value(), 2),
            "equity": round(self.equity(), 2),
            "exposure": round(self.exposure(), 4),
            "positions": {
                sym: {
                    "name": p.name,
                    "qty": p.qty,
                    "available_qty": p.available_qty,
                    "cost_price": round(p.cost_price, 4),
                    "last_price": round(p.last_price, 4),
                    "market_value": round(p.market_value, 2),
                    "pnl": round(p.pnl, 2),
                    "pnl_pct": round(p.pnl_pct, 4),
                }
                for sym, p in self.positions.items()
            },
        }
