import React from 'react';
import { motion } from 'framer-motion';

interface BlurTextProps {
  text: string;
  className?: string;
  delay?: number;
}

/**
 * ReactBits BlurText component: smooth gaussian-blur to sharp focus entrance.
 */
export const BlurText: React.FC<BlurTextProps> = ({ text, className = '', delay = 0.1 }) => {
  return (
    <motion.p
      initial={{ opacity: 0, filter: 'blur(10px)', y: 8 }}
      animate={{ opacity: 1, filter: 'blur(0px)', y: 0 }}
      transition={{ duration: 0.65, delay, ease: [0.16, 1, 0.3, 1] }}
      className={className}
    >
      {text}
    </motion.p>
  );
};
