/**
 * FastAPI backend (PostgreSQL imf_db).
 * Dev: set VITE_API_URL=/api in .env.development to use the Vite proxy → http://127.0.0.1:8000
 * Prod / direct: defaults to http://127.0.0.1:8000
 */
export const API_BASE =
  import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000';

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface MeResponse {
  user_id: number;
  name: string;
  email: string;
  role: string;
}

export interface DashboardStats {
  total_loans: number;
  active_loans: number;
  total_disbursed_usd: number;
  total_repaid_usd: number;
  outstanding_balance_usd: number;
  total_countries: number;
  total_users: number;
  total_transactions: number;
}

export interface PublicStats {
  total_loans: number;
  active_loans: number;
  total_portfolio_usd: number;
  total_disbursed_usd: number;
  total_repaid_usd: number;
  repayment_rate_pct: number;
  total_countries: number;
  total_transactions: number;
  audit_log_count: number;
  portfolio_by_country: { label: string; amount: number }[];
}

export interface AuditLog {
  user_id: number;
  log_id: number;
  action: string;
  log_timestamp: string;
  entity_affected: string;
}

export interface Loan {
  loan_id: number;
  country_id: number;
  program_id: number;
  imf_account_id: number;
  currency_code: string;
  loan_amount: number;
  interest_rate: number;
  start_date: string;
  end_date: string;
  status: string;
  no_of_installments: number;
}

export interface Country {
  country_id: number;
  currency_code: string;
  name: string;
  region?: string;
  population?: number;
}

export interface FinancialTransaction {
  transaction_id: number;
  user_id: number;
  imf_account_id: number;
  currency_code: string;
  amount: number;
  transaction_type: string;
  transaction_date: string;
  reference?: string;
}

export interface EconomicIndicator {
  indicator_id: number;
  country_id: number;
  record_date: string;
  CPI?: number;
  industrial_output?: number;
  agricultural_output?: number;
  services_output?: number;
  money_supply?: number;
  interest_rate?: number;
  exchange_rate?: number;
}

export interface ExchangeRate {
  exchange_rate_id: number;
  from_currency: string;
  to_currency: string;
  rate: number;
  rate_date: string;
}

export interface LoanSummary {
  by_status: { status: string; count: number; total_amount: number }[];
  by_program: { program: string; count: number; total_amount: number }[];
  recent_disbursements: { loan_id: number; disbursement_no: number; amount: number; date: string; status: string }[];
  overdue_installments: number;
}

export interface EconomicSummary {
  averages: { avg_CPI: number; avg_inflation: number; avg_GDP: number; avg_exchange_rate: number };
  latest_indicators: { country: string; record_date: string; CPI: number; interest_rate: number; exchange_rate: number }[];
  exchange_rates: { from: string; to: string; rate: number; date: string }[];
}

export interface Installment {
  loan_id: number;
  installment_no: number;
  due_date?: string;
  amount_due?: number;
  amount_paid?: number;
  status?: string;
}

export interface LoanDisbursement {
  loan_id: number;
  disbursement_no: number;
  imf_account_id: number;
  amount: number;
  disbursement_date: string;
  status: string;
}

export interface Repayment {
  loan_id: number;
  repayment_no: number;
  amount_paid: number;
  payment_date: string;
  outstanding_balance: number;
  total_paid: number;
}

export interface EconomicRecord {
  record_id: number;
  indicator_id: number;
  GDP?: number;
  inflation?: number;
}

export type UserRole = 'admin' | 'officer' | 'analyst';

export interface AnalyticsConversationTurn {
  role: string;
  content: string;
}

export interface AnalyticsDashboardResponse {
  title?: string;
  summary?: string;
  chart_type?: string;
  labels?: string[];
  values?: number[];
  rows?: Record<string, unknown>[];
  metadata?: Record<string, unknown>;
  export_format?: 'pdf' | 'csv' | string;
  x_axis?: string;
  y_axis?: string;
}

interface BackendDashboardPayload {
  title?: string;
  summary?: string;
  chart_type?: string;
  x_axis?: string | null;
  y_axis?: string | null;
  data?: Record<string, unknown>[];
  metadata?: Record<string, unknown>;
}

