import { motion } from 'framer-motion';
import type { ReactNode } from 'react';

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  delay?: number;
  variant?: 'default' | 'ai';
}

export function GlassCard({ children, className = '', title, subtitle, action, delay = 0, variant = 'default' }: GlassCardProps) {
  const cardClass = variant === 'ai' ? 'ai-panel' : 'neon-card';

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: delay / 1000, duration: 0.45 }}
      whileHover={{ y: variant === 'default' ? -2 : 0 }}
      className={`${cardClass} rounded-2xl p-6 relative ${className}`}
    >
      {(title || action) && (
        <motion.div className="flex items-start justify-between mb-5 relative z-10">
          <motion.div>
            {title && (
              <h3 className="text-base font-semibold font-[family-name:var(--font-display)] text-light">{title}</h3>
            )}
            {subtitle && <p className="text-sm text-slate mt-0.5">{subtitle}</p>}
          </motion.div>
          {action}
        </motion.div>
      )}
      <motion.div className="relative z-10">{children}</motion.div>
    </motion.div>
  );
}
