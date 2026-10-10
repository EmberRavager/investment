#!/usr/bin/env python3
"""命令行入口：加载 YAML -> 覆盖参数 -> 运行流水线。

示例：
    python run.py --config configs/default.yaml
    python run.py --model lightgbm --symbol 000300 --kind index
    python run.py --param n_estimators=800 --param max_depth=6
    python run.py --list-models
"""

from __future__ import annotations

import argparse

from ashare_pred.config import Config
from ashare_pred.models import list_models
from ashare_pred.pipeline import run


def _set_dotted(obj, dotted: str, value: str) -> None:
    keys = dotted.split(".")
    cur = obj
    for k in keys[:-1]:
        cur = getattr(cur, k)
    field = keys[-1]
    old = getattr(cur, field)
    if isinstance(old, bool):
        new = value.lower() in ("1", "true", "yes", "y")
    elif isinstance(old, int):
        new = int(value)
    elif isinstance(old, float):
        new = float(value)
    else:
        new = value
    setattr(cur, field, new)


def main() -> None:
    ap = argparse.ArgumentParser(description="A 股量化预测系统")
    ap.add_argument("-c", "--config", default="configs/default.yaml")
    ap.add_argument("--symbol")
    ap.add_argument("--kind", choices=["stock", "index"])
    ap.add_argument("--model")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--horizon", type=int)
    ap.add_argument("--threshold", type=float)
    ap.add_argument("--out", dest="out_dir")
    ap.add_argument("--param", action="append", default=[],
                    help="覆盖模型参数, 形如 --param n_estimators=800 (可多次)")
    ap.add_argument("--set", action="append", default=[],
                    help="覆盖任意配置项(点路径), 形如 --set backtest.prob_threshold=0.6")
    ap.add_argument("--no-plot", action="store_true")
    ap.add_argument("--list-models", action="store_true")
    args = ap.parse_args()

    if args.list_models:
        print("可用模型:")
        for m in list_models():
            print(f"  - {m}")
        return

    cfg = Config.load(args.config)

    if args.symbol:
        cfg.data.symbol = args.symbol
    if args.kind:
        cfg.data.kind = args.kind
    if args.start:
        cfg.data.start = args.start
    if args.end:
        cfg.data.end = args.end
    if args.model:
        cfg.model.name = args.model
        cfg.model.params = {}  # 换模型时清空上一个模型的遗留参数
    if args.horizon:
        cfg.labels.horizon = args.horizon
    if args.threshold is not None:
        cfg.labels.threshold = args.threshold
    if args.out_dir:
        cfg.output.dir = args.out_dir
    if args.no_plot:
        cfg.output.plot = False

    for kv in args.param:
        k, _, v = kv.partition("=")
        cfg.model.params[k] = v if not _looks_number(v) else _parse_number(v)
    for item in args.set:
        k, _, v = item.partition("=")
        if k == "model.name":
            cfg.model.params = {}
        _set_dotted(cfg, k, v)

    cfg.validate()
    run(cfg)


def _looks_number(v: str) -> bool:
    try:
        float(v)
        return True
    except ValueError:
        return False


def _parse_number(v: str):
    return float(v) if ("." in v or "e" in v.lower()) else int(v)


if __name__ == "__main__":
    main()
