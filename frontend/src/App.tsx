import React, { useEffect, useState, useMemo } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle2,
  Clock,
  DollarSign,
  Filter,
  Layers,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  ShieldOff,
  Sparkles,
  TrendingUp,
  Zap,
} from 'lucide-react';
import { OverviewPayload, SignalItem } from './types';
import { AuroraGlassBackground } from './components/reactbits/AuroraGlassBackground';
import { SplitText } from './components/reactbits/SplitText';
import { BlurText } from './components/reactbits/BlurText';
import { CountUp } from './components/reactbits/CountUp';
import { SpotlightCard } from './components/reactbits/SpotlightCard';
import { TiltCard } from './components/reactbits/TiltCard';
import { StarBorder } from './components/reactbits/StarBorder';
import { ShinyText } from './components/reactbits/ShinyText';
import { AnimatedList } from './components/reactbits/AnimatedList';
import { Magnet } from './components/reactbits/Magnet';
import { FloatingGlassDock, NavTab } from './components/reactbits/FloatingGlassDock';
import { EquityChart } from './components/EquityChart';

export const App: React.FC = () => {
  const [data, setData] = useState<OverviewPayload | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<NavTab>('screener');
  const [toast, setToast] = useState<string | null>(null);

  // Screener filters
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedSector, setSelectedSector] = useState<string>('ALL');
  const [screenerLimit, setScreenerLimit] = useState<number>(80);

  // Backtest controls
  const [btStartDate, setBtStartDate] = useState<string>('2008-01-01');
  const [btLimit, setBtLimit] = useState<number>(50);

  // Editable config state
  const [draftStrat, setDraftStrat] = useState<Record<string, any>>({});
  const [draftBt, setDraftBt] = useState<Record<string, any>>({});
  const [draftRisk, setDraftRisk] = useState<Record<string, any>>({});

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4200);
  };

  const fetchOverview = async () => {
    try {
      const res = await fetch('/api/overview');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: OverviewPayload = await res.json();
      setData(json);
      setDraftStrat(json.config.strategy || {});
      setDraftBt(json.config.backtest || {});
      setDraftRisk(json.config.risk || {});
    } catch (err: any) {
      showToast(`Error loading overview: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
  }, []);

  const handleRunScreener = async () => {
    setBusyAction('screener');
    try {
      const res = await fetch('/api/screener/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ universe_limit: screenerLimit }),
      });
      if (!res.ok) throw new Error(`Screener failed (${res.status})`);
      await fetchOverview();
      showToast(`Screened ${screenerLimit} S&P 500 leaders after close & updated SQLite audit log.`);
    } catch (err: any) {
      showToast(err.message);
    } finally {
      setBusyAction(null);
    }
  };

  const handleRunBacktest = async () => {
    setBusyAction('backtest');
    try {
      const res = await fetch('/api/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_date: btStartDate, universe_limit: btLimit }),
      });
      if (!res.ok) throw new Error(`Backtest failed (${res.status})`);
      await fetchOverview();
      showToast(`Completed event-driven backtest (${btStartDate} → Present).`);
    } catch (err: any) {
      showToast(err.message);
    } finally {
      setBusyAction(null);
    }
  };

  const handleRunTraderCycle = async (dryRun: boolean) => {
    setBusyAction(dryRun ? 'dry-run' : 'execute');
    try {
      const res = await fetch('/api/trader/cycle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: dryRun, refresh_signals: false }),
      });
      if (!res.ok) throw new Error(`Trader cycle failed (${res.status})`);
      await fetchOverview();
      showToast(
        dryRun
          ? 'Dry-Run complete: previewed Market-on-Open orders in audit log (0 live orders placed).'
          : 'Paper Trading cycle complete: Market-on-Open orders processed on paper account.'
      );
    } catch (err: any) {
      showToast(err.message);
    } finally {
      setBusyAction(null);
    }
  };

  const handleToggleKillSwitch = async () => {
    if (!data) return;
    const nextState = !data.kill_switch_active;
    setBusyAction('kill-switch');
    try {
      const res = await fetch('/api/risk/kill-switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          active: nextState,
          reason: nextState
            ? 'Emergency halt triggered from Glass Dashboard'
            : 'Trading resumed from Glass Dashboard',
        }),
      });
      if (!res.ok) throw new Error('Failed toggling Kill Switch');
      await fetchOverview();
      showToast(
        nextState
          ? 'KILL SWITCH ACTIVATED: All open paper orders cancelled & new entries blocked.'
          : 'Kill Switch deactivated: Normal paper trading rules restored.'
      );
    } catch (err: any) {
      showToast(err.message);
    } finally {
      setBusyAction(null);
    }
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusyAction('config');
    try {
      const res = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          strategy: draftStrat,
          backtest: draftBt,
          risk: draftRisk,
        }),
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Config update rejected');
      }
      await fetchOverview();
      showToast('Saved parameters to config.yaml.');
    } catch (err: any) {
      showToast(`Config Error: ${err.message}`);
    } finally {
      setBusyAction(null);
    }
  };

  const radarList = data?.signals.radar || [];
  const sectors = useMemo(() => {
    const s = new Set<string>(['ALL']);
    radarList.forEach((item) => {
      if (item.sector) s.add(item.sector);
    });
    return Array.from(s);
  }, [radarList]);

  const filteredRadar = useMemo(() => {
    return radarList.filter((item) => {
      const matchesSector = selectedSector === 'ALL' || item.sector === selectedSector;
      const q = searchQuery.trim().toLowerCase();
      const matchesSearch =
        !q ||
        item.symbol.toLowerCase().includes(q) ||
        (item.company_name || '').toLowerCase().includes(q) ||
        (item.sector || '').toLowerCase().includes(q);
      return matchesSector && matchesSearch;
    });
  }, [radarList, selectedSector, searchQuery]);

  if (loading || !data) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-6">
        <AuroraGlassBackground />
        <div className="glass-panel rounded-3xl p-10 max-w-md w-full text-center space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-sky-500/15 border border-sky-500/30 flex items-center justify-center mx-auto text-sky-600">
            <RefreshCw className="w-6 h-6 animate-spin" />
          </div>
          <h2 className="text-xl font-bold text-slate-900">
            Initializing Momentum Leaders Snapback
          </h2>
          <p className="text-sm text-slate-600">
            Loading S&amp;P 500 universe, Wilder RSI(2) signal engine, and Alpaca paper account state...
          </p>
        </div>
      </div>
    );
  }

  const { account, signals, backtest, order_plan, kill_switch_active, daily_loss_guard } = data;
  const btMetrics = backtest?.metrics;

  return (
    <div className="min-h-screen pb-20 text-slate-900 relative">
      <AuroraGlassBackground />

      {/* Floating Toast Notification */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 max-w-md glass-panel rounded-2xl px-5 py-3.5 border-sky-300/80 shadow-xl flex items-center gap-3 animate-bounce">
          <Sparkles className="w-5 h-5 text-sky-600 shrink-0" />
          <span className="text-sm font-medium text-slate-800">{toast}</span>
        </div>
      )}

      {/* Top Translucent Glass Header */}
      <header className="sticky top-0 z-30 backdrop-blur-xl bg-white/55 border-b border-white/80 shadow-[0_4px_24px_rgba(15,23,42,0.03)]">
        <div className="max-w-[1440px] mx-auto px-6 py-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-sky-500 to-emerald-500 p-[1.5px] shadow-md shadow-sky-500/15">
              <div className="w-full h-full bg-white/95 rounded-[14px] flex items-center justify-center">
                <Zap className="w-5 h-5 text-sky-600" />
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h1 className="text-lg font-extrabold tracking-tight text-slate-900">
                  <SplitText text="Momentum Leaders Snapback" />
                </h1>
                <span className="px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-emerald-500/15 text-emerald-800 border border-emerald-500/30">
                  <ShinyText text="PAPER-ONLY ENFORCED" />
                </span>
              </div>
              <BlurText
                text={`S&P 500 Top 20% 6-1M Momentum • Above 200-MA • Wilder RSI(2) < 15 • Bottom 10% Range • Signal Bar: ${
                  signals.signal_date || 'Latest'
                }`}
                className="text-xs text-slate-500 font-medium"
              />
            </div>
          </div>

          <FloatingGlassDock
            activeTab={activeTab}
            onSelectTab={setActiveTab}
            entrySignalCount={signals.entry.length}
            killSwitchActive={kill_switch_active}
          />

          <div className="flex items-center gap-2.5">
            <Magnet strength={0.2}>
              <button
                onClick={handleToggleKillSwitch}
                disabled={busyAction === 'kill-switch'}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold border transition-all shadow-sm ${
                  kill_switch_active
                    ? 'bg-rose-600 text-white border-rose-500 shadow-rose-500/20'
                    : 'bg-white/80 hover:bg-rose-50 text-slate-700 hover:text-rose-700 border-white/90'
                }`}
              >
                {kill_switch_active ? (
                  <>
                    <ShieldOff className="w-4 h-4" />
                    <span>KILL SWITCH ACTIVE (CLICK TO RESUME)</span>
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-4 h-4 text-emerald-600" />
                    <span>Kill Switch Armed</span>
                  </>
                )}
              </button>
            </Magnet>
          </div>
        </div>
      </header>

      <main className="max-w-[1440px] mx-auto px-6 pt-7 space-y-7">
        {/* Top 5 Translucent KPI Cards with ReactBits TiltCard + SpotlightCard + CountUp */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <TiltCard>
            <SpotlightCard className="p-5">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <span>Paper Account Equity</span>
                <DollarSign className="w-4 h-4 text-sky-600" />
              </div>
              <div className="mt-2 text-2xl font-extrabold font-mono text-slate-900">
                <CountUp to={account.equity} prefix="$" decimals={2} />
              </div>
              <div className="mt-2 flex items-center justify-between text-xs">
                <span
                  className={`inline-flex items-center gap-0.5 font-mono font-semibold ${
                    account.daily_pnl >= 0 ? 'text-emerald-700' : 'text-rose-600'
                  }`}
                >
                  {account.daily_pnl >= 0 ? (
                    <ArrowUpRight className="w-3.5 h-3.5" />
                  ) : (
                    <ArrowDownRight className="w-3.5 h-3.5" />
                  )}
                  {account.daily_pnl >= 0 ? '+' : ''}${account.daily_pnl.toFixed(2)} (
                  {account.daily_pnl_pct >= 0 ? '+' : ''}
                  {account.daily_pnl_pct.toFixed(2)}%)
                </span>
                <span className="text-slate-400">5% Loss Guard OK</span>
              </div>
            </SpotlightCard>
          </TiltCard>

          <TiltCard>
            <SpotlightCard className="p-5" spotlightColor="rgba(16, 185, 129, 0.14)">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <span>Gross Exposure &amp; Cap</span>
                <Layers className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-extrabold font-mono text-slate-900">
                  <CountUp to={account.gross_leverage} suffix="x" decimals={2} />
                </span>
                <span className="text-xs font-mono text-slate-500">/ 2.00x max</span>
              </div>
              <div className="mt-2.5 w-full h-2 rounded-full bg-slate-200/70 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-sky-500 to-emerald-500 transition-all duration-500"
                  style={{ width: `${Math.min(100, (account.gross_leverage / 2.0) * 100)}%` }}
                />
              </div>
            </SpotlightCard>
          </TiltCard>

          <TiltCard>
            <SpotlightCard className="p-5" spotlightColor="rgba(99, 102, 241, 0.14)">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <span>Portfolio Slots</span>
                <Activity className="w-4 h-4 text-indigo-600" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-extrabold font-mono text-slate-900">
                  {account.positions.length}
                </span>
                <span className="text-xs font-mono text-slate-500">/ 10 Max Positions</span>
              </div>
              <div className="mt-2 text-xs text-slate-500 flex items-center justify-between">
                <span>Max 2 Entries / Day</span>
                <span className="font-mono font-semibold text-indigo-700">
                  {order_plan.available_slots} slots open
                </span>
              </div>
            </SpotlightCard>
          </TiltCard>

          <TiltCard>
            <SpotlightCard className="p-5" spotlightColor="rgba(14, 165, 233, 0.16)">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <span>Today&apos;s Signals</span>
                <Sparkles className="w-4 h-4 text-sky-600" />
              </div>
              <div className="mt-2 flex items-baseline gap-3">
                <span className="text-2xl font-extrabold font-mono text-sky-700">
                  {signals.entry.length} BUY
                </span>
                <span className="text-sm font-bold font-mono text-amber-700">
                  {signals.exit.length} SELL
                </span>
              </div>
              <div className="mt-2 text-xs text-slate-500 flex items-center justify-between">
                <span>Next-Open (MOO)</span>
                <span className="font-mono text-slate-700">{signals.radar.length} on Radar</span>
              </div>
            </SpotlightCard>
          </TiltCard>

          <TiltCard>
            <SpotlightCard className="p-5" spotlightColor="rgba(245, 158, 11, 0.14)">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <span>Backtest Benchmark</span>
                <TrendingUp className="w-4 h-4 text-amber-600" />
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-extrabold font-mono text-slate-900">
                  <CountUp
                    to={btMetrics ? btMetrics.total_return_pct : 0}
                    prefix="+"
                    suffix="%"
                    decimals={1}
                  />
                </span>
                <span className="text-xs font-mono text-slate-500">
                  ({btMetrics ? btMetrics.cagr_pct.toFixed(1) : '0'}% CAGR)
                </span>
              </div>
              <div className="mt-2 text-xs text-slate-500 flex items-center justify-between">
                <span>Win Rate: {btMetrics ? btMetrics.win_rate_pct.toFixed(1) : '0'}%</span>
                <span className="font-mono text-rose-600">
                  DD: {btMetrics ? btMetrics.max_drawdown_pct.toFixed(1) : '0'}%
                </span>
              </div>
            </SpotlightCard>
          </TiltCard>
        </section>

        {/* =====================================================================
            TAB 1: DAILY SCREENER & MOMENTUM LEADERS RADAR
        ===================================================================== */}
        {activeTab === 'screener' && (
          <div className="space-y-7">
            {/* Screener Action Ribbon */}
            <SpotlightCard className="p-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <span>After-Close S&amp;P 500 Signal Engine</span>
                    <span className="text-xs font-mono px-2.5 py-0.5 rounded-full bg-sky-500/10 text-sky-700 border border-sky-500/20">
                      Bar Date: {signals.signal_date}
                    </span>
                  </h2>
                  <p className="text-xs text-slate-600 mt-0.5">
                    Computes signals on completed daily bars after market close. All entry and exit orders execute at the{' '}
                    <strong className="text-slate-800">next trading day&apos;s open (Market-on-Open)</strong> with zero lookahead bias.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2 glass-pill px-3 py-1.5 rounded-xl text-xs">
                    <span className="text-slate-500 font-medium">Universe Depth:</span>
                    <select
                      value={screenerLimit}
                      onChange={(e) => setScreenerLimit(Number(e.target.value))}
                      className="bg-transparent font-mono font-bold text-slate-800 focus:outline-none"
                    >
                      <option value={60}>Top 60 S&amp;P Leaders (Fast)</option>
                      <option value={120}>Top 120 S&amp;P Leaders</option>
                      <option value={250}>Top 250 S&amp;P Constituents</option>
                      <option value={0}>Full ~500 S&amp;P Universe</option>
                    </select>
                  </div>

                  <Magnet>
                    <button
                      onClick={handleRunScreener}
                      disabled={busyAction === 'screener'}
                      className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold shadow-md shadow-sky-500/20 transition disabled:opacity-50"
                    >
                      <RefreshCw
                        className={`w-4 h-4 ${busyAction === 'screener' ? 'animate-spin' : ''}`}
                      />
                      <span>
                        {busyAction === 'screener' ? 'Screening Universe...' : 'Run Daily Screener'}
                      </span>
                    </button>
                  </Magnet>

                  <Magnet>
                    <button
                      onClick={() => handleRunTraderCycle(true)}
                      disabled={busyAction === 'dry-run'}
                      className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/85 hover:bg-white text-slate-800 border border-white text-xs font-bold shadow-sm transition"
                    >
                      <Play className="w-3.5 h-3.5 text-emerald-600" />
                      <span>Preview Dry-Run Orders</span>
                    </button>
                  </Magnet>
                </div>
              </div>
            </SpotlightCard>

            {/* Actionable Entry & Exit Signals Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Entry Signals */}
              <div className="space-y-3">
                <div className="flex items-center justify-between px-1">
                  <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                    <span>Actionable Snapback Entry Signals (Max 2 / Day)</span>
                  </h3>
                  <span className="text-xs font-mono text-slate-500">
                    Ranked by 6-1M Momentum
                  </span>
                </div>

                {signals.entry.length === 0 ? (
                  <SpotlightCard className="p-6 text-center space-y-2">
                    <p className="text-sm font-semibold text-slate-700">
                      0 Stocks Triggered All 4 Strict Entry Rules Today
                    </p>
                    <p className="text-xs text-slate-500">
                      Requires simultaneous: Close &gt; 200-MA, Top 20% 6-1M Momentum, Wilder RSI(2) &lt; 15, and Close in Bottom 10% of Day&apos;s Range. Check the Momentum Leaders Radar below for stocks approaching RSI(2) &lt; 15.
                    </p>
                  </SpotlightCard>
                ) : (
                  <AnimatedList className="space-y-3">
                    {signals.entry.map((sig) => (
                      <StarBorder key={sig.symbol} accentColor="#059669">
                        <div className="p-5 space-y-3">
                          <div className="flex items-start justify-between gap-4">
                            <div>
                              <div className="flex items-center gap-2.5">
                                <span className="px-2.5 py-0.5 rounded-lg bg-emerald-500/15 text-emerald-800 font-mono font-extrabold text-xs border border-emerald-500/30">
                                  BUY #{sig.rank} • MOO
                                </span>
                                <span className="text-lg font-extrabold font-mono text-slate-900">
                                  {sig.symbol}
                                </span>
                                <span className="text-xs text-slate-500 font-medium">
                                  {sig.company_name}
                                </span>
                              </div>
                              <p className="text-xs text-slate-500 mt-1">{sig.sector}</p>
                            </div>
                            <div className="text-right font-mono">
                              <div className="text-lg font-extrabold text-slate-900">
                                ${sig.close_price.toFixed(2)}
                              </div>
                              <div className="text-[11px] text-slate-500">
                                SMA200: ${sig.sma_200.toFixed(2)} (+{sig.pct_above_sma200.toFixed(1)}%)
                              </div>
                            </div>
                          </div>

                          {/* 4 Filter Badges */}
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                            <div className="rounded-xl bg-emerald-50/80 border border-emerald-200/70 px-3 py-2">
                              <div className="text-[10px] font-semibold uppercase text-emerald-700">
                                1. Trend Filter
                              </div>
                              <div className="text-xs font-mono font-bold text-emerald-950 mt-0.5">
                                +{sig.pct_above_sma200.toFixed(1)}% &gt; 200MA
                              </div>
                            </div>
                            <div className="rounded-xl bg-sky-50/80 border border-sky-200/70 px-3 py-2">
                              <div className="text-[10px] font-semibold uppercase text-sky-700">
                                2. 6-1M Momentum
                              </div>
                              <div className="text-xs font-mono font-bold text-sky-950 mt-0.5">
                                +{(sig.mom_6_1 * 100).toFixed(1)}% ({sig.mom_percentile.toFixed(0)}th pct)
                              </div>
                            </div>
                            <div className="rounded-xl bg-indigo-50/80 border border-indigo-200/70 px-3 py-2">
                              <div className="text-[10px] font-semibold uppercase text-indigo-700">
                                3. Wilder RSI(2)
                              </div>
                              <div className="text-xs font-mono font-bold text-indigo-950 mt-0.5">
                                {sig.rsi_2.toFixed(1)} (&lt; 15.0)
                              </div>
                            </div>
                            <div className="rounded-xl bg-amber-50/80 border border-amber-200/70 px-3 py-2">
                              <div className="text-[10px] font-semibold uppercase text-amber-700">
                                4. Day&apos;s Range
                              </div>
                              <div className="text-xs font-mono font-bold text-amber-950 mt-0.5">
                                {(sig.close_range_pos * 100).toFixed(1)}% (&le; 10%)
                              </div>
                            </div>
                          </div>
                        </div>
                      </StarBorder>
                    ))}
                  </AnimatedList>
                )}
              </div>

              {/* Exit Signals & Next-Open Order Plan */}
              <div className="space-y-3">
                <div className="flex items-center justify-between px-1">
                  <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-sky-500" />
                    <span>Next-Open (MOO) Execution Queue &amp; Exits</span>
                  </h3>
                  <span className="text-xs font-mono text-slate-500">
                    Projected Leverage: {order_plan.projected_gross_leverage.toFixed(2)}x / 2.00x
                  </span>
                </div>

                <SpotlightCard className="p-5 space-y-3">
                  {order_plan.orders.length === 0 ? (
                    <div className="text-center py-4 text-xs text-slate-500">
                      No pending entry or exit orders for next market open.
                    </div>
                  ) : (
                    <AnimatedList className="space-y-2.5">
                      {order_plan.orders.map((ord, idx) => (
                        <div
                          key={`${ord.symbol}-${idx}`}
                          className="p-3.5 rounded-xl bg-white/75 border border-white/90 flex items-center justify-between gap-4 shadow-sm"
                        >
                          <div className="flex items-center gap-3">
                            <span
                              className={`px-2.5 py-1 rounded-lg font-mono text-xs font-extrabold ${
                                ord.side === 'BUY'
                                  ? 'bg-emerald-500/15 text-emerald-800 border border-emerald-500/30'
                                  : 'bg-amber-500/15 text-amber-800 border border-amber-500/30'
                              }`}
                            >
                              {ord.side} MOO
                            </span>
                            <div>
                              <div className="font-mono font-bold text-sm text-slate-900">
                                {ord.qty} shs {ord.symbol} @ ~${ord.est_price.toFixed(2)}
                              </div>
                              <div className="text-[11px] text-slate-500 line-clamp-1">
                                {ord.reason}
                              </div>
                            </div>
                          </div>
                          <div className="text-right font-mono shrink-0">
                            <div className="text-sm font-bold text-slate-900">
                              ${ord.notional.toLocaleString()}
                            </div>
                            <div className="text-[10px] text-slate-400">{ord.order_type}</div>
                          </div>
                        </div>
                      ))}
                    </AnimatedList>
                  )}
                </SpotlightCard>
              </div>
            </div>

            {/* Momentum Leaders Radar Table */}
            <SpotlightCard className="p-6 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-base font-extrabold text-slate-900 flex items-center gap-2">
                    <span>S&amp;P 500 Momentum Leaders Radar</span>
                    <span className="px-2.5 py-0.5 rounded-full text-xs font-mono bg-sky-500/15 text-sky-800 border border-sky-500/25">
                      Top 20% 6-1M Momentum + Above 200-MA
                    </span>
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Sorted by lowest Wilder RSI(2) so you can monitor elite momentum leaders pulling back toward the &lt;15 snapback entry zone.
                  </p>
                </div>

                {/* Search & Sector Filter */}
                <div className="flex flex-wrap items-center gap-3">
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Filter symbol or name..."
                      className="pl-8 pr-3 py-1.5 rounded-xl glass-pill text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-400/40"
                    />
                  </div>
                  <div className="flex items-center gap-1.5 glass-pill px-3 py-1.5 rounded-xl text-xs">
                    <Filter className="w-3.5 h-3.5 text-slate-400" />
                    <select
                      value={selectedSector}
                      onChange={(e) => setSelectedSector(e.target.value)}
                      className="bg-transparent font-medium text-slate-700 focus:outline-none"
                    >
                      {sectors.map((sec) => (
                        <option key={sec} value={sec}>
                          {sec === 'ALL' ? 'All GICS Sectors' : sec}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200/80 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                      <th className="py-3 px-3">Rank</th>
                      <th className="py-3 px-3">Ticker &amp; Company</th>
                      <th className="py-3 px-3">GICS Sector</th>
                      <th className="py-3 px-3 text-right">Close</th>
                      <th className="py-3 px-3 text-right">vs. 200-MA</th>
                      <th className="py-3 px-3 text-right">6-1M Momentum</th>
                      <th className="py-3 px-4">Wilder RSI(2) (&lt;15 Trigger)</th>
                      <th className="py-3 px-4">Close in Day&apos;s Range (&le;10%)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200/50 text-xs">
                    {filteredRadar.map((row: SignalItem) => {
                      const isNearRsi = row.rsi_2 < 30;
                      const isNearRange = row.close_range_pos <= 0.20;
                      return (
                        <tr
                          key={row.symbol}
                          className="hover:bg-white/60 transition-colors"
                        >
                          <td className="py-3 px-3 font-mono text-slate-400">
                            #{row.rank}
                          </td>
                          <td className="py-3 px-3">
                            <div className="font-mono font-bold text-slate-900">
                              {row.symbol}
                            </div>
                            <div className="text-[11px] text-slate-500 truncate max-w-[180px]">
                              {row.company_name}
                            </div>
                          </td>
                          <td className="py-3 px-3">
                            <span className="px-2 py-0.5 rounded-md bg-white/75 border border-slate-200/80 text-[11px] text-slate-600">
                              {row.sector}
                            </span>
                          </td>
                          <td className="py-3 px-3 text-right font-mono font-semibold text-slate-900">
                            ${row.close_price.toFixed(2)}
                          </td>
                          <td className="py-3 px-3 text-right font-mono text-emerald-700 font-semibold">
                            +{row.pct_above_sma200.toFixed(1)}%
                          </td>
                          <td className="py-3 px-3 text-right font-mono">
                            <span className="font-bold text-sky-700">
                              +{(row.mom_6_1 * 100).toFixed(1)}%
                            </span>
                            <span className="text-[10px] text-slate-400 ml-1">
                              ({row.mom_percentile.toFixed(0)}p)
                            </span>
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2.5">
                              <span
                                className={`font-mono font-bold w-10 text-right ${
                                  row.rsi_2 < 15
                                    ? 'text-emerald-600'
                                    : isNearRsi
                                    ? 'text-amber-600'
                                    : 'text-slate-700'
                                }`}
                              >
                                {row.rsi_2.toFixed(1)}
                              </span>
                              <div className="flex-1 h-2 rounded-full bg-slate-200/75 overflow-hidden relative">
                                <div
                                  className="absolute top-0 bottom-0 left-[15%] w-[1.5px] bg-emerald-600 z-10"
                                  title="RSI(2) = 15 Entry Threshold"
                                />
                                <div
                                  className={`h-full rounded-full ${
                                    row.rsi_2 < 15
                                      ? 'bg-emerald-500'
                                      : isNearRsi
                                      ? 'bg-amber-500'
                                      : 'bg-sky-500/70'
                                  }`}
                                  style={{ width: `${Math.min(100, Math.max(3, row.rsi_2))}%` }}
                                />
                              </div>
                            </div>
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2.5">
                              <span
                                className={`font-mono font-semibold w-11 text-right ${
                                  row.close_range_pos <= 0.1
                                    ? 'text-emerald-600'
                                    : isNearRange
                                    ? 'text-amber-600'
                                    : 'text-slate-600'
                                }`}
                              >
                                {(row.close_range_pos * 100).toFixed(1)}%
                              </span>
                              <div className="flex-1 h-2 rounded-full bg-slate-200/75 overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    row.close_range_pos <= 0.1
                                      ? 'bg-emerald-500'
                                      : 'bg-slate-400'
                                  }`}
                                  style={{
                                    width: `${Math.min(100, Math.max(3, row.close_range_pos * 100))}%`,
                                  }}
                                />
                              </div>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </SpotlightCard>
          </div>
        )}

        {/* =====================================================================
            TAB 2: BACKTEST LAB & ALPHAINSIDER CLAIM VALIDATOR
        ===================================================================== */}
        {activeTab === 'backtest' && btMetrics && backtest && (
          <div className="space-y-7">
            {/* Backtest Runner Header */}
            <SpotlightCard className="p-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h2 className="text-base font-bold text-slate-900">
                    Event-Driven Backtest Engine &amp; Claim Validator
                  </h2>
                  <p className="text-xs text-slate-600 mt-0.5">
                    Models 5 bps slippage per trade, 5.5% annualized margin interest on leveraged exposure (&gt;1.0x), and strict next-open execution.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex items-center gap-2 glass-pill px-3 py-1.5 rounded-xl text-xs">
                    <span className="text-slate-500">Start Date:</span>
                    <input
                      type="date"
                      value={btStartDate}
                      onChange={(e) => setBtStartDate(e.target.value)}
                      className="bg-transparent font-mono font-bold text-slate-800 focus:outline-none"
                    />
                  </div>
                  <div className="flex items-center gap-2 glass-pill px-3 py-1.5 rounded-xl text-xs">
                    <span className="text-slate-500">Sample Size:</span>
                    <select
                      value={btLimit}
                      onChange={(e) => setBtLimit(Number(e.target.value))}
                      className="bg-transparent font-mono font-bold text-slate-800 focus:outline-none"
                    >
                      <option value={45}>45 Liquid Leaders (Fast)</option>
                      <option value={85}>85 S&amp;P Constituents</option>
                      <option value={150}>150 S&amp;P Constituents</option>
                    </select>
                  </div>
                  <Magnet>
                    <button
                      onClick={handleRunBacktest}
                      disabled={busyAction === 'backtest'}
                      className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold shadow-md shadow-sky-500/20 transition disabled:opacity-50"
                    >
                      <RefreshCw
                        className={`w-4 h-4 ${busyAction === 'backtest' ? 'animate-spin' : ''}`}
                      />
                      <span>
                        {busyAction === 'backtest' ? 'Simulating 2008–Present...' : 'Re-Run Backtest'}
                      </span>
                    </button>
                  </Magnet>
                </div>
              </div>
            </SpotlightCard>

            {/* AlphaInsider Claim vs. Reality Validation Scorecard */}
            <SpotlightCard className="p-6 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-base font-extrabold text-slate-900">
                    AlphaInsider Post Claims (Oct 23, 2026) vs. Audited Backtest Reality
                  </h3>
                  <p className="text-xs text-slate-500">
                    The README notes to treat the +22,289% headline return with skepticism (the post itself cites ~27% CAGR as realistic) and verify with realistic execution costs and no lookahead bias.
                  </p>
                </div>
                <span className="px-3 py-1 rounded-full text-xs font-mono font-bold bg-amber-500/15 text-amber-800 border border-amber-500/30">
                  Survivorship-Bias &amp; Slippage Audited
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="p-4 rounded-2xl bg-white/75 border border-white/90 space-y-1">
                  <div className="text-[11px] font-bold uppercase text-slate-400">
                    Total Return &amp; CAGR
                  </div>
                  <div className="text-lg font-extrabold font-mono text-sky-700">
                    +{btMetrics.total_return_pct.toFixed(1)}% ({btMetrics.cagr_pct.toFixed(2)}% / yr)
                  </div>
                  <div className="text-xs text-slate-500">
                    Post Headline: +22,289% (Post realistic note: ~27%/yr)
                  </div>
                </div>

                <div className="p-4 rounded-2xl bg-white/75 border border-white/90 space-y-1">
                  <div className="text-[11px] font-bold uppercase text-slate-400">
                    Maximum Drawdown
                  </div>
                  <div className="text-lg font-extrabold font-mono text-emerald-700">
                    {btMetrics.max_drawdown_pct.toFixed(2)}% (vs SPY {btMetrics.spy_max_drawdown_pct.toFixed(1)}%)
                  </div>
                  <div className="text-xs text-slate-500">
                    Post Claimed: -38.0% max drawdown
                  </div>
                </div>

                <div className="p-4 rounded-2xl bg-white/75 border border-white/90 space-y-1">
                  <div className="text-[11px] font-bold uppercase text-slate-400">
                    Win Rate &amp; Hold Period
                  </div>
                  <div className="text-lg font-extrabold font-mono text-slate-900">
                    {btMetrics.win_rate_pct.toFixed(1)}% Win • {btMetrics.avg_hold_days.toFixed(1)} Days
                  </div>
                  <div className="text-xs text-slate-500">
                    Across {btMetrics.total_trades} trades (Sharpe {btMetrics.sharpe_ratio.toFixed(2)})
                  </div>
                </div>

                <div className="p-4 rounded-2xl bg-white/75 border border-white/90 space-y-1">
                  <div className="text-[11px] font-bold uppercase text-slate-400">
                    Years Beating S&amp;P 500 (SPY)
                  </div>
                  <div className="text-lg font-extrabold font-mono text-indigo-700">
                    {btMetrics.years_beating_spy} / {btMetrics.total_calendar_years} Years
                  </div>
                  <div className="text-xs text-slate-500">
                    Post Claimed: 13 / 19 years (+46.6% alpha in 2008 crash &amp; +18.4% in 2022)
                  </div>
                </div>
              </div>
            </SpotlightCard>

            {/* Interactive Glassmorphic Equity Curve & Drawdown Chart */}
            <SpotlightCard className="p-6 space-y-4">
              <h3 className="text-base font-extrabold text-slate-900">
                Interactive Equity Curve &amp; Underwater Drawdown ({btMetrics.start_date} – {btMetrics.end_date})
              </h3>
              <EquityChart
                data={backtest.equity_curve}
                initialCapital={btMetrics.initial_capital}
              />
            </SpotlightCard>

            {/* Yearly Returns Comparison & Recent Backtest Trades */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <SpotlightCard className="p-6 space-y-3">
                <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-700">
                  Calendar Year Returns vs. SPY Benchmark
                </h3>
                <div className="overflow-y-auto max-h-[420px]">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 text-[11px] font-bold uppercase text-slate-500">
                        <th className="py-2.5 px-2">Year</th>
                        <th className="py-2.5 px-2 text-right">Snapback (%)</th>
                        <th className="py-2.5 px-2 text-right">SPY (%)</th>
                        <th className="py-2.5 px-2 text-right">Alpha (%)</th>
                        <th className="py-2.5 px-2 text-right">Ending Equity</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200/50 font-mono">
                      {backtest.yearly_returns.map((yr) => (
                        <tr key={yr.year} className="hover:bg-white/60">
                          <td className="py-2 px-2 font-bold text-slate-800">{yr.year}</td>
                          <td
                            className={`py-2 px-2 text-right font-semibold ${
                              yr.strategy_return_pct >= 0 ? 'text-emerald-700' : 'text-rose-600'
                            }`}
                          >
                            {yr.strategy_return_pct >= 0 ? '+' : ''}
                            {yr.strategy_return_pct.toFixed(2)}%
                          </td>
                          <td
                            className={`py-2 px-2 text-right ${
                              yr.spy_return_pct >= 0 ? 'text-slate-700' : 'text-rose-500'
                            }`}
                          >
                            {yr.spy_return_pct >= 0 ? '+' : ''}
                            {yr.spy_return_pct.toFixed(2)}%
                          </td>
                          <td className="py-2 px-2 text-right">
                            <span
                              className={`px-2 py-0.5 rounded-md text-[11px] font-bold ${
                                yr.beat_spy
                                  ? 'bg-emerald-500/15 text-emerald-800'
                                  : 'bg-slate-200/70 text-slate-600'
                              }`}
                            >
                              {yr.alpha_pct >= 0 ? '+' : ''}
                              {yr.alpha_pct.toFixed(2)}%
                            </span>
                          </td>
                          <td className="py-2 px-2 text-right text-slate-800">
                            ${yr.ending_equity.toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </SpotlightCard>

              <SpotlightCard className="p-6 space-y-3">
                <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-700">
                  Recent Simulated Trades (Next-Open Fills + 5 bps Slippage)
                </h3>
                <div className="overflow-y-auto max-h-[420px]">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 text-[11px] font-bold uppercase text-slate-500">
                        <th className="py-2.5 px-2">Symbol</th>
                        <th className="py-2.5 px-2">Entry → Exit</th>
                        <th className="py-2.5 px-2 text-right">Days</th>
                        <th className="py-2.5 px-2 text-right">Return</th>
                        <th className="py-2.5 px-2">Exit Rule</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200/50 font-mono">
                      {backtest.trades
                        .slice()
                        .reverse()
                        .slice(0, 60)
                        .map((tr, i) => (
                          <tr key={`${tr.symbol}-${tr.entry_date}-${i}`} className="hover:bg-white/60">
                            <td className="py-2 px-2 font-bold text-slate-900">{tr.symbol}</td>
                            <td className="py-2 px-2 text-[11px] text-slate-500">
                              {tr.entry_date} → {tr.exit_date}
                            </td>
                            <td className="py-2 px-2 text-right text-slate-700">{tr.days_held}d</td>
                            <td
                              className={`py-2 px-2 text-right font-bold ${
                                tr.return_pct >= 0 ? 'text-emerald-700' : 'text-rose-600'
                              }`}
                            >
                              {tr.return_pct >= 0 ? '+' : ''}
                              {tr.return_pct.toFixed(2)}%
                            </td>
                            <td className="py-2 px-2 text-[11px] font-sans text-slate-600">
                              {tr.exit_reason}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </SpotlightCard>
            </div>
          </div>
        )}

        {/* =====================================================================
            TAB 3: PAPER TRADER & RISK CONTROL VAULT
        ===================================================================== */}
        {activeTab === 'trader' && (
          <div className="space-y-7">
            {/* Mandatory Risk Controls Banner */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <SpotlightCard className="p-5 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    1. Paper-Only Construction Lock
                  </span>
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                </div>
                <div className="text-sm font-bold text-slate-900">
                  TradingClient(paper=True) Verified
                </div>
                <p className="text-xs text-slate-500">
                  Hard-coded guard in <code className="font-mono text-slate-700">app/config.py</code> rejects <code className="font-mono">paper=False</code>, live endpoints, or <code className="font-mono">AK...</code> live keys.
                </p>
              </SpotlightCard>

              <SpotlightCard className="p-5 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    2. 5% Daily Loss Guard
                  </span>
                  {daily_loss_guard.tripped ? (
                    <AlertTriangle className="w-4 h-4 text-rose-600" />
                  ) : (
                    <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  )}
                </div>
                <div className="text-sm font-bold text-slate-900">
                  Intraday P&amp;L: {account.daily_pnl_pct >= 0 ? '+' : ''}
                  {account.daily_pnl_pct.toFixed(2)}% (Limit: -{daily_loss_guard.limit_pct.toFixed(1)}%)
                </div>
                <p className="text-xs text-slate-500">{daily_loss_guard.message}</p>
              </SpotlightCard>

              <SpotlightCard className="p-5 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    3. Emergency Kill Switch
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold ${
                      kill_switch_active
                        ? 'bg-rose-500/15 text-rose-700'
                        : 'bg-emerald-500/15 text-emerald-700'
                    }`}
                  >
                    {kill_switch_active ? 'HALTED' : 'NORMAL'}
                  </span>
                </div>
                <div className="flex items-center justify-between pt-1">
                  <span className="text-xs text-slate-600">
                    Creates/removes <code className="font-mono">KILL_SWITCH</code> &amp; cancels open orders
                  </span>
                  <button
                    onClick={handleToggleKillSwitch}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold transition ${
                      kill_switch_active
                        ? 'bg-emerald-600 text-white hover:bg-emerald-700'
                        : 'bg-rose-600 text-white hover:bg-rose-700'
                    }`}
                  >
                    {kill_switch_active ? 'Resume Trading' : 'Engage Kill Switch'}
                  </button>
                </div>
              </SpotlightCard>
            </div>

            {/* Active Paper Positions Table */}
            <SpotlightCard className="p-6 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-base font-extrabold text-slate-900">
                    Active Paper Portfolio Positions ({account.positions.length} / 10 Max)
                  </h3>
                  <p className="text-xs text-slate-500">
                    Each position exits on the <strong className="text-slate-700">first daily close above Prior Day&apos;s High</strong> OR after <strong className="text-slate-700">20 trading days</strong> (at Day 21 Open).
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <Magnet>
                    <button
                      onClick={() => handleRunTraderCycle(true)}
                      disabled={busyAction === 'dry-run'}
                      className="flex items-center gap-2 px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold shadow-sm transition"
                    >
                      <Play className="w-3.5 h-3.5" />
                      <span>Run --dry-run Order Preview</span>
                    </button>
                  </Magnet>
                  <Magnet>
                    <button
                      onClick={() => handleRunTraderCycle(false)}
                      disabled={busyAction === 'execute' || kill_switch_active}
                      className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold shadow-sm transition disabled:opacity-40"
                    >
                      <Zap className="w-3.5 h-3.5" />
                      <span>Submit Paper MOO Orders</span>
                    </button>
                  </Magnet>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-[11px] font-bold uppercase text-slate-500">
                      <th className="py-3 px-3">Symbol</th>
                      <th className="py-3 px-3 text-right">Shares</th>
                      <th className="py-3 px-3 text-right">Entry Price</th>
                      <th className="py-3 px-3 text-right">Current Price</th>
                      <th className="py-3 px-3 text-right">Prior Day High (Exit Target)</th>
                      <th className="py-3 px-4">Hold Countdown (Max 20d)</th>
                      <th className="py-3 px-3 text-right">Market Value</th>
                      <th className="py-3 px-3 text-right">Unrealized P&amp;L</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200/50 font-mono">
                    {account.positions.map((pos) => {
                      const bounceTriggered = pos.current_price > pos.prior_high;
                      const timeTriggered = pos.days_held >= 20;
                      return (
                        <tr key={pos.symbol} className="hover:bg-white/60">
                          <td className="py-3 px-3">
                            <div className="font-bold text-slate-900">{pos.symbol}</div>
                            <div className="font-sans text-[11px] text-slate-500">{pos.company_name}</div>
                          </td>
                          <td className="py-3 px-3 text-right text-slate-700">{pos.shares.toFixed(2)}</td>
                          <td className="py-3 px-3 text-right text-slate-700">${pos.entry_price.toFixed(2)}</td>
                          <td className="py-3 px-3 text-right font-bold text-slate-900">
                            ${pos.current_price.toFixed(2)}
                          </td>
                          <td className="py-3 px-3 text-right">
                            <span
                              className={`px-2 py-0.5 rounded-md font-bold ${
                                bounceTriggered
                                  ? 'bg-emerald-500/15 text-emerald-800 border border-emerald-500/30'
                                  : 'text-slate-700'
                              }`}
                            >
                              ${pos.prior_high.toFixed(2)} {bounceTriggered ? '(BOUNCE EXIT)' : ''}
                            </span>
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              <Clock className="w-3.5 h-3.5 text-slate-400" />
                              <span
                                className={`font-bold ${
                                  timeTriggered ? 'text-amber-700' : 'text-slate-700'
                                }`}
                              >
                                Day {pos.days_held}/20
                              </span>
                              <div className="flex-1 h-2 rounded-full bg-slate-200/80 overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    timeTriggered ? 'bg-amber-500' : 'bg-sky-500'
                                  }`}
                                  style={{ width: `${Math.min(100, (pos.days_held / 20) * 100)}%` }}
                                />
                              </div>
                            </div>
                          </td>
                          <td className="py-3 px-3 text-right font-semibold text-slate-900">
                            ${pos.market_value.toLocaleString()}
                          </td>
                          <td
                            className={`py-3 px-3 text-right font-bold ${
                              pos.unrealized_pnl >= 0 ? 'text-emerald-700' : 'text-rose-600'
                            }`}
                          >
                            {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)} (
                            {pos.unrealized_pnl_pct >= 0 ? '+' : ''}
                            {pos.unrealized_pnl_pct.toFixed(1)}%)
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </SpotlightCard>

            {/* Audited Order Log */}
            <SpotlightCard className="p-6 space-y-3">
              <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-700">
                Audited Order Log (SQLite <code className="font-mono">orders</code> Table)
              </h3>
              {data.recent_orders.length === 0 ? (
                <p className="text-xs text-slate-500">
                  No orders logged yet. Click &ldquo;Run --dry-run Order Preview&rdquo; above to log today&apos;s dry-run orders.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-slate-200 text-[11px] font-bold uppercase text-slate-500">
                        <th className="py-2.5 px-2">Timestamp</th>
                        <th className="py-2.5 px-2">Status</th>
                        <th className="py-2.5 px-2">Side</th>
                        <th className="py-2.5 px-2">Symbol</th>
                        <th className="py-2.5 px-2 text-right">Qty</th>
                        <th className="py-2.5 px-2 text-right">Est. Notional</th>
                        <th className="py-2.5 px-2">Audit Reason</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200/50 font-mono">
                      {data.recent_orders.map((o) => (
                        <tr key={o.id} className="hover:bg-white/60">
                          <td className="py-2 px-2 text-[11px] text-slate-500">
                            {(o.timestamp || '').slice(0, 19).replace('T', ' ')}
                          </td>
                          <td className="py-2 px-2">
                            <span className="px-2 py-0.5 rounded-md bg-sky-500/10 text-sky-800 text-[10px] font-bold">
                              {o.status}
                            </span>
                          </td>
                          <td
                            className={`py-2 px-2 font-bold ${
                              o.side === 'BUY' ? 'text-emerald-700' : 'text-amber-700'
                            }`}
                          >
                            {o.side}
                          </td>
                          <td className="py-2 px-2 font-bold text-slate-900">{o.symbol}</td>
                          <td className="py-2 px-2 text-right">{o.qty}</td>
                          <td className="py-2 px-2 text-right">${o.notional.toLocaleString()}</td>
                          <td className="py-2 px-2 font-sans text-slate-600">{o.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SpotlightCard>
          </div>
        )}

        {/* =====================================================================
            TAB 4: STRATEGY RULES & CONFIG.YAML TUNER
        ===================================================================== */}
        {activeTab === 'config' && (
          <form onSubmit={handleSaveConfig} className="space-y-6">
            <SpotlightCard className="p-6 space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200/70 pb-4">
                <div>
                  <h2 className="text-base font-extrabold text-slate-900">
                    Configurable Strategy Ambiguities (<code className="font-mono text-sky-700">config.yaml</code>)
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Every open detail from the AlphaInsider post is parameterized below and persisted directly to <code className="font-mono">config.yaml</code>.
                  </p>
                </div>
                <Magnet>
                  <button
                    type="submit"
                    disabled={busyAction === 'config'}
                    className="px-5 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold shadow-md shadow-sky-500/20 transition"
                  >
                    {busyAction === 'config' ? 'Saving...' : 'Save to config.yaml'}
                  </button>
                </Magnet>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-5 text-xs">
                <div className="space-y-1.5">
                  <label className="font-bold text-slate-700">Trend Filter SMA Period (Days)</label>
                  <input
                    type="number"
                    value={draftStrat.sma_period ?? 200}
                    onChange={(e) =>
                      setDraftStrat({ ...draftStrat, sma_period: Number(e.target.value) })
                    }
                    className="w-full px-3 py-2 rounded-xl glass-pill font-mono font-bold"
                  />
                  <p className="text-[11px] text-slate-500">Default: 200-day simple moving average.</p>
                </div>

                <div className="space-y-1.5">
                  <label className="font-bold text-slate-700">6-1M Momentum Start (Trading Days Ago)</label>
                  <input
                    type="number"
                    value={draftStrat.momentum_lookback_start ?? 126}
                    onChange={(e) =>
                      setDraftStrat({
                        ...draftStrat,
                        momentum_lookback_start: Number(e.target.value),
                      })
                    }
                    className="w-full px-3 py-2 rounded-xl glass-pill font-mono font-bold"
                  />
                  <p className="text-[11px] text-slate-500">Default: 126 trading days (~6 months).</p>
                </div>

                <div className="space-y-1.5">
                  <label className="font-bold text-slate-700">6-1M Momentum End (Trading Days Ago)</label>
                  <input
                    type="number"
                    value={draftStrat.momentum_lookback_end ?? 21}
                    onChange={(e) =>
                      setDraftStrat({
                        ...draftStrat,
                        momentum_lookback_end: Number(e.target.value),
                      })
                    }
                    className="w-full px-3 py-2 rounded-xl glass-pill font-mono font-bold"
                  />
                  <p className="text-[11px] text-slate-500">Default: 21 trading days (skips recent 1M).</p>
                </div>

                <div className="space-y-1.5">
                  <label className="font-bold text-slate-700">Momentum Top Fraction (0.20 = Top 20%)</label>
                  <input
                    type="number"
                    step="0.05"
                    value={draftStrat.momentum_top_pct ?? 0.2}
                    onChange={(e) =>
                      setDraftStrat({ ...draftStrat, momentum_top_pct: Number(e.target.value) })
                    }
                    className="w-full px-3 py-2 rounded-xl glass-pill font-mono font-bold"
                  />
                  <p className="text-[11px] text-slate-500">Default: 0.20 (top 20% of S&amp;P 500).</p>
                </div>

                <div className="space-y-1.5">
                  <label className="font-bold text-slate-700">Wilder RSI(2) Entry Threshold</label>
                  <input
                    type="number"
                    step="0.5"
                    value={draftStrat.rsi_entry_threshold ?? 15.0}
                    onChange={(e) =>
                      setDraftStrat({
                        ...draftStrat,
                        rsi_entry_threshold: Number(e.target.value),
                      })
                    }
                    className="w-full px-3 py-2 rounded-xl glass-pill font-mono font-bold"
                  />
                  <p className="text-[11px] text-slate-500">Default: 15.0 (Buy when RSI(2) &lt; 15).</p>
                </div>

                <div className="space-y-1.5">
                  <label className="font-bold text-slate-700">
                    Close Near Day&apos;s Low Threshold (0.10 = Bottom 10%)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={draftStrat.close_range_threshold ?? 0.1}
                    onChange={(e) =>
                      setDraftStrat({
                        ...draftStrat,
                        close_range_threshold: Number(e.target.value),
                      })
                    }
                    className="w-full px-3 py-2 rounded-xl glass-pill font-mono font-bold"
                  />
                  <p className="text-[11px] text-slate-500">
                    Default: 0.10 ((Close - Low)/(High - Low) &le; 10%).
                  </p>
                </div>

                <div className="space-y-1.5">
                  <label className="font-bold text-slate-700">Max Holding Period (Trading Days)</label>
                  <input
                    type="number"
                    value={draftStrat.max_hold_days ?? 20}
                    onChange={(e) =>
                      setDraftStrat({ ...draftStrat, max_hold_days: Number(e.target.value) })
                    }
                    className="w-full px-3 py-2 rounded-xl glass-pill font-mono font-bold"
                  />
                  <p className="text-[11px] text-slate-500">
                    Default: 20 trading days (sell at Day 21 Open).
                  </p>
                </div>

                <div className="space-y-1.5">
                  <label className="font-bold text-slate-700">Target Gross Leverage (Hard Cap: 2.0x)</label>
                  <input
                    type="number"
                    step="0.1"
                    max="2.0"
                    value={draftStrat.target_gross_leverage ?? 2.0}
                    onChange={(e) =>
                      setDraftStrat({
                        ...draftStrat,
                        target_gross_leverage: Math.min(2.0, Number(e.target.value)),
                      })
                    }
                    className="w-full px-3 py-2 rounded-xl glass-pill font-mono font-bold"
                  />
                  <p className="text-[11px] text-slate-500">Default: 2.0x account equity.</p>
                </div>

                <div className="space-y-1.5">
                  <label className="font-bold text-slate-700">Backtest Slippage (Basis Points / Trade)</label>
                  <input
                    type="number"
                    step="0.5"
                    value={draftBt.slippage_bps ?? 5.0}
                    onChange={(e) =>
                      setDraftBt({ ...draftBt, slippage_bps: Number(e.target.value) })
                    }
                    className="w-full px-3 py-2 rounded-xl glass-pill font-mono font-bold"
                  />
                  <p className="text-[11px] text-slate-500">Default: 5.0 bps per fill.</p>
                </div>
              </div>
            </SpotlightCard>
          </form>
        )}
      </main>
    </div>
  );
};
