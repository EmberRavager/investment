"""baostock 数据源（免费，含退市股票、支持前/后复权），用于更干净的历史数据。

优点：包含退市股票历史，缓解幸存者偏差；提供指数成分（真 PIT）。
缺点：接口较慢，需 login。
"""

from __future__ import annotations

import pandas as pd

from .base import DataProvider, no_proxy_env

_ADJ = {"": "3", "none": "3", "qfq": "2", "hfq": "1"}


def bs_code(symbol: str, kind: str) -> str:
    """转成 baostock 代码，如 sh.600519 / sz.000001 / sh.000300。"""
    s = str(symbol)
    if kind == "index":
        return ("sh." if s.startswith(("000", "999")) else "sz.") + s
    if s.startswith(("6", "9")):
        return "sh." + s
    if s.startswith(("4", "8")):
        return "bj." + s
    return "sz." + s


class BaostockProvider(DataProvider):
    name = "baostock"

    def fetch_daily(self, symbol: str, kind: str, start: str, end: str, adjust: str) -> pd.DataFrame:
        import baostock as bs

        adj = _ADJ.get((adjust or "").lower(), "3")
        fields = "date,open,high,low,close,volume,amount,turn,pctChg"
        with no_proxy_env():
            lg = bs.login()
            try:
                rs = bs.query_history_k_data_plus(
                    bs_code(symbol, kind), fields,
                    start_date=str(start), end_date=str(end), frequency="d", adjustflag=adj,
                )
                if rs.error_code != "0":
                    raise RuntimeError(f"baostock 错误 {rs.error_code}: {rs.error_msg}")
                rows = []
                while rs.next():
                    rows.append(rs.get_row_data())
            finally:
                bs.logout()

        if not rows:
            raise RuntimeError(f"baostock 空数据 {symbol} {start}~{end}")
        df = pd.DataFrame(rows, columns=fields.split(","))
        df = df.rename(columns={"turn": "turnover", "pctChg": "pct_chg"})
        for c in ["open", "high", "low", "close", "volume", "amount", "turnover", "pct_chg"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df
