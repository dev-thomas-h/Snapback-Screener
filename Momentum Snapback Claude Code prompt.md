# Claude Code Prompt: Build the "Momentum Leaders Snapback" Paper-Trading App

Copy everything below the line into Claude Code as a single prompt.

---

## Goal

Build a Python app that implements the **"Momentum Leaders Snapback"** stock strategy (from an Instagram post by AlphaInsider, Oct 23, 2026) and paper-trades it on an **Alpaca paper trading account** so I can test it with fake money before ever considering real money.

The app must do three things:
1. **Screen daily** for new trade signals using the exact rules below.
2. **Backtest** the strategy so I can see whether it actually works, including costs, leverage, and drawdowns.
3. **Paper-trade it live** through Alpaca (paper account only), with a dashboard showing positions, signals, and P&L.

## The strategy — exact rules from the post

The idea: buy the S&P 500's strongest stocks when they stumble, and sell on the first bounce.

1. **Universe:** S&P 500 stocks only.
2. **Trend filter:** Only stocks trading **above their 200-day moving average**.
3. **Momentum filter:** Only the **top 20% by 6-1 month momentum** (see "Ambiguities" — define this precisely and make it configurable).
4. **Entry trigger:** Buy when **RSI(2) drops below 15** AND the stock **closes near the day's low**.
5. **Exit:** Sell on the **first close above the prior day's high**, OR after **20 trading days** — whichever comes first.
6. **Portfolio limits:** Max **10 positions** at once, at most **2 new entries per day**.

**Reported backtest (from the post — hypothetical, Jan 2008 to Oct 19, 2026, trading costs included):** +22,289% total, $1,000 → $223,890 vs SPY $7,440, beat the S&P in 13 of 19 years, max drawdown **-38%**, up to **2x leverage**, **no stop-loss**. The post itself says a realistic expectation is closer to **27% a year**, not the headline number. Plain dip-buying *without* the momentum filter made only +316% and lost to SPY's +644% — the momentum filter is the whole point.

Treat the headline number with skepticism. The backtester you build must be able to reproduce (or refute) these claims.

## Ambiguities — resolve these as configurable parameters, don't silently guess

The post leaves details open. Implement each as a named parameter in a `config.yaml` with the default below, and list every assumption in the README:

- **"Closes near the day's low":** default = close within the bottom 10% of the day's high-low range.
- **"6-1 month momentum":** default = total return from ~126 trading days ago to ~21 trading days ago (i.e. 6-month return skipping the most recent month, the standard academic definition).
- **RSI(2):** Wilder's RSI with a 2-period lookback.
- **"Prior day's high" for the exit:** on each day a position is held, if the daily close is above the previous trading day's high, sell at the next open.
- **20-trading-day max hold:** count starts on the entry day; sell at the open of day 21 if still held.
- **More than 2 entry signals in a day:** rank by momentum (highest first) and take the top 2; queue the rest for the next day only if the signal is still valid.
- **Position sizing:** equal-weight across positions. With up to 10 positions and up to 2x leverage, target gross exposure up to 2x account equity; size each new position as `(target exposure) / (current positions + new entries)`. Never exceed 2x gross exposure.
- **Order timing (critical — no lookahead bias):** signals are computed **after the market close** using that day's completed bar. Orders are placed for the **next trading day's open**. The backtester must use the exact same timing.

## App features

### 1. Universe & data
- Fetch and maintain the current S&P 500 constituent list (e.g. from Wikipedia), cached locally and refreshed weekly. Handle tickers entering/leaving the index.
- Daily OHLCV bars for the universe. Use Alpaca market data for live/paper trading. For the long backtest (2008+), Alpaca's free data history is too short — use `yfinance` (or Stooq) for historical bars in the backtester, and document this split clearly. Note survivorship bias as a known limitation in the README.

