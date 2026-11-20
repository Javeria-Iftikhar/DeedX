import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, Shield, Globe2, BarChart3, Landmark, Sparkles } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Logo } from '../components/ui/Logo';
import { api, formatCompactUsd, formatNumber, type PublicStats } from '../lib/api';

const features = [
  { icon: Landmark, title: 'Sovereign Loan Management', desc: 'Manage IMF loan programs, sovereign disbursements, repayment schedules, and installment tracking for member countries.' },
  { icon: BarChart3, title: 'Economic Analytics', desc: 'Monitor GDP, inflation, CPI, exchange rates, and macroeconomic indicators across participating countries in real time.' },
  { icon: Shield, title: 'Financial Governance', desc: 'Ensure transparency through audit logs, role-based access control, and secure financial activity monitoring.' },
  { icon: Sparkles, title: 'AI-Powered Insights', desc: 'Generate intelligent fiscal insights, repayment analysis, and economic summaries using AI-driven financial analytics.' },
];

export function LandingPage() {
  const navigate = useNavigate();
  const [mounted, setMounted] = useState(false);
  const [stats, setStats] = useState<PublicStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState<string | null>(null);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    let cancelled = false;
    setStatsLoading(true);
    setStatsError(null);
    api.publicStats()
      .then((data) => {
        if (!cancelled) {
          setStats(data);
          setStatsLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setStats(null);
          setStatsError(e instanceof Error ? e.message : 'Could not load live stats');
          setStatsLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, []);

  const placeholder = '…';

  const heroKpis = stats
    ? [
        { label: 'Total Loans', val: formatNumber(stats.total_loans) },
        { label: 'Active Loans', val: formatNumber(stats.active_loans) },
        { label: 'Disbursed', val: formatCompactUsd(stats.total_disbursed_usd) },
        { label: 'Repayment Rate', val: `${stats.repayment_rate_pct}%` },
      ]
    : null;

  const bottomKpis = stats
    ? [
        { val: formatCompactUsd(stats.total_portfolio_usd), label: 'Portfolio (imf_db)' },
        { val: String(stats.total_countries), label: 'Member Countries' },
        { val: formatCompactUsd(stats.total_repaid_usd), label: 'Total Repaid' },
        { val: formatNumber(stats.audit_log_count), label: 'Audit Log Entries' },
      ]
    : null;

  const chartBars =
    stats && stats.portfolio_by_country.length > 0
      ? (() => {
          const withLoans = stats.portfolio_by_country.filter((c) => c.amount > 0 && c.label);
          const max = Math.max(...withLoans.map((x) => x.amount), 1);
          return withLoans.map((c) => ({
            label: c.label,
            height: Math.max(4, Math.round((c.amount / max) * 100)),
          }));
        })()
      : null;

  return (
    <motion.div className="min-h-screen dashboard-canvas relative overflow-hidden">
      <div className="ambient-orb ambient-orb-cyan" aria-hidden="true" />
      <div className="ambient-orb ambient-orb-blue" style={{ left: '5%', right: 'auto' }} aria-hidden="true" />

      <header className="relative z-10 border-b border-cyan/10">
        <nav className="flex items-center justify-between max-w-6xl mx-auto w-full px-6 lg:px-8 py-4">
          <Link to="/" className="flex items-center shrink-0">
            <Logo />
          </Link>
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={() => navigate('/signup')}>Sign Up</Button>
            <Button onClick={() => navigate('/login')}>Sign In <ArrowRight size={16} /></Button>
          </div>
        </nav>
      </header>

      <section className="relative z-10 max-w-6xl mx-auto px-6 lg:px-8 py-14 md:py-20 lg:py-24">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={mounted ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.5 }}
            className="text-center lg:text-left"
          >
            <div className="flex justify-center lg:justify-start mb-7 md:mb-8">
              <Logo variant="lead" />
            </div>

            <motion.div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full neon-card text-cyan text-xs font-semibold uppercase tracking-widest mb-6">
              <Globe2 size={14} /> IMF Loan Management ERP
            </motion.div>

            <h1 className="text-4xl sm:text-5xl lg:text-[3.25rem] font-extrabold font-[family-name:var(--font-display)] leading-[1.08] mb-6">
              <span className="text-light">Modernizing IMF</span>
              <br />
              <span className="neon-text">Loan Operations</span>
            </h1>

            <p className="text-base sm:text-lg text-slate max-w-lg mx-auto lg:mx-0 mb-9 leading-relaxed">
              Fiscala centralizes sovereign lending, loan disbursements, repayment tracking,
              economic indicators, and fiscal analytics in one IMF-style ERP for international
              monetary operations and global financial stability.
            </p>

            <div className="flex flex-col sm:flex-row items-center lg:items-start justify-center lg:justify-start gap-3 sm:gap-4">
              <Button size="lg" variant="outline" onClick={() => navigate('/signup')}>
                Sign Up
              </Button>
              <Button size="lg" onClick={() => navigate('/login')}>
                Sign In <ArrowRight size={18} />
              </Button>
            </div>
            <p className="text-xs text-slate mt-4 max-w-md mx-auto lg:mx-0">
              Registration is open to IMF Loan Officers and Economic Analysts. System administrators use dedicated credentials.
            </p>
            {statsError && (
              <p className="text-xs text-amber-400/90 mt-3 max-w-md mx-auto lg:mx-0">
                Live stats unavailable — start the API: <code className="text-cyan/80">uvicorn app.main:app --reload</code>
              </p>
            )}
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={mounted ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.55, delay: 0.12 }}
            className="hidden lg:block"
          >
            <div className="hero-preview neon-card rounded-2xl border-glow p-5 shadow-[0_24px_80px_rgba(0,0,0,0.45)]">
              <motion.div className="flex items-center justify-between mb-4 pb-3 border-b border-cyan/10">
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-cyan/70 font-semibold">Live Overview</p>
                  <p className="text-light font-semibold text-sm mt-0.5">IMF Loan Portfolio</p>
                </div>
                <span className="text-[10px] px-2 py-1 rounded-full bg-cyan/10 text-cyan border border-cyan/20">
                  {statsLoading ? 'Loading…' : 'Live from imf_db'}
                </span>
              </motion.div>
              <div className="grid grid-cols-2 gap-3 mb-4">
                {(heroKpis ?? [
                  { label: 'Total Loans', val: statsLoading ? placeholder : '—' },
                  { label: 'Active Loans', val: statsLoading ? placeholder : '—' },
                  { label: 'Disbursed', val: statsLoading ? placeholder : '—' },
                  { label: 'Repayment Rate', val: statsLoading ? placeholder : '—' },
                ]).map((item) => (
                  <div key={item.label} className="rounded-xl bg-royal/30 border border-cyan/10 p-3">
                    <p className="text-[10px] text-slate uppercase tracking-wide">{item.label}</p>
                    <p className="text-lg font-bold text-cyan font-[family-name:var(--font-display)] mt-1">{item.val}</p>
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-slate mb-2">Sovereign loan portfolio by member country</p>
              <div className="rounded-xl bg-royal/20 border border-cyan/10 p-4 h-28 flex items-end gap-1.5">
                {statsLoading ? (
                  <div className="w-full h-full flex items-center justify-center text-xs text-slate">Loading chart…</div>
                ) : chartBars ? (
                  chartBars.map((bar) => (
                    <div
                      key={bar.label}
                      title={`${bar.label}: ${formatCompactUsd(stats!.portfolio_by_country.find((c) => c.label === bar.label)?.amount ?? 0)}`}
                      className="flex-1 rounded-sm bg-gradient-to-t from-cyan/30 to-cyan/80 min-w-[6px]"
                      style={{ height: `${bar.height}%` }}
                    />
                  ))
                ) : (
                  <div className="w-full text-center text-xs text-slate">No loan data — start API to load imf_db</div>
                )}
              </div>
            </div>
          </motion.div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={mounted ? { opacity: 1, y: 0 } : {}}
          transition={{ delay: 0.2, duration: 0.5 }}
          className="mt-16 md:mt-20 grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4"
        >
          {(bottomKpis ?? [
            { val: statsLoading ? placeholder : '—', label: 'Portfolio (imf_db)' },
            { val: statsLoading ? placeholder : '—', label: 'Member Countries' },
            { val: statsLoading ? placeholder : '—', label: 'Total Repaid' },
            { val: statsLoading ? placeholder : '—', label: 'Audit Log Entries' },
          ]).map((s) => (
            <motion.div
              key={s.label}
              className="neon-card rounded-2xl p-5 border-glow glow-cyan-hover"
              whileHover={{ y: -6 }}
            >
              <p className="text-2xl font-bold text-cyan font-[family-name:var(--font-display)] shadow-[0_0_20px_rgba(34,211,238,0.2)]">{s.val}</p>
              <p className="text-slate text-sm mt-1">{s.label}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      <section className="relative z-10 py-24 px-6 border-t border-cyan/10">
        <div className="max-w-6xl mx-auto">
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan/60 text-center mb-2">IMF Operations</p>
          <h2 className="text-3xl font-bold text-center font-[family-name:var(--font-display)] mb-4 neon-text">Sovereign Finance Capabilities</h2>
          <p className="text-slate text-center mb-14 max-w-xl mx-auto">
            End-to-end tools for country-level financial programs, fiscal operations, and macroeconomic monitoring across the international lending system.
          </p>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {features.map((f, i) => (
              <motion.div
                key={f.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.1 }}
                whileHover={{ y: -8 }}
                className="neon-card rounded-2xl p-6 glow-cyan-hover border-glow transition-all duration-300"
              >
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan/20 to-royal/20 flex items-center justify-center mb-4 border border-cyan/20 shadow-[0_0_16px_rgba(34,211,238,0.12)]">
                  <f.icon size={22} className="text-aqua" />
                </div>
                <h3 className="font-semibold text-light mb-2">{f.title}</h3>
                <p className="text-sm text-slate leading-relaxed">{f.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <footer className="relative z-10 py-8 text-center text-slate text-sm border-t border-cyan/10">
        <p>&copy; 2026 Fiscala. IMF Loan Management &amp; Fiscal Analytics Platform.</p>
      </footer>
    </motion.div>
  );
}
