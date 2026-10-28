from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.config import DATA_DIR, get_logger, load_config
from app.db import save_backtest_run
from app.indicators import (
    calc_close_in_range,
    calc_momentum_6_1,
    calc_sma,
    calc_wilder_rsi,
)
from app.universe import (
    FALLBACK_SP500,
    fetch_ohlcv_bars,
    fetch_sp500_constituents,
    get_constituent_metadata_map,
)

logger = get_logger("backtest")


@dataclass
class SimPosition:
    symbol: str
    entry_date: str
    entry_price: float
    shares: float
    days_held: int = 0
    entry_mom: float = 0.0
    entry_rsi: float = 0.0


def _prepare_aligned_matrices(
    ohlcv_map: Dict[str, pd.DataFrame],
    sma_period: int = 200,
    mom_start: int = 126,
    mom_end: int = 21,
    rsi_period: int = 2,
) -> Dict[str, pd.DataFrame]:
    """
    Build aligned date x symbol DataFrames for Open, High, Low, Close, PriorHigh,
    SMA200, Mom_6_1, RSI2, and CloseRangePos for fast, exact event-driven simulation.
    """
    symbols = [s for s in ohlcv_map.keys() if s != "SPY" and not ohlcv_map[s].empty]
    open_dict: Dict[str, pd.Series] = {}
    high_dict: Dict[str, pd.Series] = {}
    low_dict: Dict[str, pd.Series] = {}
    close_dict: Dict[str, pd.Series] = {}
    prior_high_dict: Dict[str, pd.Series] = {}
    sma_dict: Dict[str, pd.Series] = {}
    mom_dict: Dict[str, pd.Series] = {}
    rsi_dict: Dict[str, pd.Series] = {}
    range_dict: Dict[str, pd.Series] = {}

    for sym in symbols:
        df = ohlcv_map[sym].sort_index()
        df = df[~df.index.duplicated(keep="last")]
        c = df["Close"].astype(float)
        h = df["High"].astype(float)
        l = df["Low"].astype(float)
        o = df["Open"].astype(float)

        open_dict[sym] = o
        high_dict[sym] = h
        low_dict[sym] = l
        close_dict[sym] = c
        prior_high_dict[sym] = h.shift(1)
        sma_dict[sym] = calc_sma(c, period=sma_period)
        mom_dict[sym] = calc_momentum_6_1(c, lookback_start=mom_start, lookback_end=mom_end)
        rsi_dict[sym] = calc_wilder_rsi(c, period=rsi_period)
        range_dict[sym] = calc_close_in_range(h, l, c)

    return {
        "Open": pd.DataFrame(open_dict).sort_index(),
        "High": pd.DataFrame(high_dict).sort_index(),
        "Low": pd.DataFrame(low_dict).sort_index(),
        "Close": pd.DataFrame(close_dict).sort_index(),
        "PriorHigh": pd.DataFrame(prior_high_dict).sort_index(),
        "SMA200": pd.DataFrame(sma_dict).sort_index(),
        "Mom": pd.DataFrame(mom_dict).sort_index(),
        "RSI2": pd.DataFrame(rsi_dict).sort_index(),
        "RangePos": pd.DataFrame(range_dict).sort_index(),
    }


