import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Header } from '../components/layout/Header';
import { GlassCard } from '../components/ui/GlassCard';
import { api } from '../lib/api';

interface UserRow {
  user_id: number;
  name: string;
  email: string;
}

export function UsersPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.users()
      .then(setUsers)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load users'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <motion.div>
      <Header title="User Management" subtitle="System users and role assignments" />

      {error && (
        <div className="mb-6 neon-card rounded-xl px-4 py-3 border border-red-500/30 text-red-300 text-sm">{error}</div>
      )}

      <GlassCard title="All Users" subtitle={`${users.length} registered users`}>
        {loading ? (
          <motion.div className="flex justify-center py-16"><motion.div className="w-8 h-8 border-2 border-cyan/30 border-t-cyan rounded-full animate-spin" /></motion.div>
        ) : (
          <motion.div className="overflow-x-auto">
            <table className="w-full data-table">
              <thead>
                <tr className="border-b border-slate/10">
                  {['ID', 'Name', 'Email'].map(h => (
                    <th key={h} className="text-left py-3 px-4">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((user, i) => (
                  <motion.tr key={user.user_id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.03 }} className="border-b border-slate/5 hover:bg-cyan/5 transition-colors">
                    <td className="py-3.5 px-4 text-sm font-mono text-royal">#{user.user_id}</td>
                    <td className="py-3.5 px-4 text-sm font-medium text-light">{user.name}</td>
                    <td className="py-3.5 px-4 text-sm text-slate">{user.email}</td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </motion.div>
        )}
      </GlassCard>
    </motion.div>
  );
}
