import { useEffect, useState } from 'react';

import { Link } from 'react-router-dom';

import { motion } from 'framer-motion';

import { Header } from '../components/layout/Header';

import { GlassCard } from '../components/ui/GlassCard';

import { FullDataTable } from '../components/ui/FullDataTable';

import { api, formatCurrency, formatDate, type Loan, type Country } from '../lib/api';



const statusColors: Record<string, string> = {

  ACTIVE: 'badge-active',

  Active: 'badge-active',

  CLOSED: 'badge-neutral',

  Completed: 'badge-neutral',

  DEFAULT: 'badge-danger',

  PENDING: 'badge-warning',

  Pending: 'badge-warning',

};



export function LoansPage() {

  const [loans, setLoans] = useState<Loan[]>([]);

  const [countries, setCountries] = useState<Country[]>([]);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState<string | null>(null);



  useEffect(() => {

    Promise.all([api.loans(), api.countries()])

      .then(([l, c]) => { setLoans(l); setCountries(c); })

      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load loans'))

      .finally(() => setLoading(false));

  }, []);



  const countryMap = Object.fromEntries(countries.map(c => [c.country_id, c.name]));



  return (

    <motion.div>

      <Header title="IMF Loan Portfolio" subtitle="Sovereign loan programs, disbursements, and repayment tracking for member countries" />



      {error && (

        <motion.div className="mb-6 neon-card rounded-xl px-4 py-3 border border-red-500/30 text-red-300 text-sm">

          {error}

        </motion.div>

      )}



      <motion.div className="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-8">

        {[

          { label: 'IMF Portfolio', val: formatCurrency(loans.reduce((s, l) => s + Number(l.loan_amount), 0)) },

          { label: 'Active Sovereign Loans', val: loans.filter(l => l.status.toUpperCase() === 'ACTIVE').length },

          { label: 'Member Countries', val: new Set(loans.map(l => l.country_id)).size },

        ].map((kpi, i) => (

          <motion.div key={kpi.label} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }} className="neon-card rounded-2xl p-5 glow-cyan-hover">

            <p className="text-xs font-semibold uppercase tracking-wider text-slate mb-1">{kpi.label}</p>

            <p className="text-2xl font-bold text-light font-[family-name:var(--font-display)]">{kpi.val}</p>

          </motion.div>

        ))}

      </motion.div>



      <GlassCard title="Sovereign Loans" subtitle={`${loans.length} IMF loan records — all database columns`}>

        {loading ? (

          <motion.div className="flex justify-center py-16"><motion.div className="w-8 h-8 border-2 border-cyan/30 border-t-cyan rounded-full animate-spin" /></motion.div>

        ) : (

          <FullDataTable

            rows={loans as unknown as Record<string, unknown>[]}

            rowKey={(row) => String(row.loan_id)}

            columns={[

              { key: 'loan_id', label: 'loan_id' },

              { key: 'country_id', label: 'country_id', render: (v) => countryMap[Number(v)] ? `${v} (${countryMap[Number(v)]})` : String(v) },

              { key: 'program_id', label: 'program_id' },

              { key: 'imf_account_id', label: 'imf_account_id' },

              { key: 'currency_code', label: 'currency_code' },

              { key: 'loan_amount', label: 'loan_amount', render: (v) => formatCurrency(Number(v)) },

              { key: 'interest_rate', label: 'interest_rate', render: (v) => `${Number(v).toFixed(2)}%` },

              { key: 'start_date', label: 'start_date', render: (v) => (v ? formatDate(String(v)) : '—') },

              { key: 'end_date', label: 'end_date', render: (v) => (v ? formatDate(String(v)) : '—') },

              { key: 'no_of_installments', label: 'no_of_installments' },

              {

                key: 'status',

                label: 'status',

                render: (v) => (

                  <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${statusColors[String(v)] ?? 'bg-slate-100 text-slate-600'}`}>

                    {String(v)}

                  </span>

                ),

              },

              {
                id: 'actions',
                key: 'loan_id',
                label: '',
                render: (_, row) => (
                  <Link to={`/loans/${row.loan_id}`} className="text-xs font-semibold text-cyan hover:text-aqua">
                    Manage
                  </Link>
                ),
              },

            ]}

          />

        )}

      </GlassCard>

    </motion.div>

  );

}

