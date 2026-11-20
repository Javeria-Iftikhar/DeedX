import { motion } from 'framer-motion';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  children: ReactNode;
  loading?: boolean;
}

export function Button({ variant = 'primary', size = 'md', children, loading, className = '', disabled, ...props }: ButtonProps) {
  const base = 'inline-flex items-center justify-center gap-2 font-semibold rounded-xl transition-all duration-300 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed';
  const variants = {
    primary: 'bg-gradient-to-r from-royal to-cyan text-white shadow-[0_0_24px_rgba(34,211,238,0.25)] hover:shadow-[0_0_36px_rgba(34,211,238,0.4)] border border-cyan/20',
    secondary: 'bg-navy text-light hover:bg-navy-light shadow-md border border-cyan/10',
    ghost: 'text-slate hover:text-light hover:bg-white/5',
    outline: 'border border-cyan/30 text-aqua hover:border-cyan hover:shadow-[0_0_24px_rgba(34,211,238,0.2)] bg-transparent',
  };
  const sizes = { sm: 'px-3 py-1.5 text-sm', md: 'px-5 py-2.5 text-sm', lg: 'px-7 py-3.5 text-base' };

  return (
    <motion.div whileHover={{ scale: disabled || loading ? 1 : 1.02 }} whileTap={{ scale: disabled || loading ? 1 : 0.98 }}>
      <button
        className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? (
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
        ) : children}
      </button>
    </motion.div>
  );
}
