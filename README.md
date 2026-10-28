# Momentum Leaders Snapback — Screener, Backtester & Alpaca Paper Trader

An end-to-end Python & React application implementing the **"Momentum Leaders Snapback"** stock strategy (based on the Oct 23, 2026 AlphaInsider post) with an audited SQLite signal screener, a zero-lookahead event-driven backtester, a paper-only Alpaca execution engine, and a **light-toned, translucent glassmorphic dashboard** built with **ReactBits** components.

---

## 1. Strategy Rules & Resolved Ambiguities (`config.yaml`)

The core thesis is simple: **buy the S&P 500's strongest momentum leaders when they experience a sharp, short-term pullback, and sell on the very first bounce.**

Every open detail in the original post is explicitly parameterized in [`config.yaml`](file:///Users/thorgy17/Snapback%20Screener/config.yaml):

| Strategy Rule / Ambiguity | Default in `config.yaml` | Exact Definition & Implementation |
| :--- | :--- | :--- |
| **Universe** | `universe: "SP500"` (`universe_refresh_days: 7`) | Current S&P 500 constituents fetched from Wikipedia (`List_of_S&P_500_companies`), cached locally at `data/sp500_constituents.json`, and refreshed weekly. |
| **Trend Filter (Above 200-MA)** | `sma_period: 200` | Stock's daily close must be strictly above its 200-trading-day simple moving average (`Close > SMA(200)`). |
| **6-1 Month Momentum (Top 20%)** | `momentum_lookback_start: 126`, `momentum_lookback_end: 21`, `momentum_top_pct: 0.20` | Standard academic 6-1M momentum: total return from 126 trading days ago (~6 months) to 21 trading days ago (~1 month), skipping the most recent month. Ranked cross-sectionally across the S&P 500; only the top 20% qualify. |
| **Wilder's RSI(2) < 15** | `rsi_period: 2`, `rsi_entry_threshold: 15.0` | Wilder's recursive smoothing ($\alpha = 1/2$) over a 2-day lookback. Stock must close with `RSI(2) < 15.0`. |
| **"Closes Near the Day's Low"** | `close_range_threshold: 0.10` | Daily close must be within the bottom 10% of the day's high-low range: $\frac{\text{Close} - \text{Low}}{\text{High} - \text{Low}} \le 0.10$. |
| **Exit #1: First Close Above Prior Day's High** | `exit_above_prior_high: true` | On each day a position is held, if `Close[t] > High[t-1]`, an exit order is queued to sell at the **next trading day's open** (`Open[t+1]`). |
| **Exit #2: 20-Trading-Day Max Hold** | `max_hold_days: 20` | Holding count starts on the entry day (`Day 1`). If a position is still held at the close of `Day 20`, it is sold at the open of `Day 21`. |
| **More Than 2 Entry Signals in a Day** | `max_new_entries_per_day: 2`, `max_positions: 10` | Valid entry signals are ranked by `6-1M momentum` descending (highest momentum first). The top 2 are taken (up to the 10-position portfolio cap); remaining signals are marked `QUEUE_CAPPED` and re-evaluated on the next day's close. |
| **Position Sizing & Leverage Cap** | `target_gross_leverage: 2.0`, `max_gross_leverage: 2.0` | Equal-weight sizing up to 2.0x gross exposure across up to 10 positions, with a hard ceiling so total gross exposure never exceeds 2.0x account equity. |
| **Order Timing (Zero Lookahead Bias)** | Market-on-Open (`TimeInForce.OPG`) | Signals are computed **after the market close** on Day $t$ using completed daily bars. Orders execute at **Day $t+1$'s open** in both the backtester and paper trader. |

---

## 2. Data Sources & Known Limitations

- **Historical Backtest Data (`yfinance`)**: Alpaca's free market data tier does not cover full historical bars back to 2008. Therefore, `app/backtest.py` and standalone screening use `yfinance` daily adjusted OHLCV bars cached locally in `data/cache/`.
- **Live / Paper Trading (`alpaca-py`)**: `app/trader.py` uses the official `alpaca-py` SDK (`TradingClient(api_key, secret_key, paper=True)`), which routes strictly to `https://paper-api.alpaca.markets`.
- **Survivorship Bias Limitation**: Using the current S&P 500 constituent list for a 2008–present backtest introduces survivorship bias (companies that were in the S&P 500 in 2008 but later went bankrupt or were removed are excluded, while modern winners like NVDA/META/TSLA are included prior to their index inclusion dates). Treat headline backtest returns with healthy skepticism.

---

## 3. Setup & Installation

### Python Backend & CLI Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Creating Alpaca Paper API Keys
1. Sign in to [https://app.alpaca.markets](https://app.alpaca.markets).
2. Switch the account selector in the top-left corner to **Paper Trading** (Ensure your key prefix starts with `PK...`, never `AK...`).
3. Navigate to **API Keys** → **Generate New Key**.
4. Copy `.env.example` to `.env` and paste your Paper keys:
   ```bash
   cp .env.example .env
   ```
   ```ini
   ALPACA_API_KEY=PKxxxxxxxxxxxxxxxxxx
   ALPACA_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ALPACA_PAPER=true
   ALPACA_BASE_URL=https://paper-api.alpaca.markets
   ```

---

## 4. Running the Application & CLI Deliverables

### 1. Run Daily Signal Screener
```bash
./.venv/bin/python -m app.screener
```
Screens the S&P 500 universe on the latest completed daily bar, outputs ranked Entry signals, Exit signals, and the Momentum Leaders Radar, and logs everything to SQLite (`data/snapback.db`).

### 2. Run Event-Driven Backtester (2008–Present)
```bash
./.venv/bin/python -m app.backtest
```
Runs the zero-lookahead daily simulation (including 5 bps slippage and margin interest), compares performance against **SPY Buy-and-Hold** and **Plain Dip-Buying (No Momentum Filter)**, prints the AlphaInsider claim validation report and yearly returns table, and saves the equity curve chart to `data/equity_curve.png`.

### 3. Run Alpaca Paper Trader (Dry-Run Mode)
```bash
./.venv/bin/python -m app.trader --dry-run
```
Connects to your Alpaca Paper account (or runs in simulated $100,000 Paper Preview mode if `.env` keys are not set yet), reconciles positions, checks the Kill Switch and 5% Daily Loss Guard, and prints the exact Market-on-Open (`TimeInForce.OPG`) orders it would place without submitting them.

### 4. Launch the Glassmorphic ReactBits Dashboard
```bash
./.venv/bin/python -m app.dashboard
```
Opens the full-stack **Light-Toned Glassmorphic React + ReactBits Dashboard** at `http://127.0.0.1:8000`.
*(Note: `streamlit run app/dashboard.py` is also supported if you prefer the Streamlit view.)*

### 5. Run Unit Tests
```bash
./.venv/bin/pytest tests/ -v
```
