from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.config import PaperTradingSafetyError, enforce_paper_only, load_config
from app.indicators import (
    calc_close_in_range,
    calc_momentum_6_1,
    calc_sma,
    calc_wilder_rsi,
    check_entry_signal,
    check_exit_signal,
    rank_momentum_cross_section,
)
from app.screener import screen_universe_on_date
from app.trader import compute_next_open_order_plan


def test_wilder_rsi2_calculation():
    # Purely rising series -> RSI(2) = 100
    up = pd.Series([100.0, 102.0, 105.0, 108.0, 112.0])
    rsi_up = calc_wilder_rsi(up, period=2)
    assert np.isnan(rsi_up.iloc[0])
    assert np.isnan(rsi_up.iloc[1])
    assert np.isclose(rsi_up.iloc[-1], 100.0)

    # Purely falling series -> RSI(2) = 0
    down = pd.Series([100.0, 98.0, 95.0, 91.0, 86.0])
    rsi_down = calc_wilder_rsi(down, period=2)
    assert np.isclose(rsi_down.iloc[-1], 0.0)

    # Known sharp 2-day pullback after uptrend produces RSI(2) < 15
    pullback = pd.Series([100.0, 102.0, 104.0, 106.0, 101.0, 95.0])
    rsi_pb = calc_wilder_rsi(pullback, period=2)
    assert rsi_pb.iloc[-1] < 15.0


def test_momentum_6_1_and_top_20_percent_ranking():
    # Create 150 bars where price at t-126 is 100, price at t-21 is 150 (+50%), and price at t is 140
    prices = np.ones(150) * 100.0
    # Index 149 is today (t). t-126 is index 23. t-21 is index 128.
    prices[23] = 100.0
    prices[128] = 150.0
    prices[149] = 140.0  # Recent 1-month dip should be ignored by 6-1M momentum!

    s = pd.Series(prices)
    mom = calc_momentum_6_1(s, lookback_start=126, lookback_end=21)
    assert np.isclose(mom.iloc[-1], 0.50)

    # Rank 10 stocks cross-sectionally: top 20% = exactly top 2 stocks
    universe_mom = pd.Series(
        {f"STK{i}": float(i) * 0.05 for i in range(1, 11)}  # STK10=0.50, STK9=0.45 are top 2
    )
    pct_ranks, is_top = rank_momentum_cross_section(universe_mom, top_pct=0.20)
    assert int(is_top.sum()) == 2
    assert bool(is_top["STK10"]) is True
    assert bool(is_top["STK9"]) is True
    assert bool(is_top["STK8"]) is False
    assert np.isclose(pct_ranks["STK10"], 1.0)


def test_close_in_range_and_entry_trigger_rules():
    # High=110, Low=100, Close=100.8 -> (100.8 - 100) / 10 = 0.08 (bottom 8% <= 10%)
    rng = calc_close_in_range(
        pd.Series([110.0]), pd.Series([100.0]), pd.Series([100.8])
    )
    assert np.isclose(rng.iloc[0], 0.08)

    # All 4 conditions met -> True
    ok, reason = check_entry_signal(
        close=105.0,
        sma_200=95.0,
        in_top_momentum=True,
        rsi_2=8.5,
        close_range_pos=0.08,
        rsi_threshold=15.0,
        close_range_threshold=0.10,
    )
    assert ok is True
    assert "SMA200" in reason

    # Fails when below 200-MA
    ok_ma, _ = check_entry_signal(90.0, 95.0, True, 8.5, 0.05)
    assert ok_ma is False

    # Fails when outside top 20% momentum
    ok_mom, _ = check_entry_signal(105.0, 95.0, False, 8.5, 0.05)
    assert ok_mom is False

    # Fails when RSI(2) >= 15
    ok_rsi, _ = check_entry_signal(105.0, 95.0, True, 18.2, 0.05)
    assert ok_rsi is False

    # Fails when close is not in bottom 10% of day's range
    ok_rng, _ = check_entry_signal(105.0, 95.0, True, 8.5, 0.25)
    assert ok_rng is False


def test_both_exit_rules():
    # Rule 1: Close > Prior Day's High triggers immediate bounce exit
    should_exit_bounce, reason_bounce = check_exit_signal(
        close=104.50,
        prior_high=103.00,
        days_held=3,
        max_hold_days=20,
        exit_above_prior_high=True,
    )
    assert should_exit_bounce is True
    assert "Bounce Exit" in reason_bounce

    # Rule 2: Held for 20 trading days triggers time exit (for open of day 21) even if Close <= Prior High
    should_exit_time, reason_time = check_exit_signal(
        close=99.00,
        prior_high=102.00,
        days_held=20,
        max_hold_days=20,
        exit_above_prior_high=True,
    )
    assert should_exit_time is True
    assert "Time Exit" in reason_time

    # Still holding when days_held < 20 and Close <= Prior High
    should_hold, _ = check_exit_signal(
        close=99.00,
        prior_high=102.00,
        days_held=12,
        max_hold_days=20,
        exit_above_prior_high=True,
    )
    assert should_hold is False