### 2. Signal screener (`app/screener.py`)
- Runs once per day after close. Outputs a ranked list of entry signals and exit signals, with the reason for each (filter values included: price vs 200-day MA, momentum percentile, RSI(2), close position in day's range).
- Save each day's signals to a local database (SQLite) so results are auditable.

### 3. Backtester (`app/backtest.py`)
- Event-driven, no lookahead: same signal logic and next-open execution as live trading.
- Model realistic costs: Alpaca equities are commission-free, but model slippage (default 5 bps per trade, configurable) and margin/borrow cost on leveraged exposure.
- Report: CAGR, total return, Sharpe, max drawdown, win rate, average holding days, number of trades, yearly returns table, and equity curve chart. Benchmark everything against buy-and-hold SPY over the same period.
- Include a validation mode that runs the full 2008–present backtest and prints how the results compare to the post's claims (+22,289%, -38% max drawdown, 13 of 19 winning years).

### 4. Paper trading (`app/trader.py`)
- Use the official `alpaca-py` SDK. Create the client with `TradingClient(api_key, secret_key, paper=True)` — this routes to `paper-api.alpaca.markets`.
- Daily loop: fetch account/positions, reconcile with the app's own state, compute signals, place market-on-open orders for entries and exits, respect the 10-position and 2-per-day limits, log every order with its reason.
- Support a `--dry-run` flag that prints what it *would* do without placing orders.

### 5. Dashboard
- Simple Streamlit (or FastAPI + plain HTML) dashboard: current positions and P&L, today's signals, equity curve, recent trades, and the latest backtest summary. Keep it local-only.

### 6. Risk controls (mandatory)
- The app must be **paper-only by construction**: a config value `ALPACA_PAPER=true` must be enforced in code; the app refuses to start if `paper=False` or if live API keys/endpoints are detected.
- API keys only from environment variables or a `.env` file — never hardcode, never log them. Add `.env` to `.gitignore`.
- Hard caps: max 2x gross leverage, max 10 positions, max 2 new entries/day.
- A **kill switch**: a `KILL_SWITCH` file or dashboard button that immediately cancels open orders and stops new entries.
- A daily loss guard: if the account loses more than 5% in a day, stop trading for the rest of the day and alert in the dashboard log.
- Every action is logged with timestamps to a local file.

## Tech stack

- Python 3.11+, `alpaca-py`, `pandas`, `numpy`, `yfinance` (backtest data only), `streamlit`, `pytest`.
- `config.yaml` for all strategy parameters and limits. `README.md` with setup steps, including how to create Alpaca paper API keys (alpaca.markets → switch to Paper view → generate keys) and how to run the backtest, the screener, and the paper trader.
- Project layout:
  ```
  momentum-snapback/
  ├── config.yaml
  ├── app/
  │   ├── universe.py      # S&P 500 constituents
  │   ├── indicators.py    # 200-day MA, momentum, RSI(2)
  │   ├── screener.py      # daily signals
  │   ├── backtest.py      # backtesting engine
  │   ├── trader.py        # Alpaca paper trading loop
  │   ├── dashboard.py     # Streamlit dashboard
  │   └── db.py            # SQLite trade/signal log
  ├── tests/
  └── README.md
  ```

## Deliverables & acceptance criteria

1. `python -m app.backtest` runs the full backtest and prints the metrics table + saves the equity curve chart.
2. `python -m app.screener` prints today's entry/exit signals (or "no signals").
3. `python -m app.trader --dry-run` connects to the Alpaca **paper** account, prints account equity/buying power and the orders it would place — without placing any.
4. `streamlit run app/dashboard.py` shows positions, signals, and P&L.
5. Unit tests for the signal logic: RSI(2) calculation, momentum ranking (top 20%), entry trigger, both exit rules, and the 10-position / 2-per-day limits.
6. README documents every assumption from the "Ambiguities" section and how to change each parameter.

## Order of work

1. Strategy core (`indicators.py`, `screener.py`) + unit tests — get the rules right first.
2. Backtester + validation run against the post's claims.
3. Alpaca paper client + dry-run mode.
4. Daily trading loop with reconciliation and logging.
5. Dashboard.
6. README and final cleanup.

## Ground rules for you (Claude Code)

- Verify the `alpaca-py` SDK usage against the current Alpaca docs as you build; don't rely on my memory of the API.
- Never write code that can place a live (real-money) order. Paper only.
- If a rule from the post is ambiguous, implement the configurable parameter above and say so in the README — don't silently pick something else.
- Keep the code simple and readable; I'm not a professional quant and I need to understand what it's doing.
