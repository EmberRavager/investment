"""数据层：通过可插拔数据源（akshare / MCP）拉取行情，本地 parquet 缓存。

统一输出列：date(index, DatetimeIndex), open, high, low, close, volume, amount,
pct_chg, turnover。
"""

from __future__ import annotations

import datetime
import hashlib
import json
import time
from pathlib import Path
from typing import Dict

import pandas as pd

from .config import DataConfig
from .providers import build_provider, normalize
from .providers.base import no_proxy_env

#: "最新"数据（end>=今天）的缓存有效期；过期即重新拉取，保证收盘后能刷新出当日行情
_LATEST_TTL_SECONDS = 600


def _cache_path(cfg: DataConfig) -> Path:
    key = json.dumps(
        {
            "provider": cfg.provider,
            "symbol": cfg.symbol,
            "kind": cfg.kind,
            "adjust": cfg.adjust,
            "start": cfg.start,
            "end": cfg.end,
        },
        sort_keys=True,
    )
    digest = hashlib.md5(key.encode()).hexdigest()[:10]
    name = f"{cfg.provider}_{cfg.kind}_{cfg.symbol}_{cfg.adjust or 'raw'}_{digest}.parquet"
    return Path(cfg.cache_dir) / name


def load_prices(cfg: DataConfig, verbose: bool = True) -> pd.DataFrame:
    """读取（或拉取并缓存）日线行情，返回按日期升序的 DataFrame。

    「最新」数据（end >= 今天）的缓存有 TTL：过期会自动重拉，
    避免收盘后页面仍停留在上一交易日。
    """
    path = _cache_path(cfg)
    if cfg.use_cache and path.exists():
        latest = bool(cfg.end) and str(cfg.end) >= datetime.date.today().isoformat()
        fresh = (time.time() - path.stat().st_mtime) < _LATEST_TTL_SECONDS
        if (not latest) or fresh:
            if verbose:
                print(f"[data] 命中缓存 {path}")
            return pd.read_parquet(path)

    provider = build_provider(cfg)
    if verbose:
        print(f"[data] 数据源={provider.name} 拉取 {cfg.kind} {cfg.symbol} {cfg.start}~{cfg.end} ...")
    raw = provider.fetch_daily(cfg.symbol, cfg.kind, cfg.start, cfg.end, cfg.adjust)
    df = normalize(raw)

    if cfg.use_cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
        if verbose:
            print(f"[data] 已缓存 -> {path}")
    return df


def prefetch_prices(symbols, start, end, adjust="qfq", progress=None, kinds=None):
    """批量预取并缓存一篮子股票的日线（顺序执行，避免 no_proxy_env 全局补丁的线程竞争）。

    返回 {"ok": [...], "failed": [...]}；progress(i, total, symbol, status) 会逐只回调。
    已缓存的会秒回；未缓存的才联网拉。
    """
    ok, failed = [], []
    total = max(1, len(symbols))
    for i, sym in enumerate(symbols):
        kind = (kinds or {}).get(sym) or infer_kind(sym)
        status = "ok"
        try:
            load_prices(DataConfig(symbol=sym, kind=kind, start=start, end=end, adjust=adjust), verbose=False)
            ok.append(sym)
        except Exception as exc:  # noqa: BLE001
            status = f"失败:{type(exc).__name__}"
            failed.append({"symbol": sym, "reason": f"{type(exc).__name__}: {str(exc)[:80]}"})
        if progress:
            progress(i + 1, total, sym, status)
    return {"ok": ok, "failed": failed, "total": len(symbols)}


def infer_kind(symbol: str) -> str:
    """按代码前缀判断 stock / index / fund（ETF）。"""
    s = str(symbol)
    if s.startswith(("000300", "000905", "000688", "000852", "399")):
        return "index"
    if s.startswith(("15", "51", "56", "58")):   # 159xxx / 51xxxx / 56xxxx / 588xxx 等 ETF
        return "fund"
    return "stock"


