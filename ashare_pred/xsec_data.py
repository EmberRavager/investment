"""横截面模型辅助数据：行业映射（静态近似）、退市名单、规模代理。

- 行业：优先东财行业板块成分（静态近似）；取不到则返回空（下游自动跳过行业中性化，只做规模中性化）。
- 退市：交易所退市名单，用于缓解幸存者偏差（历史行情能否补齐取决于数据源，缺则如实标注）。
所有结果本地缓存；失败一律优雅降级，不阻断主流程。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List

import pandas as pd

from .providers.base import no_proxy_env

_CACHE = Path("data/cache")


def _digits_col(df: pd.DataFrame) -> str:
    for c in df.columns:
        s = df[c].astype(str).head(20)
        if s.str.fullmatch(r"\d{5,6}").mean() > 0.5:
            return c
    return df.columns[0]


@lru_cache(maxsize=1)
def load_industry_map(verbose: bool = False) -> Dict[str, str]:
    """代码 -> 行业名（静态近似）。失败返回空 dict。"""
    path = _CACHE / "industry_map.parquet"
    if path.exists():
        try:
            df = pd.read_parquet(path)
            return dict(zip(df["code"].astype(str), df["industry"].astype(str)))
        except Exception:  # noqa: BLE001
            pass

    mapping: Dict[str, str] = {}
    try:
        import akshare as ak

        with no_proxy_env():
            boards = ak.stock_board_industry_name_em()
            name_col = "板块名称" if "板块名称" in boards.columns else boards.columns[1]
            for nm in list(boards[name_col])[:120]:
                try:
                    cons = ak.stock_board_industry_cons_em(symbol=str(nm))
                    code_col = "代码" if "代码" in cons.columns else _digits_col(cons)
                    for code in cons[code_col]:
                        mapping[str(code).zfill(6)] = str(nm)
                except Exception:  # noqa: BLE001
                    continue
    except Exception as exc:  # noqa: BLE001
        if verbose:
            print(f"[xsec_data] 行业映射失败（将跳过行业中性化）：{type(exc).__name__}")

    if mapping:
        try:
            _CACHE.mkdir(parents=True, exist_ok=True)
            pd.DataFrame({"code": list(mapping), "industry": list(mapping.values())}).to_parquet(path)
        except Exception:  # noqa: BLE001
            pass
    return mapping


@lru_cache(maxsize=16)
def load_index_components(index_symbol: str, verbose: bool = False) -> List[str]:
    """指数成分股代码（尽力获取，缓解幸存者偏差）。失败返回空列表。"""
    path = _CACHE / f"idxcons_{index_symbol}.parquet"
    if path.exists():
        try:
            return [str(c) for c in pd.read_parquet(path)["code"]]
        except Exception:  # noqa: BLE001
            pass

    codes: List[str] = []
    try:
        import akshare as ak

        with no_proxy_env():
            try:
                df = ak.index_stock_cons_csindex(symbol=index_symbol)
                col = "成分券代码" if "成分券代码" in df.columns else _digits_col(df)
                codes = [str(x).zfill(6) for x in df[col]]
            except Exception:  # noqa: BLE001
                df = ak.index_stock_cons_sina(symbol=index_symbol)
                col = "code" if "code" in df.columns else _digits_col(df)
                codes = [str(x).zfill(6) for x in df[col]]
    except Exception as exc:  # noqa: BLE001
        if verbose:
            print(f"[xsec_data] 指数成分失败 {index_symbol}: {type(exc).__name__}")

    codes = sorted(set(codes))
    if codes:
        try:
            _CACHE.mkdir(parents=True, exist_ok=True)
            pd.DataFrame({"code": codes}).to_parquet(path)
        except Exception:  # noqa: BLE001
            pass
    return codes


def build_index_universe(index_symbol: str = "000905", include_delisted: bool = True) -> List[str]:
    """指数成分 ∪ 退市名单：既保证可交易、又尽量缓解幸存者偏差。"""
    syms = set(load_index_components(index_symbol))
    if include_delisted:
        syms.update(load_delisted())
    return sorted(syms)


@lru_cache(maxsize=1)
def load_delisted(verbose: bool = False) -> List[str]:
    """退市股票代码（尽力获取）。失败返回空列表。"""
    path = _CACHE / "delisted.parquet"
    if path.exists():
        try:
            df = pd.read_parquet(path)
            return [str(c) for c in df["code"]]
        except Exception:  # noqa: BLE001
            pass

    out: List[str] = []
    try:
        import akshare as ak

        with no_proxy_env():
            for fn in ("stock_info_sh_delist", "stock_info_sz_delist"):
                try:
                    df = getattr(ak, fn)()
                    col = _digits_col(df)
                    out += [str(x).zfill(6) for x in df[col]]
                except Exception:  # noqa: BLE001
                    continue
    except Exception as exc:  # noqa: BLE001
        if verbose:
            print(f"[xsec_data] 退市名单失败：{type(exc).__name__}")

    out = sorted(set(out))
    if out:
        try:
            _CACHE.mkdir(parents=True, exist_ok=True)
            pd.DataFrame({"code": out}).to_parquet(path)
        except Exception:  # noqa: BLE001
            pass
    return out
