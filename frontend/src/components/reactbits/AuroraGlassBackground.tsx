import React from 'react';

/**
 * ReactBits-inspired Iridescent & Aurora Mesh Background tailored for light-toned
 * translucent glassmorphism. Renders soft pastel sky, emerald-mint, and lavender orbs
 * beneath a frosted micro-grid layer.
 */
export const AuroraGlassBackground: React.FC = () => {
  return (
    <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none bg-[#F2F6FC]">
      {/* Soft pearlescent base gradient */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(circle at 15% 15%, rgba(186, 230, 253, 0.55) 0%, transparent 45%), ' +
            'radial-gradient(circle at 85% 20%, rgba(167, 243, 208, 0.42) 0%, transparent 42%), ' +
            'radial-gradient(circle at 75% 85%, rgba(221, 214, 254, 0.45) 0%, transparent 48%), ' +
            'radial-gradient(circle at 20% 80%, rgba(254, 240, 138, 0.25) 0%, transparent 40%)',
        }}
      />

      {/* Animated floating Aurora light ribbons */}
      <div className="absolute -top-32 left-1/4 w-[38rem] h-[38rem] rounded-full bg-sky-300/35 blur-[110px] animate-aurora" />
      <div className="absolute top-1/3 -right-24 w-[34rem] h-[34rem] rounded-full bg-emerald-300/25 blur-[120px] animate-aurora-slow" />
      <div className="absolute -bottom-32 left-1/3 w-[40rem] h-[36rem] rounded-full bg-indigo-200/35 blur-[115px] animate-aurora" />

      {/* Subtle architectural dot matrix overlay */}
      <div
        className="absolute inset-0 opacity-[0.38]"
        style={{
          backgroundImage: 'radial-gradient(rgba(100, 116, 139, 0.22) 1px, transparent 1px)',
          backgroundSize: '24px 24px',
        }}
      />

      {/* Top specular daylight wash */}
      <div className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-white/70 to-transparent" />
    </div>
  );
};
