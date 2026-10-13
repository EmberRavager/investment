"""实盘交易接口抽象（未接入券商时的骨架与就绪检查）。

设计：实盘必须与回测/模拟盘**共用同一套撮合规则与风控**；接入券商前，
仅提供接口契约与"就绪清单"，任何实盘下单调用都明确拒绝，避免误操作。
"""

from __future__ import annotations

from typing import Any, Dict, List

from .broker import Broker

#: 接入实盘前必须完成的事项
LIVE_CHECKLIST: List[str] = [
    "券商交易接口（XTP / 华鑫奇点 / CTP证券等）已接入并完成仿真测试",
    "资金与持仓对账通路打通（开市前/收市后自动对账）",
    "订单状态回报、部分成交、撤单处理完整实现",
    "重复订单校验、最大委托/撤单笔数与频率限制",
    "交易授权（人工确认或额度授权）与操作审计日志",
    "紧急停止（kill switch）与异常熔断",
    "实盘与回测/模拟共用同一套风控与撮合规则（避免逻辑分叉）",
]


class LiveNotReadyError(RuntimeError):
    pass


def live_readiness() -> Dict[str, Any]:
    """返回实盘就绪状态（当前恒为未就绪，附阻塞项与说明）。"""
    return {
        "ready": False,
        "blockers": LIVE_CHECKLIST,
        "note": "当前仅支持研究与模拟盘；实盘接入需完成上述事项并通过模拟盘验证。",
    }


class LiveBroker(Broker):
    """实盘券商适配器占位。未接入前任何实例化/下单都明确拒绝。"""

    def __init__(self, *args, **kwargs):
        raise LiveNotReadyError(
            "实盘接口尚未接入：请先完成 live_readiness() 列出的就绪事项。"
        )
