import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { DashboardLayout } from './components/layout/DashboardLayout';
import { RoleRoute } from './components/RoleRoute';
import { LandingPage } from './pages/LandingPage';
import { LoginPage } from './pages/LoginPage';
import { SignUpPage } from './pages/SignUpPage';
import { DashboardPage } from './pages/DashboardPage';
import { LoansPage } from './pages/LoansPage';
import { LoanDetailPage } from './pages/LoanDetailPage';
import { EconomicPage } from './pages/EconomicPage';
import { TransactionsPage } from './pages/TransactionsPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { AuditPage } from './pages/AuditPage';
import { AdminPanelPage } from './pages/AdminPanelPage';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter basename="/FISCALA">
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignUpPage />} />
          <Route element={<DashboardLayout />}>
            <Route
              path="/dashboard"
              element={
                <RoleRoute roles={['admin', 'officer', 'analyst']}>
                  <DashboardPage />
                </RoleRoute>
              }
            />
            <Route
              path="/loans/:loanId"
              element={
                <RoleRoute roles={['admin', 'officer']}>
                  <LoanDetailPage />
                </RoleRoute>
              }
            />
            <Route
              path="/loans"
              element={
                <RoleRoute roles={['admin', 'officer']}>
                  <LoansPage />
                </RoleRoute>
              }
            />
            <Route
              path="/economic"
              element={
                <RoleRoute roles={['admin', 'analyst']}>
                  <EconomicPage />
                </RoleRoute>
              }
            />
            <Route
              path="/transactions"
              element={
                <RoleRoute roles={['admin', 'officer']}>
                  <TransactionsPage />
                </RoleRoute>
              }
            />
            <Route
              path="/analytics"
              element={
                <RoleRoute roles={['admin', 'officer', 'analyst']}>
                  <AnalyticsPage />
                </RoleRoute>
              }
            />
            <Route
              path="/audit"
              element={
                <RoleRoute roles={['admin', 'officer', 'analyst']}>
                  <AuditPage />
                </RoleRoute>
              }
            />
            <Route
              path="/admin"
              element={
                <RoleRoute roles={['admin']}>
                  <AdminPanelPage />
                </RoleRoute>
              }
            />
            <Route path="/users" element={<Navigate to="/admin" replace />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