def simulate_strategy(
    matrices: Dict[str, pd.DataFrame],
    config: Dict[str, Any],
    use_momentum_filter: bool = True,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Tuple[pd.Series, List[Dict[str, Any]], pd.Series]:
    """
    Event-driven daily simulation with zero lookahead bias:
      - Day t Close: compute signals using completed bars up to Day t.
      - Day t+1 Open: fill queued exits and entries at Open_{t+1} +/- slippage.
    Returns (equity_series, closed_trades_list, gross_leverage_series).
    """
    strat = config["strategy"]
    bt = config["backtest"]

    mom_top_pct = float(strat.get("momentum_top_pct", 0.20))
    rsi_thresh = float(strat.get("rsi_entry_threshold", 15.0))
    range_thresh = float(strat.get("close_range_threshold", 0.10))
    exit_prior_high = bool(strat.get("exit_above_prior_high", True))
    max_hold_days = int(strat.get("max_hold_days", 20))
    max_positions = int(strat.get("max_positions", 10))
    max_new_per_day = int(strat.get("max_new_entries_per_day", 2))
    target_leverage = float(strat.get("target_gross_leverage", 2.0))
    max_leverage = float(strat.get("max_gross_leverage", 2.0))

    initial_capital = float(bt.get("initial_capital", 1000.0))
    slippage_rate = float(bt.get("slippage_bps", 5.0)) / 10000.0
    daily_margin_rate = float(bt.get("margin_interest_annual", 0.055)) / 252.0

    close_df = matrices["Close"]
    open_df = matrices["Open"]
    prior_high_df = matrices["PriorHigh"]
    sma_df = matrices["SMA200"]
    mom_df = matrices["Mom"]
    rsi_df = matrices["RSI2"]
    range_df = matrices["RangePos"]

    all_dates = close_df.index
    if start_date:
        all_dates = all_dates[all_dates >= pd.Timestamp(start_date)]
    if end_date:
        all_dates = all_dates[all_dates <= pd.Timestamp(end_date)]

    if len(all_dates) < 5:
        eq = pd.Series([initial_capital], index=[ pd.Timestamp.today() ])
        return eq, [], pd.Series([0.0], index=eq.index)

    cash = initial_capital
    positions: Dict[str, SimPosition] = {}
    pending_exits: List[Tuple[str, str]] = []  # (symbol, exit_reason)
    pending_entries: List[Tuple[str, float, float]] = []  # (symbol, mom_val, rsi_val)
    closed_trades: List[Dict[str, Any]] = []

    equity_curve: Dict[pd.Timestamp, float] = {}
    leverage_curve: Dict[pd.Timestamp, float] = {}

    for dt in all_dates:
        dt_str = dt.strftime("%Y-%m-%d")
        open_row = open_df.loc[dt]
        close_row = close_df.loc[dt]
        prior_h_row = prior_high_df.loc[dt]
        sma_row = sma_df.loc[dt]
        mom_row = mom_df.loc[dt]
        rsi_row = rsi_df.loc[dt]
        range_row = range_df.loc[dt]

        # ------------------------------------------------------------------
        # STEP 1: Market Open (dt) — Execute orders queued at prior day close
        # ------------------------------------------------------------------
        # 1a. Execute pending exits at Open * (1 - slippage)
        for sym, exit_reason in pending_exits:
            if sym in positions:
                pos = positions.pop(sym)
                raw_open = float(open_row.get(sym, np.nan))
                if np.isnan(raw_open) or raw_open <= 0:
                    raw_open = float(close_row.get(sym, pos.entry_price))
                fill_price = raw_open * (1.0 - slippage_rate)
                proceeds = pos.shares * fill_price
                cash += proceeds
                pnl = proceeds - (pos.shares * pos.entry_price)
                ret_pct = ((fill_price / pos.entry_price) - 1.0) * 100.0
                closed_trades.append(
                    {
                        "symbol": sym,
                        "entry_date": pos.entry_date,
                        "exit_date": dt_str,
                        "entry_price": round(pos.entry_price, 2),
                        "exit_price": round(fill_price, 2),
                        "shares": round(pos.shares, 4),
                        "days_held": pos.days_held,
                        "pnl": round(pnl, 2),
                        "return_pct": round(ret_pct, 2),
                        "exit_reason": exit_reason,
                    }
                )
        pending_exits.clear()

        # 1b. Compute current account equity at Open before sizing new entries
        open_pos_val = 0.0
        for sym, pos in positions.items():
            op = float(open_row.get(sym, np.nan))
            if np.isnan(op) or op <= 0:
                op = pos.entry_price
            open_pos_val += pos.shares * op
        open_equity = max(0.0, cash + open_pos_val)

        # 1c. Execute up to `max_new_per_day` pending entries at Open * (1 + slippage)
        available_slots = max(0, max_positions - len(positions))
        entries_to_run = [
            item for item in pending_entries if item[0] not in positions
        ][: min(max_new_per_day, available_slots)]

        if entries_to_run and open_equity > 0:
            # Position sizing rule from specification:
            # With up to 10 positions and up to 2x leverage, target gross exposure up to 2x account equity;
            # size each new position as (target exposure) / (current positions + new entries),
            # while never exceeding max_leverage (2x) gross exposure or 0.50x equity in a single stock.
            total_after = max(1, len(positions) + len(entries_to_run))
            target_gross_dollars = target_leverage * open_equity
            max_gross_dollars = max_leverage * open_equity
            remaining_gross_capacity = max(0.0, max_gross_dollars - open_pos_val)

            ideal_per_entry = target_gross_dollars / float(total_after)
            single_stock_cap = 0.50 * open_equity
            capped_per_entry = min(
                ideal_per_entry,
                single_stock_cap,
                remaining_gross_capacity / float(len(entries_to_run)),
            )

            for sym, mom_v, rsi_v in entries_to_run:
                raw_open = float(open_row.get(sym, np.nan))
                if np.isnan(raw_open) or raw_open <= 0 or capped_per_entry <= 0:
                    continue
                fill_price = raw_open * (1.0 + slippage_rate)
                shares = capped_per_entry / fill_price
                cost = shares * fill_price
                cash -= cost
                positions[sym] = SimPosition(
                    symbol=sym,
                    entry_date=dt_str,
                    entry_price=fill_price,
                    shares=shares,
                    days_held=0,
                    entry_mom=mom_v,
                    entry_rsi=rsi_v,
                )
        pending_entries.clear()

        # ------------------------------------------------------------------
        # STEP 2: Market Close (dt) — Mark to market, charge margin, compute signals
        # ------------------------------------------------------------------
        gross_exposure = 0.0
        for sym, pos in list(positions.items()):
            pos.days_held += 1
            cp = float(close_row.get(sym, np.nan))
            if np.isnan(cp) or cp <= 0:
                cp = pos.entry_price
            gross_exposure += pos.shares * cp

        # Deduct daily margin interest if cash is negative (leveraged exposure > 1.0x equity)
        if cash < 0.0:
            borrowed = abs(cash)
            cash -= borrowed * daily_margin_rate

        close_equity = max(1e-6, cash + gross_exposure)
        equity_curve[dt] = close_equity
        leverage_curve[dt] = gross_exposure / close_equity if close_equity > 0 else 0.0

        # 2a. Check Exit Signals for held positions at Close(dt) -> queued for Open(dt+1)
        surviving_count = 0
        for sym, pos in positions.items():
            cp = float(close_row.get(sym, np.nan))
            ph = float(prior_h_row.get(sym, np.nan))
            if np.isnan(cp):
                surviving_count += 1
                continue
            if exit_prior_high and not np.isnan(ph) and cp > ph:
                pending_exits.append((sym, f"Close > Prior High (Day {pos.days_held})"))
            elif pos.days_held >= max_hold_days:
                pending_exits.append((sym, f"Max Hold {max_hold_days} Days"))
            else:
                surviving_count += 1

        # 2b. Check Entry Signals across universe at Close(dt) -> queued for Open(dt+1)
        slots_tomorrow = max(0, max_positions - surviving_count)
        if slots_tomorrow > 0:
            valid_mom = mom_row.dropna()
            if len(valid_mom) >= 5:
                if use_momentum_filter:
                    k = max(1, int(np.ceil(len(valid_mom) * mom_top_pct)))
                    top_mom_syms = set(valid_mom.nlargest(k).index)
                else:
                    top_mom_syms = set(valid_mom.index)

                candidates: List[Tuple[str, float, float]] = []
                for sym in top_mom_syms:
                    if sym in positions:
                        continue
                    cp = float(close_row.get(sym, np.nan))
                    sma_v = float(sma_row.get(sym, np.nan))
                    rsi_v = float(rsi_row.get(sym, np.nan))
                    rng_v = float(range_row.get(sym, np.nan))
                    mom_v = float(mom_row.get(sym, np.nan))

                    if (
                        not np.isnan(cp)
                        and not np.isnan(sma_v)
                        and not np.isnan(rsi_v)
                        and not np.isnan(rng_v)
                        and cp > sma_v
                        and rsi_v < rsi_thresh
                        and rng_v <= range_thresh
                    ):
                        candidates.append((sym, mom_v, rsi_v))

                # Rank by 6-1M momentum descending, take top `min(max_new_per_day, slots_tomorrow)`
                candidates.sort(key=lambda x: x[1], reverse=True)
                pending_entries = candidates[: min(max_new_per_day, slots_tomorrow)]

    eq_series = pd.Series(equity_curve).sort_index()
    lev_series = pd.Series(leverage_curve).sort_index()
    return eq_series, closed_trades, lev_series


def compute_performance_metrics(
    eq_series: pd.Series,
    spy_series: pd.Series,
    no_mom_series: pd.Series,
    trades: List[Dict[str, Any]],
    lev_series: pd.Series,
    initial_capital: float = 1000.0,
) -> Dict[str, Any]:
    """Compute comprehensive strategy and benchmark metrics + yearly returns table."""
    eq = eq_series.dropna()
    if len(eq) < 2:
        raise ValueError("Insufficient backtest equity curve points")

    start_dt = eq.index[0]
    end_dt = eq.index[-1]
    years = max(0.01, (end_dt - start_dt).days / 365.25)

    final_eq = float(eq.iloc[-1])
    total_return_pct = ((final_eq / initial_capital) - 1.0) * 100.0
    cagr_pct = (((final_eq / initial_capital) ** (1.0 / years)) - 1.0) * 100.0

    daily_rets = eq.pct_change().dropna()
    sharpe = (
        float((daily_rets.mean() / daily_rets.std()) * np.sqrt(252.0))
        if len(daily_rets) > 2 and daily_rets.std() > 0
        else 0.0
    )
    downside = daily_rets[daily_rets < 0]
    sortino = (
        float((daily_rets.mean() / downside.std()) * np.sqrt(252.0))
        if len(downside) > 2 and downside.std() > 0
        else 0.0
    )

    running_max = eq.cummax()
    drawdown = (eq / running_max) - 1.0
    max_dd_pct = float(drawdown.min() * 100.0)

    # Align SPY benchmark
    spy_aligned = spy_series.reindex(eq.index).ffill().bfill()
    spy_norm = (spy_aligned / float(spy_aligned.iloc[0])) * initial_capital
    spy_final = float(spy_norm.iloc[-1])
    spy_total_return_pct = ((spy_final / initial_capital) - 1.0) * 100.0
    spy_cagr_pct = (((spy_final / initial_capital) ** (1.0 / years)) - 1.0) * 100.0
    spy_dd = ((spy_norm / spy_norm.cummax()) - 1.0).min() * 100.0

    # Align No-Momentum Dip Buyer comparison
    no_mom_aligned = no_mom_series.reindex(eq.index).ffill().bfill()
    no_mom_final = float(no_mom_aligned.iloc[-1])
    no_mom_return_pct = ((no_mom_final / initial_capital) - 1.0) * 100.0

    # Trade stats
    n_trades = len(trades)
    wins = [t for t in trades if t["return_pct"] > 0]
    win_rate_pct = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0
    avg_hold_days = float(np.mean([t["days_held"] for t in trades])) if n_trades > 0 else 0.0
    avg_trade_ret = float(np.mean([t["return_pct"] for t in trades])) if n_trades > 0 else 0.0

    # Yearly returns table
    yearly_rows: List[Dict[str, Any]] = []
    eq_yearly = eq.groupby(eq.index.year)
    spy_yearly = spy_norm.groupby(spy_norm.index.year)

    prev_eq_end = initial_capital
    prev_spy_end = initial_capital
    years_beating_spy = 0
    total_years = 0

    for yr, grp in eq_yearly:
        yr_end_eq = float(grp.iloc[-1])
        strat_yr_ret = ((yr_end_eq / prev_eq_end) - 1.0) * 100.0
        prev_eq_end = yr_end_eq

        spy_grp = spy_yearly.get_group(yr)
        yr_end_spy = float(spy_grp.iloc[-1])
        spy_yr_ret = ((yr_end_spy / prev_spy_end) - 1.0) * 100.0
        prev_spy_end = yr_end_spy

        beat = strat_yr_ret > spy_yr_ret
        if beat:
            years_beating_spy += 1
        total_years += 1

        yearly_rows.append(
            {
                "year": int(yr),
                "strategy_return_pct": round(strat_yr_ret, 2),
                "spy_return_pct": round(spy_yr_ret, 2),
                "alpha_pct": round(strat_yr_ret - spy_yr_ret, 2),
                "beat_spy": beat,
                "ending_equity": round(yr_end_eq, 2),
                "spy_ending_equity": round(yr_end_spy, 2),
            }
        )

    # Downsample equity curve to ~280 points for responsive dashboard rendering & chart export
    step = max(1, len(eq) // 280)
    sampled_indices = list(range(0, len(eq), step))
    if sampled_indices[-1] != len(eq) - 1:
        sampled_indices.append(len(eq) - 1)

    curve_points: List[Dict[str, Any]] = []
    for i in sampled_indices:
        dt = eq.index[i]
        curve_points.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "strategy_equity": round(float(eq.iloc[i]), 2),
                "spy_equity": round(float(spy_norm.iloc[i]), 2),
                "no_momentum_equity": round(float(no_mom_aligned.iloc[i]), 2),
                "drawdown_pct": round(float(drawdown.iloc[i] * 100.0), 2),
                "gross_leverage": round(float(lev_series.iloc[i]), 2),
            }
        )

    metrics = {
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_dt.strftime("%Y-%m-%d"),
        "years_tested": round(years, 2),
        "initial_capital": round(initial_capital, 2),
        "final_equity": round(final_eq, 2),
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "avg_hold_days": round(avg_hold_days, 2),
        "avg_trade_return_pct": round(avg_trade_ret, 2),
        "total_trades": n_trades,
        "avg_gross_leverage": round(float(lev_series.mean()), 2),
        "max_gross_leverage_used": round(float(lev_series.max()), 2),
        "spy_final_equity": round(spy_final, 2),
        "spy_total_return_pct": round(spy_total_return_pct, 2),
        "spy_cagr_pct": round(spy_cagr_pct, 2),
        "spy_max_drawdown_pct": round(float(spy_dd), 2),
        "no_mom_final_equity": round(no_mom_final, 2),
        "no_mom_return_pct": round(no_mom_return_pct, 2),
        "years_beating_spy": years_beating_spy,
        "total_calendar_years": total_years,
        "post_claims_comparison": {
            "claimed_total_return_pct": 22289.0,
            "claimed_realistic_cagr_pct": 27.0,
            "claimed_max_drawdown_pct": -38.0,
            "claimed_winning_years_ratio": "13 / 19",
            "claimed_no_momentum_return_pct": 316.0,
            "actual_total_return_pct": round(total_return_pct, 2),
            "actual_cagr_pct": round(cagr_pct, 2),
            "actual_max_drawdown_pct": round(max_dd_pct, 2),
            "actual_winning_years_ratio": f"{years_beating_spy} / {total_years}",
            "actual_no_momentum_return_pct": round(no_mom_return_pct, 2),
            "momentum_filter_outperformance_pct": round(total_return_pct - no_mom_return_pct, 2),
        },
    }

    return {
        "metrics": metrics,
        "yearly_returns": yearly_rows,
        "equity_curve": curve_points,
        "trades": trades[-250:],  # Keep latest 250 trades for payload efficiency
    }


