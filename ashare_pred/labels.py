"""标签构造：预测未来 N 根 K 线的涨跌方向。

注意：标签天然用到未来价格，因此只能在训练/回测时按时间切分，
绝不能让未来标签进入训练特征。回测引擎里已用 embargo 隔离带处理。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import LabelConfig


def forward_return(df: pd.DataFrame, horizon: int) -> pd.Series:
    """未来 horizon 根的收益率：close[t+h] / close[t] - 1。"""
    close = df["close"]
    return close.shift(-horizon) / close - 1.0


def make_labels(df: pd.DataFrame, cfg: LabelConfig):
    """返回 (y, fwd)。

    y    : 0/1 分类标签（超过 threshold 为 1），最后 horizon 行为 NaN；
    fwd  : 对应的未来收益率，用于计算策略真实收益。
    """
    fwd = forward_return(df, cfg.horizon)
    if cfg.method == "direction":
        y = (fwd > cfg.threshold).astype(float)
        y[fwd.isna()] = np.nan
    else:
        raise ValueError(f"暂不支持 labels.method={cfg.method}（可选 direction）")
    return y, fwd
