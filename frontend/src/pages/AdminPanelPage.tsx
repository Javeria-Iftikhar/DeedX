import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Database } from 'lucide-react';
import { Header } from '../components/layout/Header';
import { AdminEntityCrud, type AdminLookups } from '../components/admin/AdminEntityCrud';
import { ThemedSelect } from '../components/admin/ThemedSelect';
import { api } from '../lib/api';
import { ADMIN_TABLES } from '../lib/adminTables';

export function AdminPanelPage() {
  const [activeId, setActiveId] = useState(ADMIN_TABLES[0].id);
  const [lookups, setLookups] = useState<AdminLookups | null>(null);
  const [lookupsLoading, setLookupsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const loadLookups = useCallback(async () => {
    setLookupsLoading(true);
    try {
      const [currencies, countries, programs, accounts, users, loans, conditions, indicators] = await Promise.all([
        api.currencies(),
        api.countries(),
        api.programs(),
        api.accounts(),
        api.users(),
        api.loans(),
        api.conditions(),
        api.indicators(),
      ]);
      setLookups({
        currencies,
        countries,
        programs,
        accounts,
        users,
        loans: loans.map((l) => ({ loan_id: l.loan_id })),
        conditions: conditions.map((c) => ({
          condition_id: Number(c.condition_id),
          condition_type: c.condition_type as string | undefined,
        })),
        indicators: indicators.map((i) => ({
          indicator_id: i.indicator_id,
          country_id: i.country_id,
          record_date: i.record_date,
        })),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load reference data');
    } finally {
      setLookupsLoading(false);
    }
  }, []);

  useEffect(() => { loadLookups(); }, [loadLookups]);

  const activeConfig = ADMIN_TABLES.find((t) => t.id === activeId) ?? ADMIN_TABLES[0];

  const flash = (text: string) => {
    setMsg(text);
    setTimeout(() => setMsg(null), 3000);
    loadLookups();
  };

  return (
    <motion.div>
      <Header
        title="IMF Data Management"
        subtitle="All 21 PostgreSQL tables (imf_db) with full schema columns and admin CRUD where the API allows"
      />

      {error && (
        <motion.div className="mb-4 neon-card rounded-xl px-4 py-3 border border-red-500/30 text-red-300 text-sm flex justify-between items-center">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} className="text-red-400 hover:text-red-200 text-xs">Dismiss</button>
        </motion.div>
      )}
      {msg && (
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-4 neon-card rounded-xl px-4 py-3 border border-cyan/30 text-cyan text-sm">
          {msg}
        </motion.div>
      )}

      <motion.div className="relative z-10 mb-6 neon-card rounded-xl px-4 py-4 border border-cyan/10 max-w-xl">
        <label htmlFor="imf-table-select" className="text-xs uppercase tracking-wider text-slate block mb-2">
          Select table ({ADMIN_TABLES.length} in imf_db)
        </label>
        <ThemedSelect
          id="imf-table-select"
          value={activeId}
          onChange={setActiveId}
          options={ADMIN_TABLES.map((t) => ({
            value: t.id,
            label: `${t.label} (${t.pgTable})`,
          }))}
        />
        <p className="text-xs text-slate mt-2">
          Viewing: <span className="text-cyan">{activeConfig.label}</span>
          <span className="text-slate/70"> · {activeConfig.pgTable}</span>
        </p>
      </motion.div>

      {lookupsLoading || !lookups ? (
        <motion.div className="flex flex-col items-center justify-center py-24 gap-4">
          <motion.div className="w-10 h-10 border-2 border-cyan/30 border-t-cyan rounded-full animate-spin" />
          <p className="text-slate text-sm">Loading reference data for foreign keys...</p>
        </motion.div>
      ) : (
        <AdminEntityCrud
          key={activeConfig.id}
          config={activeConfig}
          lookups={lookups}
          onError={setError}
          onFlash={flash}
        />
      )}

      <motion.div className="mt-6 flex items-center gap-2 text-slate text-xs">
        <Database size={14} className="text-cyan/60" />
        <span>
          {ADMIN_TABLES.length} tables. System-managed tables (installments, audit log, transaction links) are view-only.
          Destructive actions respect PostgreSQL foreign keys.
        </span>
      </motion.div>
    </motion.div>
  );
}
