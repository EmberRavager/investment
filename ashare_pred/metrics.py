"""绩效与分类指标。"""

from __future__ import annotations

from typing import Any, Dict, List

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


def round_trip_metrics(trades, initial_cash: float = 0.0) -> Dict[str, Any]:
    """把逐笔买/卖按 FIFO 配对成"完整回合"，给出短线真正该看的指标。

    返回：回合数、胜率、每笔平均收益、盈亏比(profit_factor)、期望值、平均持有天数、
    总费用、费用占本金比例。短线判断"每笔期望 > 成本"就看这里。
    """
    from collections import defaultdict, deque

    lots: Dict[str, deque] = defaultdict(deque)
    closed: List[Dict[str, Any]] = []
    total_fees = 0.0

    for t in trades:
        total_fees += float(getattr(t, "total_fee", 0.0) or 0.0)
        sym = t.symbol
        qty = int(t.qty)
        if qty <= 0:
            continue
        if t.side == "buy":
            lots[sym].append({"qty": qty, "price": float(t.price), "date": t.date})
        else:
            remain = qty
            while remain > 0 and lots[sym]:
                lot = lots[sym][0]
                m = min(lot["qty"], remain)
                try:
                    hold_days = int((pd.Timestamp(t.date) - pd.Timestamp(lot["date"])).days)
                except Exception:  # noqa: BLE001
                    hold_days = 0
                ret = float(t.price) / lot["price"] - 1.0 if lot["price"] else 0.0
                closed.append({
                    "symbol": sym, "entry": str(lot["date"])[:10], "exit": str(t.date)[:10],
                    "qty": m, "ret": ret, "pnl": (float(t.price) - lot["price"]) * m,
                    "hold_days": hold_days,
                })
                lot["qty"] -= m
                remain -= m
                if lot["qty"] <= 0:
                    lots[sym].popleft()

    n = len(closed)
    if n == 0:
        return {"round_trips": 0, "total_fees": round(total_fees, 2),
                "fee_pct_of_cash": round(total_fees / initial_cash * 100, 3) if initial_cash else None}

    rets = np.array([c["ret"] for c in closed])
    wins = rets[rets > 0]
    losses = rets[rets <= 0]
    gross_win = float(wins.sum())
    gross_loss = float(-losses.sum())
    return {
        "round_trips": n,
        "win_rate": float(len(wins) / n),
        "avg_return": float(rets.mean()),
        "median_return": float(np.median(rets)),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 1e-12 else None,
        "expectancy": float(rets.mean()),
        "best": float(rets.max()),
        "worst": float(rets.min()),
        "avg_hold_days": float(np.mean([c["hold_days"] for c in closed])),
        "total_pnl": float(sum(c["pnl"] for c in closed)),
        "total_fees": round(total_fees, 2),
        "fee_pct_of_cash": round(total_fees / initial_cash * 100, 3) if initial_cash else None,
    }