def save_equity_curve_chart(
    result: Dict[str, Any],
    output_path: Path = DATA_DIR / "equity_curve.png",
) -> Path:
    """Render and save a clean, light-toned equity curve & drawdown chart."""
    curve = result["equity_curve"]
    metrics = result["metrics"]
    dates = pd.to_datetime([pt["date"] for pt in curve])
    strat_eq = [pt["strategy_equity"] for pt in curve]
    spy_eq = [pt["spy_equity"] for pt in curve]
    no_mom_eq = [pt["no_momentum_equity"] for pt in curve]
    dd = [pt["drawdown_pct"] for pt in curve]

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 7.5), gridspec_kw={"height_ratios": [2.6, 1]}, sharex=True
    )
    fig.patch.set_facecolor("#F6F8FC")
    for ax in (ax1, ax2):
        ax.set_facecolor("#FFFFFF")
        ax.grid(True, linestyle="--", alpha=0.45, color="#CBD5E1")
        for spine in ax.spines.values():
            spine.set_color("#E2E8F0")

    ax1.plot(dates, strat_eq, label=f"Momentum Leaders Snapback ({metrics['total_return_pct']:+.1f}%)", color="#0284C7", linewidth=2.3)
    ax1.plot(dates, spy_eq, label=f"SPY Buy & Hold ({metrics['spy_total_return_pct']:+.1f}%)", color="#64748B", linewidth=1.6, linestyle="--")
    ax1.plot(dates, no_mom_eq, label=f"Dip Buy Without Momentum Filter ({metrics['no_mom_return_pct']:+.1f}%)", color="#F59E0B", linewidth=1.4, alpha=0.85)
    ax1.set_yscale("log")
    ax1.set_ylabel("Portfolio Value ($, Log Scale)", color="#1E293B", fontsize=10, fontweight="bold")
    ax1.set_title(
        f"Momentum Leaders Snapback vs. SPY ({metrics['start_date']} to {metrics['end_date']}) | "
        f"CAGR: {metrics['cagr_pct']:.1f}% | Sharpe: {metrics['sharpe_ratio']:.2f} | Max DD: {metrics['max_drawdown_pct']:.1f}%",
        color="#0F172A",
        fontsize=11.5,
        fontweight="bold",
        pad=12,
    )
    ax1.legend(loc="upper left", frameon=True, facecolor="#F8FAFC", edgecolor="#E2E8F0")

    ax2.fill_between(dates, dd, 0, color="#F43F5E", alpha=0.22)
    ax2.plot(dates, dd, color="#E11D48", linewidth=1.2, label="Strategy Drawdown (%)")
    ax2.set_ylabel("Drawdown (%)", color="#1E293B", fontsize=10, fontweight="bold")
    ax2.set_xlabel("Date", color="#1E293B", fontsize=10)
    ax2.legend(loc="lower left", frameon=True, facecolor="#F8FAFC", edgecolor="#E2E8F0")

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150)
    plt.close(fig)
    return output_path


