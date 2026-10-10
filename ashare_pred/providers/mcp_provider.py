"""MCP 数据源：通过 MCP 协议连接现成的 A 股数据服务（如 akshare-one-mcp / ashare-mcp）。

默认对接 akshare-one-mcp 的 streamable-http 端点：
    uvx akshare-one-mcp --streamable-http --port 8081
端点形如 http://127.0.0.1:8081/mcp，工具 get_hist_data 返回
    [{"timestamp": ms, "open":..,"high":..,"low":..,"close":..,"volume":..}, ...]

换用 ashare-mcp 时把 data.mcp_tool 改成 "get_daily_kline" 并按需调整参数（见 README）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

import pandas as pd

from .base import DataProvider

_ADJUST = {"qfq": "qfq", "hfq": "hfq", "": "none", "none": "none"}


def _extract_rows(result: Any) -> List[Dict[str, Any]]:
    """把 MCP 工具返回解析成 list[dict]。兼容 JSON 文本 / structuredContent。"""
    # 优先 structuredContent
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict):
        for key in ("data", "result", "rows", "records"):
            if isinstance(sc.get(key), list):
                return sc[key]
        return [sc]

    texts = []
    for item in getattr(result, "content", []) or []:
        t = getattr(item, "text", None)
        if t:
            texts.append(t)
    raw = "\n".join(texts).strip()
    if not raw:
        return []

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        # 退而求其次：markdown 表格无法可靠解析，直接报错提示换源
        raise ValueError(f"MCP 返回非 JSON，无法解析（前 200 字）: {raw[:200]}")

    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("data", "result", "rows", "records"):
            if isinstance(obj.get(key), list):
                return obj[key]
        return [obj]
    return []


class McpProvider(DataProvider):
    name = "mcp"

    def __init__(self, url: str, tool: str = "get_hist_data", recent_n: int = 100000,
                 timeout: float = 30.0):
        self.url = url
        self.tool = tool
        self.recent_n = recent_n
        self.timeout = timeout

    def fetch_daily(self, symbol: str, kind: str, start: str, end: str, adjust: str) -> pd.DataFrame:
        rows = asyncio.run(self._call(symbol, start, end, adjust))
        if not rows:
            raise RuntimeError(f"MCP 未返回数据: {symbol} {start}~{end}")
        return pd.DataFrame(rows)

    async def _call(self, symbol: str, start: str, end: str, adjust: str):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        args = {
            "symbol": symbol,
            "interval": "day",
            "start_date": start,
            "end_date": end,
            "adjust": _ADJUST.get(adjust, "none"),
            "source": "eastmoney",
            "fallback": True,
            "recent_n": self.recent_n,
        }
        async with streamable_http_client(self.url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(self.tool, args)
        return _extract_rows(result)
