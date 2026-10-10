"""数据源基类与归一化工具。

所有数据源统一返回：DatetimeIndex + open/high/low/close/volume(必需)，
以及可选的 amount/pct_chg/turnover。绝不把中文列名或时间戳泄漏到下游。
"""

from __future__ import annotations

import contextlib
import os
from abc import ABC, abstractmethod

import pandas as pd


@contextlib.contextmanager
def no_proxy_env():
    """取行情数据时强制绕过代理（含 macOS 系统级代理）。

    只设 no_proxy='*' 不够：requests 不把 '*' 当通配符，且删掉环境变量后
    macOS 会退回系统代理设置。这里直接把 requests 读取代理的函数临时置空，
    保证数据请求直连；退出后恢复，不影响 DeepSeek 等需要走代理的调用。
    """
    saved_lower, saved_upper = os.environ.get("no_proxy"), os.environ.get("NO_PROXY")
    os.environ["no_proxy"] = "*"
    os.environ["NO_PROXY"] = "*"

    restore = []
    try:
        import requests.utils as ru

        restore.append((ru, "getproxies", ru.getproxies))
        ru.getproxies = lambda: {}
    except Exception:  # pragma: no cover
        pass
    try:
        import urllib.request as ur

        restore.append((ur, "getproxies", ur.getproxies))
        ur.getproxies = lambda: {}
    except Exception:  # pragma: no cover
        pass

    try:
        yield
    finally:
        for mod, attr, orig in restore:
            setattr(mod, attr, orig)
        if saved_lower is None:
            os.environ.pop("no_proxy", None)
        else:
            os.environ["no_proxy"] = saved_lower
        if saved_upper is None:
            os.environ.pop("NO_PROXY", None)
        else:
            os.environ["NO_PROXY"] = saved_upper

_CN_TO_EN = {
    "日期": "date",
    "时间": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "涨跌幅": "pct_chg",
    "换手率": "turnover",
}

_REQUIRED = ["open", "high", "low", "close", "volume"]
_KEEP = ["open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"]


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """把任意来源的行情表归一化为标准格式。"""
    if df is None or len(df) == 0:
        raise RuntimeError("数据源返回空数据")

    df = df.rename(columns=_CN_TO_EN)

    # 时间列处理：date / datetime / timestamp(ms, UTC)
    if "date" not in df.columns:
        if "datetime" in df.columns:
            df["date"] = df["datetime"]
        elif "timestamp" in df.columns:
            ts = pd.to_numeric(df["timestamp"], errors="coerce")
            # A 股日线的毫秒时间戳锚定在北京时间午夜，需换算到 Asia/Shanghai 再取日期
            df["date"] = (
                pd.to_datetime(ts, unit="ms", utc=True)
                .dt.tz_convert("Asia/Shanghai")
                .dt.normalize()
                .dt.tz_localize(None)
            )
        else:
            raise ValueError(f"无法识别时间列，实际列: {list(df.columns)}")

    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"行情缺少必需列 {missing}，实际列: {list(df.columns)}")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date").set_index("date")
    keep = [c for c in _KEEP if c in df.columns]
    return df[keep].astype(float)


class DataProvider(ABC):
    name: str = "base"

    @abstractmethod
    def fetch_daily(self, symbol: str, kind: str, start: str, end: str, adjust: str):
        """返回原始 DataFrame（未归一化亦可，由调用方 normalize）。"""
        ...