def run_backtest(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    universe_limit: Optional[int] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Run the full event-driven Momentum Leaders Snapback backtest and save results."""
    cfg = load_config()
    bt_cfg = cfg["backtest"]
    strat_cfg = cfg["strategy"]

    s_date = start_date or bt_cfg.get("start_date", "2008-01-01")
    e_date = end_date or bt_cfg.get("end_date")
    limit = universe_limit if universe_limit is not None else int(bt_cfg.get("default_universe_limit", 120))

    constituents = fetch_sp500_constituents()
    curated_syms = [c["symbol"] for c in FALLBACK_SP500]
    all_syms = [c["symbol"] for c in constituents]
    combined_syms = list(dict.fromkeys(curated_syms + all_syms))
    if limit and limit > 0:
        combined_syms = combined_syms[:limit]

    if "SPY" not in combined_syms:
        combined_syms.append("SPY")

    # Fetch 1 year earlier than start_date so 200-day SMA and 126-day momentum are warm on day 1
    warm_start = (pd.Timestamp(s_date) - pd.Timedelta(days=340)).strftime("%Y-%m-%d")
    ohlcv_map = fetch_ohlcv_bars(combined_syms, start_date=warm_start, end_date=e_date)

    matrices = _prepare_aligned_matrices(
        ohlcv_map,
        sma_period=int(strat_cfg.get("sma_period", 200)),
        mom_start=int(strat_cfg.get("momentum_lookback_start", 126)),
        mom_end=int(strat_cfg.get("momentum_lookback_end", 21)),
        rsi_period=int(strat_cfg.get("rsi_period", 2)),
    )

    # 1. Run Momentum Leaders Snapback strategy
    eq_series, trades, lev_series = simulate_strategy(
        matrices=matrices,
        config=cfg,
        use_momentum_filter=True,
        start_date=s_date,
        end_date=e_date,
    )

    # 2. Run Plain Dip-Buying WITHOUT the momentum filter to validate the post's claim
    no_mom_eq, _, _ = simulate_strategy(
        matrices=matrices,
        config=cfg,
        use_momentum_filter=False,
        start_date=s_date,
        end_date=e_date,
    )

    # 3. Extract SPY Buy-and-Hold series
    if "SPY" in ohlcv_map and not ohlcv_map["SPY"].empty:
        spy_close = ohlcv_map["SPY"]["Close"].astype(float)
    else:
        spy_close = matrices["Close"].mean(axis=1)

    initial_cap = float(bt_cfg.get("initial_capital", 1000.0))
    result = compute_performance_metrics(
        eq_series=eq_series,
        spy_series=spy_close,
        no_mom_series=no_mom_eq,
        trades=trades,
        lev_series=lev_series,
        initial_capital=initial_cap,
    )

    chart_path = save_equity_curve_chart(result)
    result["chart_path"] = str(chart_path)

    if persist:
        run_id = save_backtest_run(result)
        result["id"] = run_id
        logger.info(
            f"Backtest #{run_id} completed ({result['metrics']['start_date']} -> {result['metrics']['end_date']}): "
            f"CAGR={result['metrics']['cagr_pct']:.2f}%, Sharpe={result['metrics']['sharpe_ratio']:.2f}, "
            f"MaxDD={result['metrics']['max_drawdown_pct']:.2f}%, Trades={result['metrics']['total_trades']}"
        )

    return result


def print_backtest_report(result: Dict[str, Any]) -> None:
    m = result["metrics"]
    claims = m["post_claims_comparison"]
    print("\n" + "=" * 95)
    print(" MOMENTUM LEADERS SNAPBACK — EVENT-DRIVEN BACKTEST REPORT (NO LOOKAHEAD BIAS)")
    print("=" * 95)
    print(f" Period Tested        : {m['start_date']} to {m['end_date']} ({m['years_tested']} years)")
    print(f" Initial Capital      : ${m['initial_capital']:,.2f}")
    print("-" * 95)
    print(f" {'Metric':<32} {'Momentum Snapback':>20} {'SPY Buy & Hold':>18} {'No-Mom Dip Buy':>18}")
    print("-" * 95)
    print(f" {'Final Portfolio Value':<32} ${m['final_equity']:>19,.2f} ${m['spy_final_equity']:>17,.2f} ${m['no_mom_final_equity']:>17,.2f}")
    print(f" {'Total Return (%)':<32} {m['total_return_pct']:>+19.2f}% {m['spy_total_return_pct']:>+17.2f}% {m['no_mom_return_pct']:>+17.2f}%")
    print(f" {'Annualized CAGR (%)':<32} {m['cagr_pct']:>+19.2f}% {m['spy_cagr_pct']:>+17.2f}% {'—':>18}")
    print(f" {'Max Drawdown (%)':<32} {m['max_drawdown_pct']:>19.2f}% {m['spy_max_drawdown_pct']:>17.2f}% {'—':>18}")
    print(f" {'Sharpe Ratio':<32} {m['sharpe_ratio']:>20.2f} {'—':>18} {'—':>18}")
    print(f" {'Sortino Ratio':<32} {m['sortino_ratio']:>20.2f} {'—':>18} {'—':>18}")
    print(f" {'Win Rate (%)':<32} {m['win_rate_pct']:>19.2f}% {'—':>18} {'—':>18}")
    print(f" {'Average Hold (Trading Days)':<32} {m['avg_hold_days']:>20.2f} {'—':>18} {'—':>18}")
    print(f" {'Total Closed Trades':<32} {m['total_trades']:>20d} {'1':>18} {'—':>18}")
    print("-" * 95)
    print(" VALIDATION VS. ALPHAINSIDER POST CLAIMS (Oct 23, 2026):")
    print(
        f"   • Total Return     : Post Claimed +22,289% (and ~27%/yr realistic) | "
        f"Backtest Achieved: {m['total_return_pct']:+.1f}% ({m['cagr_pct']:.2f}% CAGR)"
    )
    print(
        f"   • Max Drawdown     : Post Claimed -38.0%                           | "
        f"Backtest Achieved: {m['max_drawdown_pct']:.2f}%"
    )
    print(
        f"   • Years Beating SPY: Post Claimed 13 / 19 years                    | "
        f"Backtest Achieved: {claims['actual_winning_years_ratio']} years"
    )
    print(
        f"   • Momentum Filter  : With Top-20% 6-1M Momentum ({m['total_return_pct']:+.1f}%) vs. "
        f"Without Momentum Filter ({m['no_mom_return_pct']:+.1f}%)"
    )
    print("-" * 95)
    print(" YEARLY RETURNS TABLE:")
    print(f" {'Year':<6} {'Strategy (%)':>14} {'SPY (%)':>12} {'Alpha (%)':>12} {'Beat SPY?':>11} {'Ending Equity ($)':>20}")
    for yr in result["yearly_returns"]:
        badge = "YES" if yr["beat_spy"] else "NO"
        print(
            f" {yr['year']:<6} {yr['strategy_return_pct']:>+13.2f}% {yr['spy_return_pct']:>+11.2f}% "
            f"{yr['alpha_pct']:>+11.2f}% {badge:>11} ${yr['ending_equity']:>19,.2f}"
        )
    print("-" * 95)
    print(f" Equity curve chart saved to: {result.get('chart_path', 'data/equity_curve.png')}")
    print("=" * 95 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Momentum Leaders Snapback event-driven backtester.")
    parser.add_argument("--start", type=str, default=None, help="Backtest start date (YYYY-MM-DD), default 2008-01-01")
    parser.add_argument("--end", type=str, default=None, help="Backtest end date (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=60, help="Number of S&P 500 constituents to include (0 = all)")
    args = parser.parse_args()

    res = run_backtest(start_date=args.start, end_date=args.end, universe_limit=args.limit, persist=True)
    print_backtest_report(res)


if __name__ == "__main__":
    main()
