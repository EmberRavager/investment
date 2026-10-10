"""akshare 数据源（默认）。成熟开源库，非手写爬虫。"""

from __future__ import annotations

import pandas as pd

from .base import DataProvider


class AkshareProvider(DataProvider):
    name = "akshare"

    def fetch_daily(self, symbol: str, kind: str, start: str, end: str, adjust: str) -> pd.DataFrame:
        import akshare as ak

        s = pd.to_datetime(start).strftime("%Y%m%d")
        e = pd.to_datetime(end).strftime("%Y%m%d")

        if kind == "stock":
            df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                    start_date=s, end_date=e, adjust=adjust or "")
        elif kind == "index":
            df = ak.index_zh_a_hist(symbol=symbol, period="daily", start_date=s, end_date=e)
        else:
            raise ValueError(f"不支持的 kind: {kind}（stock / index）")

        if df is None or len(df) == 0:
            raise RuntimeError(f"akshare 未取到数据: {kind} {symbol} {start}~{end}")
        return df
