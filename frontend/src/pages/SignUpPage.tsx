import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Mail, Lock, User, ArrowRight, Landmark, TrendingUp } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Logo } from '../components/ui/Logo';
import { api } from '../lib/api';

type SignUpRole = 'officer' | 'economic_analyst';

const ROLE_OPTIONS: {
  role: SignUpRole;
  apiType: SignUpRole;
  label: string;
  description: string;
  icon: typeof Landmark;
}[] = [
  {
    role: 'officer',
    apiType: 'officer',
    label: 'Loan Officer',
    description: 'Manage IMF sovereign loans, disbursements, repayments, and fiscal transactions',
    icon: Landmark,
  },
  {
    role: 'economic_analyst',
    apiType: 'economic_analyst',
    label: 'Economic Analyst',
    description: 'Monitor member country indicators, exchange rates, and fiscal analytics',
    icon: TrendingUp,
  },
];

export function SignUpPage() {
  const navigate = useNavigate();
  const [selectedRole, setSelectedRole] = useState<SignUpRole>('officer');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password !== confirm) {
      setError('Passwords do not match');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }
    setLoading(true);
    try {
      await api.register({
        name,
        email,
        password,
        user_type: selectedRole,
      });
      navigate('/login', { state: { message: 'Account created. Sign in with your new credentials.' } });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
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
          <h1 className="text-2xl font-bold font-[family-name:var(--font-display)] neon-text">Create an account</h1>
          <p className="text-slate text-sm mt-2">
            Sign up for IMF Loan Officer or Economic Analyst access. Administrator accounts are provisioned separately.
          </p>
        </motion.div>

        <motion.div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-6">
          {ROLE_OPTIONS.map((opt) => {
            const Icon = opt.icon;
            const active = selectedRole === opt.role;
            return (
              <button
                key={opt.role}
                type="button"
                onClick={() => setSelectedRole(opt.role)}
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

        <form onSubmit={handleSubmit} className="neon-card rounded-2xl p-8 space-y-4 border-glow">
          {error && (
            <motion.div className="bg-red-500/10 border border-red-500/25 text-red-300 text-sm rounded-xl px-4 py-3">
              {error}
            </motion.div>
          )}

          <motion.div>
            <label className="text-slate text-xs font-semibold uppercase tracking-wider mb-2 block">Full name</label>
            <motion.div className="flex items-center gap-3 ai-input rounded-xl px-4 py-3">
              <User size={16} className="text-cyan/60 shrink-0" />
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="bg-transparent text-light text-sm outline-none flex-1"
                placeholder="Your name"
              />
            </motion.div>
          </motion.div>

          <motion.div>
            <label className="text-slate text-xs font-semibold uppercase tracking-wider mb-2 block">Email</label>
            <motion.div className="flex items-center gap-3 ai-input rounded-xl px-4 py-3">
              <Mail size={16} className="text-cyan/60 shrink-0" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="bg-transparent text-light text-sm outline-none flex-1"
                placeholder="you@institution.org"
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
                minLength={8}
                className="bg-transparent text-light text-sm outline-none flex-1"
                placeholder="Min. 8 characters"
              />
            </motion.div>
          </motion.div>

          <motion.div>
            <label className="text-slate text-xs font-semibold uppercase tracking-wider mb-2 block">Confirm password</label>
            <motion.div className="flex items-center gap-3 ai-input rounded-xl px-4 py-3">
              <Lock size={16} className="text-cyan/60 shrink-0" />
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
                className="bg-transparent text-light text-sm outline-none flex-1"
                placeholder="Repeat password"
              />
            </motion.div>
          </motion.div>

          <Button type="submit" className="w-full" size="lg" loading={loading}>
            Sign Up as {ROLE_OPTIONS.find((r) => r.role === selectedRole)?.label} <ArrowRight size={16} />
          </Button>
        </form>

        <p className="text-center text-slate text-sm mt-6">
          Already have an account?{' '}
          <Link to="/login" className="text-cyan hover:text-aqua transition-colors hover:underline">Sign In</Link>
          {' · '}
          <Link to="/" className="text-slate hover:text-light transition-colors">Home</Link>
        </p>
      </motion.div>
    </motion.div>
  );
}
