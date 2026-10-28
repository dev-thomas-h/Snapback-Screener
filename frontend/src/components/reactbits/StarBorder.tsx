import React from 'react';

interface StarBorderProps {
  children: React.ReactNode;
  className?: string;
  accentColor?: string;
}

/**
 * ReactBits StarBorder component: wraps high-conviction signal cards in a translucent
 * specular border with a subtle animated light sweep.
 */
export const StarBorder: React.FC<StarBorderProps> = ({
  children,
  className = '',
  accentColor = '#0284C7',
}) => {
  return (
    <div className={`relative p-[1.5px] rounded-2xl overflow-hidden group ${className}`}>
      <div
        className="absolute inset-0 opacity-75 group-hover:opacity-100 transition-opacity duration-500"
        style={{
          background: `linear-gradient(120deg, rgba(255,255,255,0.9), ${accentColor}55, rgba(16,185,129,0.35), rgba(255,255,255,0.95))`,
          backgroundSize: '200% 200%',
        }}
      />
      <div className="relative rounded-[15px] bg-white/80 backdrop-blur-2xl h-full">
        {children}
      </div>
    </div>
  );
};
