from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def calc_sma(close: pd.Series, period: int = 200) -> pd.Series:
    """Compute Simple Moving Average over `period` trading days."""
    return close.astype(float).rolling(window=period, min_periods=period).mean()


def calc_momentum_6_1(
    close: pd.Series,
    lookback_start: int = 126,
    lookback_end: int = 21,
) -> pd.Series:
    """
    Compute academic 6-1 month momentum:
    Total return from `lookback_start` (~126 trading days ago) to `lookback_end` (~21 trading days ago),
    skipping the most recent month to avoid short-term 1-month reversal effects.
    """
    if lookback_start <= lookback_end:
        raise ValueError("lookback_start must be strictly greater than lookback_end")
    c = close.astype(float)
    past_start = c.shift(lookback_start)
    past_end = c.shift(lookback_end)
    return (past_end / past_start) - 1.0


def calc_wilder_rsi(close: pd.Series, period: int = 2) -> pd.Series:
    """
    Compute Wilder's RSI over `period` bars (default 2).
    Uses Wilder's recursive smoothing (alpha = 1 / period).
    """
    c = close.astype(float)
    delta = c.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # Handle edge cases where avg_loss == 0 or avg_gain == 0
    both_zero = (avg_gain == 0.0) & (avg_loss == 0.0)
    loss_zero = (avg_loss == 0.0) & (avg_gain > 0.0)
    gain_zero = (avg_gain == 0.0) & (avg_loss > 0.0)

    rsi = rsi.mask(loss_zero, 100.0)
    rsi = rsi.mask(gain_zero, 0.0)
    rsi = rsi.mask(both_zero, 50.0)

    # Ensure first `period` elements prior to valid window remain NaN
    valid_mask = c.rolling(window=period + 1).count() >= (period + 1)
    return rsi.where(valid_mask, np.nan)


def calc_close_in_range(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> pd.Series:
    """
    Compute where the daily close sits inside the day's [low, high] range:
        (Close - Low) / (High - Low)
    Returns 0.0 at the exact low, 1.0 at the exact high.
    If High == Low (zero-range bar), returns 0.5 so flat bars do not falsely trigger.
    """
    h = high.astype(float)
    l = low.astype(float)
    c = close.astype(float)
    span = h - l
    pos = (c - l) / span.replace(0.0, np.nan)
    pos = pos.fillna(0.5).clip(lower=0.0, upper=1.0)
    return pos


def compute_stock_indicators(
    df: pd.DataFrame,
    sma_period: int = 200,
    momentum_lookback_start: int = 126,
    momentum_lookback_end: int = 21,
    rsi_period: int = 2,
) -> pd.DataFrame:
    """
    Given a single stock's daily OHLCV DataFrame with columns ['Open', 'High', 'Low', 'Close', 'Volume'],
    return a DataFrame augmented with:
      - SMA200
      - PctAboveSMA200
      - Mom_6_1
      - RSI2
      - CloseRangePos
      - PriorHigh
    """
    out = df.copy()
    out["SMA200"] = calc_sma(out["Close"], period=sma_period)
    out["PctAboveSMA200"] = ((out["Close"] / out["SMA200"]) - 1.0) * 100.0
    out["Mom_6_1"] = calc_momentum_6_1(
        out["Close"],
        lookback_start=momentum_lookback_start,
        lookback_end=momentum_lookback_end,
    )
    out["RSI2"] = calc_wilder_rsi(out["Close"], period=rsi_period)
    out["CloseRangePos"] = calc_close_in_range(out["High"], out["Low"], out["Close"])
    out["PriorHigh"] = out["High"].shift(1)
    return out


def rank_momentum_cross_section(
    momentum_values: pd.Series,
    top_pct: float = 0.20,
) -> Tuple[pd.Series, pd.Series]:
    """
    Rank stocks cross-sectionally by 6-1M momentum.
    Returns:
      - percentiles: pd.Series in [0.0, 1.0] (1.0 = highest momentum)
      - is_top_group: boolean pd.Series indicating whether the stock is in the top `top_pct` fraction.
    """
    valid = momentum_values.dropna()
    if valid.empty:
        empty_pct = pd.Series(index=momentum_values.index, dtype=float)
        empty_bool = pd.Series(False, index=momentum_values.index, dtype=bool)
        return empty_pct, empty_bool

    n = len(valid)
    k = max(1, int(np.ceil(n * top_pct)))
    # Rank descending: rank 1 is highest momentum
    desc_rank = valid.rank(ascending=False, method="first")
    pct_rank = valid.rank(ascending=True, pct=True)

    is_top = desc_rank <= k
    return (
        pct_rank.reindex(momentum_values.index),
        is_top.reindex(momentum_values.index, fill_value=False),
    )


def check_entry_signal(
    close: float,
    sma_200: float,
    in_top_momentum: bool,
    rsi_2: float,
    close_range_pos: float,
    rsi_threshold: float = 15.0,
    close_range_threshold: float = 0.10,
) -> Tuple[bool, str]:
    """
    Evaluate all four entry rules for a single stock on a completed daily bar:
      1. Close > 200-day MA
      2. In top 20% by 6-1M momentum
      3. RSI(2) < 15
      4. Close within bottom 10% of day's high-low range
    Returns (is_entry, reason_string).
    """
    if np.isnan(close) or np.isnan(sma_200) or np.isnan(rsi_2) or np.isnan(close_range_pos):
        return False, "Insufficient indicator history"

    above_ma = close > sma_200
    low_rsi = rsi_2 < rsi_threshold
    near_low = close_range_pos <= close_range_threshold

    if above_ma and in_top_momentum and low_rsi and near_low:
        pct_ma = ((close / sma_200) - 1.0) * 100.0
        return (
            True,
            f"Close ${close:.2f} > SMA200 (${sma_200:.2f}, +{pct_ma:.1f}%) | "
            f"Top 20% 6-1M Mom | RSI(2)={rsi_2:.1f} (<{rsi_threshold:.0f}) | "
            f"RangePos={close_range_pos * 100:.1f}% (<={close_range_threshold * 100:.0f}%)",
        )

    reasons = []
    if not above_ma:
        reasons.append("Below 200-MA")
    if not in_top_momentum:
        reasons.append("Outside top 20% momentum")
    if not low_rsi:
        reasons.append(f"RSI(2) {rsi_2:.1f} >= {rsi_threshold}")
    if not near_low:
        reasons.append(f"Close range {close_range_pos * 100:.1f}% > {close_range_threshold * 100:.0f}%")
    return False, "; ".join(reasons)


def check_exit_signal(
    close: float,
    prior_high: float,
    days_held: int,
    max_hold_days: int = 20,
    exit_above_prior_high: bool = True,
) -> Tuple[bool, str]:
    """
    Evaluate exit rules at the daily close for a currently held position:
      1. First close above the prior trading day's high -> exit at next open.
      2. Held for `max_hold_days` (20 trading days, counting entry day as day 1) -> exit at next open (day 21 open).
    Returns (should_exit, reason_string).
    """
    if exit_above_prior_high and not np.isnan(prior_high) and close > prior_high:
        return (
            True,
            f"Bounce Exit: Close ${close:.2f} > Prior Day High ${prior_high:.2f} (Day {days_held}/{max_hold_days})",
        )
    if days_held >= max_hold_days:
        return (
            True,
            f"Time Exit: Reached max holding period of {max_hold_days} trading days (held {days_held} days)",
        )
    return False, f"Hold (Day {days_held}/{max_hold_days}, Close ${close:.2f} <= Prior High ${prior_high:.2f})"
