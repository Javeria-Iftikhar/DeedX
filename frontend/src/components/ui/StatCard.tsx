import { motion } from 'framer-motion';
import type { LucideIcon } from 'lucide-react';
import { useEffect, useState } from 'react';

interface StatCardProps {
  label: string;
  value: number;
  prefix?: string;
  suffix?: string;
  icon: LucideIcon;
  trend?: string;
  color?: 'cyan' | 'royal' | 'aqua';
  delay?: number;
}

export function StatCard({ label, value, prefix = '', suffix = '', icon: Icon, trend, color = 'cyan', delay = 0 }: StatCardProps) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const duration = 1200;
    const start = performance.now();
    const animate = (now: number) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.round(value * eased));
      if (progress < 1) requestAnimationFrame(animate);
    };
    const timer = setTimeout(() => requestAnimationFrame(animate), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  const colors = {
    cyan: 'from-cyan/25 to-cyan/5 text-cyan border-cyan/30 shadow-[0_0_16px_rgba(34,211,238,0.15)]',
    royal: 'from-royal/25 to-royal/5 text-aqua border-royal/30 shadow-[0_0_16px_rgba(59,130,246,0.15)]',
    aqua: 'from-aqua/20 to-aqua/5 text-aqua border-aqua/25 shadow-[0_0_16px_rgba(125,211,252,0.12)]',
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: delay / 1000, duration: 0.5 }}
      whileHover={{ y: -6, transition: { duration: 0.2 } }}
      className="neon-card rounded-2xl p-5 border-glow glow-cyan-hover transition-all duration-300"
    >
      <motion.div className={`inline-flex p-2.5 rounded-xl bg-gradient-to-br ${colors[color]} border mb-4`}>
        <Icon size={20} />
      </motion.div>
      <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-slate mb-1.5">{label}</p>
      <p className="text-2xl font-bold font-[family-name:var(--font-display)] text-light">
        {prefix}{display.toLocaleString()}{suffix}
      </p>
      {trend && <p className="text-xs text-cyan/70 mt-2 font-medium">{trend}</p>}
    </motion.div>
  );
}
