import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { Landmark, DollarSign, ArrowLeftRight, TrendingUp, AlertTriangle, Activity } from 'lucide-react';
import { Header } from '../components/layout/Header';
import { StatCard } from '../components/ui/StatCard';
import { GlassCard } from '../components/ui/GlassCard';
import { api, formatCurrency, formatDate, type DashboardStats, type LoanSummary, type AuditLog, type EconomicSummary } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import { CHART } from '../lib/chartTheme';

export function DashboardPage() {
  const { user, isOfficer, isAnalyst } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loanSummary, setLoanSummary] = useState<LoanSummary | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [economicSummary, setEconomicSummary] = useState<EconomicSummary | null>(null);

  const roleSubtitle =
    user?.role === 'admin'
      ? 'IMF system overview — sovereign loans, fiscal analytics, governance, and audit'
      : user?.role === 'officer'
        ? 'Sovereign loan operations — IMF programs, disbursements, and repayments'
        : 'Macroeconomic monitoring — member country indicators, exchange rates, and fiscal analytics';

  useEffect(() => {
    const load = async () => {
      try {
        const [s, logs] = await Promise.all([
          api.dashboardStats(),
          api.auditLogsMy().catch(() => []),
        ]);
        setStats(s);
        setAuditLogs(logs.slice(0, 8));
        if (isOfficer) {
          const ls = await api.loanSummary().catch(() => null);
          setLoanSummary(ls);
        }
        if (isAnalyst && user?.role === 'analyst') {
          const es = await api.economicSummary().catch(() => null);
          setEconomicSummary(es);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load dashboard data');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [isOfficer, isAnalyst, user?.role]);

  if (loading) {
    return (
      <motion.div className="flex flex-col items-center justify-center h-64 gap-4">
        <motion.div className="w-10 h-10 border-2 border-cyan/20 border-t-cyan rounded-full animate-spin shadow-[0_0_20px_rgba(34,211,238,0.3)]" />
        <p className="text-slate text-sm tracking-wide">Loading IMF portfolio data…</p>
      </motion.div>
    );
  }

  const pieData = loanSummary?.by_status.map(s => ({ name: s.status, value: s.count })) ?? [];
  const barData = loanSummary?.by_program.map(p => ({ name: p.program?.slice(0, 12) ?? 'N/A', amount: p.total_amount })) ?? [];

  return (
    <div>
      <Header title="Operations Dashboard" subtitle={roleSubtitle} />

      {error && (
        <div className="mb-6 neon-card rounded-xl px-4 py-3 border border-red-500/30 text-red-300 text-sm">
          {error}
        </div>
      )}

      <motion.div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5 mb-8">
        <StatCard label="Total Loans" value={stats?.total_loans ?? 0} icon={Landmark} color="cyan" delay={0} />
        <StatCard label="Active Loans" value={stats?.active_loans ?? 0} icon={TrendingUp} color="royal" delay={100} trend={`${stats?.total_countries ?? 0} member countries`} />
        <StatCard label="Disbursed" value={stats?.total_disbursed_usd ?? 0} prefix="$" icon={DollarSign} color="aqua" delay={200} />
        <StatCard label="Transactions" value={stats?.total_transactions ?? 0} icon={ArrowLeftRight} color="cyan" delay={300} />
      </motion.div>

      {user?.role === 'analyst' && economicSummary && (
        <motion.div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5 mb-8">
          <StatCard label="Avg CPI" value={Math.round(economicSummary.averages.avg_CPI)} icon={TrendingUp} color="cyan" />
          <StatCard label="Avg Inflation" value={Math.round(economicSummary.averages.avg_inflation * 100)} suffix="%" icon={Activity} color="royal" />
          <StatCard label="Avg GDP" value={Math.round(economicSummary.averages.avg_GDP)} icon={DollarSign} color="aqua" />
          <StatCard label="Avg FX Rate" value={Math.round(economicSummary.averages.avg_exchange_rate)} icon={ArrowLeftRight} color="cyan" />
        </motion.div>
      )}

      <motion.div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <GlassCard title="Disbursement vs Repayment" subtitle="Sovereign lending balance across IMF programs" className="lg:col-span-2" delay={100}>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={[
              { name: 'Disbursed', value: stats?.total_disbursed_usd ?? 0 },
              { name: 'Repaid', value: stats?.total_repaid_usd ?? 0 },
              { name: 'Outstanding', value: stats?.outstanding_balance_usd ?? 0 },
            ]}>
              <defs>
                <linearGradient id="cyanGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22D3EE" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#22D3EE" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
              <XAxis dataKey="name" tick={{ fontSize: 12, fill: CHART.axis }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 12, fill: CHART.axis }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${(v / 1e6).toFixed(0)}M`} />
              <Tooltip contentStyle={CHART.tooltip.contentStyle} labelStyle={CHART.tooltip.labelStyle} formatter={(v) => formatCurrency(Number(v))} />
              <Area type="monotone" dataKey="value" stroke="#22D3EE" fill="url(#cyanGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </GlassCard>

        <GlassCard title="Loan Status" subtitle="Sovereign loan distribution by status" delay={200}>
          {isOfficer && pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={58} outerRadius={88} dataKey="value" paddingAngle={3} stroke="rgba(5,8,22,0.8)" strokeWidth={2}>
                  {pieData.map((_, i) => <Cell key={i} fill={CHART.colors[i % CHART.colors.length]} />)}
                </Pie>
                <Tooltip contentStyle={CHART.tooltip.contentStyle} />
                <Legend wrapperStyle={{ color: '#94A3B8', fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <motion.div className="flex flex-col items-center justify-center h-60 text-slate text-sm gap-2">
              <Activity size={24} className="text-cyan/30" />
              No sovereign loan data available
            </motion.div>
          )}
        </GlassCard>
      </motion.div>

      <motion.div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {barData.length > 0 && (
          <GlassCard title="Loans by IMF Program" subtitle="Sovereign financing by program type" delay={300}>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={barData}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: CHART.axis }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: CHART.axis }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={CHART.tooltip.contentStyle} formatter={(v) => formatCurrency(Number(v))} />
                <Bar dataKey="amount" fill="url(#barGrad)" radius={[6, 6, 0, 0]} />
                <defs>
                  <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3B82F6" />
                    <stop offset="100%" stopColor="#22D3EE" />
                  </linearGradient>
                </defs>
              </BarChart>
            </ResponsiveContainer>
          </GlassCard>
        )}

        <GlassCard title="Recent Activity" subtitle="Financial governance audit feed" delay={400}>
          <motion.div className="space-y-2 max-h-60 overflow-y-auto pr-1">
            {auditLogs.length === 0 ? (
              <p className="text-slate text-sm text-center py-8">No recent activity</p>
            ) : auditLogs.map((log, i) => (
              <motion.div
                key={`${log.user_id}-${log.log_id}`}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
                className="flex items-start gap-3 p-3 rounded-xl hover:bg-cyan/5 border border-transparent hover:border-cyan/10 transition-all group"
              >
                <motion.div className="w-2 h-2 rounded-full bg-cyan mt-2 shrink-0 shadow-[0_0_8px_#22D3EE] group-hover:shadow-[0_0_12px_#22D3EE]" />
                <motion.div className="flex-1 min-w-0">
                  <p className="text-sm text-light font-medium truncate">{log.action}</p>
                  <p className="text-xs text-slate mt-0.5">
                    <span className="text-cyan/60">{log.entity_affected}</span> &middot; {formatDate(log.log_timestamp)}
                  </p>
                </motion.div>
              </motion.div>
            ))}
          </motion.div>
        </GlassCard>
      </motion.div>

      {loanSummary && loanSummary.overdue_installments > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-6 flex items-center gap-3 neon-card rounded-xl px-5 py-4 border-amber-500/20 bg-amber-500/5"
        >
          <AlertTriangle size={18} className="text-amber-400 shrink-0" />
          <p className="text-sm text-amber-200">
            <strong className="text-amber-100">{loanSummary.overdue_installments}</strong> overdue installment(s) require attention.
          </p>
        </motion.div>
      )}
    </div>
  );
}
