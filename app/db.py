from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import DATA_DIR, ROOT_DIR, load_config


def get_db_path(custom_path: Path | str | None = None) -> Path:
    if custom_path is not None:
        return Path(custom_path)
    cfg = load_config()
    rel = cfg.get("risk", {}).get("database_path", "data/snapback.db")
    path = Path(rel)
    if not path.is_absolute():
        path = ROOT_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = get_db_path(db_path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | str | None = None) -> None:
    """Create all SQLite tables if they do not exist."""
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                company_name TEXT DEFAULT '',
                sector TEXT DEFAULT '',
                signal_type TEXT NOT NULL, -- 'ENTRY', 'EXIT', 'QUEUE_CAPPED', 'RADAR'
                rank INTEGER DEFAULT 0,
                close_price REAL NOT NULL,
                open_price REAL DEFAULT 0.0,
                high_price REAL DEFAULT 0.0,
                low_price REAL DEFAULT 0.0,
                prior_high REAL DEFAULT 0.0,
                sma_200 REAL NOT NULL,
                pct_above_sma200 REAL NOT NULL,
                mom_6_1 REAL NOT NULL,
                mom_percentile REAL NOT NULL,
                rsi_2 REAL NOT NULL,
                close_range_pos REAL NOT NULL,
                days_held INTEGER DEFAULT 0,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(signal_date, signal_type);

            CREATE TABLE IF NOT EXISTS positions (
                symbol TEXT PRIMARY KEY,
                company_name TEXT DEFAULT '',
                sector TEXT DEFAULT '',
                entry_date TEXT NOT NULL,
                entry_price REAL NOT NULL,
                shares REAL NOT NULL,
                current_price REAL NOT NULL,
                prior_high REAL NOT NULL,
                days_held INTEGER NOT NULL DEFAULT 1,
                market_value REAL NOT NULL,
                unrealized_pnl REAL NOT NULL,
                unrealized_pnl_pct REAL NOT NULL,
                mom_6_1 REAL DEFAULT 0.0,
                rsi_2 REAL DEFAULT 50.0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                signal_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL, -- 'BUY' or 'SELL'
                qty REAL NOT NULL,
                notional REAL NOT NULL,
                est_price REAL NOT NULL,
                order_type TEXT NOT NULL DEFAULT 'MOO',
                status TEXT NOT NULL, -- 'DRY_RUN', 'SUBMITTED', 'FILLED', 'BLOCKED_KILL_SWITCH', 'BLOCKED_LOSS_GUARD'
                dry_run INTEGER NOT NULL DEFAULT 1,
                alpaca_order_id TEXT DEFAULT '',
                reason TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_timestamp TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                initial_capital REAL NOT NULL,
                final_equity REAL NOT NULL,
                total_return_pct REAL NOT NULL,
                cagr_pct REAL NOT NULL,
                sharpe_ratio REAL NOT NULL,
                max_drawdown_pct REAL NOT NULL,
                win_rate_pct REAL NOT NULL,
                avg_hold_days REAL NOT NULL,
                total_trades INTEGER NOT NULL,
                spy_total_return_pct REAL NOT NULL,
                spy_cagr_pct REAL NOT NULL,
                spy_max_drawdown_pct REAL NOT NULL,
                no_mom_return_pct REAL NOT NULL,
                summary_json TEXT NOT NULL,
                yearly_json TEXT NOT NULL,
                equity_curve_json TEXT NOT NULL,
                trades_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS risk_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL
            );
            """
        )


def save_signals(
    signal_date: str,
    signals_list: List[Dict[str, Any]],
    db_path: Path | str | None = None,
) -> None:
    """Persist a daily batch of entry, exit, and radar signals to SQLite."""
    init_db(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM signals WHERE signal_date = ?", (signal_date,))
        for sig in signals_list:
            conn.execute(
                """
                INSERT INTO signals (
                    signal_date, symbol, company_name, sector, signal_type, rank,
                    close_price, open_price, high_price, low_price, prior_high,
                    sma_200, pct_above_sma200, mom_6_1, mom_percentile,
                    rsi_2, close_range_pos, days_held, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_date,
                    sig["symbol"],
                    sig.get("company_name", sig["symbol"]),
                    sig.get("sector", "Equity"),
                    sig["signal_type"],
                    int(sig.get("rank", 0)),
                    float(sig["close_price"]),
                    float(sig.get("open_price", sig["close_price"])),
                    float(sig.get("high_price", sig["close_price"])),
                    float(sig.get("low_price", sig["close_price"])),
                    float(sig.get("prior_high", sig["close_price"])),
                    float(sig.get("sma_200", 0.0)),
                    float(sig.get("pct_above_sma200", 0.0)),
                    float(sig.get("mom_6_1", 0.0)),
                    float(sig.get("mom_percentile", 0.0)),
                    float(sig.get("rsi_2", 50.0)),
                    float(sig.get("close_range_pos", 0.5)),
                    int(sig.get("days_held", 0)),
                    sig.get("reason", ""),
                    now_iso,
                ),
            )