def _build_synthetic_stock_df(
    n_bars: int = 230,
    mom_gain: float = 0.40,
    trigger_snapback_at_end: bool = True,
) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-01", periods=n_bars)
    close = np.linspace(100.0, 100.0 * (1.0 + mom_gain), n_bars)
    if trigger_snapback_at_end:
        # Keep above 200-MA, but drop sharply on last 2 bars so RSI(2) < 15
        close[-2] = close[-3] * 0.96
        close[-1] = close[-2] * 0.96
    open_p = close * 1.01
    high = close * 1.03
    low = close * 0.999 if trigger_snapback_at_end else close * 0.97
    # When trigger_snapback_at_end is True:
    # (Close - Low) / (High - Low) = (1 - 0.999) / (1.03 - 0.999) = 0.001 / 0.031 = 0.032 <= 0.10
    return pd.DataFrame(
        {"Open": open_p, "High": high, "Low": low, "Close": close, "Volume": 1000000},
        index=dates,
    )


def test_portfolio_limits_10_positions_and_2_entries_per_day():
    cfg = load_config()
    # Create 20 stocks: top 4 (20% of 20) are momentum leaders and all 4 trigger entry today
    ohlcv_map = {}
    for i in range(1, 21):
        is_top_leader = i >= 17  # STK17, STK18, STK19, STK20 have highest momentum
        ohlcv_map[f"STK{i:02d}"] = _build_synthetic_stock_df(
            n_bars=230,
            mom_gain=0.10 + (i * 0.04),
            trigger_snapback_at_end=is_top_leader,
        )

    # Case A: 0 held positions -> all 4 top leaders trigger, but max_new_entries_per_day=2 caps ENTRY at 2 (STK20, STK19)
    # and queues the other 2 (STK18, STK17)
    res_a = screen_universe_on_date(ohlcv_map, config=cfg, held_positions=[])
    assert len(res_a["entry"]) == 2
    assert res_a["entry"][0]["symbol"] == "STK20"
    assert res_a["entry"][1]["symbol"] == "STK19"
    assert len(res_a["queued"]) == 2
    assert {q["symbol"] for q in res_a["queued"]} == {"STK18", "STK17"}

    # Case B: 9 held positions (none exiting today) -> only 1 open portfolio slot left (max 10 positions)
    nine_positions = [
        {
            "symbol": f"HELD{j}",
            "entry_price": 100.0,
            "current_price": 100.0,
            "prior_high": 110.0,  # Won't exit today
            "days_held": 5,
            "shares": 10,
            "market_value": 1000.0,
        }
        for j in range(9)
    ]
    res_b = screen_universe_on_date(ohlcv_map, config=cfg, held_positions=nine_positions)
    assert len(res_b["entry"]) == 1
    assert res_b["entry"][0]["symbol"] == "STK20"
    assert len(res_b["queued"]) == 3


def test_leverage_cap_and_paper_only_guard():
    cfg = load_config()
    account_state = {
        "equity": 100000.0,
        "daily_pnl_pct": 0.5,
        "positions": [
            {
                "symbol": f"POS{i}",
                "shares": 100,
                "current_price": 190.0,
                "market_value": 19000.0,
            }
            for i in range(9)
        ],  # $171,000 existing exposure on $100,000 equity (1.71x)
    }
    signals_bundle = {
        "signal_date": "2026-10-27",
        "exit": [],
        "entry": [
            {
                "symbol": "NVDA",
                "close_price": 100.0,
                "mom_6_1": 0.65,
                "reason": "Entry #1",
            }
        ],
    }
    plan = compute_next_open_order_plan(account_state, signals_bundle, cfg)
    assert plan["projected_gross_leverage"] <= 2.0001
    assert plan["projected_gross_exposure"] <= 200000.01

    # Verify paper-only safety enforcement raises on any live trading config
    with pytest.raises(PaperTradingSafetyError):
        enforce_paper_only(cfg, paper_flag=False)

    with pytest.raises(PaperTradingSafetyError):
        enforce_paper_only(cfg, paper_flag=True, base_url="https://api.alpaca.markets")

    with pytest.raises(PaperTradingSafetyError):
        enforce_paper_only(cfg, paper_flag=True, api_key="AKLIVEKEY123456")
