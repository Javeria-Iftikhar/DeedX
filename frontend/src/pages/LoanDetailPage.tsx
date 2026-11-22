import { useEffect, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Banknote, CircleDollarSign } from 'lucide-react';
import { Header } from '../components/layout/Header';
import { GlassCard } from '../components/ui/GlassCard';
import { Button } from '../components/ui/Button';
import { FullDataTable } from '../components/ui/FullDataTable';
import { api, formatCurrency, formatDate, type Loan, type Country, type Installment, type LoanDisbursement, type Repayment } from '../lib/api';
import { useAuth } from '../context/AuthContext';

export function LoanDetailPage() {
  const { loanId } = useParams<{ loanId: string }>();
  const id = Number(loanId);
  const navigate = useNavigate();
  const { isOfficer } = useAuth();

  const [loan, setLoan] = useState<Loan | null>(null);
  const [countries, setCountries] = useState<Country[]>([]);
  const [installments, setInstallments] = useState<Installment[]>([]);
  const [disbursements, setDisbursements] = useState<LoanDisbursement[]>([]);
  const [repayments, setRepayments] = useState<Repayment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [disburseAmount, setDisburseAmount] = useState('');
  const [repayAmount, setRepayAmount] = useState('');

  const reload = async () => {
    const [l, c, inst, disb, rep] = await Promise.all([
      api.loan(id),
      api.countries(),
      api.installments(id).catch(() => []),
      api.disbursementsForLoan(id).catch(() => []),
      api.repaymentsForLoan(id).catch(() => []),
    ]);
    setLoan(l);
    setCountries(c);
    setInstallments(inst);
    setDisbursements(disb);
    setRepayments(rep);
  };

  useEffect(() => {
    if (!id || Number.isNaN(id)) return;
    reload()
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load loan'))
      .finally(() => setLoading(false));
  }, [id]);

  const countryName = countries.find((c) => c.country_id === loan?.country_id)?.name ?? '-';

  const handleDisburse = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loan) return;
    setBusy(true);
    setActionErr(null);
    setActionMsg(null);
    try {
      await api.processDisbursement({
        loan_id: loan.loan_id,
        imf_account_id: loan.imf_account_id,
        amount: Number(disburseAmount),
      });
      setActionMsg('Disbursement processed. Installment schedule updated if first disbursement.');
      setDisburseAmount('');
      await reload();
    } catch (err) {
      setActionErr(err instanceof Error ? err.message : 'Disbursement failed');
    } finally {
      setBusy(false);
    }
  };

  const handleRepay = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loan) return;
    setBusy(true);
    setActionErr(null);
    setActionMsg(null);
    try {
      await api.processRepayment({ loan_id: loan.loan_id, amount_paid: Number(repayAmount) });
      setActionMsg('Repayment recorded and installments allocated.');
      setRepayAmount('');
      await reload();
    } catch (err) {
      setActionErr(err instanceof Error ? err.message : 'Repayment failed');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <motion.div className="flex justify-center py-24">
        <motion.div className="w-10 h-10 border-2 border-cyan/20 border-t-cyan rounded-full animate-spin" />
      </motion.div>
    );
  }

  if (error || !loan) {
    return (
      <motion.div>
        <Header title="Loan Not Found" subtitle="Unable to load loan record" />
        <motion.div className="neon-card rounded-xl px-4 py-3 border border-red-500/30 text-red-300 text-sm mb-4">
          {error ?? 'Loan not found'}
        </motion.div>
        <Button variant="outline" onClick={() => navigate('/loans')}>
          <ArrowLeft size={16} /> Back to loans
        </Button>
      </motion.div>
    );
  }

  return (
    <motion.div>
      <motion.div className="mb-4">
        <Link to="/loans" className="inline-flex items-center gap-2 text-sm text-cyan hover:text-aqua transition-colors">
          <ArrowLeft size={16} /> Back to IMF portfolio
        </Link>
      </motion.div>

      <Header
        title={`Loan #${loan.loan_id}`}
        subtitle={`${countryName} | ${loan.status} | ${formatCurrency(Number(loan.loan_amount))}`}
      />

      {actionMsg && (
        <motion.div className="mb-4 neon-card rounded-xl px-4 py-3 border border-cyan/30 text-cyan text-sm">{actionMsg}</motion.div>
      )}
      {actionErr && (
        <motion.div className="mb-4 neon-card rounded-xl px-4 py-3 border border-red-500/30 text-red-300 text-sm">{actionErr}</motion.div>
      )}

      <motion.div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <GlassCard title="Sovereign Loan Details" className="lg:col-span-1">
          <dl className="space-y-3 text-sm">
            {[
              ['Country', countryName],
              ['Program ID', String(loan.program_id)],
              ['Currency', loan.currency_code],
              ['Interest', `${Number(loan.interest_rate).toFixed(2)}%`],
              ['Start', formatDate(loan.start_date)],
              ['End', formatDate(loan.end_date)],
              ['Installments', String(loan.no_of_installments)],
              ['IMF Account', `#${loan.imf_account_id}`],
            ].map(([k, v]) => (
              <motion.div key={k} className="flex justify-between gap-4 border-b border-cyan/5 pb-2">
                <dt className="text-slate">{k}</dt>
                <dd className="text-light font-medium text-right">{v}</dd>
              </motion.div>
            ))}
          </dl>
        </GlassCard>

        {isOfficer && (
          <GlassCard title="Process Disbursement" subtitle="Record sovereign loan disbursement — first tranche generates installment schedule" className="lg:col-span-1">
            <form onSubmit={handleDisburse} className="space-y-4">
              <motion.div>
                <label className="text-xs uppercase tracking-wider text-slate block mb-2">Amount (USD)</label>
                <input
                  type="number"
                  min="1"
                  step="0.01"
                  required
                  value={disburseAmount}
                  onChange={(e) => setDisburseAmount(e.target.value)}
                  className="ai-input w-full rounded-xl px-4 py-3 text-sm"
                  placeholder="e.g. 50000000"
                />
              </motion.div>
              <Button type="submit" className="w-full" loading={busy}>
                <Banknote size={16} /> Process Disbursement
              </Button>
            </form>
          </GlassCard>
        )}

        {isOfficer && (
          <GlassCard title="Process Repayment" subtitle="Record member country repayment against installment schedule" className="lg:col-span-1">
            <form onSubmit={handleRepay} className="space-y-4">
              <motion.div>
                <label className="text-xs uppercase tracking-wider text-slate block mb-2">Amount Paid (USD)</label>
                <input
                  type="number"
                  min="1"
                  step="0.01"
                  required
                  value={repayAmount}
                  onChange={(e) => setRepayAmount(e.target.value)}
                  className="ai-input w-full rounded-xl px-4 py-3 text-sm"
                  placeholder="e.g. 25000000"
                />
              </motion.div>
              <Button type="submit" variant="outline" className="w-full" loading={busy}>
                <CircleDollarSign size={16} /> Process Repayment
              </Button>
            </form>
          </GlassCard>
        )}
      </motion.div>

      <GlassCard title="Loan Disbursements" subtitle={`${disbursements.length} rows — all loandisbursement columns`} className="mb-8">
        <FullDataTable
          rows={disbursements as unknown as Record<string, unknown>[]}
          rowKey={(row) => `${row.loan_id}-${row.disbursement_no}`}
          emptyMessage="No disbursements recorded for this loan."
          columns={[
            { key: 'loan_id', label: 'loan_id' },
            { key: 'disbursement_no', label: 'disbursement_no' },
            { key: 'imf_account_id', label: 'imf_account_id' },
            { key: 'amount', label: 'amount', render: (v) => formatCurrency(Number(v)) },
            { key: 'disbursement_date', label: 'disbursement_date' },
            { key: 'status', label: 'status' },
          ]}
        />
      </GlassCard>

      <GlassCard title="Repayments" subtitle={`${repayments.length} rows — all repayment columns`} className="mb-8">
        <FullDataTable
          rows={repayments as unknown as Record<string, unknown>[]}
          rowKey={(row) => `${row.loan_id}-${row.repayment_no}`}
          emptyMessage="No repayments recorded for this loan."
          columns={[
            { key: 'loan_id', label: 'loan_id' },
            { key: 'repayment_no', label: 'repayment_no' },
            { key: 'amount_paid', label: 'amount_paid', render: (v) => formatCurrency(Number(v)) },
            { key: 'payment_date', label: 'payment_date' },
            { key: 'outstanding_balance', label: 'outstanding_balance', render: (v) => formatCurrency(Number(v)) },
            { key: 'total_paid', label: 'total_paid', render: (v) => formatCurrency(Number(v)) },
          ]}
        />
      </GlassCard>

      <GlassCard title="Installment Schedule" subtitle={`${installments.length} rows — all installment columns`}>
        <FullDataTable
          rows={installments as unknown as Record<string, unknown>[]}
          rowKey={(row) => `${row.loan_id}-${row.installment_no}`}
          emptyMessage="No installments yet. Process the first disbursement to auto-generate the schedule."
          columns={[
            { key: 'loan_id', label: 'loan_id' },
            { key: 'installment_no', label: 'installment_no' },
            { key: 'due_date', label: 'due_date' },
            { key: 'amount_due', label: 'amount_due', render: (v) => formatCurrency(Number(v ?? 0)) },
            { key: 'amount_paid', label: 'amount_paid', render: (v) => formatCurrency(Number(v ?? 0)) },
            {
              key: 'status',
              label: 'status',
              render: (v) => (
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full badge-active">{String(v ?? 'PENDING')}</span>
              ),
            },
          ]}
        />
      </GlassCard>
    </motion.div>
  );
}
