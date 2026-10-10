"""akshare 数据源（默认）。

- A 股：eastmoney 优先，失败降级 sina → tencent
- 港股（kind=hk）：eastmoney → sina
多源容错，避免单一源被封时整体挂掉。
"""

from __future__ import annotations

import pandas as pd

from .base import DataProvider, no_proxy_env


def _prefix(symbol: str, kind: str) -> str:
    """给纯数字代码加交易所前缀，供 sina / tencent 接口使用。"""
    symbol = str(symbol)
    if kind == "hk":
        return "hk" + symbol.zfill(5)
    if kind == "index":
        return ("sh" if symbol.startswith(("000", "999")) else "sz") + symbol
    if symbol.startswith(("6", "9")):
        return "sh" + symbol
    if symbol.startswith(("4", "8")):
        return "bj" + symbol
    return "sz" + symbol


def _slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if df is None or len(df) == 0:
        raise RuntimeError("空数据")
    if "date" not in df.columns:
        df = df.reset_index()
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    m = (df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
    return df[m]


class AkshareProvider(DataProvider):
    name = "akshare"

    def fetch_daily(self, symbol: str, kind: str, start: str, end: str, adjust: str) -> pd.DataFrame:
        import akshare as ak

        s = pd.to_datetime(start).strftime("%Y%m%d")
        e = pd.to_datetime(end).strftime("%Y%m%d")
        adj = adjust or ""
        errors = []

        with no_proxy_env():
            if kind == "hk":
                df = self._fetch_hk(ak, symbol, start, end, adj, errors)
            else:
                df = self._fetch_a(ak, symbol, kind, s, e, adj, errors)

        if df is not None and len(df) > 0:
            return df
        raise RuntimeError(
            f"akshare 所有数据源均失败 {kind} {symbol} {start}~{end}：" +
            "；".join(f"{n}: {m}" for n, m in errors)
        )

    # ------------------------------------------------------------------ #
    def _fetch_a(self, ak, symbol, kind, s, e, adj, errors):
        # 1) eastmoney
        try:
            if kind == "stock":
                df = ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                        start_date=s, end_date=e, adjust=adj)
            else:
                df = ak.index_zh_a_hist(symbol=symbol, period="daily", start_date=s, end_date=e)
            if df is not None and len(df) > 0:
                return df
            errors.append(("eastmoney", "空数据"))
        except Exception as exc:  # noqa: BLE001
            errors.append(("eastmoney", f"{type(exc).__name__}: {str(exc)[:80]}"))

        # 2) sina
        try:
            ps = _prefix(symbol, kind)
            df = ak.stock_zh_a_daily(symbol=ps, adjust=adj) if kind == "stock" \
                else ak.stock_zh_index_daily(symbol=ps)
            df = _slice(df, pd.to_datetime(s), pd.to_datetime(e))
            if len(df) > 0:
                return df
            errors.append(("sina", "空数据"))
        except Exception as exc:  # noqa: BLE001
            errors.append(("sina", f"{type(exc).__name__}: {str(exc)[:80]}"))

        # 3) tencent
        try:
            df = ak.stock_zh_a_hist_tx(symbol=_prefix(symbol, kind), adjust=adj)
            df = _slice(df, pd.to_datetime(s), pd.to_datetime(e))
            if len(df) > 0:
                return df
            errors.append(("tencent", "空数据"))
        except Exception as exc:  # noqa: BLE001
            errors.append(("tencent", f"{type(exc).__name__}: {str(exc)[:80]}"))

        return None

    def _fetch_hk(self, ak, symbol, start, end, adj, errors):
        sym = str(symbol).zfill(5)
        s = pd.to_datetime(start).strftime("%Y%m%d")
        e = pd.to_datetime(end).strftime("%Y%m%d")
        # 1) eastmoney
        try:
            df = ak.stock_hk_hist(symbol=sym, period="daily", start_date=s, end_date=e, adjust=adj)
            if df is not None and len(df) > 0:
                return df
            errors.append(("eastmoney-hk", "空数据"))
        except Exception as exc:  # noqa: BLE001
            errors.append(("eastmoney-hk", f"{type(exc).__name__}: {str(exc)[:80]}"))
        # 2) sina
        try:
            df = ak.stock_hk_daily(symbol=sym, adjust=adj)
            df = _slice(df, pd.to_datetime(start), pd.to_datetime(end))
            if len(df) > 0:
                return df
            errors.append(("sina-hk", "空数据"))
        except Exception as exc:  # noqa: BLE001
            errors.append(("sina-hk", f"{type(exc).__name__}: {str(exc)[:80]}"))
        return None
