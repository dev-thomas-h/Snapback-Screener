import React from 'react';

interface ShinyTextProps {
  text: string;
  className?: string;
}

/**
 * ReactBits ShinyText component: animated metallic/iridescent shimmer text.
 */
export const ShinyText: React.FC<ShinyTextProps> = ({ text, className = '' }) => {
  return (
    <span
      className={`inline-block bg-clip-text text-transparent bg-[linear-gradient(110deg,#0369A1,35%,#38BDF8,50%,#059669,65%,#0369A1)] bg-[length:200%_100%] animate-shimmer ${className}`}
    >
      {text}
    </span>
  );
};
