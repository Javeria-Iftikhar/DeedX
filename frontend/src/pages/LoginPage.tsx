import { useState } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Mail, Lock, ArrowRight, Shield, Landmark, TrendingUp } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/Button';
import { Logo } from '../components/ui/Logo';
import type { UserRole } from '../lib/api';

const ROLE_OPTIONS: {
  role: UserRole;
  label: string;
  description: string;
  email: string;
  password: string;
  icon: typeof Shield;
}[] = [
  {
    role: 'admin',
    label: 'Admin',
    description: 'Full system access and IMF data admin',
    email: 'ali@imf.org',
    password: 'ali123',
    icon: Shield,
  },
  {
    role: 'officer',
    label: 'Loan Officer',
    description: 'Loans, disbursements, and repayments',
    email: 'sara@imf.org',
    password: 'sara123',
    icon: Landmark,
  },
  {
    role: 'analyst',
    label: 'Economic Analyst',
    description: 'Indicators and fiscal analytics',
    email: 'fatima@imf.org',
    password: 'fatima123',
    icon: TrendingUp,
  },
];

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const successMessage = (location.state as { message?: string } | null)?.message;
  const [selectedRole, setSelectedRole] = useState<UserRole>('admin');
  const [email, setEmail] = useState(ROLE_OPTIONS[0].email);
  const [password, setPassword] = useState(ROLE_OPTIONS[0].password);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const selectRole = (role: UserRole) => {
    const opt = ROLE_OPTIONS.find((r) => r.role === role)!;
    setSelectedRole(role);
    setEmail(opt.email);
    setPassword(opt.password);
    setError('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password, selectedRole);
      navigate('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div className="min-h-screen dashboard-canvas flex items-center justify-center p-6 relative overflow-hidden">
      <motion.div className="ambient-orb ambient-orb-cyan" aria-hidden="true" />
      <motion.div className="ambient-orb ambient-orb-blue" style={{ left: '60%' }} aria-hidden="true" />

      <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} className="relative z-10 w-full max-w-lg">
        <motion.div className="text-center mb-6">
          <Link to="/" className="inline-flex justify-center mb-5">
            <Logo variant="lead" />
          </Link>
          <h1 className="text-2xl font-bold font-[family-name:var(--font-display)] neon-text">Sign in to Fiscala</h1>
          <p className="text-slate text-sm mt-2">Access the IMF Loan Management ERP</p>
        </motion.div>

        <motion.div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-6">
          {ROLE_OPTIONS.map((opt) => {
            const Icon = opt.icon;
            const active = selectedRole === opt.role;
            return (
              <button
                key={opt.role}
                type="button"
                onClick={() => selectRole(opt.role)}
                className={`text-left rounded-xl p-3 border transition-all ${
                  active
                    ? 'border-cyan/40 bg-cyan/10 shadow-[0_0_20px_rgba(34,211,238,0.12)]'
                    : 'border-cyan/10 bg-white/3 hover:border-cyan/25'
                }`}
              >
                <Icon size={18} className={active ? 'text-cyan mb-2' : 'text-slate mb-2'} />
                <p className={`text-sm font-semibold ${active ? 'text-light' : 'text-slate'}`}>{opt.label}</p>
                <p className="text-[10px] text-slate mt-1 leading-snug">{opt.description}</p>
              </button>
            );
          })}
        </motion.div>

        <form onSubmit={handleSubmit} className="neon-card rounded-2xl p-8 space-y-5 border-glow">
          {successMessage && (
            <motion.div className="bg-cyan/10 border border-cyan/25 text-cyan text-sm rounded-xl px-4 py-3">
              {successMessage}
            </motion.div>
          )}
          {error && (
            <motion.div className="bg-red-500/10 border border-red-500/25 text-red-300 text-sm rounded-xl px-4 py-3">
              {error}
            </motion.div>
          )}

          <motion.div>
            <label className="text-slate text-xs font-semibold uppercase tracking-wider mb-2 block">Email</label>
            <motion.div className="flex items-center gap-3 ai-input rounded-xl px-4 py-3">
              <Mail size={16} className="text-cyan/60 shrink-0" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="bg-transparent text-light text-sm outline-none flex-1 placeholder:text-slate/50"
              />
            </motion.div>
          </motion.div>

          <motion.div>
            <label className="text-slate text-xs font-semibold uppercase tracking-wider mb-2 block">Password</label>
            <motion.div className="flex items-center gap-3 ai-input rounded-xl px-4 py-3">
              <Lock size={16} className="text-cyan/60 shrink-0" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="bg-transparent text-light text-sm outline-none flex-1 placeholder:text-slate/50"
              />
            </motion.div>
          </motion.div>

          <Button type="submit" className="w-full" size="lg" loading={loading}>
            Sign In as {ROLE_OPTIONS.find((r) => r.role === selectedRole)?.label} <ArrowRight size={16} />
          </Button>
        </form>

        <p className="text-center text-slate text-sm mt-6">
          Need an account?{' '}
          <Link to="/signup" className="text-cyan hover:text-aqua transition-colors hover:underline">Sign Up</Link>
          {' · '}
          <Link to="/" className="text-slate hover:text-light transition-colors">Home</Link>
        </p>
      </motion.div>
    </motion.div>
  );
}
