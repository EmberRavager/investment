"""数据源注册表。"""

from __future__ import annotations

from ..config import DataConfig
from .akshare_provider import AkshareProvider
from .baostock_provider import BaostockProvider
from .base import DataProvider, normalize
from .mcp_provider import McpProvider

__all__ = ["DataProvider", "normalize", "build_provider"]


def build_provider(cfg: DataConfig) -> DataProvider:
    name = (cfg.provider or "akshare").lower()
    if name == "akshare":
        return AkshareProvider()
    if name == "baostock":
        return BaostockProvider()
    if name == "mcp":
        return McpProvider(url=cfg.mcp_url, tool=cfg.mcp_tool, recent_n=cfg.mcp_recent_n)
    raise ValueError(f"未知数据源 provider='{cfg.provider}'（可选 akshare / baostock / mcp）")
