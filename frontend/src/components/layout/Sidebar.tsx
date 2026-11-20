import { NavLink, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  LayoutDashboard, Landmark, TrendingUp, ArrowLeftRight,
  Shield, Database, LogOut, ChevronLeft, ChevronRight, Sparkles,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useState } from 'react';
import { Logo } from '../ui/Logo';

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard', roles: ['admin', 'officer', 'analyst'] },
  { to: '/loans', icon: Landmark, label: 'Sovereign Loans', roles: ['admin', 'officer'] },
  { to: '/economic', icon: TrendingUp, label: 'Macro Indicators', roles: ['admin', 'analyst'] },
  { to: '/transactions', icon: ArrowLeftRight, label: 'Fiscal Ledger', roles: ['admin', 'officer'] },
  { to: '/analytics', icon: Sparkles, label: 'Fiscal Analytics', roles: ['admin', 'officer', 'analyst'] },
  { to: '/audit', icon: Shield, label: 'Governance Audit', roles: ['admin', 'officer', 'analyst'] },
  { to: '/admin', icon: Database, label: 'IMF Data Admin', roles: ['admin'] },
];

export function Sidebar() {
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();

  const visible = navItems.filter(item => user && item.roles.includes(user.role));

  return (
    <motion.aside
      animate={{ width: collapsed ? 72 : 260 }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
      className="gradient-sidebar fixed left-0 top-0 h-screen z-40 flex flex-col"
    >
      <motion.div className="flex items-center px-3 py-4 border-b border-cyan/10 min-h-[88px]">
        {!collapsed ? <Logo className="max-w-[240px]" /> : <Logo variant="icon" className="mx-auto" />}
      </motion.div>

      <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
        {visible.map((item) => {
          const active = location.pathname === item.to;
          return (
            <NavLink key={item.to} to={item.to}>
              <motion.div
                whileHover={{ x: 4, boxShadow: '0 0 20px rgba(34,211,238,0.12)' }}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200 ${
                  active
                    ? 'bg-cyan/10 text-cyan shadow-[0_0_24px_rgba(34,211,238,0.15)] border border-cyan/25'
                    : 'text-slate hover:text-light hover:bg-white/5 border border-transparent'
                }`}
              >
                <item.icon size={20} className={`shrink-0 ${active ? 'drop-shadow-[0_0_6px_rgba(34,211,238,0.8)]' : ''}`} />
                {!collapsed && <span className="text-sm font-medium">{item.label}</span>}
                {active && !collapsed && (
                  <motion.div layoutId="nav-dot" className="ml-auto w-1.5 h-1.5 rounded-full bg-cyan shadow-[0_0_10px_#22D3EE]" />
                )}
              </motion.div>
            </NavLink>
          );
        })}
      </nav>

      <motion.div className="p-3 border-t border-cyan/10">
        {!collapsed && user && (
          <motion.div className="px-3 py-2 mb-2 rounded-xl bg-white/3 border border-white/5">
            <p className="text-light text-sm font-medium truncate">{user.name}</p>
            <p className="text-cyan/50 text-xs capitalize">{user.role}</p>
          </motion.div>
        )}
        <button
          onClick={logout}
          className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-slate hover:text-red-400 hover:bg-red-500/10 transition-all"
        >
          <LogOut size={18} />
          {!collapsed && <span className="text-sm">Sign Out</span>}
        </button>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center w-full mt-1 py-2 text-slate/50 hover:text-cyan transition-colors"
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </motion.div>
    </motion.aside>
  );
}
