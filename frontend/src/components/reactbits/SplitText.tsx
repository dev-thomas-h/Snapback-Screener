import React from 'react';
import { motion } from 'framer-motion';

interface SplitTextProps {
  text: string;
  className?: string;
  delayStep?: number;
}

/**
 * ReactBits SplitText component: animates words/characters with spring physics
 * and subtle vertical slide-up.
 */
export const SplitText: React.FC<SplitTextProps> = ({
  text,
  className = '',
  delayStep = 0.035,
}) => {
  const words = text.split(' ');

  return (
    <span className={`inline-flex flex-wrap gap-x-[0.28em] ${className}`}>
      {words.map((word, wordIdx) => (
        <span key={`${word}-${wordIdx}`} className="inline-block overflow-hidden pb-0.5">
          <motion.span
            initial={{ y: '100%', opacity: 0, filter: 'blur(6px)' }}
            animate={{ y: '0%', opacity: 1, filter: 'blur(0px)' }}
            transition={{
              type: 'spring',
              damping: 22,
              stiffness: 210,
              delay: wordIdx * delayStep,
            }}
            className="inline-block"
          >
            {word}
          </motion.span>
        </span>
      ))}
    </span>
  );
};
