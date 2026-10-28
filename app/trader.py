from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from app.config import (
    PaperTradingSafetyError,
    enforce_paper_only,
    get_logger,
    is_kill_switch_active,
    load_config,
)
from app.db import (
    get_latest_signals,
    get_positions,
    log_order,
    log_risk_event,
    upsert_positions,
)
from app.screener import run_daily_screener
from app.universe import get_constituent_metadata_map, normalize_ticker_for_alpaca

logger = get_logger("trader")


def create_paper_trading_client(
    api_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    paper: bool = True,
) -> Optional[TradingClient]:
    """
    Create an official alpaca-py TradingClient strictly enforced for paper trading (`paper=True`).
    Raises PaperTradingSafetyError if `paper=False` or if live credentials/endpoints are detected.
    Returns None if API keys are not yet configured in environment/.env (allowing dry-run preview).
    """
    cfg = load_config()
    resolved_key = (api_key if api_key is not None else os.getenv("ALPACA_API_KEY", "")).strip()
    resolved_secret = (secret_key if secret_key is not None else os.getenv("ALPACA_SECRET_KEY", "")).strip()
    base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").strip()

    # Mandatory paper-only check
    enforce_paper_only(
        config=cfg,
        paper_flag=paper,
        base_url=base_url,
        api_key=resolved_key,
    )

    if (
        not resolved_key
        or not resolved_secret
        or resolved_key == "your_paper_api_key_here"
        or resolved_secret == "your_paper_secret_key_here"
    ):
        return None

    # Official alpaca-py SDK client routed strictly to paper-api.alpaca.markets
    client = TradingClient(api_key=resolved_key, secret_key=resolved_secret, paper=True)
    return client


def ensure_demo_paper_positions_if_empty() -> List[Dict[str, Any]]:
    """
    If no positions exist in SQLite yet, seed a realistic set of paper positions
    from the S&P 500 universe so the dashboard and dry-run reconciler have auditable state.
    """
    existing = get_positions()
    if existing:
        return existing

    sig_bundle = get_latest_signals()
    radar = sig_bundle.get("radar", [])
    candidates = list(radar)
    meta_map = get_constituent_metadata_map()

    seeded: List[Dict[str, Any]] = []
    sample_specs = [
        {"days_held": 4, "entry_discount": 0.972, "prior_high_mult": 1.018},
        {"days_held": 9, "entry_discount": 0.958, "prior_high_mult": 1.012},
        {"days_held": 14, "entry_discount": 1.012, "prior_high_mult": 1.022},
        {"days_held": 20, "entry_discount": 0.965, "prior_high_mult": 0.992},
    ]

    for idx, spec in enumerate(sample_specs):
        if idx < len(candidates):
            c = candidates[idx]
            sym = c["symbol"]
            cur_p = float(c["close_price"])
            prior_h = round(cur_p * spec["prior_high_mult"], 2)
            ent_p = round(cur_p * spec["entry_discount"], 2)
            notional = 18500.0
            shares = round(notional / ent_p, 2)
            seeded.append(
                {
                    "symbol": sym,
                    "company_name": c.get("company_name", meta_map.get(sym, {}).get("name", sym)),
                    "sector": c.get("sector", meta_map.get(sym, {}).get("sector", "Technology")),
                    "entry_date": "2026-10-08",
                    "entry_price": ent_p,
                    "shares": shares,
                    "current_price": cur_p,
                    "prior_high": prior_h,
                    "days_held": spec["days_held"],
                    "mom_6_1": float(c.get("mom_6_1", 0.34)),
                    "rsi_2": float(c.get("rsi_2", 28.0)),
                }
            )

    if seeded:
        upsert_positions(seeded, replace_all=True)
        return get_positions()
    return []


