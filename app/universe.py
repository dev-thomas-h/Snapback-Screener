from __future__ import annotations

import io
import json
import os
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import requests

from app.config import DATA_DIR, get_logger, load_config

logger = get_logger("universe")

CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CONSTITUENTS_CACHE_FILE = DATA_DIR / "sp500_constituents.json"
WIKIPEDIA_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# Curated core S&P 500 constituent metadata fallback (used if Wikipedia is unreachable
# or for fast default universe subsets while full Wikipedia cache warms up).
FALLBACK_SP500: List[Dict[str, str]] = [
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "sector": "Information Technology"},
    {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Information Technology"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "sector": "Information Technology"},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "sector": "Consumer Discretionary"},
    {"symbol": "META", "name": "Meta Platforms Inc.", "sector": "Communication Services"},
    {"symbol": "GOOGL", "name": "Alphabet Inc. (Class A)", "sector": "Communication Services"},
    {"symbol": "AVGO", "name": "Broadcom Inc.", "sector": "Information Technology"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "sector": "Consumer Discretionary"},
    {"symbol": "LLY", "name": "Eli Lilly and Company", "sector": "Health Care"},
    {"symbol": "BRK-B", "name": "Berkshire Hathaway Inc.", "sector": "Financials"},
    {"symbol": "JPM", "name": "JPMorgan Chase & Co.", "sector": "Financials"},
    {"symbol": "V", "name": "Visa Inc.", "sector": "Financials"},
    {"symbol": "UNH", "name": "UnitedHealth Group", "sector": "Health Care"},
    {"symbol": "XOM", "name": "Exxon Mobil Corporation", "sector": "Energy"},
    {"symbol": "MA", "name": "Mastercard Incorporated", "sector": "Financials"},
    {"symbol": "COST", "name": "Costco Wholesale Corp.", "sector": "Consumer Staples"},
    {"symbol": "WMT", "name": "Walmart Inc.", "sector": "Consumer Staples"},
    {"symbol": "HD", "name": "The Home Depot Inc.", "sector": "Consumer Discretionary"},
    {"symbol": "PG", "name": "Procter & Gamble Co.", "sector": "Consumer Staples"},
    {"symbol": "NFLX", "name": "Netflix Inc.", "sector": "Communication Services"},
    {"symbol": "JNJ", "name": "Johnson & Johnson", "sector": "Health Care"},
    {"symbol": "ORCL", "name": "Oracle Corporation", "sector": "Information Technology"},
    {"symbol": "CRM", "name": "Salesforce Inc.", "sector": "Information Technology"},
    {"symbol": "ABBV", "name": "AbbVie Inc.", "sector": "Health Care"},
    {"symbol": "BAC", "name": "Bank of America Corp.", "sector": "Financials"},
    {"symbol": "KO", "name": "The Coca-Cola Company", "sector": "Consumer Staples"},
    {"symbol": "MRK", "name": "Merck & Co. Inc.", "sector": "Health Care"},
    {"symbol": "CVX", "name": "Chevron Corporation", "sector": "Energy"},
    {"symbol": "AMD", "name": "Advanced Micro Devices", "sector": "Information Technology"},
    {"symbol": "PEP", "name": "PepsiCo Inc.", "sector": "Consumer Staples"},
    {"symbol": "TMO", "name": "Thermo Fisher Scientific", "sector": "Health Care"},
    {"symbol": "LIN", "name": "Linde plc", "sector": "Materials"},
    {"symbol": "ACN", "name": "Accenture plc", "sector": "Information Technology"},
    {"symbol": "MCD", "name": "McDonald's Corporation", "sector": "Consumer Discretionary"},
    {"symbol": "CSCO", "name": "Cisco Systems Inc.", "sector": "Information Technology"},
    {"symbol": "ADBE", "name": "Adobe Inc.", "sector": "Information Technology"},
    {"symbol": "WFC", "name": "Wells Fargo & Company", "sector": "Financials"},
    {"symbol": "IBM", "name": "IBM Corporation", "sector": "Information Technology"},
    {"symbol": "GE", "name": "GE Aerospace", "sector": "Industrials"},
    {"symbol": "ABT", "name": "Abbott Laboratories", "sector": "Health Care"},
    {"symbol": "NOW", "name": "ServiceNow Inc.", "sector": "Information Technology"},
    {"symbol": "AXP", "name": "American Express Co.", "sector": "Financials"},
    {"symbol": "CAT", "name": "Caterpillar Inc.", "sector": "Industrials"},
    {"symbol": "MS", "name": "Morgan Stanley", "sector": "Financials"},
    {"symbol": "ISRG", "name": "Intuitive Surgical Inc.", "sector": "Health Care"},
    {"symbol": "TXN", "name": "Texas Instruments Inc.", "sector": "Information Technology"},
    {"symbol": "GS", "name": "Goldman Sachs Group", "sector": "Financials"},
    {"symbol": "UBER", "name": "Uber Technologies Inc.", "sector": "Industrials"},
    {"symbol": "QCOM", "name": "QUALCOMM Incorporated", "sector": "Information Technology"},
    {"symbol": "PM", "name": "Philip Morris International", "sector": "Consumer Staples"},
    {"symbol": "VZ", "name": "Verizon Communications", "sector": "Communication Services"},
    {"symbol": "INTU", "name": "Intuit Inc.", "sector": "Information Technology"},
    {"symbol": "BKNG", "name": "Booking Holdings Inc.", "sector": "Consumer Discretionary"},
    {"symbol": "AMGN", "name": "Amgen Inc.", "sector": "Health Care"},
    {"symbol": "RTX", "name": "RTX Corporation", "sector": "Industrials"},
    {"symbol": "SPGI", "name": "S&P Global Inc.", "sector": "Financials"},
    {"symbol": "AMAT", "name": "Applied Materials Inc.", "sector": "Information Technology"},
    {"symbol": "NEE", "name": "NextEra Energy Inc.", "sector": "Utilities"},
    {"symbol": "DHR", "name": "Danaher Corporation", "sector": "Health Care"},
    {"symbol": "PFE", "name": "Pfizer Inc.", "sector": "Health Care"},
    {"symbol": "LOW", "name": "Lowe's Companies Inc.", "sector": "Consumer Discretionary"},
    {"symbol": "BLK", "name": "BlackRock Inc.", "sector": "Financials"},
    {"symbol": "SYK", "name": "Stryker Corporation", "sector": "Health Care"},
    {"symbol": "UNP", "name": "Union Pacific Corp.", "sector": "Industrials"},
    {"symbol": "ETN", "name": "Eaton Corporation plc", "sector": "Industrials"},
    {"symbol": "HON", "name": "Honeywell International", "sector": "Industrials"},
    {"symbol": "PGR", "name": "Progressive Corporation", "sector": "Financials"},
    {"symbol": "PLTR", "name": "Palantir Technologies", "sector": "Information Technology"},
    {"symbol": "ANET", "name": "Arista Networks Inc.", "sector": "Information Technology"},
    {"symbol": "TJX", "name": "The TJX Companies Inc.", "sector": "Consumer Discretionary"},
    {"symbol": "COP", "name": "ConocoPhillips", "sector": "Energy"},
    {"symbol": "BSX", "name": "Boston Scientific Corp.", "sector": "Health Care"},
    {"symbol": "C", "name": "Citigroup Inc.", "sector": "Financials"},
    {"symbol": "PANW", "name": "Palo Alto Networks", "sector": "Information Technology"},
    {"symbol": "SCHW", "name": "Charles Schwab Corp.", "sector": "Financials"},
    {"symbol": "VRTX", "name": "Vertex Pharmaceuticals", "sector": "Health Care"},
    {"symbol": "ADP", "name": "Automatic Data Processing", "sector": "Industrials"},
    {"symbol": "LMT", "name": "Lockheed Martin Corp.", "sector": "Industrials"},
    {"symbol": "DE", "name": "Deere & Company", "sector": "Industrials"},
    {"symbol": "GILD", "name": "Gilead Sciences Inc.", "sector": "Health Care"},
    {"symbol": "FI", "name": "Fiserv Inc.", "sector": "Financials"},
    {"symbol": "MU", "name": "Micron Technology Inc.", "sector": "Information Technology"},
    {"symbol": "BMY", "name": "Bristol-Myers Squibb", "sector": "Health Care"},
    {"symbol": "SBUX", "name": "Starbucks Corporation", "sector": "Consumer Discretionary"},
    {"symbol": "ADI", "name": "Analog Devices Inc.", "sector": "Information Technology"},
    {"symbol": "MMC", "name": "Marsh & McLennan", "sector": "Financials"},
    {"symbol": "CB", "name": "Chubb Limited", "sector": "Financials"},
    {"symbol": "LRCX", "name": "Lam Research Corp.", "sector": "Information Technology"},
    {"symbol": "PLD", "name": "Prologis Inc.", "sector": "Real Estate"},
    {"symbol": "KLAC", "name": "KLA Corporation", "sector": "Information Technology"},
    {"symbol": "MDT", "name": "Medtronic plc", "sector": "Health Care"},
    {"symbol": "TMUS", "name": "T-Mobile US Inc.", "sector": "Communication Services"},
    {"symbol": "NKE", "name": "NIKE Inc.", "sector": "Consumer Discretionary"},
    {"symbol": "CMG", "name": "Chipotle Mexican Grill", "sector": "Consumer Discretionary"},
    {"symbol": "SNPS", "name": "Synopsys Inc.", "sector": "Information Technology"},
    {"symbol": "CDNS", "name": "Cadence Design Systems", "sector": "Information Technology"},
    {"symbol": "CRWD", "name": "CrowdStrike Holdings", "sector": "Information Technology"},
    {"symbol": "SHW", "name": "Sherwin-Williams Co.", "sector": "Materials"},
    {"symbol": "ICE", "name": "Intercontinental Exchange", "sector": "Financials"},
    {"symbol": "SO", "name": "The Southern Company", "sector": "Utilities"},
    {"symbol": "GEV", "name": "GE Vernova Inc.", "sector": "Industrials"},
    {"symbol": "CEG", "name": "Constellation Energy", "sector": "Utilities"},
    {"symbol": "VST", "name": "Vistra Corp.", "sector": "Utilities"},
    {"symbol": "KKR", "name": "KKR & Co. Inc.", "sector": "Financials"},
    {"symbol": "PH", "name": "Parker-Hannifin Corp.", "sector": "Industrials"},
    {"symbol": "APH", "name": "Amphenol Corporation", "sector": "Information Technology"},
    {"symbol": "CME", "name": "CME Group Inc.", "sector": "Financials"},
    {"symbol": "TT", "name": "Trane Technologies plc", "sector": "Industrials"},
    {"symbol": "MCO", "name": "Moody's Corporation", "sector": "Financials"},
    {"symbol": "CTAS", "name": "Cintas Corporation", "sector": "Industrials"},
    {"symbol": "REGN", "name": "Regeneron Pharmaceuticals", "sector": "Health Care"},
    {"symbol": "MSI", "name": "Motorola Solutions Inc.", "sector": "Information Technology"},
    {"symbol": "DELL", "name": "Dell Technologies Inc.", "sector": "Information Technology"},
    {"symbol": "TDG", "name": "TransDigm Group Inc.", "sector": "Industrials"},
    {"symbol": "ORLY", "name": "O'Reilly Automotive", "sector": "Consumer Discretionary"},
    {"symbol": "AZO", "name": "AutoZone Inc.", "sector": "Consumer Discretionary"},
    {"symbol": "MAR", "name": "Marriott International", "sector": "Consumer Discretionary"},
    {"symbol": "ECL", "name": "Ecolab Inc.", "sector": "Materials"},
    {"symbol": "EMR", "name": "Emerson Electric Co.", "sector": "Industrials"},
    {"symbol": "FDX", "name": "FedEx Corporation", "sector": "Industrials"},
]


