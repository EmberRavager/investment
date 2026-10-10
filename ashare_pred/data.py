"""数据层：通过可插拔数据源（akshare / MCP）拉取行情，本地 parquet 缓存。

统一输出列：date(index, DatetimeIndex), open, high, low, close, volume, amount,
pct_chg, turnover。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from .config import DataConfig
from .providers import build_provider, normalize


def _cache_path(cfg: DataConfig) -> Path:
    key = json.dumps(
        {
            "provider": cfg.provider,
            "symbol": cfg.symbol,
            "kind": cfg.kind,
            "adjust": cfg.adjust,
            "start": cfg.start,
            "end": cfg.end,
        },
        sort_keys=True,
    )
    digest = hashlib.md5(key.encode()).hexdigest()[:10]
    name = f"{cfg.provider}_{cfg.kind}_{cfg.symbol}_{cfg.adjust or 'raw'}_{digest}.parquet"
    return Path(cfg.cache_dir) / name


def load_prices(cfg: DataConfig, verbose: bool = True) -> pd.DataFrame:
    """读取（或拉取并缓存）日线行情，返回按日期升序的 DataFrame。"""
    path = _cache_path(cfg)
    if cfg.use_cache and path.exists():
        if verbose:
            print(f"[data] 命中缓存 {path}")
        return pd.read_parquet(path)

    provider = build_provider(cfg)
    if verbose:
        print(f"[data] 数据源={provider.name} 拉取 {cfg.kind} {cfg.symbol} {cfg.start}~{cfg.end} ...")
    raw = provider.fetch_daily(cfg.symbol, cfg.kind, cfg.start, cfg.end, cfg.adjust)
    df = normalize(raw)

    if cfg.use_cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
        if verbose:
            print(f"[data] 已缓存 -> {path}")
    return df