function normalizeAnalyticsResponse(raw: unknown): AnalyticsDashboardResponse {
  const payload =
    raw && typeof raw === 'object' && 'dashboard' in raw
      ? (raw as { dashboard: BackendDashboardPayload }).dashboard
      : (raw as BackendDashboardPayload);

  const rows = payload.data ?? [];
  const xKey = payload.x_axis ?? undefined;
  const yKey = payload.y_axis ?? undefined;

  const labels =
    xKey && rows.length > 0
      ? rows.map((row) => String(row[xKey] ?? ''))
      : undefined;

  const values =
    yKey && rows.length > 0
      ? rows.map((row) => Number(row[yKey] ?? 0))
      : undefined;

  const module = payload.metadata && typeof payload.metadata === 'object'
    ? String((payload.metadata as Record<string, unknown>).module ?? '')
    : '';

  const summaryFromPayload = payload.summary?.trim();

  return {
    title: payload.title,
    summary:
      summaryFromPayload ||
      (module ? `Module: ${module}` : undefined),
    chart_type: payload.chart_type,
    labels,
    values,
    rows,
    metadata: payload.metadata,
    export_format: (payload as { export_format?: string }).export_format,
    x_axis: xKey,
    y_axis: yKey,
  };
}

function parseContentDispositionFilename(header: string | null): string | undefined {
  if (!header) return undefined;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star?.[1]) return decodeURIComponent(star[1].trim());
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1]?.trim();
}

function triggerBrowserDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

class ApiClient {
  private getToken(): string | null {
    return localStorage.getItem('fiscala_token');
  }

