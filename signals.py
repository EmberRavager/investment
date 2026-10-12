#!/usr/bin/env python
"""QuantPilot 今日信号：用一条命令知道「现在该买什么、卖什么」。

用法示例
--------
    .venv/bin/python signals.py                          # 默认成长趋势策略，内置股票池
    .venv/bin/python signals.py --cash 3000              # 按你的本金评估能否买入（整手/仓位约束）
    .venv/bin/python signals.py --symbols 600519,000001,600036
    .venv/bin/python signals.py --nl "找站上20日线且放量的成长股，单股30%，止损8%"
    .venv/bin/python signals.py --top 8 --out outputs/signals.csv

注意：这是研究工具，输出的是「规则信号」，不构成投资建议；历史规律不代表未来。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ashare_pred.config import DataConfig
from ashare_pred.cross_section import DEFAULT_UNIVERSE
from ashare_pred.data import infer_kind, load_prices
from ashare_pred.engine import rules
from ashare_pred.strategy import Condition, StrategySpec, explain_last, validate_spec

PRESETS = {
    "growth": StrategySpec(
        name="成长趋势跟随",
        universe=[],
        filters=[Condition("ma20", ">", "ma60")],
        entry=[Condition("close", ">", "ma20"), Condition("vol_ratio", ">", 1.3)],
        exit=[Condition("close", "<", "ma20")],
        weight=0.30, max_position_per_stock=0.30, stop_loss=0.08, drawdown_stop=0.15,
    ),
    "trend": StrategySpec(
        name="纯趋势",
        universe=[],
        filters=[Condition("close", ">", "ma60")],
        entry=[Condition("close", ">", "ma20")],
        exit=[Condition("close", "<", "ma20")],
        weight=0.50, max_position_per_stock=0.50, stop_loss=0.10, drawdown_stop=0.20,
    ),
}


def infer_kind(symbol: str) -> str:
    s = str(symbol)
    if s.startswith(("000300", "000905", "000688", "000852", "399")):
        return "index"
    return "stock"


def _state(target: float, prev: float) -> str:
    if target > 0 and prev <= 0:
        return "买入"
    if target > 0:
        return "持有"
    if prev > 0:
        return "卖出"
    return "观望"


def _affordable_note(price: float, weight: float, cash: float, symbol: str) -> str:
    if weight <= 0:
        return ""
    budget = weight * cash
    need_one_lot = rules.round_price(price, symbol) * rules.lot_size(symbol)
    qty = rules.round_lot(budget / price, symbol)
    if qty <= 0:
        return f"资金不足：单股上限 {budget:.0f} 元 < 一手约 {need_one_lot:.0f} 元"
    return f"可买约 {qty} 股（{qty * price:.0f} 元）"


def build_spec(args) -> StrategySpec:
    if args.nl:
        from server.strategy_ai import nl_to_spec

        out = nl_to_spec(args.nl)
        spec = StrategySpec.from_dict(out["spec"])
        print(f"[解析] 来源={out['source']}，{out['rationale']}")
        for w in out["warnings"]:
            print(f"[解析][提示] {w}")
        return spec
    return StrategySpec.from_dict(PRESETS[args.strategy].to_dict())


def main() -> int:
    ap = argparse.ArgumentParser(description="QuantPilot 今日信号")
    ap.add_argument("--strategy", choices=list(PRESETS), default="growth")
    ap.add_argument("--nl", default="", help="自然语言策略描述（覆盖 --strategy）")
    ap.add_argument("--symbols", default="", help="逗号分隔代码；留空用内置股票池")
    ap.add_argument("--cash", type=float, default=3000.0, help="本金，用于评估能否买入")
    ap.add_argument("--top", type=int, default=12, help="股票池数量上限（默认池）")
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--end", default="")
    ap.add_argument("--out", default="", help="导出 CSV 路径")
    args = ap.parse_args()

    spec = build_spec(args)
    warnings = validate_spec(spec)

    if args.symbols:
        universe = [(s.strip(), s.strip()) for s in args.symbols.split(",") if s.strip()]
    else:
        universe = DEFAULT_UNIVERSE[: args.top]

    end = args.end or __import__("datetime").date.today().isoformat()

    print(f"\n策略：{spec.name}　本金：¥{args.cash:,.0f}　标的数：{len(universe)}")
    print(f"规则：单股仓位 ≤ {spec.max_position_per_stock:.0%}，止损 {spec.stop_loss:.0%}，回撤熔断 {spec.drawdown_stop:.0%}")
    for w in warnings:
        print(f"[提示] {w}")
    print("-" * 96)
    print(f"{'代码':<8}{'名称':<10}{'信号':<6}{'最新价':>9}{'目标仓位':>9}  依据 / 提示")
    print("-" * 96)

    rows = []
    counts = {"买入": 0, "持有": 0, "卖出": 0, "观望": 0}
    for symbol, name in universe:
        try:
            df = load_prices(
                DataConfig(symbol=symbol, kind=infer_kind(symbol), start=args.start, end=end, adjust="qfq"),
                verbose=False,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"{symbol:<8}{name:<10}{'—':<6}{'':>9}{'':>9}  数据加载失败：{type(exc).__name__}")
            continue

        info = explain_last(df, spec)
        state = _state(info["target"], info["prev"])
        counts[state] += 1
        weight = info["target"]
        tip = _affordable_note(info["price"], spec.weight, args.cash, symbol)
        basis = tip or ("；".join(info["passed"][:3]) if info["passed"] else "无")
        if state == "观望" and info["failed"]:
            basis = "未满足：" + "；".join(info["failed"][:2])
        print(f"{symbol:<8}{name:<10}{state:<6}{info['price']:>9.2f}{weight:>8.0%}  {basis}")
        rows.append({
            "symbol": symbol, "name": name, "date": str(info["date"])[:10],
            "signal": state, "price": round(info["price"], 3), "target_weight": weight,
            "reason": basis,
        })

    print("-" * 96)
    print("汇总：" + "　".join(f"{k} {v}" for k, v in counts.items()))
    print("说明：信号在收盘确认、下一交易日开盘执行；「资金不足」表示按本金和仓位上限买不起一手。")
    print("风险提示：仅为规则信号，非投资建议；请先看回测样本外表现再决定是否使用。")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else
                               ["symbol", "name", "date", "signal", "price", "target_weight", "reason"])
            w.writeheader()
            w.writerows(rows)
        print(f"已导出：{out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
