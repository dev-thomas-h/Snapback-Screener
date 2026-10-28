export interface SignalItem {
  id?: number;
  signal_date?: string;
  symbol: string;
  company_name: string;
  sector: string;
  signal_type: 'ENTRY' | 'EXIT' | 'QUEUE_CAPPED' | 'RADAR';
  rank: number;
  close_price: number;
  open_price: number;
  high_price: number;
  low_price: number;
  prior_high: number;
  sma_200: number;
  pct_above_sma200: number;
  mom_6_1: number;
  mom_percentile: number;
  rsi_2: number;
  close_range_pos: number;
  days_held: number;
  reason: string;
}

export interface PositionItem {
  symbol: string;
  company_name: string;
  sector: string;
  entry_date: string;
  entry_price: number;
  shares: number;
  current_price: number;
  prior_high: number;
  days_held: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  mom_6_1: number;
  rsi_2: number;
}

export interface PlannedOrder {
  id?: number;
  timestamp?: string;
  signal_date: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  qty: number;
  notional: number;
  est_price: number;
  order_type: string;
  status?: string;
  dry_run?: number | boolean;
  reason: string;
}

export interface YearlyReturnRow {
  year: number;
  strategy_return_pct: number;
  spy_return_pct: number;
  alpha_pct: number;
  beat_spy: boolean;
  ending_equity: number;
  spy_ending_equity: number;
}

export interface EquityPoint {
  date: string;
  strategy_equity: number;
  spy_equity: number;
  no_momentum_equity: number;
  drawdown_pct: number;
  gross_leverage: number;
}

export interface ClosedTrade {
  symbol: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  shares: number;
  days_held: number;
  pnl: number;
  return_pct: number;
  exit_reason: string;
}

export interface BacktestMetrics {
  start_date: string;
  end_date: string;
  years_tested: number;
  initial_capital: number;
  final_equity: number;
  total_return_pct: number;
  cagr_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  win_rate_pct: number;
  avg_hold_days: number;
  avg_trade_return_pct: number;
  total_trades: number;
  avg_gross_leverage: number;
  max_gross_leverage_used: number;
  spy_final_equity: number;
  spy_total_return_pct: number;
  spy_cagr_pct: number;
  spy_max_drawdown_pct: number;
  no_mom_final_equity: number;
  no_mom_return_pct: number;
  years_beating_spy: number;
  total_calendar_years: number;
  post_claims_comparison: {
    claimed_total_return_pct: number;
    claimed_realistic_cagr_pct: number;
    claimed_max_drawdown_pct: number;
    claimed_winning_years_ratio: string;
    claimed_no_momentum_return_pct: number;
    actual_total_return_pct: number;
    actual_cagr_pct: number;
    actual_max_drawdown_pct: number;
    actual_winning_years_ratio: string;
    actual_no_momentum_return_pct: number;
    momentum_filter_outperformance_pct: number;
  };
}

export interface BacktestPayload {
  id?: number;
  run_timestamp?: string;
  metrics: BacktestMetrics;
  yearly_returns: YearlyReturnRow[];
  equity_curve: EquityPoint[];
  trades: ClosedTrade[];
}

export interface OverviewPayload {
  config: {
    strategy: Record<string, any>;
    backtest: Record<string, any>;
    risk: Record<string, any>;
  };
  kill_switch_active: boolean;
  daily_loss_guard: {
    tripped: boolean;
    message: string;
    limit_pct: number;
  };
  account: {
    connected: boolean;
    mode: string;
    endpoint: string;
    equity: number;
    last_equity: number;
    cash: number;
    buying_power: number;
    gross_exposure: number;
    gross_leverage: number;
    daily_pnl: number;
    daily_pnl_pct: number;
    positions: PositionItem[];
  };
  order_plan: {
    signal_date: string;
    kill_switch_active: boolean;
    daily_loss_guard_tripped: boolean;
    daily_loss_guard_message: string;
    surviving_positions_count: number;
    available_slots: number;
    projected_gross_exposure: number;
    projected_gross_leverage: number;
    orders: PlannedOrder[];
  };
  signals: {
    signal_date: string | null;
    entry: SignalItem[];
    exit: SignalItem[];
    queued: SignalItem[];
    radar: SignalItem[];
  };
  backtest: BacktestPayload | null;
  recent_orders: PlannedOrder[];
  risk_events: Array<{
    id: number;
    timestamp: string;
    event_type: string;
    severity: string;
    message: string;
  }>;
}
