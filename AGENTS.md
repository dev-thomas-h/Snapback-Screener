# AGENTS.md — Operational Guide & Rules for AI Agents

This file defines the architecture, operational rules, safety invariants, and session-to-session workflows for AI coding agents working in the **Momentum Leaders Snapback Screener** repository.

---

## 1. Mandatory Workflow Rules

### A. Do NOT Push to GitHub Automatically
- **NEVER run `git push`** after making code, configuration, or documentation changes unless the user explicitly instructs you to push in that specific turn.
- You may stage and commit changes locally (`git add` / `git commit`) when requested, but pushing to any remote repository is strictly manual/user-approved.
- Never stage or commit `.env`, `.venv/`, `frontend/node_modules/`, `KILL_SWITCH`, or runtime SQLite databases (`data/*.db`).

### B. Synchronize Documentation After Every Change
- **Every code or configuration change MUST be accompanied by synchronized documentation updates** before you complete your turn:
  1. **[`README.md`](file:///Users/thorgy17/Snapback%20Screener/README.md)**: Keep the "Strategy Rules & Resolved Ambiguities" table, CLI usage examples, setup instructions, and architecture notes in sync with the codebase.
  2. **[`config.yaml`](file:///Users/thorgy17/Snapback%20Screener/config.yaml) & [`app/config.py`](file:///Users/thorgy17/Snapback%20Screener/app/config.py)**: Keep inline YAML comments and `DEFAULT_CONFIG` synchronized whenever strategy, backtest, or risk parameters are added, renamed, or re-defaulted.
  3. **[`AGENTS.md`](file:///Users/thorgy17/Snapback%20Screener/AGENTS.md)**: Update this file whenever new modules, API endpoints, frontend views, or workflow conventions are introduced.

---

## 2. Non-Negotiable Trading Safety & Strategy Invariants

1. **Paper-Only by Construction**:
   - Never remove, bypass, or weaken `enforce_paper_only()` in [`app/config.py`](file:///Users/thorgy17/Snapback%20Screener/app/config.py).
   - `TradingClient` in [`app/trader.py`](file:///Users/thorgy17/Snapback%20Screener/app/trader.py) must always be instantiated with `paper=True` (`https://paper-api.alpaca.markets`).
   - Live API endpoints (`api.alpaca.markets` without `paper-api`) and live key prefixes (`AK...`) must always raise `PaperTradingSafetyError`.
2. **Zero Lookahead Bias**:
   - Both [`app/screener.py`](file:///Users/thorgy17/Snapback%20Screener/app/screener.py) and [`app/backtest.py`](file:///Users/thorgy17/Snapback%20Screener/app/backtest.py) compute signals **after the market close** on Day $t$ using completed daily bars and execute fills at **Day $t+1$'s open** (`Market-on-Open` / `TimeInForce.OPG`).
3. **Hard Portfolio & Risk Caps**:
   - Maximum **10 concurrent positions** (`max_positions: 10`).
   - Maximum **2 new entries per day** (`max_new_entries_per_day: 2`), ranked by highest 6-1M momentum.
   - Maximum **2.0x gross leverage** (`max_gross_leverage: 2.0`).
   - Preserve the `KILL_SWITCH` file/button handler and the **5% daily loss guard** (`daily_loss_limit_pct: 0.05`).

---

## 3. Repository Architecture & Tech Stack

```text
Snapback Screener/
├── AGENTS.md                 # Agent instructions & session-to-session rules
├── README.md                 # User & developer documentation (keep synchronized!)
├── config.yaml               # Strategy, backtest, and risk parameters
├── requirements.txt          # Python dependencies (installed in ./.venv)
├── pytest.ini                # Pytest configuration
├── app/
│   ├── config.py             # Config loader, logger, kill switch, paper-only guard
│   ├── db.py                 # SQLite persistence (signals, positions, orders, backtest_runs, risk_events)
│   ├── universe.py           # Wikipedia S&P 500 fetcher + weekly cache + yfinance/Alpaca OHLCV loader
│   ├── indicators.py         # SMA(200), 6-1M momentum, Wilder's RSI(2), Close-in-Range, entry/exit checks
│   ├── screener.py           # Daily after-close screener + Momentum Leaders Radar (CLI & service)
│   ├── backtest.py           # Event-driven 2008–present simulator + SPY & No-Momentum benchmarks
│   ├── trader.py             # Alpaca paper trading loop + position reconciliation + --dry-run mode
│   ├── api.py                # FastAPI REST backend & static SPA host
│   └── dashboard.py          # Unified dashboard launcher (Uvicorn FastAPI server + Streamlit fallback)
├── frontend/                 # React 18 + TypeScript + Vite 5 + Tailwind CSS
│   ├── src/
│   │   ├── App.tsx           # Light-toned glassmorphic multi-tab dashboard
│   │   ├── types.ts          # Shared TypeScript API payload interfaces
│   │   ├── index.css         # Translucent frosted glass & pearlescent surface utilities
│   │   └── components/
│   │       ├── EquityChart.tsx
│   │       └── reactbits/    # Custom ReactBits components (AuroraGlassBackground, SplitText,
│   │                         # BlurText, CountUp, SpotlightCard, TiltCard, StarBorder,
│   │                         # ShinyText, AnimatedList, Magnet, FloatingGlassDock)
└── tests/
    └── test_strategy.py      # Unit tests for indicators, signals, portfolio caps, and paper guard
```

---

## 4. UI & Aesthetic Guidelines

- **Light-Toned Translucent Glassmorphism**:
  - Maintain the bright alabaster/porcelain canvas (`#F2F6FC`) with soft pastel aurora lighting and multi-layered frosted glass cards (`glass-panel`, `backdrop-blur-2xl`, `bg-white/65`, crisp `border-white/85`, and subtle inner specular highlights).
  - Do not revert the UI to dark mode or flat opaque cards.
- **ReactBits Component Usage**:
  - Use the components in [`frontend/src/components/reactbits/`](file:///Users/thorgy17/Snapback%20Screener/frontend/src/components/reactbits) (`SpotlightCard`, `TiltCard`, `CountUp`, `StarBorder`, `ShinyText`, `SplitText`, `BlurText`, `AnimatedList`, `Magnet`, `FloatingGlassDock`) when adding new dashboard sections or cards.
- **Frontend Build Synchronization**:
  - [`app/api.py`](file:///Users/thorgy17/Snapback%20Screener/app/api.py) serves the production bundle from `frontend/dist`. Whenever you modify any file inside `frontend/src/`, run `cd frontend && npm run build` so `frontend/dist` stays up to date.

---

## 5. Standard Commands & Pre-Completion Checklist

Always use the local virtual environment (`./.venv/bin/python` and `./.venv/bin/pytest`):

1. **Run Unit Tests**:
   ```bash
   ./.venv/bin/pytest tests/ -v
   ```
2. **Test CLI Deliverables**:
   ```bash
   ./.venv/bin/python -m app.screener --limit 60
   ./.venv/bin/python -m app.backtest --limit 45
   ./.venv/bin/python -m app.trader --dry-run
   ```
3. **Rebuild Frontend (if UI changed)**:
   ```bash
   cd frontend && npm run build
   ```
4. **Launch Dashboard Server**:
   ```bash
   ./.venv/bin/python -m app.dashboard
   ```
5. **Final Check Before Ending Turn**:
   - Did all unit tests pass?
   - Are `README.md`, `config.yaml`, and `AGENTS.md` synchronized with your changes?
   - Confirm you have **not** executed `git push`.
