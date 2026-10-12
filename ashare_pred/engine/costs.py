"""A 股交易成本模型：佣金（含最低 5 元）、印花税（卖出单边）、滑点。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class TradingCost:
    commission: float = 0.00025     # 佣金费率（双边）
    stamp_tax: float = 0.0005       # 印花税（仅卖出）
    slippage: float = 0.0005        # 滑点（按成交价比例）
    min_commission: float = 5.0     # 单笔最低佣金
    transfer_fee: float = 0.00001   # 过户费（沪市，双边；这里统一按费率近似）
    apply_transfer_fee: bool = False

    def breakdown(self, side: str, amount: float) -> Tuple[float, float, float]:
        """返回 (佣金, 印花税, 过户费)。amount 为成交额。"""
        comm = max(amount * self.commission, self.min_commission) if amount > 0 else 0.0
        stamp = amount * self.stamp_tax if side == "sell" else 0.0
        transfer = amount * self.transfer_fee if self.apply_transfer_fee else 0.0
        return comm, stamp, transfer

    def fee(self, side: str, amount: float) -> Tuple[float, float]:
        """返回 (总费用, 其中佣金)。"""
        comm, stamp, transfer = self.breakdown(side, amount)
        return comm + stamp + transfer, comm


def apply_slippage(price: float, side: str, slippage: float) -> float:
    """买入向上滑、卖出向下滑。"""
    if side == "buy":
        return price * (1.0 + slippage)
    return price * (1.0 - slippage)
