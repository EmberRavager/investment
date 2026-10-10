"""流水线：把数据 → 特征 → 标签 → 滚动回测 → 评估 → 输出 串起来。

对外两个入口：
- analyze(cfg): 返回可序列化的完整分析结果（供 API / 程序调用）；
- run(cfg):    在 analyze 基础上落盘（CSV / JSON / 图）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from .backtest import feature_importance, latest_signal, walk_forward
from .config import Config
from .data import load_prices
from .features import build_features
from .labels import make_labels
from .metrics import equity_curve, summarize


def _setup_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = [
        "PingFang SC", "Arial Unicode MS", "Heiti SC", "SimHei", "sans-serif",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def analyze(cfg: Config, verbose: bool = True) -> Dict[str, Any]:
    """跑完整分析，返回 JSON 可序列化的结果字典。"""
    # 1) 数据
    df = load_prices(cfg.data, verbose=verbose)

    # 2) 特征 & 标签
    feats = build_features(df, cfg.features)
    y_all, fwd_all = make_labels(df, cfg.labels)
    y_all = y_all.reindex(feats.index)
    fwd_all = fwd_all.reindex(feats.index)
    X_all = feats

    valid = y_all.notna()
    X = X_all[valid]
    y = y_all[valid]
    fwd = fwd_all[valid]

    if verbose:
        print(f"[pipeline] 特征矩阵: {X.shape[0]} 行 x {X.shape[1]} 列, "
              f"时间 {X.index.min().date()} ~ {X.index.max().date()}")

    # 3) 风控用的因果序列：趋势过滤 + 已实现波动率（仅用历史）
    trend = None
    vol = None
    if cfg.backtest.trend_filter:
        trend = (df["close"] > df["close"].rolling(cfg.backtest.trend_ma).mean()).astype(float)
        trend = trend.reindex(X.index)
    if cfg.backtest.vol_target > 0:
        vol = df["close"].pct_change().rolling(cfg.backtest.vol_lookback).std() * np.sqrt(252)
        vol = vol.reindex(X.index)

    # 4) 滚动回测
    result = walk_forward(
        X, y, fwd, cfg.model, cfg.backtest, trend=trend, vol=vol, verbose=verbose
    )

    # 5) 指标
    metrics = summarize(
        result.proba, y, result.strategy_ret, result.benchmark_ret,
        result.position, cfg.backtest.prob_threshold,
    )

    # 6) 最新信号
    model, last_date, last_prob, signal = latest_signal(X_all, y_all, cfg.model, cfg.backtest)
    imp = feature_importance(model, list(X_all.columns))

    # 7) 组装结果
    idx = result.proba.index
    strat_eq = equity_curve(result.strategy_ret)
    bench_eq = equity_curve(result.benchmark_ret)

    series = {
        "dates": [d.strftime("%Y-%m-%d") for d in idx],
        "close": _round_list(df["close"].reindex(idx)),
        "proba": _round_list(result.proba),
        "position": _round_list(result.position, 4),
        "strategy_nav": _round_list(strat_eq, 4),
        "benchmark_nav": _round_list(bench_eq, 4),
    }

    summary = {
        "symbol": cfg.data.symbol,
        "kind": cfg.data.kind,
        "model": cfg.model.name,
        "last_date": last_date.strftime("%Y-%m-%d"),
        "last_prob": round(float(last_prob), 4),
        "signal": signal,
        "config": cfg.to_dict(),
        "metrics": metrics,
        "feature_importance": (
            {k: round(float(v), 4) for k, v in imp.head(20).items()} if imp is not None else {}
        ),
        "n_features": int(X_all.shape[1]),
    }

    out = {"summary": summary, "series": series}
    if verbose:
        _print_summary(out)
    return out


def _round_list(s: pd.Series, nd: int = 6):
    return [None if pd.isna(v) else round(float(v), nd) for v in s.to_numpy()]


def run(cfg: Config, verbose: bool = True) -> Dict[str, Any]:
    """分析 + 落盘。"""
    out_dir = Path(cfg.output.dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    out = analyze(cfg, verbose=verbose)
    summary = out["summary"]
    series = out["series"]

    preds = pd.DataFrame({
        "date": series["dates"],
        "close": series["close"],
        "proba": series["proba"],
        "position": series["position"],
    })
    if cfg.output.save_predictions:
        preds.to_csv(out_dir / "predictions.csv", index=False, encoding="utf-8-sig")

    fi = summary.get("feature_importance", {})
    if fi:
        pd.Series(fi).to_csv(out_dir / "feature_importance.csv", encoding="utf-8-sig")

    (out_dir / "config.json").write_text(
        json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "metrics.json").write_text(
        json.dumps(summary["metrics"], ensure_ascii=False, indent=2, default=float),
        encoding="utf-8",
    )
    (out_dir / "result.json").write_text(
        json.dumps(out, ensure_ascii=False, default=float), encoding="utf-8"
    )

    if cfg.output.plot:
        _replot(cfg, out_dir, out)
    return summary


def _replot(cfg: Config, out_dir: Path, out: Dict[str, Any]) -> None:
    """用序列数据重绘报告图（避免重复计算）。"""
    import pandas as pd

    plt = _setup_matplotlib()
    s = out["series"]
    d = pd.to_datetime(s["dates"])
    fig, axes = plt.subplots(2, 1, figsize=(13, 9))

    axes[0].plot(d, s["strategy_nav"], label="策略", color="#d62728")
    axes[0].plot(d, s["benchmark_nav"], label="买入持有", color="#1f77b4", alpha=0.8)
    axes[0].set_title(f"{cfg.data.symbol} 策略 vs 基准（净值）")
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    axes[1].plot(d, s["proba"], label="多头概率", color="#2ca02c")
    axes[1].axhline(cfg.backtest.prob_threshold, color="gray", ls="--",
                    label=f"开仓阈值 {cfg.backtest.prob_threshold}")
    axes[1].set_title("预测概率")
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_dir / "report.png", dpi=120)
    plt.close(fig)


def _print_summary(out: Dict[str, Any]) -> None:
    s = out["summary"]
    clf = s["metrics"]["classification"]
    st = s["metrics"]["strategy"]
    bm = s["metrics"]["benchmark"]
    print("\n" + "=" * 56)
    print(f"标的一 {s['symbol']}   模型一 {s['model']}")
    print("-" * 56)
    print(f"样本数 {clf.get('n_samples', 0)}   上涨基准率 {clf.get('base_rate_up', float('nan')):.3f}")
    print(f"准确率 {clf.get('accuracy', float('nan')):.4f}   "
          f"AUC {clf.get('roc_auc', float('nan')):.4f}   "
          f"精确率 {clf.get('precision', float('nan')):.4f}   "
          f"召回率 {clf.get('recall', float('nan')):.4f}")
    print("-" * 56)
    print(f"策略  总收益 {st.get('total_return', 0):.2%}   "
          f"年化 {st.get('annual_return', 0):.2%}   "
          f"夏普 {st.get('sharpe', float('nan')):.2f}   "
          f"Calmar {st.get('calmar', float('nan')):.2f}   "
          f"最大回撤 {st.get('max_drawdown', 0):.2%}")
    print(f"基准  总收益 {bm.get('total_return', 0):.2%}   "
          f"年化 {bm.get('annual_return', 0):.2%}   "
          f"夏普 {bm.get('sharpe', float('nan')):.2f}   "
          f"Calmar {bm.get('calmar', float('nan')):.2f}   "
          f"最大回撤 {bm.get('max_drawdown', 0):.2%}")
    print(f"进场次数 {st.get('num_trades', 0)}   持仓占比 {st.get('exposure', 0):.2%}")
    print("-" * 56)
    print(f"最新交易日 {s['last_date']}   多头概率 {s['last_prob']:.4f}   → 信号: {s['signal']}")
    print("=" * 56)
