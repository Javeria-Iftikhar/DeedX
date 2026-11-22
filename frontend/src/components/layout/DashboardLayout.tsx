import { Navigate, Outlet } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../../context/AuthContext';
import { Sidebar } from './Sidebar';
import { AskAiAssistant } from '../ai/AskAiAssistant';

export function DashboardLayout() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center dashboard-canvas">
        <motion.div className="w-10 h-10 border-2 border-cyan/20 border-t-cyan rounded-full animate-spin shadow-[0_0_20px_rgba(34,211,238,0.3)]" />
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;

  return (
    <motion.div className="dashboard-canvas min-h-screen">
      <div className="ambient-orb ambient-orb-cyan" aria-hidden="true" />
      <div className="ambient-orb ambient-orb-blue" aria-hidden="true" />
      <Sidebar />
      <main className="ml-[260px] min-h-screen p-6 lg:p-8 relative z-10">
        <Outlet />
      </main>
      <AskAiAssistant />
    </motion.div>
  );
}
