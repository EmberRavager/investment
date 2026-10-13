"""模拟盘长期跟踪：记录选股快照，事后用真实行情结算，检验信号"能不能用"。

用法：记录当日选股（as_of + 标的 + 持有期）→ 若干交易日后 resolve_pending()，
用真实行情算这批标的的持有期收益与相对指数超额、命中率，形成可累积的样本外记录。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from .config import DataConfig
from .data import infer_kind, load_prices
from .store import Store


def record_snapshot(store: Store, *, as_of: str, picks: List[Dict[str, Any]], horizon: int = 5,
                    index_symbol: str = "000300", strategy_id: Optional[int] = None,
                    kind: str = "xsec", params: Optional[Dict[str, Any]] = None,
                    initial_cash: float = 0.0) -> int:
    return store.create_paper(as_of=as_of, horizon=int(horizon), index_symbol=index_symbol,
                              picks=picks, strategy_id=strategy_id, kind=kind,
                              params=params or {}, initial_cash=initial_cash)


def _forward_return(symbol: str, start: str, end: str, horizon: int) -> Optional[float]:
    try:
        df = load_prices(DataConfig(symbol=symbol, kind=infer_kind(symbol), start=start, end=end,
                                    adjust="qfq"), verbose=False)
    except Exception:  # noqa: BLE001
        return None
    df = df[df.index >= pd.Timestamp(start)]
    if len(df) <= horizon:
        return None
    p0 = float(df["close"].iloc[0])
    p1 = float(df["close"].iloc[horizon])
    return p1 / p0 - 1.0 if p0 > 0 else None


def resolve_pending(store: Store, verbose: bool = False) -> int:
    """对所有未结算快照，若前向数据已足够则结算，返回结算数量。"""
    done = 0
    for snap in store.list_papers(only_pending=True):
        as_of = str(snap["as_of"])
        horizon = int(snap["horizon"])
        end = (pd.Timestamp(as_of) + pd.Timedelta(days=horizon * 3 + 12)).strftime("%Y-%m-%d")
        rets = []
        for p in snap["picks"]:
            r = _forward_return(str(p["symbol"]), as_of, end, horizon)
            if r is not None:
                rets.append(r)
        if not rets:
            continue
        idx_r = _forward_return(str(snap["index_symbol"]), as_of, end, horizon)
        avg = sum(rets) / len(rets)
        store.resolve_paper(snap["id"], {
            "pick_return": round(avg, 4),
            "index_return": round(idx_r, 4) if idx_r is not None else None,
            "excess": round(avg - idx_r, 4) if idx_r is not None else None,
            "hit_rate": round(sum(1 for r in rets if r > 0) / len(rets), 3),
            "n": len(rets),
        })
        done += 1
    return done
