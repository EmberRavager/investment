"""独立风险引擎（与 AI 模块完全解耦）。

职责：在**任何订单提交前**做确定性校验；并在运行时监控组合级风险。
回测 / 模拟盘 / 未来实盘共用同一份规则，避免"回测能过、实盘被拒"。

设计原则：
- 只依赖传入的上下文（RiskContext），不主动读数据、不联网、不调 AI。
- 校验失败必须给出可读原因，便于复盘与前端展示。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np


@dataclass
class RiskConfig:
    max_position_per_stock: float = 0.30   # 单只股票最大权重
    max_total_exposure: float = 1.00       # 总仓位上限
    max_daily_buy_amount: float = 0.0      # 单日新增买入额度(元)，0=不限
    max_drawdown_stop: float = 0.15        # 回撤熔断阈值，0=关闭
    drawdown_cooldown_days: int = 0        # 熔断后冷却天数
    min_order_amount: float = 0.0          # 单笔最小成交额(元)，0=不限
    min_turnover: float = 0.0              # 流动性门槛：日均成交额(元)，0=不限
    max_volatility: float = 0.0            # 异常波动过滤：年化波动率上限，0=不限
    allow_odd_lot_sell: bool = True        # 允许卖出零股（不足整手时清仓）


@dataclass
class RiskContext:
    equity: float
    peak_equity: float
    cash: float
    weight: float = 0.0                    # 当前标的权重
    total_exposure: float = 0.0
    daily_bought: float = 0.0              # 当日已买入金额
    turnover: float = float("nan")         # 标的日均成交额(元)
    volatility: float = float("nan")       # 标的年化波动率
    data_stale: bool = False               # 数据是否过期/异常


@dataclass
class RiskDecision:
    approved: bool
    reason: str = ""

    def __bool__(self) -> bool:  # 便于 if decision:
        return self.approved


@dataclass
class RiskEvent:
    date: object
    kind: str                 # reject | halt | resume
    symbol: str = ""
    reason: str = ""


class RiskEngine:
    def __init__(self, cfg: RiskConfig | None = None):
        self.cfg = cfg or RiskConfig()
        self.events: List[RiskEvent] = []
        self.cooldown_left = 0

    # ---- 订单级校验 ----
    def check_order(
        self, symbol: str, side: str, qty: int, price: float, ctx: RiskContext
    ) -> RiskDecision:
        c = self.cfg
        if ctx.data_stale:
            return self._reject(symbol, "数据过期或异常，暂停执行", ctx)
        if qty <= 0 or price <= 0:
            return self._reject(symbol, "下单数量或价格非法", ctx)

        amount = qty * price

        if side == "sell":
            # 卖出仅减仓，始终允许；是否可卖由引擎按 T+1/跌停处理
            return RiskDecision(True, "")

        # 买入校验
        if amount > ctx.cash + 1e-6:
            return self._reject(symbol, f"资金不足：需 {amount:.0f} 元，可用 {ctx.cash:.0f} 元", ctx)

        if c.max_daily_buy_amount > 0 and ctx.daily_bought + amount > c.max_daily_buy_amount + 1e-6:
            return self._reject(symbol, "超出单日新增买入额度", ctx)

        if amount < c.min_order_amount - 1e-6:
            return self._reject(symbol, f"单笔金额 {amount:.0f} 元低于下限 {c.min_order_amount:.0f}", ctx)

        if ctx.equity > 0:
            proj_weight = (ctx.weight * ctx.equity + amount) / ctx.equity
            if proj_weight > c.max_position_per_stock + 1e-9:
                return self._reject(
                    symbol,
                    f"超出单股仓位上限：拟 {proj_weight:.1%} > {c.max_position_per_stock:.0%}",
                    ctx,
                )
            proj_exposure = ctx.total_exposure + amount / ctx.equity
            if proj_exposure > c.max_total_exposure + 1e-9:
                return self._reject(
                    symbol,
                    f"超出总仓位上限：拟 {proj_exposure:.1%} > {c.max_total_exposure:.0%}",
                    ctx,
                )

        if c.min_turnover > 0 and np.isfinite(ctx.turnover) and ctx.turnover < c.min_turnover:
            return self._reject(symbol, "流动性不足", ctx)

        if c.max_volatility > 0 and np.isfinite(ctx.volatility) and ctx.volatility > c.max_volatility:
            return self._reject(symbol, "波动率异常，过滤", ctx)

        return RiskDecision(True, "")

    # ---- 组合级监控 ----
    def monitor(self, date, equity: float, peak_equity: float) -> bool:
        """返回是否处于熔断（halt）状态。触发时进入冷却。"""
        c = self.cfg
        if c.max_drawdown_stop <= 0:
            return False
        if self.cooldown_left > 0:
            self.cooldown_left -= 1
            if self.cooldown_left == 0:
                self.events.append(RiskEvent(date, "resume", reason="熔断冷却结束"))
                return False
            return True
        dd = equity / peak_equity - 1.0 if peak_equity > 0 else 0.0
        if dd <= -c.max_drawdown_stop:
            self.cooldown_left = c.drawdown_cooldown_days
            self.events.append(
                RiskEvent(date, "halt", reason=f"回撤 {dd:.1%} 触发熔断，冷却 {c.drawdown_cooldown_days} 天")
            )
            return True
        return False

    def _reject(self, symbol: str, reason: str, ctx: RiskContext) -> RiskDecision:
        self.events.append(RiskEvent(None, "reject", symbol=symbol, reason=reason))
        return RiskDecision(False, reason)

    def drain_event_dicts(self) -> List[dict]:
        out = [
            {"date": str(e.date) if e.date is not None else "", "kind": e.kind,
             "symbol": e.symbol, "reason": e.reason}
            for e in self.events
        ]
        self.events.clear()
        return out
