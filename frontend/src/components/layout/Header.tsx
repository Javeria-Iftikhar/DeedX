import { motion } from 'framer-motion';
import { Bell, Search } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

interface HeaderProps {
  title: string;
  subtitle?: string;
}

export function Header({ title, subtitle }: HeaderProps) {
  const { user } = useAuth();
  const initial = user?.name?.charAt(0) ?? 'U';

  return (
    <motion.header className="flex items-center justify-between mb-8">
      <motion.div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan/60 mb-1">Fiscala ERP</p>
        <h1 className="text-2xl font-bold font-[family-name:var(--font-display)] neon-text">{title}</h1>
        {subtitle && <p className="text-slate text-sm mt-1.5">{subtitle}</p>}
      </motion.div>
      <motion.div className="flex items-center gap-3">
        <motion.div className="hidden md:flex items-center gap-2 neon-card rounded-xl px-4 py-2.5">
          <Search size={16} className="text-cyan/70" />
          <input
            type="text"
            placeholder="Search operations..."
            className="bg-transparent text-sm outline-none w-48 text-light placeholder:text-slate/50"
          />
        </motion.div>
        <button
          type="button"
          className="relative p-2.5 neon-card rounded-xl glow-cyan-hover transition-all"
        >
          <Bell size={18} className="text-aqua" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-cyan rounded-full shadow-[0_0_8px_#22D3EE] animate-pulse" />
        </button>
        <motion.div className="hidden sm:flex items-center gap-3 neon-card rounded-xl px-3 py-2">
          <motion.div className="w-8 h-8 rounded-lg bg-gradient-to-br from-royal to-cyan flex items-center justify-center text-white text-sm font-bold shadow-[0_0_16px_rgba(34,211,238,0.3)]">
            {initial}
          </motion.div>
          <motion.div>
            <p className="text-sm font-medium text-light leading-tight">{user?.name}</p>
            <p className="text-[10px] text-cyan/60 capitalize tracking-wide">{user?.role}</p>
          </motion.div>
        </motion.div>
      </motion.div>
    </motion.header>
  );
}
