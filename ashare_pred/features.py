"""特征工程：基于 ta 库生成技术指标，全部严格使用历史信息（无前视）。

价格类指标统一转成相对 close 的比例，保证平稳性（更适合树模型与线性模型）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import ta

from .config import FeatureConfig


def _add_price_relative(out: pd.DataFrame, close: pd.Series, col: str, series: pd.Series):
    out[col] = close / series - 1.0


def build_features(df: pd.DataFrame, cfg: FeatureConfig) -> pd.DataFrame:
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    out = pd.DataFrame(index=df.index)
    ind = set(cfg.indicators)

    if "returns" in ind:
        out["logret_1"] = np.log(close / close.shift(1))
        for w in cfg.windows:
            out[f"mom_{w}"] = close / close.shift(w) - 1.0
            out[f"vol_{w}"] = out["logret_1"].rolling(w).std()

    if "sma" in ind:
        for w in cfg.windows:
            _add_price_relative(out, close, f"sma_{w}", ta.trend.sma_indicator(close, w, fillna=False))

    if "ema" in ind:
        for w in cfg.windows:
            _add_price_relative(out, close, f"ema_{w}", ta.trend.ema_indicator(close, w, fillna=False))

    if "rsi" in ind:
        for w in cfg.windows:
            out[f"rsi_{w}"] = ta.momentum.rsi(close, w, fillna=False)

    if "macd" in ind:
        out["macd_diff"] = ta.trend.macd_diff(close, fillna=False) / close
        out["macd_signal"] = ta.trend.macd_signal(close, fillna=False) / close
        out["macd"] = ta.trend.macd(close, fillna=False) / close

    if "atr" in ind:
        atr = ta.volatility.average_true_range(high, low, close, window=14, fillna=False)
        out["atr_14"] = atr / close

    if "bollinger" in ind:
        out["bb_pband"] = ta.volatility.bollinger_pband(close, fillna=False)
        out["bb_wband"] = ta.volatility.bollinger_wband(close, fillna=False)

    if "obv" in ind:
        obv = ta.volume.on_balance_volume(close, volume, fillna=False)
        out["obv_slope_20"] = obv.rolling(20).apply(
            lambda s: np.polyfit(np.arange(len(s)), s, 1)[0] / (abs(s).mean() + 1e-9),
            raw=True,
        )

    if "roc" in ind:
        for w in cfg.windows:
            out[f"roc_{w}"] = ta.momentum.roc(close, w, fillna=False)

    if "volume" in ind:
        logv = np.log(volume.replace(0, np.nan))
        out["vol_chg_1"] = logv.diff()
        for w in cfg.windows:
            out[f"vratio_{w}"] = volume / volume.rolling(w).mean() - 1.0

    out = out.replace([np.inf, -np.inf], np.nan)
    if cfg.dropna:
        out = out.dropna()
    return out