def get_latest_signals(db_path: Path | str | None = None) -> Dict[str, Any]:
    """Fetch the most recent signal date and all signals recorded on that date."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT signal_date FROM signals ORDER BY signal_date DESC, id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {"signal_date": None, "entry": [], "exit": [], "queued": [], "radar": []}

        sig_date = row["signal_date"]
        rows = conn.execute(
            "SELECT * FROM signals WHERE signal_date = ? ORDER BY rank ASC, rsi_2 ASC",
            (sig_date,),
        ).fetchall()

    items = [dict(r) for r in rows]
    return {
        "signal_date": sig_date,
        "entry": [x for x in items if x["signal_type"] == "ENTRY"],
        "exit": [x for x in items if x["signal_type"] == "EXIT"],
        "queued": [x for x in items if x["signal_type"] == "QUEUE_CAPPED"],
        "radar": [x for x in items if x["signal_type"] == "RADAR"],
    }


def upsert_positions(
    positions: List[Dict[str, Any]],
    replace_all: bool = True,
    db_path: Path | str | None = None,
) -> None:
    """Save active positions to SQLite."""
    init_db(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        if replace_all:
            conn.execute("DELETE FROM positions")
        for pos in positions:
            entry_price = float(pos["entry_price"])
            current_price = float(pos.get("current_price", entry_price))
            shares = float(pos["shares"])
            market_value = shares * current_price
            unrealized_pnl = (current_price - entry_price) * shares
            unrealized_pnl_pct = ((current_price / entry_price) - 1.0) * 100.0 if entry_price > 0 else 0.0
            conn.execute(
                """
                INSERT OR REPLACE INTO positions (
                    symbol, company_name, sector, entry_date, entry_price, shares,
                    current_price, prior_high, days_held, market_value,
                    unrealized_pnl, unrealized_pnl_pct, mom_6_1, rsi_2, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pos["symbol"],
                    pos.get("company_name", pos["symbol"]),
                    pos.get("sector", "Technology"),
                    pos["entry_date"],
                    entry_price,
                    shares,
                    current_price,
                    float(pos.get("prior_high", current_price * 1.01)),
                    int(pos.get("days_held", 1)),
                    market_value,
                    unrealized_pnl,
                    unrealized_pnl_pct,
                    float(pos.get("mom_6_1", 0.25)),
                    float(pos.get("rsi_2", 35.0)),
                    now_iso,
                ),
            )


def get_positions(db_path: Path | str | None = None) -> List[Dict[str, Any]]:
    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM positions ORDER BY unrealized_pnl_pct DESC, symbol ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def log_order(
    order: Dict[str, Any],
    db_path: Path | str | None = None,
) -> int:
    init_db(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO orders (
                timestamp, signal_date, symbol, side, qty, notional,
                est_price, order_type, status, dry_run, alpaca_order_id, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order.get("timestamp", now_iso),
                order.get("signal_date", now_iso[:10]),
                order["symbol"],
                order["side"],
                float(order.get("qty", 0.0)),
                float(order.get("notional", 0.0)),
                float(order.get("est_price", 0.0)),
                order.get("order_type", "MOO"),
                order.get("status", "DRY_RUN"),
                1 if order.get("dry_run", True) else 0,
                order.get("alpaca_order_id", ""),
                order.get("reason", ""),
            ),
        )
        return int(cur.lastrowid or 0)


def get_recent_orders(limit: int = 50, db_path: Path | str | None = None) -> List[Dict[str, Any]]:
    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def save_backtest_run(
    result: Dict[str, Any],
    db_path: Path | str | None = None,
) -> int:
    init_db(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    metrics = result["metrics"]
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO backtest_runs (
                run_timestamp, start_date, end_date, initial_capital, final_equity,
                total_return_pct, cagr_pct, sharpe_ratio, max_drawdown_pct,
                win_rate_pct, avg_hold_days, total_trades,
                spy_total_return_pct, spy_cagr_pct, spy_max_drawdown_pct,
                no_mom_return_pct, summary_json, yearly_json, equity_curve_json, trades_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso,
                metrics["start_date"],
                metrics["end_date"],
                float(metrics["initial_capital"]),
                float(metrics["final_equity"]),
                float(metrics["total_return_pct"]),
                float(metrics["cagr_pct"]),
                float(metrics["sharpe_ratio"]),
                float(metrics["max_drawdown_pct"]),
                float(metrics["win_rate_pct"]),
                float(metrics["avg_hold_days"]),
                int(metrics["total_trades"]),
                float(metrics.get("spy_total_return_pct", 0.0)),
                float(metrics.get("spy_cagr_pct", 0.0)),
                float(metrics.get("spy_max_drawdown_pct", 0.0)),
                float(metrics.get("no_mom_return_pct", 0.0)),
                json.dumps(metrics),
                json.dumps(result.get("yearly_returns", [])),
                json.dumps(result.get("equity_curve", [])),
                json.dumps(result.get("trades", [])),
            ),
        )
        return int(cur.lastrowid or 0)


def get_latest_backtest(db_path: Path | str | None = None) -> Optional[Dict[str, Any]]:
    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM backtest_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    return {
        "id": d["id"],
        "run_timestamp": d["run_timestamp"],
        "metrics": json.loads(d["summary_json"]),
        "yearly_returns": json.loads(d["yearly_json"]),
        "equity_curve": json.loads(d["equity_curve_json"]),
        "trades": json.loads(d["trades_json"]),
    }


def log_risk_event(
    event_type: str,
    message: str,
    severity: str = "INFO",
    db_path: Path | str | None = None,
) -> None:
    init_db(db_path)
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO risk_events (timestamp, event_type, severity, message) VALUES (?, ?, ?, ?)",
            (now_iso, event_type, severity, message),
        )


def get_risk_events(limit: int = 30, db_path: Path | str | None = None) -> List[Dict[str, Any]]:
    init_db(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM risk_events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