  private async request<T>(path: string, options: RequestInit = {}, opts?: { public?: boolean }): Promise<T> {
    const token = opts?.public ? null : this.getToken();
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };
    const hasBody = options.body != null && options.method !== 'GET';
    if (hasBody && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

    if (!opts?.public && res.status === 401) {
      localStorage.removeItem('fiscala_token');
      localStorage.removeItem('fiscala_refresh');
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (!res.ok) {
      if (res.status === 502 || res.status === 503) {
        throw new Error('Backend API is not running. Start it with: uvicorn app.main:app --reload');
      }
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
    }

    if (res.status === 204) return {} as T;
    return res.json();
  }

  login(email: string, password: string) {
    return this.request<TokenResponse>(
      '/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }) },
      { public: true },
    );
  }

  register(data: { name: string; email: string; password: string; user_type: string }) {
    return this.request(
      '/auth/register',
      { method: 'POST', body: JSON.stringify(data) },
      { public: true },
    );
  }

  logout() {
    return this.request<{ message: string }>('/auth/logout', { method: 'POST' });
  }

  me() {
    return this.request<MeResponse>('/auth/me');
  }

  dashboardStats() {
    return this.request<DashboardStats>('/dashboard/stats');
  }

  publicStats() {
    return this.request<PublicStats>('/public/stats', {}, { public: true });
  }

  loanSummary() {
    return this.request<LoanSummary>('/reports/loan-summary');
  }

  economicSummary() {
    return this.request<EconomicSummary>('/reports/economic-summary');
  }

  loans() {
    return this.request<Loan[]>('/loans/');
  }

  loan(loanId: number) {
    return this.request<Loan>(`/loans/${loanId}`);
  }

  countries() {
    return this.request<Country[]>('/countries/');
  }

  transactions() {
    return this.request<FinancialTransaction[]>('/transactions/');
  }

  indicators() {
    return this.request<EconomicIndicator[]>('/indicators/');
  }

  exchangeRates() {
    return this.request<ExchangeRate[]>('/exchange-rates/');
  }

  auditLogsMy() {
    return this.request<AuditLog[]>('/audit-logs/my');
  }

  auditLogsAll() {
    return this.request<AuditLog[]>('/audit-logs/');
  }

  analyticsQuery(query: string, conversation: AnalyticsConversationTurn[] = []) {
    return this.request<unknown>('/analytics/query', {
      method: 'POST',
      body: JSON.stringify({ query, conversation }),
    }).then(normalizeAnalyticsResponse);
  }

  private async downloadAnalyticsExport(
    path: '/analytics/export/pdf' | '/analytics/export/csv',
    query: string,
    conversation: AnalyticsConversationTurn[] = [],
  ): Promise<void> {
    const token = this.getToken();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;

    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ query, conversation }),
    });

    if (res.status === 401) {
      localStorage.removeItem('fiscala_token');
      localStorage.removeItem('fiscala_refresh');
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
    }

    const blob = await res.blob();
    const fallback = path.endsWith('/pdf') ? 'dashboard-export.pdf' : 'dashboard-export.csv';
    const fname = parseContentDispositionFilename(res.headers.get('Content-Disposition')) ?? fallback;
    triggerBrowserDownload(blob, fname);
  }

  analyticsExportPdf(query: string, conversation: AnalyticsConversationTurn[] = []) {
    return this.downloadAnalyticsExport('/analytics/export/pdf', query, conversation);
  }

  analyticsExportCsv(query: string, conversation: AnalyticsConversationTurn[] = []) {
    return this.downloadAnalyticsExport('/analytics/export/csv', query, conversation);
  }

  async generateReport(prompt: string): Promise<void> {
    const token = this.getToken();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;

    const res = await fetch(`${API_BASE}/reports/generate`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ prompt }),
    });

    if (res.status === 401) {
      localStorage.removeItem('fiscala_token');
      localStorage.removeItem('fiscala_refresh');
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail));
    }

    const blob = await res.blob();
    const fname =
      parseContentDispositionFilename(res.headers.get('Content-Disposition')) ??
      'economic-report.pdf';
    triggerBrowserDownload(blob, fname);
  }

  installments(loanId: number) {
    return this.request<Installment[]>(`/installments/${loanId}`);
  }

  processDisbursement(data: { loan_id: number; amount: number; imf_account_id: number; disbursement_date?: string }) {
    return this.request('/process-disbursement/', { method: 'POST', body: JSON.stringify(data) });
  }

  processRepayment(data: { loan_id: number; amount_paid: number; payment_date?: string }) {
    return this.request('/process-repayment/', { method: 'POST', body: JSON.stringify(data) });
  }

  pdfReportData() {
    return this.request<Record<string, unknown>>('/reports/pdf-data');
  }

  users() {
    return this.request<{ user_id: number; name: string; email: string }[]>('/users/');
  }

  createUser(data: { name: string; email: string; password: string }) {
    return this.request('/users/', { method: 'POST', body: JSON.stringify(data) });
  }

  updateUser(userId: number, data: { name?: string; email?: string; password?: string }) {
    return this.request(`/users/${userId}`, { method: 'PUT', body: JSON.stringify(data) });
  }

  deleteUser(userId: number) {
    return this.request(`/users/${userId}`, { method: 'DELETE' });
  }

  assignAdmin(userId: number, data?: { admin_type?: string; access_scope?: string }) {
    return this.request('/users/admin/', { method: 'POST', body: JSON.stringify({ user_id: userId, ...data }) });
  }

  assignOfficer(userId: number, data?: Record<string, unknown>) {
    return this.request('/users/officer/', { method: 'POST', body: JSON.stringify({ user_id: userId, ...data }) });
  }

  assignAnalyst(userId: number, data?: Record<string, unknown>) {
    return this.request('/users/analyst/', { method: 'POST', body: JSON.stringify({ user_id: userId, ...data }) });
  }

  currencies() {
    return this.request<{ currency_code: string; currency_name?: string; symbol?: string; exchange_regime?: string }[]>('/currencies/');
  }

  createCurrency(data: { currency_code: string; currency_name?: string; symbol?: string; exchange_regime?: string }) {
    return this.request('/currencies/', { method: 'POST', body: JSON.stringify(data) });
  }

  deleteCurrency(code: string) {
    return this.request(`/currencies/${code}`, { method: 'DELETE' });
  }

  createCountry(data: { currency_code: string; name: string; region?: string; population?: number }) {
    return this.request<Country>('/countries/', { method: 'POST', body: JSON.stringify(data) });
  }

  updateCountry(id: number, data: { currency_code: string; name: string; region?: string; population?: number }) {
    return this.request<Country>(`/countries/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  }

  deleteCountry(id: number) {
    return this.request(`/countries/${id}`, { method: 'DELETE' });
  }

  createLoan(data: Record<string, unknown>) {
    return this.request<Loan>('/loans/', { method: 'POST', body: JSON.stringify(data) });
  }

  updateLoan(id: number, data: Record<string, unknown>) {
    return this.request<Loan>(`/loans/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
  }

  deleteLoan(id: number) {
    return this.request(`/loans/${id}`, { method: 'DELETE' });
  }

  createIndicator(data: Record<string, unknown>) {
    return this.request<EconomicIndicator>('/indicators/', { method: 'POST', body: JSON.stringify(data) });
  }

  updateIndicator(id: number, data: Record<string, unknown>) {
    return this.request<EconomicIndicator>(`/indicators/${id}`, { method: 'PUT', body: JSON.stringify(data) });
  }

  deleteIndicator(id: number) {
    return this.request(`/indicators/${id}`, { method: 'DELETE' });
  }

  createExchangeRate(data: { from_currency: string; to_currency: string; rate: number; rate_date: string }) {
    return this.request<ExchangeRate>('/exchange-rates/', { method: 'POST', body: JSON.stringify(data) });
  }

  deleteExchangeRate(id: number) {
    return this.request(`/exchange-rates/${id}`, { method: 'DELETE' });
  }

  deleteTransaction(id: number) {
    return this.request(`/transactions/${id}`, { method: 'DELETE' });
  }

  programs() {
    return this.request<{ program_id: number; program_name: string }[]>('/programs/');
  }

  accounts() {
    return this.request<{ imf_account_id: number; account_number: string; account_type?: string; balance?: number; created_at?: string }[]>('/accounts/');
  }

  createProgram(data: { program_name: string; description?: string; max_amount?: number; interest_policy?: string }) {
    return this.request('/programs/', { method: 'POST', body: JSON.stringify(data) });
  }

  deleteProgram(id: number) {
    return this.request(`/programs/${id}`, { method: 'DELETE' });
  }

  createAccount(data: { account_number: string; account_type: string; opening_balance?: number }) {
    return this.request('/accounts/', { method: 'POST', body: JSON.stringify(data) });
  }

  deleteAccount(id: number) {
    return this.request(`/accounts/${id}`, { method: 'DELETE' });
  }

  adjustAccount(id: number, adjustment_amount: number, reason = '') {
    const q = new URLSearchParams({ adjustment_amount: String(adjustment_amount), reason });
    return this.request(`/accounts/${id}/adjust?${q}`, { method: 'PATCH' });
  }

  conditions() {
    return this.request<Record<string, unknown>[]>('/conditions/');
  }

  createCondition(data: Record<string, unknown>) {
    return this.request('/conditions/', { method: 'POST', body: JSON.stringify(data) });
  }

  deleteCondition(id: number) {
    return this.request(`/conditions/${id}`, { method: 'DELETE' });
  }

  mappings() {
    return this.request<{ loan_id: number; condition_id: number }[]>('/mappings/');
  }

  createMapping(data: { loan_id: number; condition_id: number }) {
    return this.request('/mappings/', { method: 'POST', body: JSON.stringify(data) });
  }

  deleteMapping(loanId: number, conditionId: number) {
    return this.request(`/mappings/${loanId}/${conditionId}`, { method: 'DELETE' });
  }

  economicRecords() {
    return this.request<Record<string, unknown>[]>('/records/');
  }

  createEconomicRecord(data: { indicator_id: number; GDP?: number; inflation?: number }) {
    return this.request('/records/', { method: 'POST', body: JSON.stringify(data) });
  }

  deleteEconomicRecord(id: number) {
    return this.request(`/records/${id}`, { method: 'DELETE' });
  }

  admins() {
    return this.request<Record<string, unknown>[]>('/users/admin/');
  }

  deleteAdmin(userId: number) {
    return this.request(`/users/admin/${userId}`, { method: 'DELETE' });
  }

  officers() {
    return this.request<Record<string, unknown>[]>('/users/officer/');
  }

  deleteOfficer(userId: number) {
    return this.request(`/users/officer/${userId}`, { method: 'DELETE' });
  }

  analysts() {
    return this.request<Record<string, unknown>[]>('/users/analyst/');
  }

  deleteAnalyst(userId: number) {
    return this.request(`/users/analyst/${userId}`, { method: 'DELETE' });
  }

  disbursementsForLoan(loanId: number) {
    return this.request<LoanDisbursement[]>(`/disbursements/${loanId}`);
  }

  allDisbursements() {
    return this.request<Record<string, unknown>[]>('/disbursements/all/');
  }

  createDisbursement(data: { loan_id: number; imf_account_id: number; amount: number; disbursement_date?: string }) {
    return this.request('/disbursements/', { method: 'POST', body: JSON.stringify(data) });
  }

  updateDisbursementStatus(loanId: number, disbursementNo: number, status: string) {
    const q = new URLSearchParams({ status });
    return this.request(`/disbursements/${loanId}/${disbursementNo}/status?${q}`, { method: 'PATCH' });
  }

  deleteDisbursement(loanId: number, disbursementNo: number) {
    return this.request(`/disbursements/${loanId}/${disbursementNo}`, { method: 'DELETE' });
  }

  repaymentsForLoan(loanId: number) {
    return this.request<Repayment[]>(`/repayments/${loanId}`);
  }

  allRepayments() {
    return this.request<Record<string, unknown>[]>('/repayments/all/');
  }

  createRepayment(data: { loan_id: number; amount_paid: number; payment_date?: string }) {
    return this.request('/repayments/', { method: 'POST', body: JSON.stringify(data) });
  }

  deleteRepayment(loanId: number, repaymentNo: number) {
    return this.request(`/repayments/${loanId}/${repaymentNo}`, { method: 'DELETE' });
  }

  allInstallments() {
    return this.request<Record<string, unknown>[]>('/installments/all/');
  }

  disbursementLinks() {
    return this.request<Record<string, unknown>[]>('/transactions/disbursement-link/');
  }

  repaymentLinks() {
    return this.request<Record<string, unknown>[]>('/transactions/repayment-link/');
  }
}

export const api = new ApiClient();

export function formatCurrency(n: number, currency = 'USD') {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n);
}

export function formatCompactUsd(n: number) {
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return formatCurrency(n);
}

export function formatNumber(n: number) {
  return new Intl.NumberFormat('en-US').format(n);
}

export function formatDate(d: string) {
  return new Date(d).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}
