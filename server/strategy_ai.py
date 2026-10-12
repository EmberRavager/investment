"""自然语言 -> 结构化策略规格（AI 辅助，确定性校验）。

- 有 DEEPSEEK_API_KEY：调用 DeepSeek 输出严格 JSON 规格；
- 无 Key 或调用失败：回退到基于关键词的规则解析，保证离线可用。

无论哪种来源，产出都必须是 StrategySpec 且通过 validate_spec 校验；
AI 不参与信号计算与下单（那由 ashare_pred.strategy + engine 完成）。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from ashare_pred.strategy import Condition, DEFAULT_SPEC, StrategySpec, SPEC_SCHEMA, validate_spec

_SYSTEM = """你是 QuantPilot 的量化策略研究员。
把用户的自然语言投资想法，转换成**严格的 JSON 策略规格**，便于确定性回测。

字段说明（schema）：
{schema}

硬性要求：
1. 只输出 JSON，不要任何解释、不要 Markdown 代码块。
2. 字段名必须用英文键：name, universe, filters, entry, exit, weight, stop_loss,
   max_position_per_stock, drawdown_stop, notes。
3. 每个条件形如 {{"field": "...", "op": ">|>=|<|<=|==|cross_above|cross_below", "value": 数字或字段名}}。
4. 可用价格字段：close, open, high, low, volume, amount, ma5, ma10, ma20, ma60, ma120,
   vol_ratio, ret5, ret20。财务字段（profit_growth 等）可保留，但会被标注为需外部数据。
5. 买入条件放 entry，卖出条件放 exit，标的池放 universe；仓位相关的放 weight/stop_loss。
6. 若用户未指定股票池，universe 用 ["600519"]。
"""


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*", "", text).strip()
        text = text.rstrip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def _heuristic(text: str) -> StrategySpec:
    """关键词回退解析（离线可用）。"""
    t = text
    spec = StrategySpec.from_dict(DEFAULT_SPEC.to_dict())
    spec.notes = "由关键词规则解析（未启用 AI）。"

    if re.search(r"利润|成长|增长|业绩", t):
        spec.filters.append(Condition("profit_growth", ">", 20))
    m = re.search(r"(\d{2})\s*日?(?:均线|线)", t)
    if m:
        w = int(m.group(1))
        fa, fb = f"ma{w}", f"ma{w * 3}"
        if fb not in (5, 10, 20, 60, 120):
            fb = "ma60"
        spec.filters = [c for c in spec.filters if c.field not in ("ma5", "ma10", "ma20", "ma60", "ma120")]
        spec.filters.append(Condition(fa, ">", fb))
        spec.entry = [Condition("close", ">", fa)]
        spec.exit = [Condition("close", "<", fa)]
    if re.search(r"放量|成交量|量比|放量确认", t):
        mv = re.search(r"(\d+(?:\.\d+)?)\s*倍", t)
        spec.entry.append(Condition("vol_ratio", ">", float(mv.group(1)) if mv else 1.3))
    ms = re.search(r"止损[^\d]{0,4}(\d+(?:\.\d+)?)\s*%?", t)
    if ms:
        spec.stop_loss = float(ms.group(1)) / 100.0
    mw = re.search(r"(?:单股|仓位)[^\d]{0,6}(\d+)\s*%", t)
    if mw:
        spec.max_position_per_stock = int(mw.group(1)) / 100.0
        spec.weight = spec.max_position_per_stock
    return spec


def nl_to_spec(text: str) -> Dict[str, Any]:
    """返回 {spec, warnings, source, rationale}。"""
    spec: StrategySpec
    source = "rule"
    rationale = ""
    if _api_key():
        try:
            from server.reflect import _chat  # 复用同一 DeepSeek 客户端

            content = _chat(
                [
                    {"role": "system", "content": _SYSTEM.format(schema=json.dumps(SPEC_SCHEMA, ensure_ascii=False))},
                    {"role": "user", "content": f"用户想法：{text}"},
                ],
                temperature=0.1,
            )
            spec = StrategySpec.from_dict(_extract_json(content))
            source = "ai"
            rationale = "由 DeepSeek 解析为结构化规格。"
        except Exception as exc:  # noqa: BLE001 — 任何失败都回退
            spec = _heuristic(text)
            rationale = f"AI 解析失败，已回退规则解析（{type(exc).__name__}）。"
    else:
        spec = _heuristic(text)
        rationale = "未配置 DEEPSEEK_API_KEY，使用关键词规则解析。"

    warnings = validate_spec(spec)
    return {
        "spec": spec.to_dict(),
        "warnings": warnings,
        "source": source,
        "rationale": rationale,
        "rules": spec.summary_lines(),
    }


def _api_key() -> bool:
    import os

    return bool(os.getenv("DEEPSEEK_API_KEY"))
