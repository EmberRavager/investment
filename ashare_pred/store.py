"""持久化层（SQLite，零额外依赖）。

保存策略、策略版本、运行（回测/模拟盘）、订单、成交、持仓、净值曲线、
风险事件与每日信号。先本地 SQLite 打通闭环，后续可平滑迁移到 PostgreSQL。

设计要点（呼应 PRD）：
- 策略配置与版本分离，任何改动生成新版本，保证回测可复现；
- 未完成回测的策略不允许标记为「已验证 / 盈利」；
- 运行结果（成交、被拒订单、风控事件、净值）全部落库，可追溯。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    source TEXT DEFAULT 'manual',
    status TEXT DEFAULT 'draft',
    current_version INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS strategy_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    note TEXT DEFAULT '',
    created_at TEXT,
    UNIQUE(strategy_id, version)
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER,
    version INTEGER,
    kind TEXT NOT NULL,
    symbol TEXT,
    start TEXT,
    end TEXT,
    initial_cash REAL,
    status TEXT DEFAULT 'running',
    metrics_json TEXT,
    error TEXT,
    created_at TEXT,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    date TEXT,
    signal_date TEXT,
    symbol TEXT,
    name TEXT,
    side TEXT,
    qty INTEGER,
    price REAL,
    amount REAL,
    status TEXT,
    strategy_version INTEGER,
    reason TEXT,
    evidence_json TEXT
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    date TEXT,
    signal_date TEXT,
    symbol TEXT,
    name TEXT,
    side TEXT,
    qty INTEGER,
    price REAL,
    amount REAL,
    commission REAL,
    stamp_tax REAL,
    slippage_cost REAL,
    total_fee REAL,
    strategy_version INTEGER,
    reason TEXT,
    evidence_json TEXT
);
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    date TEXT,
    symbol TEXT,
    name TEXT,
    qty INTEGER,
    available_qty INTEGER,
    cost_price REAL,
    last_price REAL,
    market_value REAL,
    pnl REAL,
    pnl_pct REAL
);
CREATE TABLE IF NOT EXISTS equity_curve (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    date TEXT,
    equity REAL,
    exposure REAL
);
CREATE TABLE IF NOT EXISTS risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    date TEXT,
    kind TEXT,
    symbol TEXT,
    reason TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    date TEXT,
    symbol TEXT,
    score REAL,
    target_weight REAL,
    signal TEXT
);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path = "data/quantpilot.db"):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False：FastAPI 的同步端点与流式后台线程会跨线程访问同一连接
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """给旧库补列（幂等）。"""
        def cols(table):
            return {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
        wanted = {
            "orders": {
                "signal_date": "TEXT", "strategy_version": "INTEGER", "evidence_json": "TEXT",
            },
            "trades": {
                "signal_date": "TEXT", "strategy_version": "INTEGER", "evidence_json": "TEXT",
            },
        }
        for table, add in wanted.items():
            existing = cols(table)
            for col, typ in add.items():
                if col not in existing:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")

    def close(self) -> None:
        self.conn.close()

    # ---- 策略与版本 ----
    def create_strategy(
        self, name: str, config: Dict[str, Any], description: str = "", source: str = "manual"
    ) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO strategies (name, description, source, status, current_version, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (name, description, source, "draft", 1, _now(), _now()),
        )
        sid = int(cur.lastrowid)
        cur.execute(
            "INSERT INTO strategy_versions (strategy_id, version, config_json, note, created_at)"
            " VALUES (?,?,?,?,?)",
            (sid, 1, json.dumps(config, ensure_ascii=False), "初始版本", _now()),
        )
        self.conn.commit()
        return sid

    def add_version(self, strategy_id: int, config: Dict[str, Any], note: str = "") -> int:
        row = self.conn.execute(
            "SELECT current_version FROM strategies WHERE id=?", (strategy_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"策略 {strategy_id} 不存在")
        version = int(row["current_version"]) + 1
        self.conn.execute(
            "INSERT INTO strategy_versions (strategy_id, version, config_json, note, created_at)"
            " VALUES (?,?,?,?,?)",
            (strategy_id, version, json.dumps(config, ensure_ascii=False), note, _now()),
        )
        self.conn.execute(
            "UPDATE strategies SET current_version=?, updated_at=? WHERE id=?",
            (version, _now(), strategy_id),
        )
        self.conn.commit()
        return version

    def get_strategy(self, strategy_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM strategies WHERE id=?", (strategy_id,)).fetchone()
        if row is None:
            return None
        out = dict(row)
        ver = self.conn.execute(
            "SELECT config_json, note, created_at FROM strategy_versions"
            " WHERE strategy_id=? AND version=?",
            (strategy_id, row["current_version"]),
        ).fetchone()
        if ver:
            out["config"] = json.loads(ver["config_json"])
            out["config_note"] = ver["note"]
        return out

    def list_strategies(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM strategies ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    def delete_strategy(self, strategy_id: int) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM strategy_versions WHERE strategy_id=?", (strategy_id,))
            self.conn.execute("UPDATE runs SET strategy_id=NULL WHERE strategy_id=?", (strategy_id,))
            self.conn.execute("DELETE FROM strategies WHERE id=?", (strategy_id,))
            self.conn.commit()

    def dedupe_by_name(self) -> int:
        """同名策略只保留最新一条，删除其余重复。返回删除数量。"""
        with self._lock:
            rows = self.conn.execute("SELECT id, name FROM strategies ORDER BY id DESC").fetchall()
            seen, to_del = set(), []
            for r in rows:
                if r["name"] in seen:
                    to_del.append(r["id"])
                else:
                    seen.add(r["name"])
            for sid in to_del:
                self.conn.execute("DELETE FROM strategy_versions WHERE strategy_id=?", (sid,))
                self.conn.execute("UPDATE runs SET strategy_id=NULL WHERE strategy_id=?", (sid,))
                self.conn.execute("DELETE FROM strategies WHERE id=?", (sid,))
            self.conn.commit()
            return len(to_del)

    def seed_presets(self, presets: List[Dict[str, Any]]) -> int:
        """把预设策略写入策略库（同名已存在则跳过）。返回新增数量。"""
        existing = {r["name"] for r in self.conn.execute("SELECT name FROM strategies").fetchall()}
        added = 0
        for p in presets:
            if p["name"] in existing:
                continue
            self.create_strategy(p["name"], p["spec"], description=p.get("description", ""), source="preset")
            added += 1
        return added

    def set_status(self, strategy_id: int, status: str) -> None:
        if status in ("validated", "active"):
            if self._has_completed_run(strategy_id) is False:
                raise ValueError("未完成回测验证，不能标记为已验证/启用")
        self.conn.execute(
            "UPDATE strategies SET status=?, updated_at=? WHERE id=?", (status, _now(), strategy_id)
        )
        self.conn.commit()

    def _has_completed_run(self, strategy_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM runs WHERE strategy_id=? AND status='done' LIMIT 1", (strategy_id,)
        ).fetchone()
        return row is not None

    # ---- 运行 ----
    def create_run(
        self,
        kind: str,
        strategy_id: Optional[int] = None,
        version: Optional[int] = None,
        symbol: str = "",
        start: str = "",
        end: str = "",
        initial_cash: float = 0.0,
    ) -> int:
        cur = self.conn.cursor()
        with self._lock:
            cur.execute(
                "INSERT INTO runs (strategy_id, version, kind, symbol, start, end, initial_cash,"
                " status, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (strategy_id, version, kind, symbol, start, end, initial_cash, "running", _now()),
            )
            self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, metrics: Dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE runs SET status='done', metrics_json=?, finished_at=? WHERE id=?",
            (json.dumps(metrics, ensure_ascii=False), _now(), run_id),
        )
        self.conn.commit()

    def fail_run(self, run_id: int, error: str) -> None:
        self.conn.execute(
            "UPDATE runs SET status='failed', error=?, finished_at=? WHERE id=?",
            (error, _now(), run_id),
        )
        self.conn.commit()

    def list_runs(self, strategy_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if strategy_id is None:
            rows = self.conn.execute("SELECT * FROM runs ORDER BY id DESC").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM runs WHERE strategy_id=? ORDER BY id DESC", (strategy_id,)
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("metrics_json"):
                d["metrics"] = json.loads(d["metrics_json"])
            out.append(d)
        return out

    def get_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        row = self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        if d.get("metrics_json"):
            d["metrics"] = json.loads(d["metrics_json"])
        return d

    # ---- 结果落库 ----
    def save_trades(self, run_id: int, trades: List[Any]) -> None:
        self.conn.executemany(
            "INSERT INTO trades (run_id, date, signal_date, symbol, name, side, qty, price, amount,"
            " commission, stamp_tax, slippage_cost, total_fee, strategy_version, reason, evidence_json)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (run_id, str(t.date), str(getattr(t, "signal_date", "") or ""), t.symbol, t.name,
                 t.side, int(t.qty), float(t.price), float(t.amount), float(t.commission),
                 float(t.stamp_tax), float(t.slippage_cost), float(t.total_fee),
                 getattr(t, "strategy_version", None), t.reason,
                 json.dumps(getattr(t, "evidence", None), ensure_ascii=False))
                for t in trades
            ],
        )
        self.conn.commit()

    def save_rejected_orders(self, run_id: int, skips: List[Dict[str, Any]]) -> None:
        self.conn.executemany(
            "INSERT INTO orders (run_id, date, signal_date, symbol, name, side, qty, price, amount,"
            " status, strategy_version, reason, evidence_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (run_id, s.get("date", ""), s.get("signal_date", ""), s.get("symbol", ""),
                 s.get("name", ""), s.get("side", ""), int(s.get("qty", 0) or 0),
                 float(s.get("price", 0) or 0), 0.0, s.get("status", "已拒绝"),
                 s.get("strategy_version"), s.get("reason", ""),
                 json.dumps(s.get("evidence"), ensure_ascii=False))
                for s in skips
            ],
        )
        self.conn.commit()

    def save_snapshots(self, run_id: int, snapshots: List[Dict[str, Any]]) -> None:
        pos_rows, eq_rows = [], []
        for snap in snapshots:
            eq_rows.append((run_id, snap["date"], float(snap["equity"]), float(snap["exposure"])))
            for sym, p in snap.get("positions", {}).items():
                pos_rows.append((
                    run_id, snap["date"], sym, p.get("name", ""), int(p["qty"]),
                    int(p.get("available_qty", 0)), float(p["cost_price"]),
                    float(p["last_price"]), float(p["market_value"]),
                    float(p["pnl"]), float(p["pnl_pct"]),
                ))
        self.conn.executemany(
            "INSERT INTO positions (run_id, date, symbol, name, qty, available_qty, cost_price,"
            " last_price, market_value, pnl, pnl_pct) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            pos_rows,
        )
        self.conn.executemany(
            "INSERT INTO equity_curve (run_id, date, equity, exposure) VALUES (?,?,?,?)",
            eq_rows,
        )
        self.conn.commit()

    def save_risk_events(self, run_id: int, events: List[Dict[str, Any]]) -> None:
        self.conn.executemany(
            "INSERT INTO risk_events (run_id, date, kind, symbol, reason) VALUES (?,?,?,?,?)",
            [(run_id, e.get("date", ""), e.get("kind", ""), e.get("symbol", ""), e.get("reason", ""))
             for e in events],
        )
        self.conn.commit()

    def save_signals(self, run_id: int, signals: List[Dict[str, Any]]) -> None:
        self.conn.executemany(
            "INSERT INTO signals (run_id, date, symbol, score, target_weight, signal)"
            " VALUES (?,?,?,?,?,?)",
            [(run_id, s.get("date", ""), s.get("symbol", ""), float(s.get("score", 0) or 0),
              float(s.get("target_weight", 0) or 0), s.get("signal", "")) for s in signals],
        )
        self.conn.commit()

    def persist_engine_result(self, run_id: int, result) -> None:
        """把 EngineResult 一次性落库（加锁，允许多线程）。"""
        with self._lock:
            self.save_trades(run_id, result.trades)
            self.save_rejected_orders(run_id, result.skips)
            self.save_snapshots(run_id, result.snapshots)
            self.save_risk_events(run_id, result.risk_events)

    # ---- 读取明细 ----
    def get_run_detail(self, run_id: int) -> Dict[str, Any]:
        def q(sql: str):
            return [dict(r) for r in self.conn.execute(sql, (run_id,)).fetchall()]

        return {
            "run": self.get_run(run_id),
            "trades": q("SELECT * FROM trades WHERE run_id=? ORDER BY date, id"),
            "orders": q("SELECT * FROM orders WHERE run_id=? ORDER BY date, id"),
            "positions": q("SELECT * FROM positions WHERE run_id=? ORDER BY date, symbol"),
            "equity_curve": q("SELECT date, equity, exposure FROM equity_curve WHERE run_id=? ORDER BY date"),
            "risk_events": q("SELECT * FROM risk_events WHERE run_id=? ORDER BY date, id"),
        }
