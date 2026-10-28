import React, { useState, useMemo } from 'react';
import { EquityPoint } from '../types';

interface EquityChartProps {
  data: EquityPoint[];
  initialCapital: number;
}

export const EquityChart: React.FC<EquityChartProps> = ({ data, initialCapital }) => {
  const [logScale, setLogScale] = useState<boolean>(true);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const width = 940;
  const height = 340;
  const ddHeight = 115;
  const padLeft = 68;
  const padRight = 24;
  const padTop = 20;
  const padBottom = 28;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;
  const ddPlotH = ddHeight - 12 - 24;

  const {
    stratPath,
    stratArea,
    spyPath,
    noMomPath,
    ddPath,
    ddArea,
    yTicks,
    xTicks,
    coords,
  } = useMemo(() => {
    if (!data || data.length < 2) {
      return {
        stratPath: '',
        stratArea: '',
        spyPath: '',
        noMomPath: '',
        ddPath: '',
        ddArea: '',
        yTicks: [],
        xTicks: [],
        coords: [],
      };
    }

    const transform = (val: number) =>
      logScale ? Math.log10(Math.max(val, 1)) : val;

    const allVals = data.flatMap((d) => [
      d.strategy_equity,
      d.spy_equity,
      d.no_momentum_equity,
    ]);
    const minRaw = Math.min(...allVals, initialCapital * 0.6);
    const maxRaw = Math.max(...allVals, initialCapital * 1.5);
    const minT = transform(minRaw);
    const maxT = transform(maxRaw);
    const spanT = Math.max(1e-6, maxT - minT);

    const minDD = Math.min(...data.map((d) => d.drawdown_pct), -25);

    const toX = (i: number) => padLeft + (i / (data.length - 1)) * plotW;
    const toY = (val: number) =>
      padTop + plotH - ((transform(val) - minT) / spanT) * plotH;
    const toDDY = (ddVal: number) =>
      12 + ((0 - ddVal) / Math.max(1, Math.abs(minDD))) * ddPlotH;

    const pts = data.map((d, i) => ({
      x: toX(i),
      stratY: toY(d.strategy_equity),
      spyY: toY(d.spy_equity),
      noMomY: toY(d.no_momentum_equity),
      ddY: toDDY(d.drawdown_pct),
      raw: d,
    }));

    const buildLine = (key: 'stratY' | 'spyY' | 'noMomY' | 'ddY') =>
      pts
        .map((p, idx) => `${idx === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p[key].toFixed(1)}`)
        .join(' ');

    const sPath = buildLine('stratY');
    const sArea = `${sPath} L${pts[pts.length - 1].x.toFixed(1)},${(padTop + plotH).toFixed(1)} L${pts[0].x.toFixed(1)},${(padTop + plotH).toFixed(1)} Z`;

    const dPath = buildLine('ddY');
    const dArea = `${dPath} L${pts[pts.length - 1].x.toFixed(1)},12 L${pts[0].x.toFixed(1)},12 Z`;

    const yTickValues: number[] = [];
    for (let k = 0; k <= 4; k++) {
      const frac = k / 4;
      const tVal = minT + frac * spanT;
      const rawVal = logScale ? Math.pow(10, tVal) : tVal;
      yTickValues.push(rawVal);
    }

    const xTickItems: Array<{ x: number; label: string }> = [];
    const step = Math.max(1, Math.floor((data.length - 1) / 6));
    for (let i = 0; i < data.length; i += step) {
      xTickItems.push({ x: toX(i), label: data[i].date.slice(0, 7) });
    }

    return {
      stratPath: sPath,
      stratArea: sArea,
      spyPath: buildLine('spyY'),
      noMomPath: buildLine('noMomY'),
      ddPath: dPath,
      ddArea: dArea,
      yTicks: yTickValues.map((v) => ({ val: v, y: toY(v) })),
      xTicks: xTickItems,
      coords: pts,
    };
  }, [data, logScale, initialCapital, plotW, plotH, ddPlotH]);

  if (!data || data.length < 2) {
    return (
      <div className="p-8 text-center text-slate-500">
        No equity curve points loaded yet.
      </div>
    );
  }

  const activePoint =
    hoverIdx !== null && coords[hoverIdx]
      ? coords[hoverIdx]
      : coords[coords.length - 1];

  return (
    <div className="space-y-3">
      {/* Interactive Legend & Scale Controls */}
      <div className="flex flex-wrap items-center justify-between gap-4 px-2">
        <div className="flex flex-wrap items-center gap-5 text-xs font-medium">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-sky-600 shadow-sm shadow-sky-400" />
            <span className="text-slate-700 font-semibold">Momentum Snapback:</span>
            <span className="font-mono font-bold text-sky-700">
              ${activePoint.raw.strategy_equity.toLocaleString()}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-0.5 bg-slate-500 inline-block" />
            <span className="text-slate-600">SPY Buy &amp; Hold:</span>
            <span className="font-mono font-semibold text-slate-800">
              ${activePoint.raw.spy_equity.toLocaleString()}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-0.5 bg-amber-500 inline-block" />
            <span className="text-slate-600">No-Momentum Dip Buy:</span>
            <span className="font-mono font-semibold text-amber-700">
              ${activePoint.raw.no_momentum_equity.toLocaleString()}
            </span>
          </div>
          <div className="text-slate-500 font-mono">
            Date: <strong className="text-slate-800">{activePoint.raw.date}</strong> | DD:{' '}
            <strong className="text-rose-600">{activePoint.raw.drawdown_pct.toFixed(1)}%</strong> | Lev:{' '}
            <strong className="text-indigo-600">{activePoint.raw.gross_leverage.toFixed(2)}x</strong>
          </div>
        </div>

        <div className="inline-flex rounded-xl p-1 bg-white/70 border border-white/90 shadow-sm">
          <button
            onClick={() => setLogScale(true)}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition ${
              logScale ? 'bg-sky-600 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Log Scale
          </button>
          <button
            onClick={() => setLogScale(false)}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition ${
              !logScale ? 'bg-sky-600 text-white shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Linear
          </button>
        </div>
      </div>

      {/* Main Equity SVG */}
      <div className="relative rounded-2xl bg-white/55 border border-white/85 p-3 shadow-inner">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto overflow-visible select-none"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const relX = ((e.clientX - rect.left) / rect.width) * width;
            const ratio = Math.max(0, Math.min(1, (relX - padLeft) / plotW));
            const idx = Math.round(ratio * (coords.length - 1));
            setHoverIdx(idx);
          }}
          onMouseLeave={() => setHoverIdx(null)}
        >
          <defs>
            <linearGradient id="stratGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#0284C7" stopOpacity="0.26" />
              <stop offset="100%" stopColor="#0284C7" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Horizontal Y gridlines */}
          {yTicks.map((t, i) => (
            <g key={i}>
              <line
                x1={padLeft}
                x2={width - padRight}
                y1={t.y}
                y2={t.y}
                stroke="#CBD5E1"
                strokeDasharray="4 4"
                strokeWidth="1"
              />
              <text
                x={padLeft - 8}
                y={t.y + 4}
                textAnchor="end"
                className="fill-slate-500 text-[10px] font-mono"
              >
                ${t.val >= 1000 ? `${(t.val / 1000).toFixed(1)}k` : t.val.toFixed(0)}
              </text>
            </g>
          ))}

          {/* X axis labels */}
          {xTicks.map((xt, i) => (
            <text
              key={i}
              x={xt.x}
              y={height - 6}
              textAnchor="middle"
              className="fill-slate-500 text-[10px] font-mono"
            >
              {xt.label}
            </text>
          ))}

          {/* Area & curves */}
          <path d={stratArea} fill="url(#stratGrad)" />
          <path
            d={noMomPath}
            fill="none"
            stroke="#F59E0B"
            strokeWidth="1.6"
            strokeOpacity="0.85"
          />
          <path
            d={spyPath}
            fill="none"
            stroke="#64748B"
            strokeWidth="1.8"
            strokeDasharray="5 4"
          />
          <path
            d={stratPath}
            fill="none"
            stroke="#0284C7"
            strokeWidth="2.6"
            strokeLinecap="round"
          />

          {/* Hover crosshair */}
          {activePoint && (
            <g>
              <line
                x1={activePoint.x}
                x2={activePoint.x}
                y1={padTop}
                y2={padTop + plotH}
                stroke="#0EA5E9"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
              <circle
                cx={activePoint.x}
                cy={activePoint.stratY}
                r="4.5"
                fill="#0284C7"
                stroke="#FFFFFF"
                strokeWidth="2"
              />
              <circle
                cx={activePoint.x}
                cy={activePoint.spyY}
                r="3.5"
                fill="#64748B"
                stroke="#FFFFFF"
                strokeWidth="1.5"
              />
            </g>
          )}
        </svg>

        {/* Underwater Drawdown Subchart */}
        <svg viewBox={`0 0 ${width} ${ddHeight}`} className="w-full h-auto mt-1 select-none">
          <defs>
            <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#F43F5E" stopOpacity="0.06" />
              <stop offset="100%" stopColor="#F43F5E" stopOpacity="0.28" />
            </linearGradient>
          </defs>
          <line
            x1={padLeft}
            x2={width - padRight}
            y1={12}
            y2={12}
            stroke="#CBD5E1"
            strokeWidth="1"
          />
          <text
            x={padLeft - 8}
            y={16}
            textAnchor="end"
            className="fill-slate-400 text-[10px] font-mono"
          >
            0% DD
          </text>
          <path d={ddArea} fill="url(#ddGrad)" />
          <path d={ddPath} fill="none" stroke="#E11D48" strokeWidth="1.5" />
          {activePoint && (
            <circle
              cx={activePoint.x}
              cy={activePoint.ddY}
              r="3.5"
              fill="#E11D48"
              stroke="#FFFFFF"
              strokeWidth="1.5"
            />
          )}
        </svg>
      </div>
    </div>
  );
};
