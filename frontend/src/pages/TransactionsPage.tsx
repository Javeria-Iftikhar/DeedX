import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Header } from '../components/layout/Header';
import { GlassCard } from '../components/ui/GlassCard';
import { FullDataTable } from '../components/ui/FullDataTable';
import { api, formatCurrency, type FinancialTransaction } from '../lib/api';

const typeColors: Record<string, string> = {
  DISBURSEMENT: 'badge-active',
  REPAYMENT: 'badge-active',
  ADJUSTMENT: 'badge-warning',
};

export function TransactionsPage() {
  const [txns, setTxns] = useState<FinancialTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.transactions()
      .then(setTxns)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load transactions'))
      .finally(() => setLoading(false));
  }, []);

  const totalVolume = txns.reduce((s, t) => s + Number(t.amount), 0);

  return (
    <motion.div>
      <Header title="Fiscal Transactions" subtitle="Sovereign disbursement and repayment ledger" />

      {error && (
        <motion.div className="mb-6 neon-card rounded-xl px-4 py-3 border border-red-500/30 text-red-300 text-sm">{error}</motion.div>
      )}

      <motion.div className="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-8">
        {[
          { label: 'Total Volume', val: formatCurrency(totalVolume) },
          { label: 'Transactions', val: txns.length },
          { label: 'Types', val: new Set(txns.map(t => t.transaction_type)).size },
        ].map((kpi, i) => (
          <motion.div key={kpi.label} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }} className="neon-card rounded-2xl p-5 glow-cyan-hover">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate mb-1">{kpi.label}</p>
            <p className="text-2xl font-bold text-light font-[family-name:var(--font-display)]">{kpi.val}</p>
          </motion.div>
        ))}
      </motion.div>

      <GlassCard title="Transaction History" subtitle={`${txns.length} rows — all financialtransaction columns`}>
        {loading ? (
          <motion.div className="flex justify-center py-16"><motion.div className="w-8 h-8 border-2 border-cyan/30 border-t-cyan rounded-full animate-spin" /></motion.div>
        ) : (
          <FullDataTable
            rows={txns as unknown as Record<string, unknown>[]}
            rowKey={(row) => String(row.transaction_id)}
            columns={[
              { key: 'transaction_id', label: 'transaction_id' },
              { key: 'user_id', label: 'user_id' },
              { key: 'imf_account_id', label: 'imf_account_id' },
              { key: 'currency_code', label: 'currency_code' },
              {
                key: 'amount',
                label: 'amount',
                render: (v, row) => formatCurrency(Number(v), String(row.currency_code ?? 'USD')),
              },
              {
                key: 'transaction_type',
                label: 'transaction_type',
                render: (v) => (
                  <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${typeColors[String(v)] ?? 'bg-slate-100 text-slate-600'}`}>
                    {String(v)}
                  </span>
                ),
              },
              { key: 'transaction_date', label: 'transaction_date' },
              { key: 'reference', label: 'reference', render: (v) => (v ? String(v) : '—') },
            ]}
          />
        )}
      </GlassCard>
    </motion.div>
  );
}
