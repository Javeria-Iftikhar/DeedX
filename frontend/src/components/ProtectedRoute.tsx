import { Navigate, Outlet } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../context/AuthContext';

export function ProtectedRoute() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <motion.div className="min-h-screen flex items-center justify-center dashboard-canvas">
        <motion.div className="w-10 h-10 border-2 border-cyan/20 border-t-cyan rounded-full animate-spin shadow-[0_0_20px_rgba(34,211,238,0.3)]" />
      </motion.div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}
