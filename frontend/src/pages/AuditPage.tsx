import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Header } from '../components/layout/Header';
import { GlassCard } from '../components/ui/GlassCard';
import { FullDataTable } from '../components/ui/FullDataTable';
import { api, type AuditLog } from '../lib/api';
import { useAuth } from '../context/AuthContext';

export function AuditPage() {
  const { isAdmin } = useAuth();
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const fetcher = isAdmin ? api.auditLogsAll() : api.auditLogsMy();
    fetcher
      .then(setLogs)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load audit logs'))
      .finally(() => setLoading(false));
  }, [isAdmin]);

  return (
    <motion.div>
      <Header title="Audit Logs" subtitle={isAdmin ? 'IMF financial governance — full system audit trail' : 'Your fiscal activity history'} />

      {error && (
        <motion.div className="mb-6 neon-card rounded-xl px-4 py-3 border border-red-500/30 text-red-300 text-sm">
          {error}
        </motion.div>
      )}

      <GlassCard title="Audit Log" subtitle={`${logs.length} entries — all auditlog columns`}>
        {loading ? (
          <motion.div className="flex justify-center py-16"><motion.div className="w-8 h-8 border-2 border-cyan/30 border-t-cyan rounded-full animate-spin" /></motion.div>
        ) : (
          <FullDataTable
            rows={logs as unknown as Record<string, unknown>[]}
            rowKey={(row) => `${row.user_id}-${row.log_id}`}
            columns={[
              { key: 'user_id', label: 'user_id' },
              { key: 'log_id', label: 'log_id' },
              { key: 'action', label: 'action', render: (v) => <span className="max-w-md inline-block whitespace-normal">{String(v)}</span> },
              { key: 'log_timestamp', label: 'log_timestamp' },
              { key: 'entity_affected', label: 'entity_affected' },
            ]}
          />
        )}
      </GlassCard>
    </motion.div>
  );
}