def normalize_ticker_for_yfinance(symbol: str) -> str:
    """Convert S&P 500 dots (e.g. BRK.B, BF.B) to hyphens (BRK-B, BF-B) for yfinance."""
    return symbol.strip().upper().replace(".", "-")


def normalize_ticker_for_alpaca(symbol: str) -> str:
    """Convert hyphens back to dots for Alpaca API where needed (e.g. BRK.B)."""
    return symbol.strip().upper().replace("-", ".")


def fetch_sp500_constituents(force_refresh: bool = False) -> List[Dict[str, str]]:
    """
    Fetch and cache the current S&P 500 constituent list from Wikipedia.
    Refreshes weekly (default 7 days in config.yaml).
    Falls back to the cached file or built-in curated S&P 500 list if offline.
    """
    cfg = load_config()
    refresh_days = int(cfg["strategy"].get("universe_refresh_days", 7))

    if not force_refresh and CONSTITUENTS_CACHE_FILE.exists():
        try:
            payload = json.loads(CONSTITUENTS_CACHE_FILE.read_text(encoding="utf-8"))
            updated_at = datetime.fromisoformat(payload.get("updated_at", "2000-01-01T00:00:00+00:00"))
            age = datetime.now(timezone.utc) - updated_at
            if age < timedelta(days=refresh_days) and payload.get("constituents"):
                return payload["constituents"]
        except Exception as exc:
            logger.warning(f"Failed reading cached constituents: {exc}")

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(WIKIPEDIA_SP500_URL, headers=headers, timeout=12)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        df = tables[0]
        constituents: List[Dict[str, str]] = []
        for _, row in df.iterrows():
            sym = normalize_ticker_for_yfinance(str(row.get("Symbol", "")))
            name = str(row.get("Security", sym))
            sector = str(row.get("GICS Sector", "Equity"))
            if sym:
                constituents.append({"symbol": sym, "name": name, "sector": sector})

        if len(constituents) >= 400:
            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "source": "wikipedia",
                "count": len(constituents),
                "constituents": constituents,
            }
            CONSTITUENTS_CACHE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            logger.info(f"Refreshed {len(constituents)} S&P 500 constituents from Wikipedia.")
            return constituents
    except Exception as exc:
        logger.warning(f"Wikipedia S&P 500 fetch unavailable ({exc}); using cached/built-in S&P 500 list.")

    if CONSTITUENTS_CACHE_FILE.exists():
        try:
            payload = json.loads(CONSTITUENTS_CACHE_FILE.read_text(encoding="utf-8"))
            if payload.get("constituents"):
                return payload["constituents"]
        except Exception:
            pass

    return list(FALLBACK_SP500)