def _normalize_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """把不同数据源的快照统一成 symbol/name/price/pct_chg/amount。"""
    ren = {"代码": "symbol", "名称": "name", "最新价": "price",
           "涨跌幅": "pct_chg", "成交额": "amount"}
    out = df.rename(columns=ren).copy()
    keep = [c for c in ["symbol", "name", "price", "pct_chg", "amount"] if c in out.columns]
    out = out[keep]
    out["symbol"] = (
        out["symbol"].astype(str).str.replace(r"\D", "", regex=True).str[-6:].str.zfill(6)
    )
    for col in ("price", "pct_chg", "amount"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["symbol", "name"])


def load_code_name_map(verbose: bool = True) -> Dict[str, str]:
    """全市场 代码->名称 映射（用于界面展示；本地缓存）。

    数据源：akshare stock_info_a_code_name（快）；失败则退回全市场快照。
    """
    cache = Path("data/cache") / "code_name.parquet"
    if cache.exists():
        try:
            df = pd.read_parquet(cache)
            return {
                str(c).zfill(6): str(n).replace(" ", "")
                for c, n in zip(df["code"], df["name"])
            }
        except Exception:  # noqa: BLE001
            pass

    mapping: Dict[str, str] = {}
    try:
        import akshare as ak

        with no_proxy_env():
            raw = ak.stock_info_a_code_name()
        code_col = "code" if "code" in raw.columns else raw.columns[0]
        name_col = "name" if "name" in raw.columns else raw.columns[1]
        mapping = {
            str(c).zfill(6): str(n).replace(" ", "")
            for c, n in zip(raw[code_col], raw[name_col])
            if str(c).strip()
        }
        # 追加 ETF/基金名称（代码不冲突）
        try:
            with no_proxy_env():
                funds = ak.fund_name_em()
            for c, n in zip(funds["基金代码"], funds["基金简称"]):
                code = str(c).zfill(6)
                if code not in mapping:
                    mapping[code] = str(n).replace(" ", "")
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001 — 退回快照
        if verbose:
            print(f"[data] code->name 失败，改用快照：{type(exc).__name__}")
        try:
            snap = load_market_snapshot(verbose=verbose)
            mapping = {
                str(s): str(n).replace(" ", "")
                for s, n in zip(snap["symbol"], snap["name"])
            }
        except Exception:  # noqa: BLE001
            mapping = {}

    if mapping:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                {"code": list(mapping), "name": list(mapping.values())}
            ).to_parquet(cache)
        except Exception:  # noqa: BLE001
            pass
    return mapping


def load_market_snapshot(verbose: bool = True) -> pd.DataFrame:
    """全市场 A 股实时快照（eastmoney 优先，失败自动降级 sina）。

    返回统一列：symbol(6位) / name / price / pct_chg / amount。
    """
    import akshare as ak

    with no_proxy_env():
        for source, fn in (("eastmoney", ak.stock_zh_a_spot_em), ("sina", ak.stock_zh_a_spot)):
            try:
                if verbose:
                    print(f"[data] 拉取全市场快照 {source} ...")
                snap = fn()
                if snap is not None and len(snap) > 0:
                    return _normalize_snapshot(snap)
            except Exception as exc:  # noqa: BLE001 — 换下一个源
                if verbose:
                    print(f"[data] {source} 失败：{type(exc).__name__}: {str(exc)[:80]}")
    raise RuntimeError("未取到全市场快照（eastmoney / sina 均失败）")


def load_etf_snapshot(verbose: bool = True) -> pd.DataFrame:
    """全市场 ETF 快照（新浪列表优先），返回统一列 symbol/name/price/pct_chg/amount。"""
    import akshare as ak

    with no_proxy_env():
        for source, fn in (
            ("sina", lambda: ak.fund_etf_category_sina(symbol="ETF基金")),
            ("eastmoney", lambda: ak.fund_etf_spot_em()),
        ):
            try:
                if verbose:
                    print(f"[data] 拉取 ETF 快照 {source} ...")
                snap = fn()
                if snap is not None and len(snap) > 0:
                    return _normalize_snapshot(snap)
            except Exception as exc:  # noqa: BLE001
                if verbose:
                    print(f"[data] ETF {source} 失败：{type(exc).__name__}: {str(exc)[:80]}")
    raise RuntimeError("未取到 ETF 快照（sina / eastmoney 均失败）")
