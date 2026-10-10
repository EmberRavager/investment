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


def _build_recommendation(df: pd.DataFrame, cfg: Config, last_prob: float, prev_holding: bool):
    """把「模型概率 + 趋势 + 当前持仓」翻译成买/持/卖/观望的明确建议。"""
    bt = cfg.backtest
    threshold = bt.prob_threshold
    trend_up = True
    if bt.trend_filter:
        ma = df["close"].rolling(bt.trend_ma).mean()
        trend_up = bool(df["close"].iloc[-1] > ma.iloc[-1]) if not np.isnan(ma.iloc[-1]) else True

    desired_long = (last_prob >= threshold) and trend_up
    if desired_long and not prev_holding:
        action = "买入"
    elif desired_long and prev_holding:
        action = "持有"
    elif (not desired_long) and prev_holding:
        action = "卖出"
    else:
        action = "观望"

    reasons = [
        f"模型看涨概率 {last_prob:.0%}，" + ("达到" if last_prob >= threshold else "未达到")
        + f"出手门槛 {threshold:.0%}",
    ]
    if bt.trend_filter:
        reasons.append(
            "价格" + ("还在" if trend_up else "已跌破")
            + f"{bt.trend_ma} 日均线" + ("（趋势向上）" if trend_up else "（趋势转弱）")
        )
    reasons.append("策略判定当前" + ("持仓中" if prev_holding else "空仓"))

    sell_conditions = [f"看涨概率跌破 {threshold:.0%}（模型不再看好）"]
    if bt.trend_filter:
        sell_conditions.append(f"股价跌破 {bt.trend_ma} 日均线（趋势转弱）")
    if bt.drawdown_stop > 0:
        sell_conditions.append(f"账户从最高点回撤超过 {bt.drawdown_stop:.0%}（保护性止损）")
    sell_conditions.append(f"持有满 {bt.min_hold} 天后信号转空即卖出（最短持有期）")

    # 建议仓位（占本金比例）：波动越大买得越少
    position_pct = 0.0
    realized_vol = 0.0
    if desired_long:
        if bt.vol_target > 0:
            vol = df["close"].pct_change().rolling(bt.vol_lookback).std() * (252 ** 0.5)
            realized_vol = float(vol.iloc[-1]) if not np.isnan(vol.iloc[-1]) else 0.0
            scale = min(bt.vol_target / realized_vol, bt.max_position) if realized_vol > 1e-6 else bt.max_position
        else:
            scale = bt.max_position
        position_pct = round(scale, 3)

    if not desired_long:
        sizing_note = "当前不建议买入，暂不投入。"
    elif position_pct >= 0.999:
        sizing_note = "建议满仓（用全部计划资金）。"
    else:
        sizing_note = (
            f"建议只用本金的约 {position_pct:.0%} 买入。"
            f"（当前波动率越高、买得越少，让账户更平稳。）"
        )

    return {
        "action": action,
        "trend_up": trend_up,
        "holding": prev_holding,
        "reasons": reasons,
        "sell_conditions": sell_conditions,
        "position_pct": position_pct,
        "realized_vol": round(realized_vol, 4),
        "sizing_note": sizing_note,
    }


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

    # 6) 最新信号 + 操作建议
    model, last_date, last_prob, signal = latest_signal(X_all, y_all, cfg.model, cfg.backtest)
    imp = feature_importance(model, list(X_all.columns))
    prev_holding = bool(len(result.position) and result.position.iloc[-1] > 1e-9)
    recommendation = _build_recommendation(df, cfg, float(last_prob), prev_holding)

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
        "recommendation": recommendation,
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


def rank(cfg: Config, items: list, verbose: bool = False) -> list:
    """选股榜：对一批标的分别算「最新看涨概率」，按概率从高到低排序。"""
    results = []
    for it in items:
        symbol = str(it.get("symbol"))
        kind = it.get("kind", "stock")
        name = it.get("name", symbol)
        try:
            sub = Config.from_dict(cfg.to_dict())
            sub.data.symbol = symbol
            sub.data.kind = kind
            df = load_prices(sub.data, verbose=False)
            feats = build_features(df, sub.features)
            y_all, _ = make_labels(df, sub.labels)
            y_all = y_all.reindex(feats.index)
            _, _, prob, _ = latest_signal(feats, y_all, sub.model, sub.backtest)
            rec = _build_recommendation(df, sub, float(prob), False)
            results.append({
                "symbol": symbol, "kind": kind, "name": name,
                "prob": round(float(prob), 4),
                "action": rec["action"],
                "trend_up": rec["trend_up"],
                "position_pct": rec["position_pct"],
            })
        except Exception as exc:  # noqa: BLE001
            results.append({"symbol": symbol, "kind": kind, "name": name, "error": str(exc)})
    results.sort(key=lambda r: r.get("prob", -1), reverse=True)
    return results


def screen(
    cfg: Config,
    top_n: int = 20,
    min_amount: float = 1e8,
    max_pct: float = 9.5,
    verbose: bool = True,
) -> Dict[str, Any]:
    """全市场选股（两级漏斗）。

    1) 粗筛：全市场快照，剔除 ST/退市/涨跌停/低流动性，按成交额取最活跃 top_n；
    2) 精算：对这 top_n 只跑模型，按「看涨概率」排序。
    """
    from .data import load_market_snapshot

    snap = load_market_snapshot(verbose=verbose).rename(
        columns={"代码": "symbol", "名称": "name", "成交额": "amount", "涨跌幅": "pct_chg"}
    )
    n_all = len(snap)
    snap["amount"] = pd.to_numeric(snap["amount"], errors="coerce")
    snap["pct_chg"] = pd.to_numeric(snap["pct_chg"], errors="coerce")
    snap = snap.dropna(subset=["symbol", "name"])
    snap = snap[~snap["name"].astype(str).str.contains("ST|退", regex=True, na=False)]
    snap = snap[snap["pct_chg"].abs() < max_pct]           # 剔除涨跌停
    snap = snap[snap["amount"] >= min_amount]              # 剔除流动性差的
    snap = snap.sort_values("amount", ascending=False).head(top_n)

    items = []
    for r in snap.itertuples():
        s = str(r.symbol).split(".")[0]
        if s.isdigit():
            s = s.zfill(6)
        items.append({"symbol": s, "name": str(r.name), "kind": "stock"})

    if verbose:
        print(f"[screen] 全市场 {n_all} 只 -> 粗筛后 {len(items)} 只，开始精算…")
    ranked = rank(cfg, items, verbose=verbose)
    return {
        "universe_size": int(n_all),
        "shortlist_size": len(items),
        "filters": {"top_n": top_n, "min_amount": min_amount, "max_pct": max_pct},
        "results": ranked,
    }


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
