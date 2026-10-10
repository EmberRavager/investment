"""绩效与分类指标。"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def classification_metrics(
    proba: pd.Series, y: pd.Series, threshold: float = 0.5
) -> Dict[str, float]:
    """在可评估的样本上给出分类指标。"""
    mask = proba.notna() & y.notna()
    if mask.sum() < 2:
        return {}
    p = proba[mask].to_numpy()
    yy = y[mask].to_numpy()
    pred = (p >= threshold).astype(int)

    from sklearn.metrics import (
        accuracy_score, f1_score, precision_score, recall_score, roc_auc_score,
    )

    out = {
        "n_samples": int(mask.sum()),
        "accuracy": float(accuracy_score(yy, pred)),
        "precision": float(precision_score(yy, pred, zero_division=0)),
        "recall": float(recall_score(yy, pred, zero_division=0)),
        "f1": float(f1_score(yy, pred, zero_division=0)),
        "base_rate_up": float(yy.mean()),
    }
    if len(np.unique(yy)) > 1:
        out["roc_auc"] = float(roc_auc_score(yy, p))
    else:
        out["roc_auc"] = float("nan")
    return out


def equity_curve(returns: pd.Series) -> pd.Series:
    return (1.0 + returns.fillna(0.0)).cumprod()


def strategy_metrics(
    strategy_ret: pd.Series,
    position: pd.Series,
    periods_per_year: int = 252,
) -> Dict[str, float]:
    ret = strategy_ret.fillna(0.0)
    equity = equity_curve(ret)
    n = len(ret)
    if n == 0:
        return {}

    total_return = float(equity.iloc[-1] - 1.0)
    years = n / periods_per_year
    annual_return = float(equity.iloc[-1] ** (1 / years) - 1.0) if years > 0 else float("nan")

    std = ret.std(ddof=0)
    sharpe = float(ret.mean() / std * np.sqrt(periods_per_year)) if std > 1e-12 else float("nan")

    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    max_dd = float(drawdown.min())

    active = ret[position.fillna(0.0) > 0]
    win_rate = float((active > 0).mean()) if len(active) else float("nan")

    calmar = float(annual_return / abs(max_dd)) if max_dd < -1e-9 else float("nan")

    # 交易次数按"空仓<->持仓"切换计（连续仓位的变化不算交易）
    on = (position.fillna(0.0) > 1e-9).astype(int)
    entries = int((on.diff() == 1).sum())

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "sharpe": sharpe,
        "calmar": calmar,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "num_trades": entries,
        "exposure": float((position.fillna(0.0) > 0).mean()),
    }


def summarize(
    proba: pd.Series,
    y: pd.Series,
    strategy_ret: pd.Series,
    bench_ret: pd.Series,
    position: pd.Series,
    threshold: float,
    periods_per_year: int = 252,
) -> Dict[str, Dict[str, float]]:
    return {
        "classification": classification_metrics(proba, y, threshold=0.5),
        "strategy": strategy_metrics(strategy_ret, position, periods_per_year),
        "benchmark": strategy_metrics(bench_ret.fillna(0.0), pd.Series(1.0, index=bench_ret.index),
                                      periods_per_year),
    }
