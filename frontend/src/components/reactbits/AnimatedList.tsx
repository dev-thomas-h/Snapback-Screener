import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface AnimatedListProps {
  children: React.ReactNode[];
  className?: string;
}

/**
 * ReactBits AnimatedList component: staggered spring entrance for signal rows and trade cards.
 */
export const AnimatedList: React.FC<AnimatedListProps> = ({ children, className = '' }) => {
  return (
    <div className={className}>
      <AnimatePresence initial={false}>
        {React.Children.map(children, (child, idx) => (
          <motion.div
            key={(child as React.ReactElement)?.key ?? idx}
            initial={{ opacity: 0, y: 12, scale: 0.99 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.99 }}
            transition={{
              type: 'spring',
              stiffness: 260,
              damping: 25,
              delay: Math.min(idx * 0.035, 0.35),
            }}
          >
            {child}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
};
