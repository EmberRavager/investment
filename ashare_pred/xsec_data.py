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


#: baostock 支持的指数（真 PIT 成分）
_BS_INDEX = {"000300": "hs300", "000905": "zz500", "000016": "sz50"}


@lru_cache(maxsize=64)
def load_pit_membership(index_symbol: str, start: str, end: str, step_days: int = 30) -> List[tuple]:
    """按日期采样的指数成分（真 PIT）。返回 [(date, symbol)] 列表；baostock 不可用则返回 []。"""
    if index_symbol not in _BS_INDEX:
        return []
    path = _CACHE / f"pit_{index_symbol}_{start}_{end}.parquet"
    if path.exists():
        try:
            df = pd.read_parquet(path)
            return list(zip(df["date"].astype(str), df["code"].astype(str)))
        except Exception:  # noqa: BLE001
            pass

    out = []
    try:
        import baostock as bs
        import datetime

        with no_proxy_env():
            bs.login()
            try:
                d0 = pd.to_datetime(start)
                d1 = pd.to_datetime(end)
                d = d0
                while d <= d1:
                    fn = getattr(bs, f"query_{_BS_INDEX[index_symbol]}_stocks")
                    rs = fn(date=d.strftime("%Y-%m-%d"))
                    while rs.next():
                        row = rs.get_row_data()
                        code = str(row[1]).split(".")[-1].zfill(6)
                        out.append((d.strftime("%Y-%m-%d"), code))
                    d = d + pd.Timedelta(days=step_days)
            finally:
                bs.logout()
    except Exception:  # noqa: BLE001
        return []

    if out:
        try:
            _CACHE.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(out, columns=["date", "code"]).to_parquet(path)
        except Exception:  # noqa: BLE001
            pass
    return out


def build_pit_universe(index_symbol: str = "000905", start: str = "2018-01-01",
                       end: str = "2026-12-31", include_delisted: bool = True) -> List[str]:
    """指数的 PIT 成分并集（期间任一时点属于指数）+ 退市名单。"""
    syms = {code for _, code in load_pit_membership(index_symbol, start, end)}
    if not syms:
        syms = set(load_index_components(index_symbol))
    if include_delisted:
        syms.update(load_delisted())
    return sorted(syms)


def membership_months(index_symbol: str, start: str, end: str) -> set:
    """返回 {'symbol|YYYY-MM'} 集合，用于按月份过滤面板（近似 PIT 成分）。"""
    out = set()
    for d, code in load_pit_membership(index_symbol, start, end):
        out.add(f"{code}|{str(d)[:7]}")
    return out


@lru_cache(maxsize=1)
def load_industry_history(verbose: bool = False) -> pd.DataFrame:
    """时变行业历史（尽力）：返回 [code, date, industry]。取不到则空表（回退静态行业）。"""
    path = _CACHE / "industry_hist.parquet"
    if path.exists():
        try:
            return pd.read_parquet(path)
        except Exception:  # noqa: BLE001
            pass
    df = pd.DataFrame(columns=["code", "date", "industry"])
    try:
        import akshare as ak

        with no_proxy_env():
            raw = ak.stock_industry_clf_hist_sw()
        # 尽力解析（不同版本列名不一）
        cols = list(raw.columns)
        ccol = next((c for c in cols if "代码" in c or c.lower() == "code"), cols[1] if len(cols) > 1 else cols[0])
        dcol = next((c for c in cols if "日期" in c or "date" in c.lower()), cols[0])
        icol = next((c for c in cols if "行业" in c), cols[-1])
        df = pd.DataFrame({
            "code": raw[ccol].astype(str).str.zfill(6),
            "date": pd.to_datetime(raw[dcol], errors="coerce").dt.strftime("%Y-%m-%d"),
            "industry": raw[icol].astype(str),
        }).dropna()
        if len(df):
            _CACHE.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path)
    except Exception as exc:  # noqa: BLE001
        if verbose:
            print(f"[xsec_data] 时变行业不可用（回退静态）：{type(exc).__name__}")
    return df


def industry_resolver() -> "callable":
    """返回 (symbol, date_str) -> industry 的函数；无时变数据则回退静态行业映射。"""
    hist = load_industry_history()
    static = load_industry_map()
    if len(hist):
        by_code = {c: g.sort_values("date") for c, g in hist.groupby("code")}

        def resolve(sym: str, date: str) -> str:
            g = by_code.get(str(sym))
            if g is not None:
                sub = g[g["date"] <= str(date)[:10]]
                if len(sub):
                    return str(sub.iloc[-1]["industry"])
            return static.get(str(sym), "UNK")
        return resolve

    def resolve_static(sym: str, date: str = "") -> str:  # noqa: ARG001
        return static.get(str(sym), "UNK")
    return resolve_static


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
