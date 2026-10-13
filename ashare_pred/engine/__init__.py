"""A 股事件驱动撮合引擎（回测与模拟盘共用）。"""

from .account import Account, Position, Trade
from .broker import Broker, EngineConfig, EngineResult
from .costs import TradingCost, apply_slippage
from .live import LiveBroker, LiveNotReadyError, live_readiness
from . import rules

__all__ = [
    "Account",
    "Position",
    "Trade",
    "Broker",
    "EngineConfig",
    "EngineResult",
    "TradingCost",
    "apply_slippage",
    "LiveBroker",
    "LiveNotReadyError",
    "live_readiness",
    "rules",
]
