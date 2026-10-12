"""事件驱动回测 / 模拟撮合引擎。

把"策略产生的目标权重"变成"符合 A 股规则的真实成交"：

- 信号在 T 日收盘产生，T+1 开盘按可成交价撮合（信号与执行时点分离，杜绝未来函数）；
- T+1 交收：当日买入次日才可卖；
- 涨跌停：一字涨停买不进、跌停卖不出；停牌不成交；
- 100 股整手申报，科创板 200 股起；卖出允许清仓零股；
- 佣金（含最低 5 元）、印花税（卖出）、滑点；
- 止损：以「收盘价」判定（≤ 成本×(1-止损)），**次日开盘**执行，不保证按止损价成交；
- 回撤熔断：以组合权益相对历史峰值的回撤判定，触发后清仓并进入冷却；
- 每笔订单先过独立 RiskEngine：现金、最小买入数量、单股/总仓位、单日买入额度、流动性、波动率；
- 每笔成交/被拒订单都带：策略版本、信号日、触发依据（条件+实际值），全程可追溯。

同一引擎用于回测与模拟盘，实盘阶段只需替换撮合通道。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from ..risk.engine import RiskConfig, RiskContext, RiskEngine
from .account import Account, Trade
from .costs import TradingCost, apply_slippage
from . import rules


@dataclass
class EngineConfig:
    initial_cash: float = 3000.0
    t_plus_1: bool = True
    cost: TradingCost = field(default_factory=TradingCost)
    risk: RiskConfig = field(default_factory=RiskConfig)
    names: Dict[str, str] = field(default_factory=dict)
    turnover_window: int = 20          # 流动性：日均成交额窗口
    vol_window: int = 20               # 异常波动：已实现波动率窗口
    stop_loss: float = 0.0             # 止损比例（0=关闭）；收盘判定、次日开盘执行
    strategy_version: object = None    # 策略版本（写入每笔成交，便于追溯）
    strategy_name: str = ""


@dataclass
class EngineResult:
    equity: pd.Series
    returns: pd.Series
    exposure: pd.Series
    trades: List[Trade]
    snapshots: List[dict]
    risk_events: List[dict]
    skips: List[dict]
    account: Account
    names: Dict[str, str]


@dataclass
class _Bar:
    open: float
    high: float
    low: float
    close: float
    volume: float


class Broker:
    def __init__(self, cfg: EngineConfig):
        self.cfg = cfg
        self.account = Account(initial_cash=cfg.initial_cash)
        self.account.names = dict(cfg.names)
        self.risk = RiskEngine(cfg.risk)
        self.trades: List[Trade] = []
        self.skips: List[dict] = []
        self.daily_bought = 0.0
        self._prices: Dict[str, pd.DataFrame] = {}
        self._evidence: Dict[Tuple[object, str], dict] = {}
        self._stop_exit: Set[str] = set()   # 次日强制卖出（止损）

    # ---- 主流程 ----
    def run(
        self,
        prices: Dict[str, pd.DataFrame],
        targets: Dict[object, Dict[str, float]],
        evidence: Optional[Dict[Tuple[object, str], dict]] = None,
    ) -> EngineResult:
        self._prices = prices
        self._evidence = evidence or {}
        names = {s: self.cfg.names.get(s, s) for s in prices}
        self.account.names = names

        cal = sorted({d for df in prices.values() for d in df.index})
        turnover, vol = _precompute(prices, self.cfg.turnover_window, self.cfg.vol_window)

        prev_close: Dict[str, float] = {}
        equity_hist: List[float] = []
        exposure_hist: List[float] = []
        snapshots: List[dict] = []
        pending: Optional[Tuple[object, Dict[str, float]]] = None

        for day in cal:
            closes = {s: _close(prices[s], day) for s in prices}

            if self.cfg.t_plus_1:
                self.account.settle()
            self.daily_bought = 0.0

            forced = set(self._stop_exit)
            self._stop_exit = set()

            halted = self.risk.monitor(day, self.account.equity(), max([self.cfg.initial_cash] + equity_hist))
            if pending is not None:
                sday, tgt = pending
                self._rebalance({} if halted else tgt, day, prev_close, turnover, vol, sday, forced)
            elif (halted or forced) and self.account.positions:
                self._rebalance({}, day, prev_close, turnover, vol, None, forced)

            self.account.mark_to_market({s: p for s, p in closes.items() if np.isfinite(p)})
            equity_hist.append(self.account.equity())
            exposure_hist.append(self.account.exposure())
            snapshots.append(self.account.snapshot(day, closes))

            # 收盘判定止损 -> 次日执行
            if self.cfg.stop_loss > 0:
                for sym, pos in self.account.positions.items():
                    px = closes.get(sym, np.nan)
                    if pos.cost_price > 0 and np.isfinite(px) and px <= pos.cost_price * (1 - self.cfg.stop_loss):
                        self._stop_exit.add(sym)

            pending = None
            if day in targets:
                pending = (day, targets[day])
            prev_close = {s: p for s, p in closes.items() if np.isfinite(p)}

        idx = pd.DatetimeIndex(cal)
        equity = pd.Series(equity_hist, index=idx) / self.cfg.initial_cash
        return EngineResult(
            equity=equity,
            returns=equity.pct_change().fillna(0.0),
            exposure=pd.Series(exposure_hist, index=idx),
            trades=self.trades,
            snapshots=snapshots,
            risk_events=self.risk.drain_event_dicts(),
            skips=self.skips,
            account=self.account,
            names=names,
        )

    # ---- 调仓 ----
    def _rebalance(self, target, day, prev_close, turnover, vol, signal_day, forced: Set[str]) -> None:
        self.account.mark_to_market(self._open_prices(day))
        c = self.cfg.risk

        # 1) 卖出（先卖释放现金）：调仓卖出 + 强制止损
        for sym in list(self.account.positions.keys()):
            pos = self.account.positions[sym]
            px = self._open(sym, day)
            if not np.isfinite(px) or px <= 0:
                continue
            is_stop = sym in forced
            desired_w = 0.0 if is_stop else float(target.get(sym, 0.0))
            equity = self.account.equity()
            target_qty = rules.round_lot(desired_w * equity / px, sym)
            delta = pos.qty - target_qty
            if delta <= 0:
                continue
            sell_qty = pos.available_qty if desired_w <= 1e-9 else min(delta, pos.available_qty)
            if sell_qty <= 0:
                continue
            reason = "止损卖出" if is_stop else "调仓卖出"
            self._execute(sym, "sell", int(sell_qty), day, prev_close, turnover, vol, reason, signal_day)

        # 2) 买入：先算清是哪条约束卡住，给出精确原因
        for sym, w in target.items():
            if w <= 1e-9 or sym in forced:
                continue
            px = self._open(sym, day)
            if not np.isfinite(px) or px <= 0:
                self._skip(day, sym, "无有效开盘价/停牌", "buy", np.nan, signal_day)
                continue
            equity = self.account.equity()
            held = self.account.positions[sym].qty if sym in self.account.positions else 0
            desired_qty = rules.round_lot(w * equity / px, sym)

            lot = rules.lot_size(sym)
            one_lot_cost = px * lot
            pos_cap_value = max(0.0, c.max_position_per_stock * equity - held * px)
            exp_room_value = max(0.0, (c.max_total_exposure - self.account.exposure()) * equity)
            cash_value = self.account.cash

            if desired_qty <= held:
                if desired_qty == 0 and held == 0:
                    self._skip(day, sym, _binding_reason(pos_cap_value, exp_room_value, cash_value, one_lot_cost),
                               "buy", px, signal_day)
                continue

            budget = min(pos_cap_value, exp_room_value, cash_value)
            if budget < one_lot_cost - 1e-9:
                self._skip(day, sym, _binding_reason(pos_cap_value, exp_room_value, cash_value, one_lot_cost),
                           "buy", px, signal_day)
                continue

            qty_cap = rules.round_lot(pos_cap_value / px, sym)
            exp_cap = rules.round_lot(exp_room_value / px, sym)
            cash_cap = rules.round_lot(cash_value * 0.999 / px, sym)
            qty = min(desired_qty - held, qty_cap, exp_cap, cash_cap)
            if qty <= 0:
                self._skip(day, sym, "不足一手，跳过交易", "buy", px, signal_day)
                continue
            self._execute(sym, "buy", int(qty), day, prev_close, turnover, vol, "调仓买入", signal_day)

    # ---- 撮合 ----
    def _execute(self, sym, side, qty, day, prev_close, turnover, vol, reason, signal_day=None) -> None:
        bar = _bar(self._prices[sym], day)
        fill = rules.fillable_open(bar, prev_close.get(sym), sym, side, is_st=False)
        if fill is None:
            self._skip(day, sym, "停牌/涨跌停，无法成交", side, np.nan, signal_day, qty)
            return
        price = rules.round_price(apply_slippage(fill, side, self.cfg.cost.slippage), sym)
        amount = qty * price

        if side == "buy":
            ctx = RiskContext(
                equity=self.account.equity(),
                peak_equity=self.account.equity(),
                cash=self.account.cash,
                weight=self.account.weight(sym),
                total_exposure=self.account.exposure(),
                daily_bought=self.daily_bought,
                turnover=_lookup(turnover, sym, day),
                volatility=_lookup(vol, sym, day),
            )
            decision = self.risk.check_order(sym, side, qty, price, ctx)
            if not decision.approved:
                self._skip(day, sym, decision.reason, side, price, signal_day, qty)
                return

        comm, stamp, transfer = self.cfg.cost.breakdown(side, amount)
        fee = comm + stamp + transfer
        self.trades.append(Trade(
            date=day, symbol=sym, name=self.account.names.get(sym, sym), side=side,
            qty=qty, price=price, amount=amount, commission=comm, stamp_tax=stamp,
            slippage_cost=abs(price - fill) * qty, total_fee=fee, reason=reason,
            signal_date=signal_day, strategy_version=self.cfg.strategy_version,
            strategy_name=self.cfg.strategy_name,
            evidence=self._evidence.get((signal_day, sym)) if signal_day is not None else None,
        ))
        if side == "buy":
            self.account.apply_buy(sym, qty, price, fee)
            self.daily_bought += amount
        else:
            self.account.apply_sell(sym, qty, price, fee)

    def _skip(self, day, sym, reason, side="buy", price=np.nan, signal_day=None, qty=0) -> None:
        self.skips.append({
            "date": str(day),
            "signal_date": str(signal_day) if signal_day is not None else "",
            "symbol": sym,
            "name": self.account.names.get(sym, sym),
            "side": side,
            "qty": int(qty) if qty else 0,
            "price": None if not np.isfinite(price) else float(price),
            "status": "已拒绝",
            "strategy_version": self.cfg.strategy_version,
            "reason": reason,
            "evidence": self._evidence.get((signal_day, sym)) if signal_day is not None else None,
        })

    # ---- 价格读取 ----
    def _open(self, sym, day) -> float:
        return _open(self._prices[sym], day)

    def _open_prices(self, day) -> Dict[str, float]:
        return {s: self._open(s, day) for s in self._prices}


# ---- 辅助 ----
def _binding_reason(pos_cap: float, exp_room: float, cash: float, one_lot: float) -> str:
    eps = 1e-9
    if pos_cap <= exp_room + eps and pos_cap <= cash + eps:
        return f"超出单股仓位限制：单股上限 {pos_cap:.0f} 元 < 一手约 {one_lot:.0f} 元"
    if exp_room <= cash + eps:
        return f"超出总仓位限制：剩余额度 {exp_room:.0f} 元 < 一手约 {one_lot:.0f} 元"
    return f"资金不足：可用 {cash:.0f} 元 < 一手约 {one_lot:.0f} 元"


def _row(df: pd.DataFrame, day):
    if day not in df.index:
        return None
    return df.loc[day]


def _num(row, col) -> float:
    if row is None:
        return float("nan")
    v = row.get(col, np.nan) if hasattr(row, "get") else np.nan
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _open(df, day) -> float:
    return _num(_row(df, day), "open")


def _close(df, day) -> float:
    return _num(_row(df, day), "close")


def _bar(df, day) -> Optional[_Bar]:
    row = _row(df, day)
    if row is None:
        return None
    return _Bar(
        open=_num(row, "open"), high=_num(row, "high"),
        low=_num(row, "low"), close=_num(row, "close"), volume=_num(row, "volume"),
    )


def _lookup(table: Optional[pd.DataFrame], sym: str, day) -> float:
    if table is None or sym not in table.columns or day not in table.index:
        return float("nan")
    try:
        return float(table.at[day, sym])
    except (KeyError, TypeError, ValueError):
        return float("nan")


def _precompute(prices, turn_window, vol_window):
    turnover_data, vol_data = {}, {}
    for sym, df in prices.items():
        if "amount" in df.columns:
            turnover_data[sym] = df["amount"].rolling(turn_window, min_periods=1).mean()
        if "close" in df.columns:
            ret = df["close"].pct_change()
            vol_data[sym] = ret.rolling(vol_window, min_periods=2).std() * np.sqrt(252)
    turnover = pd.DataFrame(turnover_data) if turnover_data else None
    vol = pd.DataFrame(vol_data) if vol_data else None
    return turnover, vol
