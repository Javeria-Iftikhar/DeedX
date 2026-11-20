import { Navigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuth } from '../context/AuthContext';

type Role = 'admin' | 'officer' | 'analyst';

interface RoleRouteProps {
  roles: Role[];
  children: ReactNode;
}

export function RoleRoute({ roles, children }: RoleRouteProps) {
  const { user, loading } = useAuth();

  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (!roles.includes(user.role as Role)) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}