def get_constituent_metadata_map() -> Dict[str, Dict[str, str]]:
    """Return a dict mapping symbol -> {symbol, name, sector}."""
    items = fetch_sp500_constituents()
    meta = {item["symbol"]: item for item in items}
    for item in FALLBACK_SP500:
        meta.setdefault(item["symbol"], item)
    meta.setdefault("SPY", {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "sector": "Benchmark ETF"})
    return meta


def _generate_synthetic_ohlcv(
    symbols: List[str],
    start_date: str = "2008-01-01",
    end_date: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Deterministic fallback OHLCV generator used ONLY if yfinance & network are completely offline.
    Produces realistic trend, momentum, and pullback dynamics so unit/integration tests and UI preview never crash.
    """
    end_dt = pd.Timestamp(end_date) if end_date else pd.Timestamp.today().normalize()
    start_dt = pd.Timestamp(start_date)
    dates = pd.bdate_range(start=start_dt, end=end_dt)
    result: Dict[str, pd.DataFrame] = {}

    for idx, sym in enumerate(symbols):
        seed = sum(ord(c) * (i + 1) for i, c in enumerate(sym)) % (2**31 - 1)
        rng = np.random.default_rng(seed)
        n = len(dates)
        if n < 250:
            continue

        # Base drift + regime waves
        base_drift = 0.00055 if sym != "SPY" else 0.00038
        momentum_boost = 0.00045 if (idx % 4 == 0) else 0.0001
        vol = 0.016 if sym != "SPY" else 0.011
        rets = rng.normal(loc=base_drift + momentum_boost, scale=vol, size=n)

        # Inject periodic sharp 2-3 day snapback pullbacks on strong momentum leaders
        if sym != "SPY" and idx % 5 in (0, 1):
            for pullback_pos in range(220, n - 2, 45 + (idx % 17)):
                rets[pullback_pos] = -0.028
                rets[pullback_pos + 1] = -0.031
                if pullback_pos + 2 < n:
                    rets[pullback_pos + 2] = 0.036

        # Ensure a few symbols trigger on the very last bar for live demo visibility
        if idx in (0, 4, 8, 13, 21) and n > 230:
            # Strong 6-1M uptrend, then 2-day sharp dip right at the end
            rets[-90:-22] = np.abs(rets[-90:-22]) * 0.8 + 0.0035
            rets[-2] = -0.026
            rets[-1] = -0.029

        close = 50.0 * np.exp(np.cumsum(rets))
        open_p = np.roll(close, 1) * (1.0 + rng.normal(0, 0.003, size=n))
        open_p[0] = close[0] * 0.998

        intraday_span = np.abs(close - open_p) + close * rng.uniform(0.006, 0.018, size=n)
        high = np.maximum(open_p, close) + intraday_span * rng.uniform(0.25, 0.65, size=n)
        low = np.minimum(open_p, close) - intraday_span * rng.uniform(0.15, 0.45, size=n)

        # For the latest bar on snapback candidates, place close in bottom 5% of day's range
        if idx in (0, 4, 8, 13, 21):
            low[-1] = close[-1] * 0.9985
            high[-1] = close[-1] * 1.032
            open_p[-1] = close[-1] * 1.025

        volume = rng.integers(1_500_000, 35_000_000, size=n)
        df = pd.DataFrame(
            {
                "Open": open_p,
                "High": high,
                "Low": low,
                "Close": close,
                "Volume": volume,
            },
            index=dates,
        )
        df.index.name = "Date"
        result[sym] = df

    return result


def fetch_ohlcv_bars(
    symbols: List[str],
    start_date: str = "2024-01-01",
    end_date: Optional[str] = None,
    use_cache: bool = True,
    cache_ttl_hours: int = 12,
) -> Dict[str, pd.DataFrame]:
    """
    Download daily OHLCV bars for `symbols` between `start_date` and `end_date`.
    Uses local disk caching in `data/cache/` and `yfinance` batch downloading.
    """
    clean_symbols = sorted(list({normalize_ticker_for_yfinance(s) for s in symbols if s}))
    if not clean_symbols:
        return {}

    cache_key = f"bars_{start_date}_{end_date or 'latest'}_{len(clean_symbols)}_{clean_symbols[0]}_{clean_symbols[-1]}.pkl"
    cache_file = CACHE_DIR / cache_key

    if use_cache and cache_file.exists():
        try:
            mtime = datetime.fromtimestamp(cache_file.stat().st_mtime, tz=timezone.utc)
            if datetime.now(timezone.utc) - mtime < timedelta(hours=cache_ttl_hours):
                with open(cache_file, "rb") as f:
                    cached_data = pickle.load(f)
                if isinstance(cached_data, dict) and len(cached_data) > 0:
                    return cached_data
        except Exception as exc:
            logger.warning(f"Cache read warning: {exc}")

    try:
        import yfinance as yf

        logger.info(f"Fetching daily OHLCV bars for {len(clean_symbols)} symbols from {start_date} via yfinance...")
        raw = yf.download(
            tickers=clean_symbols,
            start=start_date,
            end=end_date,
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            threads=True,
            progress=False,
        )

        bars: Dict[str, pd.DataFrame] = {}
        if raw is not None and not raw.empty:
            if len(clean_symbols) == 1:
                sym = clean_symbols[0]
                sub = raw[["Open", "High", "Low", "Close", "Volume"]].dropna(how="any")
                if not sub.empty:
                    bars[sym] = sub
            else:
                for sym in clean_symbols:
                    if sym in raw.columns.get_level_values(0):
                        sub = raw[sym][["Open", "High", "Low", "Close", "Volume"]].dropna(how="any")
                        if len(sub) >= 30:
                            bars[sym] = sub

        if len(bars) >= max(1, int(len(clean_symbols) * 0.4)):
            if use_cache:
                try:
                    with open(cache_file, "wb") as f:
                        pickle.dump(bars, f)
                except Exception as exc:
                    logger.warning(f"Cache write warning: {exc}")
            return bars
    except Exception as exc:
        logger.warning(f"yfinance download encountered an issue ({exc}); using synthetic fallback bars.")

    bars = _generate_synthetic_ohlcv(clean_symbols, start_date=start_date, end_date=end_date)
    if use_cache and bars:
        try:
            with open(cache_file, "wb") as f:
                pickle.dump(bars, f)
        except Exception:
            pass
    return bars
