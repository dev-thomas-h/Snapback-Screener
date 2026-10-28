from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.yaml"
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load .env from project root if present
load_dotenv(ROOT_DIR / ".env")


class PaperTradingSafetyError(RuntimeError):
    """Raised when any configuration or environment variable violates paper-only trading rules."""


DEFAULT_CONFIG: Dict[str, Any] = {
    "strategy": {
        "universe": "SP500",
        "universe_refresh_days": 7,
        "sma_period": 200,
        "momentum_lookback_start": 126,
        "momentum_lookback_end": 21,
        "momentum_top_pct": 0.20,
        "rsi_period": 2,
        "rsi_entry_threshold": 15.0,
        "close_range_threshold": 0.10,
        "exit_above_prior_high": True,
        "max_hold_days": 20,
        "max_positions": 10,
        "max_new_entries_per_day": 2,
        "target_gross_leverage": 2.0,
        "max_gross_leverage": 2.0,
        "radar_rsi_threshold": 45.0,
    },
    "backtest": {
        "start_date": "2008-01-01",
        "end_date": None,
        "initial_capital": 1000.0,
        "benchmark_symbol": "SPY",
        "slippage_bps": 5.0,
        "margin_interest_annual": 0.055,
        "default_universe_limit": 120,
    },
    "risk": {
        "alpaca_paper": True,
        "daily_loss_limit_pct": 0.05,
        "kill_switch_file": "KILL_SWITCH",
        "log_file": "data/snapback.log",
        "database_path": "data/snapback.db",
    },
}


def enforce_paper_only(
    config: Dict[str, Any] | None = None,
    paper_flag: bool = True,
    base_url: str | None = None,
    api_key: str | None = None,
) -> None:
    """
    Mandatory safety guard: verifies that the app is strictly configured for Alpaca PAPER trading.
    Raises PaperTradingSafetyError if any live trading configuration or key is detected.
    """
    if not paper_flag:
        raise PaperTradingSafetyError(
            "SAFETY BLOCK: paper=False detected. This application is strictly paper-only by construction."
        )

    if config is not None:
        risk_cfg = config.get("risk", {})
        if risk_cfg.get("alpaca_paper") is not True:
            raise PaperTradingSafetyError(
                "SAFETY BLOCK: config.yaml 'risk.alpaca_paper' must be set to true."
            )

    env_paper = os.getenv("ALPACA_PAPER", "true").strip().lower()
    if env_paper not in ("true", "1", "yes"):
        raise PaperTradingSafetyError(
            f"SAFETY BLOCK: Environment variable ALPACA_PAPER='{env_paper}' is not 'true'. Refusing to start."
        )

    resolved_url = (base_url or os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")).strip().lower()
    if "api.alpaca.markets" in resolved_url and "paper-api.alpaca.markets" not in resolved_url:
        raise PaperTradingSafetyError(
            f"SAFETY BLOCK: Live Alpaca endpoint '{resolved_url}' detected. Only paper-api.alpaca.markets is allowed."
        )

    resolved_key = (api_key or os.getenv("ALPACA_API_KEY", "")).strip()
    if resolved_key.upper().startswith("AK"):
        raise PaperTradingSafetyError(
            "SAFETY BLOCK: Live Alpaca API key prefix ('AK...') detected. Only Paper keys ('PK...') are permitted."
        )


def load_config(config_path: Path | str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Load config.yaml merged with safe defaults and validate paper-only risk rules."""
    path = Path(config_path)
    merged: Dict[str, Any] = {
        section: dict(values) for section, values in DEFAULT_CONFIG.items()
    }
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        for section, values in raw.items():
            if isinstance(values, dict) and section in merged:
                merged[section].update(values)
            else:
                merged[section] = values

    # Enforce hard safety caps
    strat = merged["strategy"]
    strat["max_positions"] = min(int(strat.get("max_positions", 10)), 10)
    strat["max_new_entries_per_day"] = min(int(strat.get("max_new_entries_per_day", 2)), 2)
    strat["max_gross_leverage"] = min(float(strat.get("max_gross_leverage", 2.0)), 2.0)
    strat["target_gross_leverage"] = min(
        float(strat.get("target_gross_leverage", 2.0)),
        strat["max_gross_leverage"],
    )

    enforce_paper_only(merged)
    return merged


def save_config(new_config: Dict[str, Any], config_path: Path | str = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Validate and persist updated configuration to config.yaml."""
    enforce_paper_only(new_config)
    current = load_config(config_path)
    for section in ("strategy", "backtest", "risk"):
        if section in new_config and isinstance(new_config[section], dict):
            current[section].update(new_config[section])

    # Re-validate after merge
    enforce_paper_only(current)
    path = Path(config_path)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(current, f, sort_keys=False, default_flow_style=False)
    return load_config(path)


def get_logger(name: str = "snapback") -> logging.Logger:
    """Configure a logger that writes timestamped entries to both data/snapback.log and stdout."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")

        log_file = ROOT_DIR / DEFAULT_CONFIG["risk"]["log_file"]
        log_file.parent.mkdir(parents=True, exist_ok=True)

        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


def is_kill_switch_active(config: Dict[str, Any] | None = None) -> bool:
    """Check whether the KILL_SWITCH file exists in the workspace root."""
    cfg = config or load_config()
    ks_name = cfg.get("risk", {}).get("kill_switch_file", "KILL_SWITCH")
    ks_path = ROOT_DIR / ks_name
    return ks_path.exists()


def set_kill_switch(active: bool, reason: str = "Manual dashboard toggle", config: Dict[str, Any] | None = None) -> bool:
    """Activate or deactivate the KILL_SWITCH file and log the action."""
    cfg = config or load_config()
    ks_name = cfg.get("risk", {}).get("kill_switch_file", "KILL_SWITCH")
    ks_path = ROOT_DIR / ks_name
    logger = get_logger("risk")
    if active:
        ks_path.write_text(f"KILL SWITCH ACTIVE: {reason}\n", encoding="utf-8")
        logger.warning(f"KILL SWITCH ACTIVATED: {reason}")
    else:
        if ks_path.exists():
            ks_path.unlink()
        logger.info(f"KILL SWITCH DEACTIVATED: {reason}")
    return ks_path.exists()
