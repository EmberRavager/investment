"""数据源基类与归一化工具。

所有数据源统一返回：DatetimeIndex + open/high/low/close/volume(必需)，
以及可选的 amount/pct_chg/turnover。绝不把中文列名或时间戳泄漏到下游。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

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
