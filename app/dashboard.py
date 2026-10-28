from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _is_running_in_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


def run_streamlit_dashboard() -> None:
    import pandas as pd
    import streamlit as st
    from app.api import api_get_overview
    from app.backtest import run_backtest
    from app.config import set_kill_switch
    from app.screener import run_daily_screener
    from app.trader import run_trading_cycle

    st.set_page_config(
        page_title="Momentum Leaders Snapback — Glass Dashboard",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(135deg, #F4F7FB 0%, #E9F0FA 50%, #F0F6F6 100%);
            color: #0F172A;
        }
        div[data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.72);
            backdrop-filter: blur(18px);
            border: 1px solid rgba(255, 255, 255, 0.9);
            border-radius: 16px;
            padding: 16px;
            box-shadow: 0 10px 30px -10px rgba(15, 23, 42, 0.06);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    data = api_get_overview()
    acct = data["account"]
    sigs = data["signals"]
    bt = data["backtest"]
    ks = data["kill_switch_active"]

    st.title("Momentum Leaders Snapback — Paper Trading & Screener")
    st.caption(
        f"Paper-Only Enforced | Signal Date: {sigs.get('signal_date') or 'N/A'} | "
        f"Mode: {acct['mode']}"
    )

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Paper Equity", f"${acct['equity']:,.2f}", f"{acct['daily_pnl_pct']:+.2f}% today")
    col2.metric("Gross Exposure", f"${acct['gross_exposure']:,.2f}", f"{acct['gross_leverage']:.2f}x / 2.00x Cap")
    col3.metric("Open Positions", f"{len(acct['positions'])} / 10", f"Max 2 new/day")
    col4.metric("Today's Entry Signals", f"{len(sigs['entry'])}", f"{len(sigs['exit'])} exits")
    col5.metric("Kill Switch", "ACTIVE (HALTED)" if ks else "ARMED (NORMAL)")

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Run Daily Screener"):
        run_daily_screener(universe_limit=60, persist=True)
        st.rerun()
    if b2.button("Run Dry-Run Order Preview"):
        run_trading_cycle(dry_run=True)
        st.rerun()
    if b3.button("Re-Run Backtest"):
        run_backtest(start_date="2008-01-01", universe_limit=45, persist=True)
        st.rerun()
    if b4.button("Toggle Kill Switch"):
        set_kill_switch(not ks, reason="Streamlit dashboard button")
        st.rerun()

    st.subheader("Current Paper Positions")
    if acct["positions"]:
        st.dataframe(pd.DataFrame(acct["positions"]), use_container_width=True)
    else:
        st.info("No open positions.")

    st.subheader("Today's Actionable Entry & Exit Signals")
    if sigs["entry"] or sigs["exit"]:
        st.dataframe(pd.DataFrame(sigs["entry"] + sigs["exit"]), use_container_width=True)
    else:
        st.info("No exact RSI(2) < 15 entry signals today. Inspect the Momentum Leaders Radar below.")

    st.subheader("Momentum Leaders Radar (Top 20% 6-1M Momentum + Above 200-MA)")
    if sigs["radar"]:
        st.dataframe(pd.DataFrame(sigs["radar"]), use_container_width=True)

    if bt:
        st.subheader("Backtest Summary & Equity Curve")
        m = bt["metrics"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Strategy CAGR", f"{m['cagr_pct']:.2f}%", f"Total: {m['total_return_pct']:+.1f}%")
        m2.metric("Sharpe Ratio", f"{m['sharpe_ratio']:.2f}", f"Win Rate: {m['win_rate_pct']:.1f}%")
        m3.metric("Max Drawdown", f"{m['max_drawdown_pct']:.2f}%", f"SPY DD: {m['spy_max_drawdown_pct']:.1f}%")
        m4.metric("Years Beating SPY", f"{m['years_beating_spy']} / {m['total_calendar_years']}", f"{m['total_trades']} trades")

        chart_file = ROOT_DIR / "data" / "equity_curve.png"
        if chart_file.exists():
            st.image(str(chart_file), caption="Momentum Leaders Snapback vs. SPY Equity Curve")


def main() -> None:
    if _is_running_in_streamlit():
        run_streamlit_dashboard()
    else:
        import uvicorn
        print("Starting Momentum Leaders Snapback Glassmorphic ReactBits Server on http://127.0.0.1:8000 ...")
        uvicorn.run("app.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
