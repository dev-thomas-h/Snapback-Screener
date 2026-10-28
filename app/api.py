from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.backtest import run_backtest
from app.config import (
    DATA_DIR,
    ROOT_DIR,
    get_logger,
    is_kill_switch_active,
    load_config,
    save_config,
    set_kill_switch,
)
from app.db import (
    get_latest_backtest,
    get_latest_signals,
    get_positions,
    get_recent_orders,
    get_risk_events,
    init_db,
    log_risk_event,
)
from app.screener import run_daily_screener
from app.trader import (
    check_daily_loss_guard,
    compute_next_open_order_plan,
    create_paper_trading_client,
    ensure_demo_paper_positions_if_empty,
    fetch_account_and_reconcile,
    run_trading_cycle,
)

logger = get_logger("api")

app = FastAPI(
    title="Momentum Leaders Snapback API",
    description="Screener, Backtester & Alpaca Paper Trading API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScreenerRequest(BaseModel):
    universe_limit: Optional[int] = 80
    as_of_date: Optional[str] = None


class BacktestRequest(BaseModel):
    start_date: Optional[str] = "2008-01-01"
    end_date: Optional[str] = None
    universe_limit: Optional[int] = 50


class TraderCycleRequest(BaseModel):
    dry_run: bool = True
    refresh_signals: bool = False


class KillSwitchRequest(BaseModel):
    active: bool
    reason: str = "Toggled via Glass Dashboard"


def _ensure_bootstrapped() -> None:
    """Ensure SQLite has initial screener signals, positions, and a backtest run on first startup."""
    init_db()
    sig = get_latest_signals()
    if not sig.get("signal_date"):
        logger.info("Bootstrapping initial S&P 500 screener snapshot...")
        run_daily_screener(universe_limit=60, persist=True)

    ensure_demo_paper_positions_if_empty()

    bt = get_latest_backtest()
    if bt is None:
        logger.info("Bootstrapping initial 2008–Present Momentum Snapback backtest...")
        run_backtest(start_date="2008-01-01", universe_limit=45, persist=True)


@app.on_event("startup")
def on_startup() -> None:
    try:
        _ensure_bootstrapped()
    except Exception as exc:
        logger.warning(f"Startup bootstrap notice: {exc}")


@app.get("/api/overview")
def api_get_overview() -> Dict[str, Any]:
    _ensure_bootstrapped()
    cfg = load_config()
    client = create_paper_trading_client(paper=True)
    account = fetch_account_and_reconcile(client)
    signals = get_latest_signals()
    plan = compute_next_open_order_plan(account, signals, cfg)
    backtest = get_latest_backtest()
    loss_tripped, loss_msg = check_daily_loss_guard(account, cfg)

    return {
        "config": cfg,
        "kill_switch_active": is_kill_switch_active(cfg),
        "daily_loss_guard": {
            "tripped": loss_tripped,
            "message": loss_msg,
            "limit_pct": float(cfg["risk"].get("daily_loss_limit_pct", 0.05)) * 100.0,
        },
        "account": account,
        "order_plan": plan,
        "signals": signals,
        "backtest": backtest,
        "recent_orders": get_recent_orders(limit=30),
        "risk_events": get_risk_events(limit=20),
    }


@app.post("/api/screener/run")
def api_run_screener(req: ScreenerRequest) -> Dict[str, Any]:
    res = run_daily_screener(
        universe_limit=req.universe_limit,
        as_of_date=req.as_of_date,
        persist=True,
    )
    signals = get_latest_signals()
    cfg = load_config()
    client = create_paper_trading_client(paper=True)
    account = fetch_account_and_reconcile(client)
    plan = compute_next_open_order_plan(account, signals, cfg)
    return {
        "screener_result": res,
        "signals": signals,
        "order_plan": plan,
    }


@app.post("/api/backtest/run")
def api_run_backtest(req: BacktestRequest) -> Dict[str, Any]:
    res = run_backtest(
        start_date=req.start_date,
        end_date=req.end_date,
        universe_limit=req.universe_limit,
        persist=True,
    )
    return {"backtest": get_latest_backtest() or res}


@app.post("/api/trader/cycle")
def api_run_trader_cycle(req: TraderCycleRequest) -> Dict[str, Any]:
    cycle = run_trading_cycle(dry_run=req.dry_run, refresh_screener=req.refresh_signals)
    return {
        "cycle": cycle,
        "recent_orders": get_recent_orders(limit=30),
        "risk_events": get_risk_events(limit=20),
    }


@app.post("/api/risk/kill-switch")
def api_toggle_kill_switch(req: KillSwitchRequest) -> Dict[str, Any]:
    active = set_kill_switch(req.active, reason=req.reason)
    log_risk_event(
        "KILL_SWITCH",
        f"Kill switch {'ACTIVATED' if active else 'DEACTIVATED'}: {req.reason}",
        severity="WARNING" if active else "INFO",
    )
    return {
        "kill_switch_active": active,
        "risk_events": get_risk_events(limit=20),
    }


@app.get("/api/config")
def api_get_config() -> Dict[str, Any]:
    return load_config()


@app.put("/api/config")
def api_update_config(new_cfg: Dict[str, Any]) -> Dict[str, Any]:
    try:
        updated = save_config(new_cfg)
        log_risk_event("CONFIG_UPDATE", "Updated strategy/risk parameters in config.yaml", severity="INFO")
        return {"config": updated}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/chart/equity-curve")
def api_get_equity_chart() -> FileResponse:
    chart_file = DATA_DIR / "equity_curve.png"
    if not chart_file.exists():
        run_backtest(start_date="2008-01-01", universe_limit=45, persist=True)
    return FileResponse(chart_file, media_type="image/png")


# Serve built React frontend if frontend/dist exists
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str) -> FileResponse:
        target = FRONTEND_DIST / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
