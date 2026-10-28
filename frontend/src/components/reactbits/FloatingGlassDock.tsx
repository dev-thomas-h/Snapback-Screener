import React from 'react';
import { motion } from 'framer-motion';
import {
  Radar,
  LineChart,
  ShieldAlert,
  Sliders,
} from 'lucide-react';

export type NavTab = 'screener' | 'backtest' | 'trader' | 'config';

interface FloatingGlassDockProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  entrySignalCount: number;
  killSwitchActive: boolean;
}

/**
 * ReactBits-inspired Floating Glass Dock with spring layoutId pill transitions.
 */
export const FloatingGlassDock: React.FC<FloatingGlassDockProps> = ({
  activeTab,
  onSelectTab,
  entrySignalCount,
  killSwitchActive,
}) => {
  const items: Array<{
    id: NavTab;
    label: string;
    icon: React.ReactNode;
    badge?: string | number;
    badgeColor?: string;
  }> = [
    {
      id: 'screener',
      label: 'Daily Screener & Radar',
      icon: <Radar className="w-4 h-4" />,
      badge: entrySignalCount > 0 ? `${entrySignalCount} BUY` : undefined,
      badgeColor: 'bg-emerald-500/15 text-emerald-700 border-emerald-500/30',
    },
    {
      id: 'backtest',
      label: 'Backtest & Claim Validator',
      icon: <LineChart className="w-4 h-4" />,
    },
    {
      id: 'trader',
      label: 'Paper Trader & Risk Vault',
      icon: <ShieldAlert className="w-4 h-4" />,
      badge: killSwitchActive ? 'HALTED' : 'PAPER',
      badgeColor: killSwitchActive
        ? 'bg-rose-500/15 text-rose-700 border-rose-500/30'
        : 'bg-sky-500/15 text-sky-700 border-sky-500/30',
    },
    {
      id: 'config',
      label: 'Strategy Rules & Config',
      icon: <Sliders className="w-4 h-4" />,
    },
  ];

  return (
    <nav className="inline-flex items-center gap-1.5 p-1.5 rounded-2xl glass-panel">
      {items.map((item) => {
        const isActive = activeTab === item.id;
        return (
          <button
            key={item.id}
            onClick={() => onSelectTab(item.id)}
            className={`relative flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-colors duration-200 ${
              isActive
                ? 'text-slate-900'
                : 'text-slate-600 hover:text-slate-900 hover:bg-white/40'
            }`}
          >
            {isActive && (
              <motion.div
                layoutId="glass-dock-pill"
                className="absolute inset-0 rounded-xl bg-white/90 border border-white shadow-[0_4px_16px_rgba(14,165,233,0.12)]"
                transition={{ type: 'spring', stiffness: 320, damping: 28 }}
              />
            )}
            <span className="relative z-10 flex items-center gap-2">
              <span className={isActive ? 'text-sky-600' : 'text-slate-500'}>
                {item.icon}
              </span>
              <span>{item.label}</span>
              {item.badge !== undefined && (
                <span
                  className={`px-2 py-0.5 text-[11px] font-mono font-bold rounded-full border ${
                    item.badgeColor || 'bg-slate-100 text-slate-700 border-slate-200'
                  }`}
                >
                  {item.badge}
                </span>
              )}
            </span>
          </button>
        );
      })}
    </nav>
  );
};
