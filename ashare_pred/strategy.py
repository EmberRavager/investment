"""策略规格（StrategySpec）与确定性规则引擎。

职责边界（呼应 PRD）：
- LLM 只负责把自然语言转成**结构化规格**（StrategySpec）；
- 信号的确定性计算、校验、撮合全部由本模块 + engine 完成，AI 不参与下单。

规格可回测、可复现、可版本化（配合 store）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .engine import Broker, EngineConfig, EngineResult, TradingCost
from .fundamentals import attach_fundamentals
from .risk.engine import RiskConfig

#: 规则引擎当前支持的字段（价格/成交量派生）。财务类字段需外部数据源。
PRICE_FIELDS = {
    "close", "open", "high", "low", "volume", "amount", "pct_chg",
    "ma5", "ma10", "ma20", "ma60", "ma120",
    "vol_ratio", "vol_ratio5", "ret5", "ret20", "rsi14", "high20", "low20",
}
FUNDAMENTAL_FIELDS = {"profit_growth", "roe", "pe", "pb", "revenue_growth"}

_OPS = {">", ">=", "<", "<=", "==", "cross_above", "cross_below"}


_FIELD_CN = {
    "close": "收盘价", "open": "开盘价", "high": "最高价", "low": "最低价",
    "volume": "成交量", "amount": "成交额", "pct_chg": "当日涨跌幅",
    "ma5": "5日线", "ma10": "10日线", "ma20": "20日线", "ma60": "60日线", "ma120": "120日线",
    "vol_ratio": "量比", "vol_ratio5": "5日量比",
    "ret5": "5日动量", "ret20": "20日动量", "rsi14": "RSI(14)",
    "high20": "20日最高", "low20": "20日最低",
    "profit_growth": "扣非净利润同比",
}
_OP_CN = {">": "大于", ">=": "≥", "<": "小于", "<=": "≤", "==": "等于",
          "cross_above": "上穿", "cross_below": "下穿"}


@dataclass
class Condition:
    field: str
    op: str
    value: Any            # 数字，或另一个字段名(str)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Condition":
        return cls(field=str(d["field"]), op=str(d["op"]), value=d.get("value"))

    def to_dict(self) -> Dict[str, Any]:
        return {"field": self.field, "op": self.op, "value": self.value}

    def describe(self) -> str:
        name = _FIELD_CN.get(self.field, self.field)
        if isinstance(self.value, str):
            val = _FIELD_CN.get(self.value, self.value)
        else:
            val = self.value
        return f"{name} {_OP_CN.get(self.op, self.op)} {val}"


@dataclass
class StrategySpec:
    name: str = "未命名策略"
    universe: List[str] = field(default_factory=lambda: ["600519"])
    filters: List[Condition] = field(default_factory=list)   # 满足才允许持仓
    entry: List[Condition] = field(default_factory=list)     # 全部满足 -> 买入
    exit: List[Condition] = field(default_factory=list)      # 任一满足 -> 卖出
    filters_logic: str = "and"                               # and | or
    entry_logic: str = "and"
    exit_logic: str = "or"
    weight: float = 0.30                                     # 单标的目标权重
    min_hold: int = 0
    max_hold: int = 0                                        # 最长持有天数（0=不限）；到期强制卖出
    # 风控（进入独立 RiskEngine）
    max_position_per_stock: float = 0.30
    max_total_exposure: float = 1.0
    drawdown_stop: float = 0.15
    drawdown_cooldown: int = 20
    stop_loss: float = 0.08
    notes: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StrategySpec":
        return cls(
            name=d.get("name", "未命名策略"),
            universe=list(d.get("universe") or ["600519"]),
            filters=[Condition.from_dict(c) for c in d.get("filters", [])],
            entry=[Condition.from_dict(c) for c in d.get("entry", [])],
            exit=[Condition.from_dict(c) for c in d.get("exit", [])],
            filters_logic=str(d.get("filters_logic", "and")).lower(),
            entry_logic=str(d.get("entry_logic", "and")).lower(),
            exit_logic=str(d.get("exit_logic", "or")).lower(),
            weight=float(d.get("weight", 0.30)),
            min_hold=int(d.get("min_hold", 0)),
            max_hold=int(d.get("max_hold", 0)),
            max_position_per_stock=float(d.get("max_position_per_stock", 0.30)),
            max_total_exposure=float(d.get("max_total_exposure", 1.0)),
            drawdown_stop=float(d.get("drawdown_stop", 0.15)),
            drawdown_cooldown=int(d.get("drawdown_cooldown", 20)),
            stop_loss=float(d.get("stop_loss", 0.08)),
            notes=d.get("notes", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "universe": self.universe,
            "filters": [c.to_dict() for c in self.filters],
            "entry": [c.to_dict() for c in self.entry],
            "exit": [c.to_dict() for c in self.exit],
            "filters_logic": self.filters_logic,
            "entry_logic": self.entry_logic,
            "exit_logic": self.exit_logic,
            "weight": self.weight,
            "min_hold": self.min_hold,
            "max_hold": self.max_hold,
            "max_position_per_stock": self.max_position_per_stock,
            "max_total_exposure": self.max_total_exposure,
            "drawdown_stop": self.drawdown_stop,
            "drawdown_cooldown": self.drawdown_cooldown,
            "stop_loss": self.stop_loss,
            "notes": self.notes,
        }

    def risk_config(self) -> RiskConfig:
        return RiskConfig(
            max_position_per_stock=self.max_position_per_stock,
            max_total_exposure=self.max_total_exposure,
            max_drawdown_stop=self.drawdown_stop,
            drawdown_cooldown_days=self.drawdown_cooldown,
        )

    def summary_lines(self) -> List[Dict[str, str]]:
        out = []
        for c in self.filters:
            out.append({"kind": "filter", "text": c.describe()})
        for c in self.entry:
            out.append({"kind": "entry", "text": c.describe()})
        for c in self.exit:
            out.append({"kind": "exit", "text": c.describe()})
        return out


#: 给 LLM 的 JSON schema 说明
SPEC_SCHEMA = {
    "name": "策略名称（中文）",
    "universe": ["股票/ETF 代码，如 600519"],
    "filters": [{"field": "字段", "op": "> | >= | < | <= | == | cross_above | cross_below", "value": "数字或其他字段"}],
    "entry": [{"field": "同 filters", "op": "同上", "value": "同上"}],
    "exit": [{"field": "同上", "op": "同上", "value": "同上"}],
    "weight": "单标的目标权重 0~1",
    "stop_loss": "止损比例，如 0.08",
    "max_position_per_stock": "单股最大仓位，如 0.3",
    "drawdown_stop": "回撤熔断阈值，如 0.15",
    "notes": "补充说明",
}

#: 默认策略（PRD Strategy 001 的等价可回测规格）
DEFAULT_SPEC = StrategySpec(
    name="成长趋势跟随",
    universe=["600519"],
    filters=[Condition("ma20", ">", "ma60")],
    entry=[Condition("close", ">", "ma20"), Condition("vol_ratio", ">", 1.3)],
    exit=[Condition("close", "<", "ma20")],
    weight=0.30,
    stop_loss=0.08,
    max_position_per_stock=0.30,
    drawdown_stop=0.15,
    notes="利润增长等财务过滤需接入财务数据后生效；此处为价格/量规则。",
)


def validate_spec(spec: StrategySpec) -> List[str]:
    """严格校验策略规格。致命问题抛 ValueError；返回非致命警告。

    拒绝：空股票池、缺少买入条件、非法仓位、未知字段、非法算子、空值、
    非法值类型（值必须是数字或已知字段名）、非法的 AND/OR。
    """
    warnings: List[str] = []
    if not spec.universe:
        raise ValueError("策略股票池为空")
    if not spec.entry:
        raise ValueError("策略缺少买入条件")
    if not (0 < spec.weight <= 1):
        raise ValueError("单标的目标权重需在 (0, 1] 之间")
    for name, logic in (("filters", spec.filters_logic), ("entry", spec.entry_logic), ("exit", spec.exit_logic)):
        if logic not in ("and", "or"):
            raise ValueError(f"{name}_logic 只能是 and / or，收到 {logic!r}")

    known = PRICE_FIELDS | FUNDAMENTAL_FIELDS
    for group_name, group in (("filters", spec.filters), ("entry", spec.entry), ("exit", spec.exit)):
        for c in group:
            where = f"{group_name} 条件 {c.field} {c.op} {c.value!r}"
            if c.field not in known:
                raise ValueError(f"不支持的字段：{c.field}（{where}）")
            if c.op not in _OPS:
                raise ValueError(f"不支持的算子：{c.op}（{where}）")
            if c.value is None or (isinstance(c.value, str) and c.value.strip() == ""):
                raise ValueError(f"条件的值不能为空（{where}）")
            if isinstance(c.value, str):
                if c.value not in known:
                    raise ValueError(f"值必须是数字或已知字段名，收到 {c.value!r}（{where}）")
                if c.value in FUNDAMENTAL_FIELDS or c.field in FUNDAMENTAL_FIELDS:
                    # 财务字段之间/与价格字段比较先允许，但需财务数据
                    pass
            elif not isinstance(c.value, (int, float)):
                raise ValueError(f"值类型非法（仅支持数字或字段名）：{c.value!r}（{where}）")

    uses_fundamental = any(
        c.field in FUNDAMENTAL_FIELDS or (isinstance(c.value, str) and c.value in FUNDAMENTAL_FIELDS)
        for g in (spec.filters, spec.entry, spec.exit) for c in g
    )
    if uses_fundamental:
        warnings.append("该策略使用财务因子；需要财务数据（按公告日对齐）才能回测。")

    if spec.max_position_per_stock > spec.max_total_exposure:
        warnings.append("单股仓位上限大于总仓位上限，将以总仓位为准。")
    return warnings


def uses_fundamentals(spec: StrategySpec) -> bool:
    return any(
        c.field in FUNDAMENTAL_FIELDS or (isinstance(c.value, str) and c.value in FUNDAMENTAL_FIELDS)
        for g in (spec.filters, spec.entry, spec.exit) for c in g
    )


def describe_spec(spec: StrategySpec) -> str:
    """把策略规格翻成一段中文说明（用于策略库展示）。"""
    def join(cs: List[Condition], logic: str) -> str:
        return (" 且 " if logic == "and" else " 或 ").join(c.describe() for c in cs)

    parts: List[str] = []
    if spec.filters:
        parts.append(f"前提（{join(spec.filters, spec.filters_logic)}）")
    if spec.entry:
        parts.append(f"当 {join(spec.entry, spec.entry_logic)} 时，次日开盘买入")
    if spec.exit:
        parts.append(f"当 {join(spec.exit, spec.exit_logic)} 时，次日开盘卖出")
    risk = (f"风控：单股≤{spec.max_position_per_stock:.0%}，止损 {spec.stop_loss:.0%}，"
            f"回撤 {spec.drawdown_stop:.0%} 熔断、冷却 {spec.drawdown_cooldown} 日")
    if spec.min_hold:
        risk += f"，最少持有 {spec.min_hold} 日"
    if spec.max_hold:
        risk += f"，最长持有 {spec.max_hold} 日"
    parts.append(risk)
    if spec.notes:
        parts.append(spec.notes)
    return "；".join(parts)


# ---- 特征与信号 ----
def compute_features(df: pd.DataFrame, windows=(5, 10, 20, 60, 120)) -> pd.DataFrame:
    out = df.copy()
    close = out["close"]
    for w in windows:
        out[f"ma{w}"] = close.rolling(w).mean()
    # 量比口径：日线数据没有盘中分时，故 vol_ratio = 当日成交量 / 过去20日均量（日线口径）
    out["vol_ma20"] = out["volume"].rolling(20, min_periods=1).mean()
    out["vol_ratio"] = out["volume"] / out["vol_ma20"].replace(0, np.nan)
    out["vol_ratio5"] = out["volume"] / out["volume"].rolling(5, min_periods=1).mean().replace(0, np.nan)
    out["ret5"] = close.pct_change(5)
    out["ret20"] = close.pct_change(20)
    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=5).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=5).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi14"] = 100 - 100 / (1 + rs)
    # 通道：过去 20 日的最高/最低（不含当日，用于"突破"语义）
    if "high" in out.columns:
        out["high20"] = out["high"].rolling(20).max().shift(1)
    if "low" in out.columns:
        out["low20"] = out["low"].rolling(20).min().shift(1)
    if "amount" not in out.columns:
        out["amount"] = close * out["volume"]
    return out


def _operand(feats: pd.DataFrame, val, index) -> pd.Series:
    if isinstance(val, str) and val in feats.columns:
        return feats[val]
    try:
        return pd.Series(float(val), index=index)
    except (TypeError, ValueError):
        return pd.Series(np.nan, index=index)


def _eval_condition(feats: pd.DataFrame, c: Condition) -> pd.Series:
    idx = feats.index
    left = feats[c.field] if c.field in feats.columns else pd.Series(np.nan, index=idx)
    right = _operand(feats, c.value, idx)
    if c.op == ">":
        m = left > right
    elif c.op == ">=":
        m = left >= right
    elif c.op == "<":
        m = left < right
    elif c.op == "<=":
        m = left <= right
    elif c.op == "==":
        m = left == right
    elif c.op == "cross_above":
        m = (left > right) & (left.shift(1) <= right.shift(1))
    elif c.op == "cross_below":
        m = (left < right) & (left.shift(1) >= right.shift(1))
    else:
        m = pd.Series(False, index=idx)
    return m.fillna(False)


def _group_mask(feats: pd.DataFrame, conds: List[Condition], logic: str) -> pd.Series:
    """按 and/or 组合一组条件。空组：and->True(无限制)，or->False。"""
    masks = [_eval_condition(feats, c) for c in conds]
    if not masks:
        return pd.Series(logic == "and", index=feats.index)
    acc = masks[0]
    for m in masks[1:]:
        acc = (acc & m) if logic == "and" else (acc | m)
    return acc


def _feats_for(df: pd.DataFrame, fundamentals: Optional[pd.DataFrame]) -> pd.DataFrame:
    feats = compute_features(df)
    if fundamentals is not None and len(fundamentals):
        feats = attach_fundamentals(feats, fundamentals)
    return feats


def _require_fundamentals(spec: StrategySpec, fundamentals: Optional[pd.DataFrame]) -> None:
    if uses_fundamentals(spec) and (fundamentals is None or len(fundamentals) == 0):
        raise ValueError(
            "该策略使用财务因子（如扣非净利润同比），但未提供财务数据——"
            "需先接入财务数据（按公告日对齐），不能静默忽略。"
        )


def _condition_detail(feats: pd.DataFrame, c: Condition, i: int) -> Dict[str, Any]:
    left = feats[c.field].iloc[i] if c.field in feats.columns else np.nan
    right_series = _operand(feats, c.value, feats.index)
    right = right_series.iloc[i]
    ok = bool(_eval_condition(feats, c).iloc[i])
    return {
        "group": None,
        "text": c.describe(),
        "field": c.field, "op": c.op, "value": c.value,
        "left": None if pd.isna(left) else float(left),
        "right": None if pd.isna(right) else float(right),
        "ok": ok,
    }


def _evidence(feats: pd.DataFrame, i: int, spec: StrategySpec, action: str) -> Dict[str, Any]:
    conds = []
    for grp, cs in (("filter", spec.filters), ("entry", spec.entry), ("exit", spec.exit)):
        for c in cs:
            d = _condition_detail(feats, c, i)
            d["group"] = grp
            conds.append(d)
    return {"action": action, "date": str(feats.index[i])[:10], "conditions": conds}


def evaluate(
    df: pd.DataFrame, spec: StrategySpec, fundamentals: Optional[pd.DataFrame] = None
) -> tuple:
    """输出 (每期目标权重, 状态事件)。事件记录每次买入/卖出的条件证据（可追溯）。"""
    _require_fundamentals(spec, fundamentals)
    feats = _feats_for(df, fundamentals)
    if len(feats) == 0:
        return pd.Series(dtype=float, name="target_weight"), {}

    filt = _group_mask(feats, spec.filters, spec.filters_logic)
    entry = _group_mask(feats, spec.entry, spec.entry_logic)
    exit_ = _group_mask(feats, spec.exit, spec.exit_logic)

    target = np.zeros(len(feats))
    events: Dict[Any, Dict[str, Any]] = {}
    in_pos = False
    hold_left = 0
    held = 0
    for i in range(len(feats)):
        if in_pos:
            held += 1
            if hold_left > 0:
                hold_left -= 1
            time_up = spec.max_hold > 0 and held >= spec.max_hold
            if (bool(exit_.iloc[i]) or not bool(filt.iloc[i]) or time_up) and hold_left <= 0:
                in_pos = False
                ev = _evidence(feats, i, spec, "exit")
                if time_up and not bool(exit_.iloc[i]):
                    ev["trigger"] = "max_hold"
                    ev["note"] = f"达到最长持有 {spec.max_hold} 天，强制卖出"
                events[feats.index[i]] = ev
        if not in_pos and bool(filt.iloc[i]) and bool(entry.iloc[i]):
            in_pos = True
            hold_left = spec.min_hold
            held = 0
            events[feats.index[i]] = _evidence(feats, i, spec, "enter")
        target[i] = spec.weight if in_pos else 0.0
    return pd.Series(target, index=feats.index, name="target_weight"), events


def evaluate_signals(df: pd.DataFrame, spec: StrategySpec, fundamentals: Optional[pd.DataFrame] = None) -> pd.Series:
    """仅返回目标权重（兼容用法）。"""
    return evaluate(df, spec, fundamentals)[0]


def explain_last(df: pd.DataFrame, spec: StrategySpec, fundamentals: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """解释最新一根 K 线的信号：目标权重、条件命中/未命中的**实际数据值**。"""
    _require_fundamentals(spec, fundamentals)
    feats = _feats_for(df, fundamentals)
    if len(feats) == 0:
        return {"target": 0.0, "prev": 0.0, "passed": [], "failed": [], "conditions": [],
                "values": {}, "date": None, "price": None}

    i = len(feats) - 1
    conditions: List[Dict[str, Any]] = []
    for grp, cs in (("filter", spec.filters), ("entry", spec.entry), ("exit", spec.exit)):
        for c in cs:
            d = _condition_detail(feats, c, i)
            d["group"] = grp
            conditions.append(d)

    passed = [d["text"] for d in conditions if d["group"] in ("filter", "entry") and d["ok"]]
    failed = [d["text"] for d in conditions if d["group"] in ("filter", "entry") and not d["ok"]]
    exit_hit = bool(_group_mask(feats, spec.exit, spec.exit_logic).iloc[i]) if spec.exit else False

    sig, _ = evaluate(df, spec, fundamentals)
    target = float(sig.iloc[-1])
    prev = float(sig.iloc[-2]) if len(sig) > 1 else 0.0
    last = feats.iloc[-1]
    prev_close = float(feats["close"].iloc[-2]) if len(feats) > 1 else float(last["close"])
    change_pct = (
        float(last["pct_chg"]) if "pct_chg" in feats.columns and pd.notna(last.get("pct_chg"))
        else (float(last["close"]) / prev_close - 1.0 if prev_close else 0.0)
    )

    def val(f):
        return float(last[f]) if f in feats.columns and pd.notna(last.get(f)) else None

    return {
        "date": feats.index[-1],
        "price": float(last["close"]),
        "change_pct": change_pct,
        "vol_ratio": val("vol_ratio"),
        "above_ma20": bool(last["close"] > last["ma20"]) if pd.notna(last.get("ma20")) else None,
        "ret20": val("ret20"),
        "turnover": val("amount"),
        "target": target,
        "prev": prev,
        "exit_hit": exit_hit,
        "passed": passed,
        "failed": failed,
        "conditions": conditions,
        "values": {f: val(f) for f in
                   ("close", "ma5", "ma10", "ma20", "ma60", "ma120", "vol_ratio", "vol_ratio5",
                    "ret5", "ret20", "rsi14", "high20", "low20", "amount", "profit_growth")},
    }


def targets_from_spec(
    prices: Dict[str, pd.DataFrame],
    spec: StrategySpec,
    fundamentals_map: Optional[Dict[str, pd.DataFrame]] = None,
) -> tuple:
    """生成 ({日期: {symbol: 权重}}, {(日期, symbol): 触发证据})。"""
    targets: Dict[Any, Dict[str, float]] = {}
    evidence: Dict[Any, Dict[str, Any]] = {}
    fmap = fundamentals_map or {}
    for sym in spec.universe:
        if sym not in prices:
            continue
        sig, events = evaluate(prices[sym], spec, fmap.get(sym))
        for d, w in sig.items():
            if w > 0:
                targets.setdefault(d, {})[sym] = float(w)
        for d, ev in events.items():
            evidence[(d, sym)] = ev
    return targets, evidence


def run_spec(
    prices: Dict[str, pd.DataFrame],
    spec: StrategySpec,
    initial_cash: float = 3000.0,
    cost: Optional[TradingCost] = None,
    names: Optional[Dict[str, str]] = None,
    fundamentals_map: Optional[Dict[str, pd.DataFrame]] = None,
    strategy_version: Optional[int] = None,
) -> EngineResult:
    """用事件驱动引擎回测规格。"""
    targets, evidence = targets_from_spec(prices, spec, fundamentals_map)
    cfg = EngineConfig(
        initial_cash=initial_cash,
        cost=cost or TradingCost(),
        risk=spec.risk_config(),
        names=dict(names or {}),
        stop_loss=spec.stop_loss,
        strategy_version=strategy_version,
        strategy_name=spec.name,
    )
    return Broker(cfg).run(prices, targets, evidence=evidence)
