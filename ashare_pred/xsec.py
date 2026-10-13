"""横截面多因子选股（qlib / vnpy.alpha 式，接真实撮合引擎）——科学/数学强化版。

因子族对齐 **Alpha158**（源自微软 Qlib，vnpy.alpha 亦采用该定义，MIT）；
在 qlib/vnpy 的基础上，我们额外提供**真实 A 股撮合**（T+1/涨跌停/整手/成本/冲击）
与**组合优化 + 自动解读**。区别：不引入 vnpy 的 Qt/数据库/付费数据依赖，数据用 akshare。

流程：
  因子(Alpha158 精简版, ~150 个) → 横截面标准化(zscore+winsorize) → 中性化(规模+静态行业)
  → purged walk-forward 训练 LightGBM(rank 目标) → 样本外打分
  → 组合优化(scipy: 打分+换手惩罚+行业/单票约束) → 事件驱动引擎撮合
  → 评估：Rank IC / ICIR / IC-t(Newey-West)、分层单调性、多空、超额 vs 指数、含/不含成本。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .engine import Broker, EngineConfig, EngineResult, TradingCost
from .metrics import strategy_metrics
from .risk.engine import RiskConfig

WINDOWS = (5, 10, 20, 30, 60)


# ==================== 因子（Alpha158 精简版） ====================
def make_factors(df: pd.DataFrame) -> pd.DataFrame:
    """单标的的因果因子（全部只用历史）。约 110 列。"""
    c = df["close"]
    o = df.get("open", c)
    h = df.get("high", c)
    low = df.get("low", c)
    v = df["volume"]
    a = df["amount"] if "amount" in df.columns else c * v
    eps = 1e-12
    t = pd.Series(np.arange(len(c)), index=c.index, dtype=float)
    f = pd.DataFrame(index=df.index)

    # K 线形态 (9)
    rng = (h - low).replace(0, np.nan)
    f["kmid"] = (c - o) / o
    f["klen"] = (h - low) / o
    f["kmid2"] = (c - o) / rng
    f["kup"] = (h - np.maximum(o, c)) / o
    f["kup2"] = (h - np.maximum(o, c)) / rng
    f["klow"] = (np.minimum(o, c) - low) / o
    f["klow2"] = (np.minimum(o, c) - low) / rng
    f["ksft"] = (2 * c - h - low) / o
    f["ksft2"] = (2 * c - h - low) / rng
    # 价格相对 (4)
    f["open0"] = o / c
    f["high0"] = h / c
    f["low0"] = low / c
    f["vwap0"] = (a / (v + eps)) / c

    ret = c.pct_change()
    up = (ret > 0).astype(float)
    dn = (ret < 0).astype(float)
    vp = up * v
    vn = dn * v
    for w in WINDOWS:
        ma = c.rolling(w).mean()
        f[f"ma{w}"] = (c - ma) / ma.replace(0, np.nan)
        f[f"roc{w}"] = c.pct_change(w)
        f[f"std{w}"] = c.rolling(w).std() / c
        cov = c.rolling(w).cov(t)
        var = t.rolling(w).var()
        f[f"beta{w}"] = cov / var.replace(0, np.nan)
        f[f"rsqr{w}"] = c.rolling(w).corr(t) ** 2
        mn = low.rolling(w).min()
        mx = h.rolling(w).max()
        f[f"rsv{w}"] = (c - mn) / (mx - mn).replace(0, np.nan)
        f[f"rank{w}"] = c.rolling(w).rank(pct=True)
        f[f"skew{w}"] = ret.rolling(w).skew()
        # 通道/分位/回归（Alpha158: qtlu/qtld/max/min/resi）
        f[f"qtlu{w}"] = c.rolling(w).quantile(0.8) / c
        f[f"qtld{w}"] = c.rolling(w).quantile(0.2) / c
        f[f"max{w}"] = h.rolling(w).max() / c
        f[f"min{w}"] = low.rolling(w).min() / c
        resid = c - (cov / var.replace(0, np.nan)) * t
        f[f"resi{w}"] = resid.rolling(w).std() / c
        f[f"corr{w}"] = c.rolling(w).corr(np.log(v + 1))
        # 价量变化相关（Alpha158: cord）
        f[f"cord{w}"] = c.pct_change().rolling(w).corr(np.log(v.pct_change() + 1))
        # 量变化方向占比（Alpha158: vsump/vsumn/vsumd）
        dv = v.diff()
        vup2 = (dv > 0).astype(float) * dv.abs()
        vdn2 = (dv < 0).astype(float) * dv.abs()
        vden = vup2.rolling(w).sum() + vdn2.rolling(w).sum() + eps
        f[f"vsump{w}"] = vup2.rolling(w).sum() / vden
        f[f"vsumn{w}"] = vdn2.rolling(w).sum() / vden
        f[f"vsumd{w}"] = (vup2.rolling(w).sum() - vdn2.rolling(w).sum()) / vden
        f[f"cntp{w}"] = up.rolling(w).mean()
        f[f"cntn{w}"] = dn.rolling(w).mean()
        f[f"cntd{w}"] = f[f"cntp{w}"] - f[f"cntn{w}"]
        f[f"sump{w}"] = vp.rolling(w).sum() / (v.rolling(w).sum() + eps)
        f[f"sumn{w}"] = vn.rolling(w).sum() / (v.rolling(w).sum() + eps)
        f[f"sumd{w}"] = f[f"sump{w}"] - f[f"sumn{w}"]
        f[f"vma{w}"] = v.rolling(w).mean() / (v + eps)
        f[f"vstd{w}"] = v.rolling(w).std() / (v + eps)
        f[f"vroc{w}"] = v.pct_change(w)
        wv = ret.abs() * v
        f[f"wvma{w}"] = wv.rolling(w).std() / (wv.rolling(w).mean() + eps)

    # 趋势/强弱 (4)
    f["macd"] = (c.ewm(span=12).mean() - c.ewm(span=26).mean()) / c
    rsv9 = (c - low.rolling(9).min()) / (h.rolling(9).max() - low.rolling(9).min()).replace(0, np.nan) * 100
    k = rsv9.ewm(com=2).mean()
    d = k.ewm(com=2).mean()
    f["kdj_j"] = (3 * k - 2 * d) / 100
    tr = pd.concat([(h - low), (h - c.shift()).abs(), (low - c.shift()).abs()], axis=1).max(axis=1)
    f["atr14"] = tr.rolling(14).mean() / c
    f["amp"] = (h - low) / c
    return f


def _factor_cols_of(f: pd.DataFrame) -> List[str]:
    return list(f.columns)


# ==================== 面板 ====================
def build_panel(prices: Dict[str, pd.DataFrame], horizon: int = 5) -> Tuple[pd.DataFrame, List[str]]:
    """长表面板 (date,symbol) × 因子 + label + size(规模代理)。"""
    frames = []
    factor_cols: Optional[List[str]] = None
    for sym, df in prices.items():
        if "close" not in df.columns or len(df) < 90:
            continue
        f = make_factors(df)
        # 标签口径与执行一致：T+1 才能进场，故预测 close_{t+h}/close_{t+1}-1
        f["label"] = df["close"].shift(-horizon) / df["close"].shift(-1) - 1.0
        a = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
        f["size"] = np.log1p(a.rolling(20, min_periods=5).mean())  # 规模代理 = ln(20日均成交额)
        f["symbol"] = sym
        f = f.reset_index()
        f = f.rename(columns={f.columns[0]: "date"})
        frames.append(f)
        if factor_cols is None:
            factor_cols = [x for x in _factor_cols_of(f) if x not in ("date", "symbol", "label", "size")]
    if not frames:
        return pd.DataFrame(), []
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"])
    # 标签横截面去均值（学相对强弱）
    panel["label"] = panel["label"] - panel.groupby("date")["label"].transform("mean")
    return panel, (factor_cols or [])


def _winsor_zscore(panel: pd.DataFrame, factor_cols: List[str]) -> None:
    """按日 z-score 后裁剪（廉价 winsorize）。"""
    eps = 1e-12
    for col in factor_cols:
        g = panel.groupby("date")[col]
        mean = g.transform("mean")
        std = g.transform("std")
        panel[col] = ((panel[col] - mean) / (std + eps)).clip(-5, 5)


def neutralize(panel: pd.DataFrame, factor_cols: List[str], industry,
               use_size: bool = True) -> pd.DataFrame:
    """对每个因子做横截面回归取残差：f ~ 1 + ln(size) + 行业哑变量。

    industry 可以是 {symbol: 行业}（静态）或 (symbol, date)->行业 的可调用（时变）。
    """
    out = panel.copy()
    out["lnsize"] = out["size"].astype(float)
    if callable(industry):
        out["ind"] = [industry(str(s), str(d)[:10]) for s, d in zip(out["symbol"], out["date"])]
    else:
        out["ind"] = out["symbol"].map(industry).fillna("UNK")
    for d, idx in out.groupby("date").groups.items():
        sub = out.loc[idx]
        F = sub[factor_cols].to_numpy(float)
        nanmask = np.isnan(F)
        Fz = np.nan_to_num(F)
        cols = [np.ones(len(sub))]
        if use_size:
            cols.append(sub["lnsize"].to_numpy(float))
        ind_counts = sub["ind"].value_counts()
        keep = [k for k in ind_counts.index if k != "UNK"][:30]
        for k in keep:
            cols.append((sub["ind"] == k).to_numpy(float))
        X = np.nan_to_num(np.column_stack(cols))
        try:
            Xp = np.linalg.pinv(X)
            B = Xp @ Fz
            R = Fz - X @ B
        except Exception:  # noqa: BLE001
            R = Fz
        R[nanmask] = np.nan
        out.loc[idx, factor_cols] = R
    return out


# ==================== 模型 ====================
class _EnsembleModel:
    """集成：LightGBM + Lasso + MLP 的预测均值（特征重要性取 LGB）。"""

    def __init__(self, members):
        self.members = members

    def fit(self, X, y):
        for m in self.members:
            try:
                m.fit(X, y)
            except Exception:  # noqa: BLE001
                pass
        return self

    def predict(self, X):
        preds = [m.predict(X) for m in self.members if hasattr(m, "predict")]
        return np.mean(preds, axis=0) if preds else np.zeros(len(X))

    @property
    def feature_importances_(self):
        for m in self.members:
            if hasattr(m, "feature_importances_"):
                return m.feature_importances_
        return None


def _make_model(name: str = "lightgbm"):
    if name == "lightgbm":
        try:
            from lightgbm import LGBMRegressor
            return LGBMRegressor(
                n_estimators=400, learning_rate=0.03, num_leaves=31,
                subsample=0.8, colsample_bytree=0.6, min_child_samples=50,
                reg_lambda=1.0, n_jobs=1, verbose=-1,
            )
        except Exception:  # noqa: BLE001
            pass
    if name == "lasso":
        from sklearn.linear_model import Lasso
        return Lasso(alpha=1e-3, max_iter=5000)
    if name == "mlp":
        from sklearn.neural_network import MLPRegressor
        return MLPRegressor(hidden_layer_sizes=(64, 32), max_iter=300,
                            early_stopping=True, random_state=0)
    if name == "ensemble":
        members = []
        for m in ("lightgbm", "lasso", "mlp"):
            try:
                members.append(_make_model(m))
            except Exception:  # noqa: BLE001
                pass
        return _EnsembleModel(members)
    if name == "xgboost":
        try:
            from xgboost import XGBRegressor
            return XGBRegressor(n_estimators=400, max_depth=4, learning_rate=0.04,
                                subsample=0.8, colsample_bytree=0.6, n_jobs=1)
        except Exception:  # noqa: BLE001
            pass
    from sklearn.ensemble import GradientBoostingRegressor
    return GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05)


# ==================== Walk-forward 打分 ====================
def walk_forward_scores(
    panel: pd.DataFrame, factor_cols: List[str], target: str = "rank",
    horizon: int = 5, train_window: int = 500, retrain: int = 20, min_train: int = 500,
    model_name: str = "lightgbm", progress=None,
) -> Tuple[pd.DataFrame, Any]:
    """purged walk-forward：训练集与测试集间留 horizon 隔离带，防重叠标签泄漏。"""
    dates = sorted(panel["date"].unique())
    n = len(dates)
    embargo = horizon
    y_col = "label_rank" if target == "rank" else "label"
    if target == "rank":
        panel = panel.copy()
        panel["label_rank"] = panel.groupby("date")["label"].rank(pct=True)

    rows = []
    last_model = None
    i = train_window + embargo
    done = 0
    steps = max(1, (n - i + retrain - 1) // retrain) if n > i else 1
    while i < n:
        train_dates = dates[max(0, i - train_window): i - embargo]
        test_dates = dates[i: i + retrain]
        tr = panel[panel["date"].isin(train_dates)].dropna(subset=factor_cols + [y_col])
        if len(tr) >= min_train:
            model = _make_model(model_name)
            try:
                model.fit(tr[factor_cols].fillna(0.0).to_numpy(), tr[y_col].to_numpy())
                te = panel[panel["date"].isin(test_dates)].dropna(subset=factor_cols)
                if len(te):
                    te = te.copy()
                    te["score"] = model.predict(te[factor_cols].fillna(0.0).to_numpy())
                    rows.append(te[["date", "symbol", "score", "label"]])
                    last_model = model
            except Exception:  # noqa: BLE001
                pass
        i += retrain
        done += 1
        if progress:
            progress({"stage": "滚动训练与打分", "pct": round(100 * min(1.0, done / steps), 1)})
    if progress:
        progress({"stage": "完成", "pct": 100})
    scores = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["date", "symbol", "score", "label"])
    return scores, last_model


# ==================== 评估 ====================
def _nw_tstat(x: pd.Series, lag: int) -> Optional[float]:
    x = x.dropna().to_numpy()
    n = len(x)
    if n < 5:
        return None
    mean = x.mean()
    var = x.var(ddof=1)
    for l in range(1, min(lag, n - 1) + 1):
        w = 1 - l / (lag + 1)
        cov = np.cov(x[l:], x[:-l])[0, 1]
        var += 2 * w * cov
    if var <= 1e-12:
        return None
    return float(mean / np.sqrt(var / n))


def ic_metrics(scores: pd.DataFrame, horizon: int = 5) -> Dict[str, Any]:
    ics = []
    for _, g in scores.dropna(subset=["score", "label"]).groupby("date"):
        if len(g) >= 5:
            ics.append(g["score"].corr(g["label"], method="spearman"))
    s = pd.Series(ics, dtype=float).dropna()
    if len(s) == 0:
        return {"ic_mean": None, "ic_std": None, "icir": None, "ic_positive_pct": None,
                "n_days": 0, "ic_t": None, "ic_series": []}
    std = s.std()
    return {
        "ic_mean": round(float(s.mean()), 4),
        "ic_std": round(float(std), 4),
        "icir": round(float(s.mean() / std), 4) if std > 1e-9 else None,
        "ic_positive_pct": round(float((s > 0).mean()), 4),
        "ic_t": round(_nw_tstat(s, horizon), 2) if _nw_tstat(s, horizon) is not None else None,
        "n_days": int(len(s)),
        "ic_series": [{"date": str(pd.Timestamp(d))[:10], "ic": round(float(v), 4)}
                      for d, v in s.items()][-400:],
    }


def layered_returns(scores: pd.DataFrame, q: int = 5) -> Dict[str, Any]:
    per_q: List[pd.Series] = []
    for _, g in scores.dropna(subset=["score", "label"]).groupby("date"):
        if len(g) < q * 3:
            continue
        g = g.copy()
        g["bucket"] = pd.qcut(g["score"].rank(method="first"), q, labels=False)
        per_q.append(g.groupby("bucket")["label"].mean())
    if not per_q:
        return {"quantiles": {}, "long_short": None, "monotonic": None}
    df = pd.DataFrame(per_q)
    quant = {int(k): round(float(df[k].mean()) * 100, 3) for k in df.columns}
    ls = round(float(df[q - 1].mean() - df[0].mean()) * 100, 3) if q > 1 else None
    means = df.mean().to_numpy()
    mono = float(pd.Series(means).corr(pd.Series(np.arange(q)), method="spearman"))
    return {"quantiles": quant, "long_short": ls, "monotonic": round(mono, 3)}


def verdict_of(ic: Dict[str, Any]) -> Dict[str, Any]:
    """验收门槛：IC 太弱或 t 不显著 → 判无效。"""
    m = ic.get("ic_mean") or 0.0
    ir = ic.get("icir")
    t = ic.get("ic_t")
    reasons = []
    if m < 0.02:
        reasons.append(f"IC均值 {m:.4f} < 0.02")
    if ir is not None and ir < 0.2:
        reasons.append(f"ICIR {ir} < 0.2")
    if t is not None and abs(t) < 2:
        reasons.append(f"IC-t {t} 不显著")
    ok = not reasons
    return {"usable": ok, "label": "可用候选" if ok else "无效/不建议使用", "reasons": reasons}


def explain_narrative(
    *, ic: Dict[str, Any], layered: Dict[str, Any], verdict: Dict[str, Any],
    metrics: Dict[str, Any], metrics_free: Dict[str, Any], index_metrics: Dict[str, Any],
    excess: Optional[float], cost_drag: Optional[float], index_name: str = "沪深300",
) -> Dict[str, Any]:
    """把量化指标翻成'为什么有效/无效、相对买指数值不值'的中文解释（确定性，不依赖 LLM）。"""
    eff = bool(verdict.get("usable"))
    reasons: List[str] = []

    # 1) 因子有效性
    if eff:
        reasons.append(
            f"打分对未来收益有统计意义：IC均值 {ic.get('ic_mean')}（>0.02）、"
            f"ICIR {ic.get('icir')}、t={ic.get('ic_t')}。"
        )
    else:
        detail = "；".join(verdict.get("reasons") or []) or "指标过弱"
        reasons.append(f"打分对未来收益几乎没有预测力：{detail}。")

    # 2) 分层单调性
    mono = layered.get("monotonic")
    if mono is not None:
        if mono >= 0.6:
            reasons.append(f"分层收益单调（单调性 {mono}）：打分越高、未来涨得越多，方向清晰。")
        elif mono <= -0.6:
            reasons.append(f"分层收益反向（单调性 {mono}）：打分方向可能是反的。")
        else:
            reasons.append(f"分层收益不单调（单调性 {mono}）：因子方向不稳定，多空收益不可靠。")

    # 3) 相对指数
    if excess is not None:
        if excess > 0:
            reasons.append(f"扣除成本后，组合相对{index_name}超额 {excess*100:.1f}%。")
        else:
            reasons.append(f"扣除成本后，组合相对{index_name}跑输 {abs(excess)*100:.1f}%。")

    # 4) 风险对比
    s = metrics.get("sharpe")
    si = index_metrics.get("sharpe")
    dd = metrics.get("max_drawdown")
    ddi = index_metrics.get("max_drawdown")
    if s is not None and si is not None:
        reasons.append(
            f"风险对比：夏普 {s} vs {index_name} {si}；最大回撤 "
            f"{(dd*100 if dd is not None else 0):.1f}% vs {(ddi*100 if ddi is not None else 0):.1f}%。"
        )

    # 5) 成本
    if cost_drag is not None and cost_drag > 0.02:
        reasons.append(f"换手成本拖累约每年 {cost_drag*100:.1f}%，是主要损耗来源。")

    # 结论
    worth = bool(eff and excess is not None and excess > 0)
    if eff and excess is not None and excess > 0:
        headline = f"因子有可靠边际，且扣除成本后跑赢{index_name}，相对直接买指数更值得采用。"
    elif eff and excess is not None and excess <= 0:
        headline = f"因子有效，但扣除成本后没跑赢{index_name}，直接用指数更省事。"
    elif (not eff) and excess is not None and excess > 0:
        headline = (f"因子本身没有可靠边际；组合虽跑赢{index_name}，但超额很可能来自"
                    f"小盘/风格暴露而非选股能力，不宜据此外推。")
    else:
        headline = f"因子没有可靠边际且未跑赢{index_name}，不如直接买指数。"
    return {"headline": headline, "worth_index": worth, "effective": eff, "reasons": reasons}


# ==================== 组合优化 ====================
def optimize_weights(
    scores: Dict[str, float], prev_w: Dict[str, float], industry: Dict[str, str],
    cap: float, turnover_penalty: float, ind_limit: float, top_k: int,
    vol: Optional[Dict[str, float]] = None, risk_aversion: float = 0.0,
) -> Dict[str, float]:
    syms = list(scores)
    if not syms:
        return {}
    n = len(syms)
    s = np.array([scores[x] for x in syms], dtype=float)
    sd = s.std()
    if sd > 1e-12:
        s = (s - s.mean()) / sd
    w0 = np.array([prev_w.get(x, 0.0) for x in syms], dtype=float)
    volv = np.array([(vol or {}).get(x, 0.3) for x in syms], dtype=float)

    def obj(w):
        risk = risk_aversion * np.sum((w * volv) ** 2)
        return -(s @ w) + turnover_penalty * np.sum((w - w0) ** 2) + risk

    cons = [{"type": "ineq", "fun": lambda w: 1.0 - w.sum()}]
    groups: Dict[str, List[int]] = {}
    for i, x in enumerate(syms):
        groups.setdefault(industry.get(x, "UNK"), []).append(i)
    for idx in groups.values():
        if len(idx) >= 2:
            cons.append({"type": "ineq", "fun": (lambda idx: (lambda w: ind_limit - w[idx].sum()))(idx)})

    w_init = np.minimum(np.where(w0 > 0, w0, 1.0 / n), cap)
    try:
        from scipy.optimize import minimize
        res = minimize(obj, w_init, method="SLSQP", bounds=[(0.0, cap)] * n,
                       constraints=cons, options={"maxiter": 200, "ftol": 1e-7})
        if res.success:
            w = np.clip(res.x, 0.0, cap)
            if w.sum() > 1:
                w = w / w.sum()
            picked = {syms[i]: round(float(w[i]), 4) for i in range(n) if w[i] > 1e-4}
            if picked:
                return picked
    except Exception:  # noqa: BLE001
        pass
    # 兜底：等权前 top_k
    order = np.argsort(-s)[: max(1, top_k)]
    wt = 1.0 / len(order)
    return {syms[i]: wt for i in order}


def scores_to_targets(
    scores: pd.DataFrame, industry: Dict[str, str], top_k: int = 30,
    top_pool: Optional[int] = None, cap: float = 0.1, turnover_penalty: float = 0.05,
    ind_limit: float = 0.2, rebalance: int = 5,
    vol: Optional[Dict[str, float]] = None, risk_aversion: float = 0.0,
) -> Tuple[Dict[Any, Dict[str, float]], Dict[Any, dict]]:
    top_pool = top_pool or max(top_k * 3, 40)
    dates = sorted(scores["date"].unique())
    targets: Dict[Any, Dict[str, float]] = {}
    evidence: Dict[Any, dict] = {}
    prev: Dict[str, float] = {}
    for i, d in enumerate(dates):
        if i % max(1, rebalance) != 0:
            continue
        g = scores[scores["date"] == d].dropna(subset=["score"])
        if len(g) == 0:
            continue
        g = g.sort_values("score", ascending=False).head(top_pool)
        sc = {str(r["symbol"]): float(r["score"]) for _, r in g.iterrows()}
        w = optimize_weights(sc, prev, industry, cap=cap, turnover_penalty=turnover_penalty,
                             ind_limit=ind_limit, top_k=top_k, vol=vol, risk_aversion=risk_aversion)
        if not w:
            continue
        targets[d] = w
        prev = w
        for rank, (sym, ww) in enumerate(sorted(w.items(), key=lambda kv: -kv[1]), 1):
            evidence[(d, sym)] = {"action": "xsec", "rank": rank, "weight": ww,
                                  "reason": f"多因子打分组合（权重 {ww:.2f}）"}
    return targets, evidence


# ==================== 主流程 ====================
def _run_broker(prices, targets, evidence, names, top_k, initial_cash, drawdown_stop, cost, version):
    cap = min(1.0, max(0.05, 3.0 / max(1, top_k)))
    cfg = EngineConfig(
        initial_cash=initial_cash, cost=cost,
        risk=RiskConfig(max_position_per_stock=cap, max_total_exposure=1.0,
                        max_drawdown_stop=drawdown_stop, drawdown_cooldown_days=5),
        names=dict(names or {}), strategy_version=version, strategy_name=f"多因子 top{top_k}",
    )
    return Broker(cfg).run(prices, targets, evidence=evidence)


def run_xsec(
    prices: Dict[str, pd.DataFrame],
    top_k: int = 30,
    horizon: int = 5,
    rebalance: int = 5,
    train_window: int = 500,
    retrain: int = 20,
    model_name: str = "lightgbm",
    target: str = "rank",
    neutralize_size: bool = True,
    neutralize_industry: bool = True,
    membership: Optional[set] = None,
    risk_aversion: float = 0.0,
    impact: float = 0.0,
    initial_cash: float = 100000.0,
    names: Optional[Dict[str, str]] = None,
    drawdown_stop: float = 0.20,
    cost: Optional[TradingCost] = None,
    strategy_version: Optional[int] = None,
    progress=None,
) -> Dict[str, Any]:
    from .xsec_data import industry_resolver

    panel, factor_cols = build_panel(prices, horizon=horizon)
    if panel.empty:
        raise ValueError("有效标的不足，无法构建多因子面板")
    if membership:
        ym = panel["date"].dt.strftime("%Y-%m")
        mask = [f"{s}|{m}" in membership for s, m in zip(panel["symbol"], ym)]
        panel = panel[mask]
        if panel.empty:
            raise ValueError("按指数成分过滤后无数据（PIT 成分不可用？）")

    def emit(stage, pct):
        if progress:
            progress({"stage": stage, "pct": pct})

    emit("横截面标准化", 5)
    _winsor_zscore(panel, factor_cols)
    from .xsec_data import load_industry_map
    resolver = industry_resolver() if neutralize_industry else {}
    port_industry = load_industry_map(verbose=False)
    if neutralize_size or neutralize_industry:
        emit("中性化(规模/行业)", 10)
        panel = neutralize(panel, factor_cols, resolver, use_size=neutralize_size)
    emit("滚动训练与打分", 15)
    scores, last_model = walk_forward_scores(
        panel, factor_cols, target=target, horizon=horizon,
        train_window=train_window, retrain=retrain, model_name=model_name,
        progress=lambda ev: emit(ev.get("stage", "训练中"), 15 + 0.7 * float(ev.get("pct", 0))),
    )
    ic = ic_metrics(scores, horizon=horizon)
    layered = layered_returns(scores)
    verdict = verdict_of(ic)

    emit("组合优化", 88)
    cap = min(1.0, max(0.05, 3.0 / max(1, top_k)))
    vol = {s: float(prices[s]["close"].pct_change().std() * (252 ** 0.5)) for s in prices}
    targets, evidence = scores_to_targets(
        scores, port_industry, top_k=top_k, cap=cap, rebalance=rebalance,
        vol=vol, risk_aversion=risk_aversion,
    )

    emit("撮合回测", 92)
    base_cost = cost or TradingCost()
    base_cost.impact_coef = impact
    res_cost = _run_broker(prices, targets, evidence, names, top_k, initial_cash, drawdown_stop, base_cost, strategy_version)
    res_free = _run_broker(prices, targets, evidence, names, top_k, initial_cash, drawdown_stop,
                           TradingCost(commission=0, stamp_tax=0, slippage=0, min_commission=0, impact_coef=0.0), strategy_version)

    factor_importance = []
    if last_model is not None and hasattr(last_model, "feature_importances_"):
        imp = pd.Series(last_model.feature_importances_, index=factor_cols).sort_values(ascending=False)
        factor_importance = [{"factor": k, "importance": round(float(v), 1)} for k, v in imp.head(20).items()]

    return {
        "result": res_cost, "result_free": res_free,
        "ic": ic, "layered": layered, "verdict": verdict,
        "scores": scores,
        "factor_cols": factor_cols, "factor_importance": factor_importance,
        "n_factor_days": int(scores["date"].nunique()) if len(scores) else 0,
        "normalized": True,
    }
