from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from app.config import get_logger, load_config
from app.db import get_positions, save_signals
from app.indicators import (
    check_entry_signal,
    check_exit_signal,
    compute_stock_indicators,
    rank_momentum_cross_section,
)
from app.universe import (
    FALLBACK_SP500,
    fetch_ohlcv_bars,
    fetch_sp500_constituents,
    get_constituent_metadata_map,
)

logger = get_logger("screener")


def screen_universe_on_date(
    ohlcv_map: Dict[str, pd.DataFrame],
    config: Optional[Dict[str, Any]] = None,
    held_positions: Optional[List[Dict[str, Any]]] = None,
    as_of_date: Optional[str] = None,
    metadata_map: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Core signal engine: evaluates all stocks in `ohlcv_map` at the completed daily bar
    (either `as_of_date` or the latest available date).
    """
    cfg = config or load_config()
    strat = cfg["strategy"]
    sma_period = int(strat.get("sma_period", 200))
    mom_start = int(strat.get("momentum_lookback_start", 126))
    mom_end = int(strat.get("momentum_lookback_end", 21))
    mom_top_pct = float(strat.get("momentum_top_pct", 0.20))
    rsi_period = int(strat.get("rsi_period", 2))
    rsi_thresh = float(strat.get("rsi_entry_threshold", 15.0))
    range_thresh = float(strat.get("close_range_threshold", 0.10))
    exit_prior_high = bool(strat.get("exit_above_prior_high", True))
    max_hold_days = int(strat.get("max_hold_days", 20))
    max_positions = int(strat.get("max_positions", 10))
    max_new_per_day = int(strat.get("max_new_entries_per_day", 2))

    meta = metadata_map or {}
    snapshots: List[Dict[str, Any]] = []
    latest_dates: List[pd.Timestamp] = []

    for symbol, df in ohlcv_map.items():
        if symbol == "SPY" or df is None or df.empty:
            continue
        work_df = df
        if as_of_date:
            work_df = df.loc[df.index <= pd.Timestamp(as_of_date)]
        if len(work_df) < sma_period + 2:
            continue

        ind_df = compute_stock_indicators(
            work_df,
            sma_period=sma_period,
            momentum_lookback_start=mom_start,
            momentum_lookback_end=mom_end,
            rsi_period=rsi_period,
        )
        last = ind_df.iloc[-1]
        bar_date = pd.Timestamp(ind_df.index[-1])
        latest_dates.append(bar_date)

        close_val = float(last["Close"])
        sma_val = float(last["SMA200"])
        mom_val = float(last["Mom_6_1"])
        rsi_val = float(last["RSI2"])
        range_val = float(last["CloseRangePos"])
        prior_high_val = float(last["PriorHigh"]) if not np.isnan(last["PriorHigh"]) else float(last["High"])

        if np.isnan(close_val) or np.isnan(sma_val) or np.isnan(mom_val) or np.isnan(rsi_val):
            continue

        sym_meta = meta.get(symbol, {})
        snapshots.append(
            {
                "symbol": symbol,
                "company_name": sym_meta.get("name", symbol),
                "sector": sym_meta.get("sector", "Equity"),
                "bar_date": bar_date.strftime("%Y-%m-%d"),
                "open_price": float(last["Open"]),
                "high_price": float(last["High"]),
                "low_price": float(last["Low"]),
                "close_price": close_val,
                "prior_high": prior_high_val,
                "sma_200": sma_val,
                "pct_above_sma200": float(last["PctAboveSMA200"]),
                "mom_6_1": mom_val,
                "rsi_2": rsi_val,
                "close_range_pos": range_val,
            }
        )

    if not snapshots:
        signal_date = as_of_date or datetime.now().strftime("%Y-%m-%d")
        return {
            "signal_date": signal_date,
            "universe_size": 0,
            "above_sma200_count": 0,
            "top_momentum_count": 0,
            "entry": [],
            "exit": [],
            "queued": [],
            "radar": [],
            "all_persisted": [],
        }

    snap_df = pd.DataFrame(snapshots).set_index("symbol")
    signal_date = max(latest_dates).strftime("%Y-%m-%d") if latest_dates else (as_of_date or datetime.now().strftime("%Y-%m-%d"))

    # Rank 6-1M momentum across the full universe
    pct_ranks, is_top_mom = rank_momentum_cross_section(snap_df["mom_6_1"], top_pct=mom_top_pct)
    snap_df["mom_percentile"] = pct_ranks * 100.0
    snap_df["in_top_momentum"] = is_top_mom
    snap_df["above_sma200"] = snap_df["close_price"] > snap_df["sma_200"]

    # 1. Check Exit Signals on currently held positions first
    held_list = held_positions or []
    held_symbols = {p["symbol"] for p in held_list}
    exit_signals: List[Dict[str, Any]] = []
    surviving_positions_count = 0

    for pos in held_list:
        sym = pos["symbol"]
        days_held = int(pos.get("days_held", 1))
        if sym in snap_df.index:
            row = snap_df.loc[sym]
            close_p = float(row["close_price"])
            prior_h = float(row["prior_high"])
            sma_200 = float(row["sma_200"])
            pct_sma = float(row["pct_above_sma200"])
            mom_6_1 = float(row["mom_6_1"])
            mom_pct = float(row["mom_percentile"])
            rsi_2 = float(row["rsi_2"])
            range_pos = float(row["close_range_pos"])
            open_p = float(row["open_price"])
            high_p = float(row["high_price"])
            low_p = float(row["low_price"])
        else:
            close_p = float(pos.get("current_price", pos.get("entry_price", 0.0)))
            prior_h = float(pos.get("prior_high", close_p * 1.01))
            sma_200 = close_p * 0.9
            pct_sma = 10.0
            mom_6_1 = float(pos.get("mom_6_1", 0.25))
            mom_pct = 85.0
            rsi_2 = float(pos.get("rsi_2", 55.0))
            range_pos = 0.5
            open_p = close_p
            high_p = close_p
            low_p = close_p

        should_exit, reason = check_exit_signal(
            close=close_p,
            prior_high=prior_h,
            days_held=days_held,
            max_hold_days=max_hold_days,
            exit_above_prior_high=exit_prior_high,
        )
        if should_exit:
            exit_signals.append(
                {
                    "symbol": sym,
                    "company_name": pos.get("company_name", sym),
                    "sector": pos.get("sector", "Equity"),
                    "signal_type": "EXIT",
                    "rank": len(exit_signals) + 1,
                    "close_price": close_p,
                    "open_price": open_p,
                    "high_price": high_p,
                    "low_price": low_p,
                    "prior_high": prior_h,
                    "sma_200": sma_200,
                    "pct_above_sma200": pct_sma,
                    "mom_6_1": mom_6_1,
                    "mom_percentile": mom_pct,
                    "rsi_2": rsi_2,
                    "close_range_pos": range_pos,
                    "days_held": days_held,
                    "reason": reason,
                }
            )
        else:
            surviving_positions_count += 1

    # 2. Evaluate Entry Signals across all non-held stocks
    raw_entry_candidates: List[Dict[str, Any]] = []
    radar_candidates: List[Dict[str, Any]] = []

    for sym, row in snap_df.iterrows():
        is_entry, reason = check_entry_signal(
            close=float(row["close_price"]),
            sma_200=float(row["sma_200"]),
            in_top_momentum=bool(row["in_top_momentum"]),
            rsi_2=float(row["rsi_2"]),
            close_range_pos=float(row["close_range_pos"]),
            rsi_threshold=rsi_thresh,
            close_range_threshold=range_thresh,
        )
        record = {
            "symbol": sym,
            "company_name": row["company_name"],
            "sector": row["sector"],
            "close_price": float(row["close_price"]),
            "open_price": float(row["open_price"]),
            "high_price": float(row["high_price"]),
            "low_price": float(row["low_price"]),
            "prior_high": float(row["prior_high"]),
            "sma_200": float(row["sma_200"]),
            "pct_above_sma200": float(row["pct_above_sma200"]),
            "mom_6_1": float(row["mom_6_1"]),
            "mom_percentile": float(row["mom_percentile"]),
            "rsi_2": float(row["rsi_2"]),
            "close_range_pos": float(row["close_range_pos"]),
            "days_held": 0,
            "reason": reason,
        }

        if is_entry and sym not in held_symbols:
            raw_entry_candidates.append(record)
        elif bool(row["above_sma200"]) and bool(row["in_top_momentum"]):
            # Top 20% Momentum Leader above 200-MA -> include in Momentum Leaders Radar
            dist_to_trigger = max(0.0, float(row["rsi_2"]) - rsi_thresh)
            radar_item = dict(record)
            radar_item["signal_type"] = "RADAR"
            radar_item["reason"] = (
                f"Momentum Leader ({row['mom_percentile']:.0f}th pct, +{row['mom_6_1'] * 100:.1f}% 6-1M) | "
                f"Above SMA200 (+{row['pct_above_sma200']:.1f}%) | "
                f"RSI(2)={row['rsi_2']:.1f} ({dist_to_trigger:.1f} pts above <{rsi_thresh:.0f} trigger)"
            )
            radar_candidates.append(radar_item)

    # Sort valid entry signals by 6-1M momentum descending (highest momentum first)
    raw_entry_candidates.sort(key=lambda x: x["mom_6_1"], reverse=True)

    open_portfolio_slots = max(0, max_positions - surviving_positions_count)
    allowed_today = min(max_new_per_day, open_portfolio_slots)

    entry_signals: List[Dict[str, Any]] = []
    queued_signals: List[Dict[str, Any]] = []

    for idx, cand in enumerate(raw_entry_candidates):
        item = dict(cand)
        item["rank"] = idx + 1
        if idx < allowed_today:
            item["signal_type"] = "ENTRY"
            item["reason"] = f"[RANK #{idx + 1} ENTRY — EXECUTE NEXT OPEN] " + item["reason"]
            entry_signals.append(item)
        else:
            item["signal_type"] = "QUEUE_CAPPED"
            cap_reason = (
                f"Max {max_new_per_day} entries/day cap"
                if open_portfolio_slots >= max_new_per_day
                else f"Max {max_positions} portfolio positions cap"
            )
            item["reason"] = f"[QUEUED — {cap_reason}; re-check tomorrow] " + item["reason"]
            queued_signals.append(item)

    # Sort radar candidates by lowest RSI(2) first (closest to snapback trigger)
    radar_candidates.sort(key=lambda x: (x["rsi_2"], -x["mom_6_1"]))
    top_radar = radar_candidates[:25]
    for idx, r_item in enumerate(top_radar):
        r_item["rank"] = idx + 1

    all_persisted = entry_signals + exit_signals + queued_signals + top_radar

    return {
        "signal_date": signal_date,
        "universe_size": len(snap_df),
        "above_sma200_count": int(snap_df["above_sma200"].sum()),
        "top_momentum_count": int(snap_df["in_top_momentum"].sum()),
        "entry": entry_signals,
        "exit": exit_signals,
        "queued": queued_signals,
        "radar": top_radar,
        "all_persisted": all_persisted,
    }


def run_daily_screener(
    universe_limit: Optional[int] = None,
    as_of_date: Optional[str] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """
    Fetch S&P 500 constituents + daily bars, run the Momentum Leaders Snapback screener,
    and save results to SQLite.
    """
    cfg = load_config()
    constituents = fetch_sp500_constituents()
    meta_map = get_constituent_metadata_map()

    limit = universe_limit if universe_limit is not None else int(cfg["backtest"].get("default_universe_limit", 120))
    if limit and limit > 0:
        # Ensure curated high-liquidity leaders are included
        curated_syms = [c["symbol"] for c in FALLBACK_SP500]
        all_syms = [c["symbol"] for c in constituents]
        combined = list(dict.fromkeys(curated_syms + all_syms))[:limit]
    else:
        combined = [c["symbol"] for c in constituents]

    start_dt = (datetime.now() - timedelta(days=380)).strftime("%Y-%m-%d")
    ohlcv_map = fetch_ohlcv_bars(combined, start_date=start_dt, end_date=as_of_date)

    held_positions = get_positions()
    result = screen_universe_on_date(
        ohlcv_map=ohlcv_map,
        config=cfg,
        held_positions=held_positions,
        as_of_date=as_of_date,
        metadata_map=meta_map,
    )

    if persist and result["all_persisted"]:
        save_signals(result["signal_date"], result["all_persisted"])
        logger.info(
            f"Saved signals for {result['signal_date']}: "
            f"{len(result['entry'])} entries, {len(result['exit'])} exits, "
            f"{len(result['queued'])} queued, {len(result['radar'])} radar leaders."
        )

    return result


def print_screener_report(result: Dict[str, Any]) -> None:
    print("\n" + "=" * 95)
    print(f" MOMENTUM LEADERS SNAPBACK — DAILY SIGNAL SCREENER ({result['signal_date']})")
    print("=" * 95)
    print(
        f" Universe Evaluated : {result['universe_size']} S&P 500 stocks | "
        f"Above 200-MA: {result['above_sma200_count']} | "
        f"Top 20% 6-1M Momentum Leaders: {result['top_momentum_count']}"
    )
    print("-" * 95)

    entries = result["entry"]
    exits = result["exit"]
    queued = result["queued"]
    radar = result["radar"]

    print(f"\n[1] ACTIONABLE ENTRY SIGNALS (Execute Next Open, Max 2/Day) — {len(entries)} found:")
    if not entries:
        print("    No new entry signals triggered today (0 stocks met all 4 strict criteria simultaneously).")
    else:
        print(f"    {'Rank':<5} {'Symbol':<7} {'Close':>9} {'SMA200':>9} {'6-1M Mom':>10} {'MomPct':>7} {'RSI(2)':>7} {'RangePos':>9}")
        for s in entries:
            print(
                f"    #{s['rank']:<4} {s['symbol']:<7} "
                f"${s['close_price']:>8.2f} ${s['sma_200']:>8.2f} "
                f"{s['mom_6_1'] * 100:>+9.1f}% {s['mom_percentile']:>6.1f}% "
                f"{s['rsi_2']:>7.1f} {s['close_range_pos'] * 100:>8.1f}%"
            )
            print(f"          Reason: {s['reason']}")

    if queued:
        print(f"\n[2] QUEUED / CAPPED ENTRY SIGNALS (Exceeded 2/day or 10-position limit) — {len(queued)} found:")
        for s in queued:
            print(
                f"    #{s['rank']:<4} {s['symbol']:<7} Close=${s['close_price']:.2f} | "
                f"Mom={s['mom_6_1'] * 100:+.1f}% | RSI(2)={s['rsi_2']:.1f} | Range={s['close_range_pos'] * 100:.1f}%"
            )

    print(f"\n[3] EXIT SIGNALS FOR HELD POSITIONS (Execute Next Open) — {len(exits)} found:")
    if not exits:
        print("    No exit signals for held positions today.")
    else:
        for s in exits:
            print(f"    SELL  {s['symbol']:<7} @ Next Open | {s['reason']}")

    print(f"\n[4] MOMENTUM LEADERS RADAR (Top 20% Momentum + Above 200-MA, Lowest RSI(2) Watchlist):")
    if not radar:
        print("    No radar candidates available.")
    else:
        print(f"    {'Symbol':<7} {'Sector':<24} {'Close':>9} {'% > SMA200':>11} {'6-1M Mom':>10} {'RSI(2)':>8} {'Range%':>8}")
        for s in radar[:10]:
            print(
                f"    {s['symbol']:<7} {s['sector'][:23]:<24} "
                f"${s['close_price']:>8.2f} {s['pct_above_sma200']:>+10.1f}% "
                f"{s['mom_6_1'] * 100:>+9.1f}% {s['rsi_2']:>8.1f} {s['close_range_pos'] * 100:>7.1f}%"
            )
    print("=" * 95 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Momentum Leaders Snapback daily signal screener.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of S&P 500 stocks screened.")
    parser.add_argument("--date", type=str, default=None, help="Evaluate as of YYYY-MM-DD.")
    args = parser.parse_args()

    res = run_daily_screener(universe_limit=args.limit, as_of_date=args.date, persist=True)
    print_screener_report(res)


if __name__ == "__main__":
    main()
