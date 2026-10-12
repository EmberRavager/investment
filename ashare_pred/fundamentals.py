"""财务因子（point-in-time，按公告披露日对齐）。

关键：严格按「公告日」把财报值并入交易日，任何交易日只能看到**已公告**的财报，
杜绝未来函数（防止用未公布的下季度数据）。

当前支持：扣非净利润同比增长率（profit_growth，单位 %）。
数据源：akshare `stock_yjbb_em`（业绩报表，含最新公告日期）。
取不到时明确报错（调用方据此拒绝使用财务因子的策略），绝不静默忽略。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from .providers.base import no_proxy_env

_CACHE_DIR = Path("data/cache/fundamentals")

#: 财务字段 -> 数据列名（akshare 业绩报表）
PROFIT_GROWTH_COL = "扣非净利润同比增长率"
_ANN_DATE_COL = "最新公告日期"


def _quarters(years_back: int = 6) -> list[str]:
    """最近 N 年的季度报告期，如 20241231。"""
    import datetime

    today = datetime.date.today()
    out = []
    for y in range(today.year - years_back, today.year + 1):
        for md in ("0331", "0630", "0930", "1231"):
            period = f"{y}{md}"
            if period <= today.strftime("%Y%m%d"):
                out.append(period)
    return out


def _fetch_akshare(symbol: str) -> pd.DataFrame:
    import akshare as ak

    rows = []
    with no_proxy_env():
        for period in _quarters():
            try:
                df = ak.stock_yjbb_em(date=period)
            except Exception:  # noqa: BLE001 — 单个季度失败跳过
                continue
            if df is None or len(df) == 0 or "股票代码" not in df.columns:
                continue
            sub = df[df["股票代码"].astype(str).str.zfill(6) == symbol]
            if len(sub) == 0:
                continue
            if PROFIT_GROWTH_COL in sub.columns and _ANN_DATE_COL in sub.columns:
                rows.append({
                    "announce_date": sub[_ANN_DATE_COL].iloc[0],
                    "profit_growth": pd.to_numeric(sub[PROFIT_GROWTH_COL].iloc[0], errors="coerce"),
                })

    if not rows:
        raise RuntimeError(f"{symbol} 未取到财务（业绩报表）数据")
    out = pd.DataFrame(rows)
    out["announce_date"] = pd.to_datetime(out["announce_date"])
    out = out.dropna(subset=["announce_date"]).sort_values("announce_date")
    out = out.drop_duplicates("announce_date", keep="last").set_index("announce_date")
    return out


def load_fundamentals(symbol: str, verbose: bool = False) -> pd.DataFrame:
    """返回按公告日(升序)索引、含 profit_growth 的 DataFrame。失败抛异常。"""
    cache = _CACHE_DIR / f"{symbol}.parquet"
    if cache.exists():
        try:
            return pd.read_parquet(cache)
        except Exception:  # noqa: BLE001
            pass

    df = _fetch_akshare(symbol)
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache)
    except Exception:  # noqa: BLE001
        pass
    if verbose:
        print(f"[fundamentals] {symbol}: {len(df)} 期财报")
    return df


def attach_fundamentals(feats: pd.DataFrame, fundamentals: pd.DataFrame) -> pd.DataFrame:
    """把财务值按公告日 asof 并入交易日（当日只能看到已公告值）。"""
    if fundamentals is None or len(fundamentals) == 0:
        return feats
    out = feats.sort_index()
    fund = fundamentals.sort_index()
    merged = pd.merge_asof(
        out, fund, left_index=True, right_index=True, direction="backward",
    )
    return merged