def fetch_account_and_reconcile(
    client: Optional[TradingClient] = None,
) -> Dict[str, Any]:
    """
    Fetch Alpaca paper account summary and open positions, reconciling with SQLite state.
    If no live Alpaca paper keys are configured yet, returns simulated paper account state
    backed by SQLite positions.
    """
    local_positions = get_positions()
    local_by_sym = {p["symbol"]: p for p in local_positions}
    meta_map = get_constituent_metadata_map()

    if client is not None:
        try:
            acct = client.get_account()
            alpaca_positions = client.get_all_positions()

            equity = float(acct.equity)
            last_equity = float(acct.last_equity) if acct.last_equity else equity
            cash = float(acct.cash)
            buying_power = float(acct.buying_power)
            daily_pnl = equity - last_equity
            daily_pnl_pct = ((equity / last_equity) - 1.0) * 100.0 if last_equity > 0 else 0.0

            reconciled: List[Dict[str, Any]] = []
            for ap in alpaca_positions:
                sym = str(ap.symbol).replace(".", "-")
                loc = local_by_sym.get(sym, {})
                cur_price = float(ap.current_price)
                ent_price = float(ap.avg_entry_price)
                qty = float(ap.qty)
                reconciled.append(
                    {
                        "symbol": sym,
                        "company_name": loc.get("company_name", meta_map.get(sym, {}).get("name", sym)),
                        "sector": loc.get("sector", meta_map.get(sym, {}).get("sector", "Equity")),
                        "entry_date": loc.get("entry_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                        "entry_price": ent_price,
                        "shares": qty,
                        "current_price": cur_price,
                        "prior_high": float(loc.get("prior_high", cur_price * 1.01)),
                        "days_held": int(loc.get("days_held", 1)),
                        "mom_6_1": float(loc.get("mom_6_1", 0.30)),
                        "rsi_2": float(loc.get("rsi_2", 40.0)),
                    }
                )

            upsert_positions(reconciled, replace_all=True)
            persisted_positions = get_positions()
            gross_exposure = sum(float(p["market_value"]) for p in persisted_positions)
            gross_leverage = gross_exposure / equity if equity > 0 else 0.0

            return {
                "connected": True,
                "mode": "ALPACA_PAPER_LIVE",
                "endpoint": "https://paper-api.alpaca.markets",
                "equity": round(equity, 2),
                "last_equity": round(last_equity, 2),
                "cash": round(cash, 2),
                "buying_power": round(buying_power, 2),
                "gross_exposure": round(gross_exposure, 2),
                "gross_leverage": round(gross_leverage, 2),
                "daily_pnl": round(daily_pnl, 2),
                "daily_pnl_pct": round(daily_pnl_pct, 2),
                "positions": persisted_positions,
            }
        except Exception as exc:
            logger.warning(f"Alpaca paper API connection error ({exc}); falling back to local paper state.")

    if not local_positions:
        local_positions = ensure_demo_paper_positions_if_empty()

    base_cash = 100000.0
    total_cost = sum(float(p["entry_price"]) * float(p["shares"]) for p in local_positions)
    gross_exposure = sum(float(p["market_value"]) for p in local_positions)
    unrealized_pnl = sum(float(p["unrealized_pnl"]) for p in local_positions)
    equity = base_cash + unrealized_pnl
    cash = base_cash - total_cost
    last_equity = equity - (unrealized_pnl * 0.35)
    daily_pnl = equity - last_equity
    daily_pnl_pct = ((equity / last_equity) - 1.0) * 100.0 if last_equity > 0 else 0.0
    buying_power = max(0.0, (2.0 * equity) - gross_exposure)
    gross_leverage = gross_exposure / equity if equity > 0 else 0.0

    return {
        "connected": False,
        "mode": "PAPER_SIMULATION_PREVIEW",
        "endpoint": "https://paper-api.alpaca.markets (Set ALPACA_API_KEY in .env for live broker sync)",
        "equity": round(equity, 2),
        "last_equity": round(last_equity, 2),
        "cash": round(cash, 2),
        "buying_power": round(buying_power, 2),
        "gross_exposure": round(gross_exposure, 2),
        "gross_leverage": round(gross_leverage, 2),
        "daily_pnl": round(daily_pnl, 2),
        "daily_pnl_pct": round(daily_pnl_pct, 2),
        "positions": local_positions,
    }


def check_daily_loss_guard(account_state: Dict[str, Any], config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Check if intraday account loss exceeds `daily_loss_limit_pct` (default 5.0%).
    Returns (is_tripped, message).
    """
    limit_pct = float(config["risk"].get("daily_loss_limit_pct", 0.05)) * 100.0
    daily_pnl_pct = float(account_state.get("daily_pnl_pct", 0.0))
    if daily_pnl_pct <= -abs(limit_pct):
        msg = (
            f"DAILY LOSS GUARD TRIPPED: Account daily P&L is {daily_pnl_pct:.2f}%, "
            f"exceeding the -{limit_pct:.1f}% daily loss limit. New entries halted."
        )
        return True, msg
    return False, f"Daily P&L ({daily_pnl_pct:+.2f}%) is within the -{limit_pct:.1f}% daily loss guard."


def compute_next_open_order_plan(
    account_state: Dict[str, Any],
    signals_bundle: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Compute exact market-on-open (MOO) exit and entry orders based on:
      - Current reconciled positions
      - Daily screener signals
      - Hard risk caps (max 10 positions, max 2 new entries/day, max 2.0x gross leverage)
      - Kill switch & 5% daily loss guard
    """
    cfg = config or load_config()
    strat = cfg["strategy"]
    max_positions = min(int(strat.get("max_positions", 10)), 10)
    max_new_per_day = min(int(strat.get("max_new_entries_per_day", 2)), 2)
    target_leverage = min(float(strat.get("target_gross_leverage", 2.0)), 2.0)
    max_leverage = min(float(strat.get("max_gross_leverage", 2.0)), 2.0)

    kill_switch = is_kill_switch_active(cfg)
    loss_tripped, loss_msg = check_daily_loss_guard(account_state, cfg)

    positions = account_state.get("positions", [])
    pos_by_sym = {p["symbol"]: p for p in positions}
    equity = float(account_state.get("equity", 100000.0))
    signal_date = signals_bundle.get("signal_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    planned_orders: List[Dict[str, Any]] = []

    # 1. Exit orders (always permitted unless kill switch cancels all open orders; exits reduce risk)
    exit_signals = signals_bundle.get("exit", [])
    exiting_symbols = set()
    freed_exposure = 0.0

    for ex in exit_signals:
        sym = ex["symbol"]
        if sym in pos_by_sym:
            pos = pos_by_sym[sym]
            qty = float(pos["shares"])
            est_p = float(ex.get("close_price", pos["current_price"]))
            notional = round(qty * est_p, 2)
            exiting_symbols.add(sym)
            freed_exposure += notional
            planned_orders.append(
                {
                    "signal_date": signal_date,
                    "symbol": sym,
                    "side": "SELL",
                    "qty": qty,
                    "notional": notional,
                    "est_price": est_p,
                    "order_type": "MOO (TimeInForce.OPG)",
                    "reason": ex["reason"],
                }
            )

    surviving_positions = [p for p in positions if p["symbol"] not in exiting_symbols]
    surviving_exposure = sum(float(p["market_value"]) for p in surviving_positions)
    available_slots = max(0, max_positions - len(surviving_positions))

    # 2. Entry orders (subject to Kill Switch, Daily Loss Guard, 2/day cap, 10-position cap, and 2x leverage cap)
    entry_candidates = [
        e for e in signals_bundle.get("entry", []) if e["symbol"] not in pos_by_sym
    ]
    entry_candidates.sort(key=lambda x: float(x.get("mom_6_1", 0.0)), reverse=True)
    selected_entries = entry_candidates[: min(max_new_per_day, available_slots)]

    if selected_entries and not kill_switch and not loss_tripped and equity > 0:
        total_positions_after = len(surviving_positions) + len(selected_entries)
        target_gross_dollars = target_leverage * equity
        max_gross_dollars = max_leverage * equity
        remaining_gross_room = max(0.0, max_gross_dollars - surviving_exposure)

        # Size each new position as (target exposure) / max(max_positions, current_positions + new_entries)
        # while strictly respecting the 2.0x gross exposure ceiling.
        slot_divisor = max(max_positions, total_positions_after)
        per_slot_dollars = min(
            target_gross_dollars / float(slot_divisor),
            remaining_gross_room / float(len(selected_entries)),
        )

        for ent in selected_entries:
            est_p = float(ent["close_price"])
            if est_p <= 0 or per_slot_dollars <= 0:
                continue
            qty = int(per_slot_dollars // est_p)
            if qty <= 0:
                qty = round(per_slot_dollars / est_p, 2)
            notional = round(float(qty) * est_p, 2)
            planned_orders.append(
                {
                    "signal_date": signal_date,
                    "symbol": ent["symbol"],
                    "side": "BUY",
                    "qty": qty,
                    "notional": notional,
                    "est_price": est_p,
                    "order_type": "MOO (TimeInForce.OPG)",
                    "reason": ent["reason"],
                }
            )

    projected_new_buy_notional = sum(
        o["notional"] for o in planned_orders if o["side"] == "BUY"
    )
    projected_gross_exposure = surviving_exposure + projected_new_buy_notional
    projected_leverage = projected_gross_exposure / equity if equity > 0 else 0.0

    return {
        "signal_date": signal_date,
        "kill_switch_active": kill_switch,
        "daily_loss_guard_tripped": loss_tripped,
        "daily_loss_guard_message": loss_msg,
        "surviving_positions_count": len(surviving_positions),
        "available_slots": available_slots,
        "projected_gross_exposure": round(projected_gross_exposure, 2),
        "projected_gross_leverage": round(projected_leverage, 2),
        "orders": planned_orders,
    }


def run_trading_cycle(
    dry_run: bool = True,
    refresh_screener: bool = False,
) -> Dict[str, Any]:
    """
    Execute the daily paper-trading workflow:
      1. Verify paper-only safety rules.
      2. Connect to Alpaca paper account (or local paper state) and reconcile positions.
      3. Load or compute today's screener signals.
      4. Check Kill Switch & 5% Daily Loss Guard.
      5. Place or preview Market-on-Open (TimeInForce.OPG) orders and audit-log every decision.
    """
    cfg = load_config()
    enforce_paper_only(cfg, paper_flag=True)

    client = create_paper_trading_client(paper=True)
    signals_bundle = get_latest_signals()
    if refresh_screener or not signals_bundle.get("signal_date"):
        signals_bundle = run_daily_screener(persist=True)

    account_state = fetch_account_and_reconcile(client)
    plan = compute_next_open_order_plan(account_state, signals_bundle, cfg)

    if plan["kill_switch_active"]:
        log_risk_event(
            "KILL_SWITCH",
            "Kill switch is ACTIVE. Cancelling open paper orders and blocking new entries.",
            severity="WARNING",
        )
        if client is not None and not dry_run:
            try:
                client.cancel_orders()
                logger.warning("Cancelled all open Alpaca paper orders due to active KILL_SWITCH.")
            except Exception as exc:
                logger.error(f"Failed cancelling open orders: {exc}")

    if plan["daily_loss_guard_tripped"]:
        log_risk_event("DAILY_LOSS_GUARD", plan["daily_loss_guard_message"], severity="ERROR")

    executed_orders: List[Dict[str, Any]] = []
    for ord_spec in plan["orders"]:
        record = dict(ord_spec)
        record["dry_run"] = dry_run

        if plan["kill_switch_active"] and record["side"] == "BUY":
            record["status"] = "BLOCKED_KILL_SWITCH"
        elif plan["daily_loss_guard_tripped"] and record["side"] == "BUY":
            record["status"] = "BLOCKED_LOSS_GUARD"
        elif dry_run or client is None:
            record["status"] = "DRY_RUN"
        else:
            try:
                alpaca_sym = normalize_ticker_for_alpaca(record["symbol"])
                side_enum = OrderSide.BUY if record["side"] == "BUY" else OrderSide.SELL
                req = MarketOrderRequest(
                    symbol=alpaca_sym,
                    qty=record["qty"],
                    side=side_enum,
                    time_in_force=TimeInForce.OPG,
                )
                submitted = client.submit_order(order_data=req)
                record["status"] = "SUBMITTED"
                record["alpaca_order_id"] = str(getattr(submitted, "id", ""))
                logger.info(
                    f"Submitted PAPER {record['side']} MOO order for {record['qty']} {alpaca_sym} "
                    f"(id={record['alpaca_order_id']})"
                )
            except Exception as exc:
                record["status"] = f"ERROR: {exc}"
                logger.error(f"Order submission error for {record['symbol']}: {exc}")

        log_order(record)
        executed_orders.append(record)

    return {
        "dry_run": dry_run,
        "account": account_state,
        "plan": plan,
        "executed_orders": executed_orders,
    }


def print_trader_report(cycle: Dict[str, Any]) -> None:
    acct = cycle["account"]
    plan = cycle["plan"]
    orders = cycle["executed_orders"]
    mode_tag = "DRY-RUN PREVIEW (No orders placed)" if cycle["dry_run"] else "PAPER ORDER EXECUTION"

    print("\n" + "=" * 95)
    print(f" MOMENTUM LEADERS SNAPBACK — ALPACA PAPER TRADER ({mode_tag})")
    print("=" * 95)
    print(f" Broker Mode          : {acct['mode']} | Paper-Only Enforced: YES")
    print(f" Endpoint             : {acct['endpoint']}")
    print(
        f" Account Equity       : ${acct['equity']:,.2f} | "
        f"Cash: ${acct['cash']:,.2f} | Buying Power: ${acct['buying_power']:,.2f}"
    )
    print(
        f" Current Gross Exp.   : ${acct['gross_exposure']:,.2f} ({acct['gross_leverage']:.2f}x / 2.00x Cap) | "
        f"Daily P&L: ${acct['daily_pnl']:+,.2f} ({acct['daily_pnl_pct']:+.2f}%)"
    )
    print(
        f" Risk Controls        : Kill Switch={'ACTIVE' if plan['kill_switch_active'] else 'OFF'} | "
        f"{plan['daily_loss_guard_message']}"
    )
    print("-" * 95)

    positions = acct.get("positions", [])
    print(f"\n[1] CURRENT PAPER POSITIONS ({len(positions)} / 10 Max Slots):")
    if not positions:
        print("    No open positions.")
    else:
        print(f"    {'Symbol':<7} {'Shares':>8} {'Entry $':>9} {'Current $':>10} {'PriorHigh':>10} {'Day':>6} {'Mkt Value':>12} {'Unreal. P&L':>14}")
        for p in positions:
            print(
                f"    {p['symbol']:<7} {p['shares']:>8.2f} ${p['entry_price']:>8.2f} "
                f"${p['current_price']:>9.2f} ${p['prior_high']:>9.2f} "
                f"{p['days_held']:>3d}/20 ${p['market_value']:>11,.2f} "
                f"${p['unrealized_pnl']:>+8,.2f} ({p['unrealized_pnl_pct']:+.1f}%)"
            )

    print(f"\n[2] NEXT-OPEN (MOO) ORDERS {'WOULD PLACE' if cycle['dry_run'] else 'PROCESSED'} ({len(orders)} orders):")
    if not orders:
        print("    No entry or exit orders queued for next trading day's open.")
    else:
        for o in orders:
            print(
                f"    [{o['status']}] {o['side']:<4} {o['qty']} shs {o['symbol']:<6} "
                f"@ Est. ${o['est_price']:.2f} (${o['notional']:,.2f}) — {o['order_type']}"
            )
            print(f"        Reason: {o['reason']}")

    print(
        f"\n Projected Post-Trade Gross Exposure: ${plan['projected_gross_exposure']:,.2f} "
        f"({plan['projected_gross_leverage']:.2f}x equity — capped at 2.00x)"
    )
    print("=" * 95 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Momentum Leaders Snapback Alpaca Paper Trader.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview account state and orders without submitting to Alpaca.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Submit paper orders to Alpaca paper-api.alpaca.markets.",
    )
    parser.add_argument(
        "--refresh-signals",
        action="store_true",
        default=False,
        help="Re-run the daily screener before computing orders.",
    )
    args = parser.parse_args()

    # Default to dry_run=True unless --execute is explicitly passed
    is_dry_run = True if args.dry_run or not args.execute else False
    cycle = run_trading_cycle(dry_run=is_dry_run, refresh_screener=args.refresh_signals)
    print_trader_report(cycle)


if __name__ == "__main__":
    main()
