import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { api, type MeResponse, type UserRole } from '../lib/api';

interface AuthContextType {
  user: MeResponse | null;
  loading: boolean;
  login: (email: string, password: string, expectedRole?: UserRole) => Promise<void>;
  logout: () => void;
  isAdmin: boolean;
  isOfficer: boolean;
  isAnalyst: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('fiscala_token');
    if (!token) { setLoading(false); return; }
    api.me()
      .then(setUser)
      .catch(() => {
        localStorage.removeItem('fiscala_token');
        localStorage.removeItem('fiscala_refresh');
      })
      .finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string, expectedRole?: UserRole) => {
    const tokens = await api.login(email, password);
    localStorage.setItem('fiscala_token', tokens.access_token);
    localStorage.setItem('fiscala_refresh', tokens.refresh_token);
    const me = await api.me();
    if (expectedRole && me.role !== expectedRole) {
      localStorage.removeItem('fiscala_token');
      localStorage.removeItem('fiscala_refresh');
      const labels: Record<UserRole, string> = {
        admin: 'Admin',
        officer: 'Loan Officer',
        analyst: 'Economic Analyst',
      };
      throw new Error(`This account is not a ${labels[expectedRole]}. Use the correct role option or credentials.`);
    }
    setUser(me);
  };

  const logout = () => {
    api.logout().catch(() => {});
    localStorage.removeItem('fiscala_token');
    localStorage.removeItem('fiscala_refresh');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{
      user,
      loading,
      login,
      logout,
      isAdmin: user?.role === 'admin',
      isOfficer: user?.role === 'officer' || user?.role === 'admin',
      isAnalyst: user?.role === 'analyst' || user?.role === 'admin',
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
