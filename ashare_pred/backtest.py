"""回测引擎：滚动（walk-forward）训练与预测。

核心防前视机制：
- 每个预测点 t 只用 <= t 的特征（特征本身已保证因果）；
- 训练集与测试点之间留 embargo 隔离带（默认 = 预测跨度），
  避免训练样本的标签"看到"测试期的价格；
- 训练窗口随 t 向前滚动，可设置定期重训。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from .config import BacktestConfig, CostConfig, ModelConfig
from .models import build_model


@dataclass
class BacktestResult:
    #: 每个可评估交易日的多头概率
    proba: pd.Series
    #: 仓位（0/1）
    position: pd.Series
    #: 策略每期收益（已扣成本）
    strategy_ret: pd.Series
    #: 标的每期收益（基准 = 满仓持有），与 strategy_ret 同索引
    benchmark_ret: pd.Series
    #: 最后一次训练的模型，供最新信号预测
    last_model: object


def walk_forward(
    X: pd.DataFrame,
    y: pd.Series,
    fwd_ret: pd.Series,
    model_cfg: ModelConfig,
    bt_cfg: BacktestConfig,
    trend: Optional[pd.Series] = None,
    vol: Optional[pd.Series] = None,
    verbose: bool = True,
) -> BacktestResult:
    """在特征矩阵 X 上做滚动训练，返回每期概率与策略收益。

    trend / vol 为可选的、与 X 同索引的因果序列（趋势过滤、已实现波动率）。
    """
    n = len(X)
    # 训练集与测试点之间的隔离带；config.validate 已保证 embargo >= horizon
    embargo = max(int(bt_cfg.embargo), 1)
    Xv = X.to_numpy(dtype=float)
    yv = y.to_numpy(dtype=float)
    index = X.index

    proba = pd.Series(np.nan, index=index, name="proba")
    model = None
    last_fit_at = -10 ** 9
    n_fits = 0

    start = min(bt_cfg.min_train + embargo, n)

    for i in range(start, n):
        if model is None or (i - last_fit_at) >= bt_cfg.retrain_every:
            hi = i - embargo
            lo = max(0, hi - bt_cfg.train_window)
            if hi - lo < bt_cfg.min_train:
                continue
            model = build_model(model_cfg.name, scale=model_cfg.scale, **model_cfg.params)
            model.fit(Xv[lo:hi], yv[lo:hi])
            last_fit_at = i
            n_fits += 1

        proba.iloc[i] = float(model.predict_proba(Xv[i : i + 1])[:, 1][0])

    if verbose:
        print(f"[backtest] 滚动训练次数={n_fits}，有效预测点={int(proba.notna().sum())}/{n}")

    position, strategy_ret = build_strategy(proba, fwd_ret, trend, vol, bt_cfg)
    benchmark_ret = fwd_ret.copy()

    return BacktestResult(
        proba=proba,
        position=position,
        strategy_ret=strategy_ret,
        benchmark_ret=benchmark_ret,
        last_model=model,
    )


def build_strategy(
    proba: pd.Series,
    fwd_ret: pd.Series,
    trend: Optional[pd.Series],
    vol: Optional[pd.Series],
    bt_cfg: BacktestConfig,
) -> Tuple[pd.Series, pd.Series]:
    """把概率转成仓位，叠加风控层，扣成本后得到策略收益。

    风控顺序（全部因果，只用历史信息）：
        概率阈值 -> 趋势过滤 -> 最少持有期 -> 波动率目标仓位 -> 回撤熔断
    """
    cost: CostConfig = bt_cfg.cost
    index = proba.index
    n = len(proba)

    p_v = proba.to_numpy(dtype=float)
    f_v = fwd_ret.reindex(index).to_numpy(dtype=float)
    trend_v = trend.reindex(index).to_numpy(dtype=float) if trend is not None else np.ones(n)
    vol_v = vol.reindex(index).to_numpy(dtype=float) if vol is not None else np.full(n, np.nan)

    pos = np.zeros(n)
    strat = np.zeros(n)

    equity = 1.0
    peak = 1.0
    cooldown = 0
    in_pos = False
    hold_left = 0
    prev_pos = 0.0

    for t in range(n):
        p = p_v[t]
        if np.isnan(p):
            pos[t] = 0.0
            prev_pos = 0.0
            continue

        desired = 1.0 if p >= bt_cfg.prob_threshold else 0.0
        if bt_cfg.trend_filter and not np.isnan(trend_v[t]):
            desired *= trend_v[t]

        # 最少持有期状态机
        if in_pos:
            hold_left -= 1
            if desired < 1.0 and hold_left <= 0:
                in_pos = False
        else:
            if desired >= 1.0:
                in_pos = True
                hold_left = bt_cfg.min_hold
        base = 1.0 if in_pos else 0.0

        # 波动率目标仓位：目标波动 / 已实现波动
        if bt_cfg.vol_target > 0 and not np.isnan(vol_v[t]) and vol_v[t] > 1e-6:
            scale = min(bt_cfg.vol_target / vol_v[t], bt_cfg.max_position)
        else:
            scale = 1.0
        target = base * scale

        # 回撤熔断：冷却期内强制空仓
        if cooldown > 0:
            target = 0.0
            cooldown -= 1

        # 交易成本
        turn = abs(target - prev_pos)
        sell = max(prev_pos - target, 0.0)
        tc = turn * (cost.commission + cost.slippage) + sell * cost.stamp_tax

        ret = target * (0.0 if np.isnan(f_v[t]) else f_v[t]) - tc
        pos[t] = target
        strat[t] = ret
        prev_pos = target

        equity *= 1.0 + ret
        peak = max(peak, equity)
        dd = equity / peak - 1.0
        if bt_cfg.drawdown_stop > 0 and dd <= -bt_cfg.drawdown_stop and cooldown == 0:
            cooldown = bt_cfg.drawdown_cooldown
            in_pos = False

    return pd.Series(pos, index=index, name="position"), pd.Series(strat, index=index, name="strategy_ret")


def latest_signal(
    X_all: pd.DataFrame,
    y_all: pd.Series,
    model_cfg: ModelConfig,
    bt_cfg: BacktestConfig,
):
    """用全部可用数据训练一个模型，对最新一个交易日给出信号。"""
    valid = y_all.notna()
    Xv = X_all[valid].to_numpy(dtype=float)
    yv = y_all[valid].to_numpy(dtype=float)
    model = build_model(model_cfg.name, scale=model_cfg.scale, **model_cfg.params)
    model.fit(Xv, yv)
    x_last = X_all.to_numpy(dtype=float)[-1:]
    p = float(model.predict_proba(x_last)[:, 1][0])
    signal = "买入" if p >= bt_cfg.prob_threshold else "观望"
    return model, X_all.index[-1], p, signal


def feature_importance(model, feature_names) -> Optional[pd.Series]:
    imp = getattr(model, "feature_importances_", None)
    if imp is None:
        return None
    return pd.Series(np.asarray(imp), index=feature_names).sort_values(ascending=False)
