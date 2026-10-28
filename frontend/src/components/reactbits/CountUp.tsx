import React, { useEffect, useState } from 'react';
import { useSpring, useMotionValue } from 'framer-motion';

interface CountUpProps {
  to: number;
  from?: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
  separator?: string;
}

/**
 * ReactBits CountUp component: spring-interpolated numerical counter for financial KPIs.
 */
export const CountUp: React.FC<CountUpProps> = ({
  to,
  from = 0,
  decimals = 2,
  prefix = '',
  suffix = '',
  className = '',
  separator = ',',
}) => {
  const motionValue = useMotionValue(from);
  const springValue = useSpring(motionValue, {
    damping: 28,
    stiffness: 140,
  });
  const [display, setDisplay] = useState<string>(() => formatNum(to, decimals, separator));

  useEffect(() => {
    motionValue.set(to);
  }, [to, motionValue]);

  useEffect(() => {
    const unsubscribe = springValue.on('change', (latest) => {
      setDisplay(formatNum(latest, decimals, separator));
    });
    return () => unsubscribe();
  }, [springValue, decimals, separator]);

  return (
    <span className={`tabular-nums ${className}`}>
      {prefix}
      {display}
      {suffix}
    </span>
  );
};

function formatNum(val: number, decimals: number, separator: string): string {
  if (Number.isNaN(val)) return '0';
  const fixed = val.toFixed(decimals);
  const parts = fixed.split('.');
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, separator);
  return parts.join('.');
}
