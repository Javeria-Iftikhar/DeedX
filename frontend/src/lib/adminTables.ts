/**
 * All 21 IMF database tables — column definitions aligned with PostgreSQL / models.py.
 * CRUD operations call existing FastAPI routes (backend constraints preserved).
 */
import { api } from './api';

export type FieldType = 'text' | 'number' | 'decimal' | 'date' | 'datetime' | 'textarea' | 'password' | 'select';

export type LookupKey = 'currencies' | 'countries' | 'programs' | 'accounts' | 'users' | 'loans' | 'conditions' | 'indicators';

export interface AdminColumn {
  key: string;
  label: string;
  type: FieldType;
  required?: boolean;
  hideInTable?: boolean;
  hideOnCreate?: boolean;
  hideOnEdit?: boolean;
  readOnlyAlways?: boolean;
  selectFrom?: LookupKey;
  staticOptions?: { value: string; label: string }[];
}

export interface AdminTableConfig {
  id: string;
  label: string;
  pgTable: string;
  columns: AdminColumn[];
  canCreate: boolean;
  canEdit: boolean;
  canDelete: boolean;
  readOnlyNote?: string;
  list: () => Promise<Record<string, unknown>[]>;
  create?: (form: Record<string, string>) => Promise<void>;
  update?: (row: Record<string, unknown>, form: Record<string, string>) => Promise<void>;
  remove?: (row: Record<string, unknown>) => Promise<void>;
  getRowKey: (row: Record<string, unknown>) => string;
  emptyForm: () => Record<string, string>;
  rowToForm: (row: Record<string, unknown>) => Record<string, string>;
}

const s = (v: unknown) => (v == null ? '' : String(v));
const n = (v: string) => { const x = parseFloat(v); return v === '' || Number.isNaN(x) ? undefined : x; };
const i = (v: string) => { const x = parseInt(v, 10); return v === '' || Number.isNaN(x) ? undefined : x; };

async function asRows<T>(promise: Promise<T[]>): Promise<Record<string, unknown>[]> {
  return (await promise) as unknown as Record<string, unknown>[];
}

export const ADMIN_TABLES: AdminTableConfig[] = [
  {
    id: 'currency',
    label: 'Currency',
    pgTable: 'currency',
    canCreate: true,
    canEdit: false,
    canDelete: true,
    columns: [
      { key: 'currency_code', label: 'currency_code', type: 'text', required: true },
      { key: 'currency_name', label: 'currency_name', type: 'text' },
      { key: 'symbol', label: 'symbol', type: 'text' },
      { key: 'exchange_regime', label: 'exchange_regime', type: 'text' },
    ],
    list: () => asRows(api.currencies()),
    create: async (f) => {
      await api.createCurrency({
        currency_code: f.currency_code.trim().toUpperCase(),
        currency_name: f.currency_name || undefined,
        symbol: f.symbol || undefined,
        exchange_regime: f.exchange_regime || undefined,
      });
    },
    remove: async (row) => { await api.deleteCurrency(String(row.currency_code)); },
    getRowKey: (r) => String(r.currency_code),
    emptyForm: () => ({ currency_code: '', currency_name: '', symbol: '', exchange_regime: '' }),
    rowToForm: (r) => ({ currency_code: s(r.currency_code), currency_name: s(r.currency_name), symbol: s(r.symbol), exchange_regime: s(r.exchange_regime) }),
  },
  {
    id: 'country',
    label: 'Country',
    pgTable: 'country',
    canCreate: true,
    canEdit: true,
    canDelete: true,
    columns: [
      { key: 'country_id', label: 'country_id', type: 'number', readOnlyAlways: true },
      { key: 'currency_code', label: 'currency_code', type: 'select', required: true, selectFrom: 'currencies' },
      { key: 'name', label: 'name', type: 'text', required: true },
      { key: 'region', label: 'region', type: 'text' },
      { key: 'population', label: 'population', type: 'number' },
    ],
    list: () => asRows(api.countries()),
    create: async (f) => {
      await api.createCountry({ currency_code: f.currency_code, name: f.name, region: f.region || undefined, population: i(f.population) });
    },
    update: async (row, f) => {
      await api.updateCountry(Number(row.country_id), { currency_code: f.currency_code, name: f.name, region: f.region || undefined, population: i(f.population) });
    },
    remove: async (row) => { await api.deleteCountry(Number(row.country_id)); },
    getRowKey: (r) => String(r.country_id),
    emptyForm: () => ({ country_id: '', currency_code: '', name: '', region: '', population: '' }),
    rowToForm: (r) => ({ country_id: s(r.country_id), currency_code: s(r.currency_code), name: s(r.name), region: s(r.region), population: s(r.population) }),
  },
  {
    id: 'loanprogram',
    label: 'Loan Program',
    pgTable: 'loanprogram',
    canCreate: true,
    canEdit: false,
    canDelete: true,
    columns: [
      { key: 'program_id', label: 'program_id', type: 'number', readOnlyAlways: true },
      { key: 'program_name', label: 'program_name', type: 'text', required: true },
      { key: 'description', label: 'description', type: 'textarea' },
      { key: 'max_amount', label: 'max_amount', type: 'decimal' },
      { key: 'interest_policy', label: 'interest_policy', type: 'text' },
    ],
    list: () => asRows(api.programs()),
    create: async (f) => {
      await api.createProgram({ program_name: f.program_name, description: f.description || undefined, max_amount: n(f.max_amount), interest_policy: f.interest_policy || undefined });
    },
    remove: async (row) => { await api.deleteProgram(Number(row.program_id)); },
    getRowKey: (r) => String(r.program_id),
    emptyForm: () => ({ program_id: '', program_name: '', description: '', max_amount: '', interest_policy: '' }),
    rowToForm: (r) => ({ program_id: s(r.program_id), program_name: s(r.program_name), description: s(r.description), max_amount: s(r.max_amount), interest_policy: s(r.interest_policy) }),
  },
  {
    id: 'imf_account',
    label: 'IMF Account',
    pgTable: 'imf_account',
    canCreate: true,
    canEdit: true,
    canDelete: true,
    readOnlyNote: 'balance and created_at are system-managed. Use adjustment_amount on edit to PATCH balance.',
    columns: [
      { key: 'imf_account_id', label: 'imf_account_id', type: 'number', readOnlyAlways: true },
      { key: 'account_number', label: 'account_number', type: 'text', required: true, hideOnEdit: true },
      { key: 'account_type', label: 'account_type', type: 'select', required: true, hideOnEdit: true, staticOptions: [
        { value: 'General Fund', label: 'General Fund' },
        { value: 'Special Drawing', label: 'Special Drawing' },
        { value: 'Concessional', label: 'Concessional' },
      ]},
      { key: 'opening_balance', label: 'opening_balance', type: 'decimal', hideOnEdit: true, hideInTable: true },
      { key: 'balance', label: 'balance', type: 'decimal', readOnlyAlways: true },
      { key: 'created_at', label: 'created_at', type: 'datetime', readOnlyAlways: true },
      { key: 'adjustment_amount', label: 'adjustment_amount', type: 'decimal', hideInTable: true, hideOnCreate: true },
      { key: 'adjust_reason', label: 'adjust_reason', type: 'text', hideInTable: true, hideOnCreate: true },
    ],
    list: () => asRows(api.accounts()),
    create: async (f) => {
      await api.createAccount({ account_number: f.account_number, account_type: f.account_type, opening_balance: n(f.opening_balance) ?? 0 });
    },
    update: async (row, f) => {
      const amt = n(f.adjustment_amount);
      if (amt != null && amt !== 0) await api.adjustAccount(Number(row.imf_account_id), amt, f.adjust_reason || '');
    },
    remove: async (row) => { await api.deleteAccount(Number(row.imf_account_id)); },
    getRowKey: (r) => String(r.imf_account_id),
    emptyForm: () => ({ imf_account_id: '', account_number: '', account_type: '', opening_balance: '0', balance: '', created_at: '', adjustment_amount: '', adjust_reason: '' }),
    rowToForm: (r) => ({ imf_account_id: s(r.imf_account_id), account_number: s(r.account_number), account_type: s(r.account_type), opening_balance: '', balance: s(r.balance), created_at: s(r.created_at), adjustment_amount: '', adjust_reason: '' }),
  },
  {
    id: 'users',
    label: 'Users',
    pgTable: 'users',
    canCreate: true,
    canEdit: true,
    canDelete: true,
    columns: [
      { key: 'user_id', label: 'user_id', type: 'number', readOnlyAlways: true },
      { key: 'name', label: 'name', type: 'text', required: true },
      { key: 'email', label: 'email', type: 'text', required: true },
      { key: 'password', label: 'password', type: 'password', hideInTable: true, hideOnEdit: true },
      { key: 'role_assign', label: 'role_assign', type: 'select', hideInTable: true, hideOnEdit: true, staticOptions: [
        { value: '', label: 'No role' }, { value: 'admin', label: 'Admin' }, { value: 'officer', label: 'Officer' }, { value: 'analyst', label: 'Analyst' },
      ]},
      { key: 'new_password', label: 'new_password', type: 'password', hideInTable: true, hideOnCreate: true },
    ],
    list: () => asRows(api.users()),
    create: async (f) => {
      const created = await api.createUser({ name: f.name, email: f.email, password: f.password }) as { user_id: number };
      if (f.role_assign === 'admin') await api.assignAdmin(created.user_id);
      else if (f.role_assign === 'officer') await api.assignOfficer(created.user_id);
      else if (f.role_assign === 'analyst') await api.assignAnalyst(created.user_id);
    },
    update: async (row, f) => {
      await api.updateUser(Number(row.user_id), { name: f.name || undefined, email: f.email || undefined, password: f.new_password || undefined });
    },
    remove: async (row) => { await api.deleteUser(Number(row.user_id)); },
    getRowKey: (r) => String(r.user_id),
    emptyForm: () => ({ user_id: '', name: '', email: '', password: '', role_assign: 'officer', new_password: '' }),
    rowToForm: (r) => ({ user_id: s(r.user_id), name: s(r.name), email: s(r.email), password: '', role_assign: '', new_password: '' }),
  },
  {
    id: 'admin',
    label: 'Admin',
    pgTable: 'admin',
    canCreate: true,
    canEdit: false,
    canDelete: true,
    readOnlyNote: 'last_login is set by the auth layer on login.',
    columns: [
      { key: 'user_id', label: 'user_id', type: 'select', required: true, selectFrom: 'users', hideOnEdit: true },
      { key: 'admin_type', label: 'admin_type', type: 'text' },
      { key: 'access_scope', label: 'access_scope', type: 'text' },
      { key: 'last_login', label: 'last_login', type: 'datetime', readOnlyAlways: true },
    ],
    list: () => asRows(api.admins()),
    create: async (f) => { await api.assignAdmin(Number(f.user_id), { admin_type: f.admin_type || undefined, access_scope: f.access_scope || undefined }); },
    remove: async (row) => { await api.deleteAdmin(Number(row.user_id)); },
    getRowKey: (r) => `admin-${r.user_id}`,
    emptyForm: () => ({ user_id: '', admin_type: '', access_scope: '', last_login: '' }),
    rowToForm: (r) => ({ user_id: s(r.user_id), admin_type: s(r.admin_type), access_scope: s(r.access_scope), last_login: s(r.last_login) }),
  },
  {
    id: 'officer',
    label: 'Officer',
    pgTable: 'officer',
    canCreate: true,
    canEdit: false,
    canDelete: true,
    columns: [
      { key: 'user_id', label: 'user_id', type: 'select', required: true, selectFrom: 'users' },
      { key: 'department', label: 'department', type: 'text' },
      { key: 'designation', label: 'designation', type: 'text' },
      { key: 'approval_limit', label: 'approval_limit', type: 'decimal' },
      { key: 'approval_role', label: 'approval_role', type: 'text' },
      { key: 'approval_scope', label: 'approval_scope', type: 'text' },
    ],
    list: () => asRows(api.officers()),
    create: async (f) => {
      await api.assignOfficer(Number(f.user_id), { department: f.department || undefined, designation: f.designation || undefined, approval_limit: n(f.approval_limit), approval_role: f.approval_role || undefined, approval_scope: f.approval_scope || undefined });
    },
    remove: async (row) => { await api.deleteOfficer(Number(row.user_id)); },
    getRowKey: (r) => `officer-${r.user_id}`,
    emptyForm: () => ({ user_id: '', department: '', designation: '', approval_limit: '', approval_role: '', approval_scope: '' }),
    rowToForm: (r) => ({ user_id: s(r.user_id), department: s(r.department), designation: s(r.designation), approval_limit: s(r.approval_limit), approval_role: s(r.approval_role), approval_scope: s(r.approval_scope) }),
  },
  {
    id: 'economicanalyst',
    label: 'Economic Analyst',
    pgTable: 'economicanalyst',
    canCreate: true,
    canEdit: false,
    canDelete: true,
    columns: [
      { key: 'user_id', label: 'user_id', type: 'select', required: true, selectFrom: 'users' },
      { key: 'specialization', label: 'specialization', type: 'text' },
      { key: 'organization', label: 'organization', type: 'text' },
      { key: 'report_access_level', label: 'report_access_level', type: 'text' },
    ],
    list: () => asRows(api.analysts()),
    create: async (f) => {
      await api.assignAnalyst(Number(f.user_id), { specialization: f.specialization || undefined, organization: f.organization || undefined, report_access_level: f.report_access_level || undefined });
    },
    remove: async (row) => { await api.deleteAnalyst(Number(row.user_id)); },
    getRowKey: (r) => `analyst-${r.user_id}`,
    emptyForm: () => ({ user_id: '', specialization: '', organization: '', report_access_level: '' }),
    rowToForm: (r) => ({ user_id: s(r.user_id), specialization: s(r.specialization), organization: s(r.organization), report_access_level: s(r.report_access_level) }),
  },
  {
    id: 'loan',
    label: 'Loan',
    pgTable: 'loan',
    canCreate: true,
    canEdit: true,
    canDelete: true,
    readOnlyNote: 'status is managed by the financial service (read-only).',
    columns: [
      { key: 'loan_id', label: 'loan_id', type: 'number', readOnlyAlways: true },
      { key: 'country_id', label: 'country_id', type: 'select', required: true, selectFrom: 'countries', hideOnEdit: true },
      { key: 'program_id', label: 'program_id', type: 'select', required: true, selectFrom: 'programs', hideOnEdit: true },
      { key: 'imf_account_id', label: 'imf_account_id', type: 'select', required: true, selectFrom: 'accounts', hideOnEdit: true },
      { key: 'currency_code', label: 'currency_code', type: 'select', required: true, selectFrom: 'currencies', hideOnEdit: true },
      { key: 'loan_amount', label: 'loan_amount', type: 'decimal', required: true },
      { key: 'interest_rate', label: 'interest_rate', type: 'decimal' },
      { key: 'start_date', label: 'start_date', type: 'date' },
      { key: 'end_date', label: 'end_date', type: 'date' },
      { key: 'no_of_installments', label: 'no_of_installments', type: 'number', required: true, hideOnEdit: true },
      { key: 'status', label: 'status', type: 'text', readOnlyAlways: true },
    ],
    list: () => asRows(api.loans()),
    create: async (f) => {
      await api.createLoan({
        country_id: Number(f.country_id), program_id: Number(f.program_id), imf_account_id: Number(f.imf_account_id),
        currency_code: f.currency_code, loan_amount: Number(f.loan_amount), interest_rate: n(f.interest_rate),
        start_date: f.start_date || undefined, end_date: f.end_date || undefined, no_of_installments: Number(f.no_of_installments),
      });
    },
    update: async (row, f) => {
      await api.updateLoan(Number(row.loan_id), { loan_amount: n(f.loan_amount), interest_rate: n(f.interest_rate), start_date: f.start_date || undefined, end_date: f.end_date || undefined });
    },
    remove: async (row) => { await api.deleteLoan(Number(row.loan_id)); },
    getRowKey: (r) => String(r.loan_id),
    emptyForm: () => ({ loan_id: '', country_id: '', program_id: '', imf_account_id: '', currency_code: '', loan_amount: '', interest_rate: '', start_date: '', end_date: '', no_of_installments: '12', status: '' }),
    rowToForm: (r) => ({ loan_id: s(r.loan_id), country_id: s(r.country_id), program_id: s(r.program_id), imf_account_id: s(r.imf_account_id), currency_code: s(r.currency_code), loan_amount: s(r.loan_amount), interest_rate: s(r.interest_rate), start_date: s(r.start_date).slice(0, 10), end_date: s(r.end_date).slice(0, 10), no_of_installments: s(r.no_of_installments), status: s(r.status) }),
  },
  {
    id: 'loancondition',
    label: 'Loan Condition',
    pgTable: 'loancondition',
    canCreate: true,
    canEdit: false,
    canDelete: true,
    columns: [
      { key: 'condition_id', label: 'condition_id', type: 'number', readOnlyAlways: true },
      { key: 'program_id', label: 'program_id', type: 'select', required: true, selectFrom: 'programs' },
      { key: 'condition_type', label: 'condition_type', type: 'text' },
      { key: 'description', label: 'description', type: 'textarea' },
      { key: 'threshold_value', label: 'threshold_value', type: 'decimal' },
      { key: 'eligibility_criteria', label: 'eligibility_criteria', type: 'textarea' },
    ],
    list: () => asRows(api.conditions()),
    create: async (f) => {
      await api.createCondition({ program_id: Number(f.program_id), condition_type: f.condition_type || undefined, description: f.description || undefined, threshold_value: n(f.threshold_value), eligibility_criteria: f.eligibility_criteria || undefined });
    },
    remove: async (row) => { await api.deleteCondition(Number(row.condition_id)); },
    getRowKey: (r) => String(r.condition_id),
    emptyForm: () => ({ condition_id: '', program_id: '', condition_type: '', description: '', threshold_value: '', eligibility_criteria: '' }),
    rowToForm: (r) => ({ condition_id: s(r.condition_id), program_id: s(r.program_id), condition_type: s(r.condition_type), description: s(r.description), threshold_value: s(r.threshold_value), eligibility_criteria: s(r.eligibility_criteria) }),
  },
  {
    id: 'loanconditionmapping',
    label: 'Loan Condition Mapping',
    pgTable: 'loanconditionmapping',
    canCreate: true,
    canEdit: false,
    canDelete: true,
    columns: [
      { key: 'loan_id', label: 'loan_id', type: 'select', required: true, selectFrom: 'loans' },
      { key: 'condition_id', label: 'condition_id', type: 'select', required: true, selectFrom: 'conditions' },
    ],
    list: () => asRows(api.mappings()),
    create: async (f) => { await api.createMapping({ loan_id: Number(f.loan_id), condition_id: Number(f.condition_id) }); },
    remove: async (row) => { await api.deleteMapping(Number(row.loan_id), Number(row.condition_id)); },
    getRowKey: (r) => `${r.loan_id}-${r.condition_id}`,
    emptyForm: () => ({ loan_id: '', condition_id: '' }),
    rowToForm: (r) => ({ loan_id: s(r.loan_id), condition_id: s(r.condition_id) }),
  },
  {
    id: 'economicindicator',
    label: 'Economic Indicator',
    pgTable: 'economicindicator',
    canCreate: true,
    canEdit: true,
    canDelete: true,
    columns: [
      { key: 'indicator_id', label: 'indicator_id', type: 'number', readOnlyAlways: true },
      { key: 'country_id', label: 'country_id', type: 'select', required: true, selectFrom: 'countries' },
      { key: 'record_date', label: 'record_date', type: 'date', required: true },
      { key: 'CPI', label: 'CPI', type: 'decimal' },
      { key: 'industrial_output', label: 'industrial_output', type: 'decimal' },
      { key: 'agricultural_output', label: 'agricultural_output', type: 'decimal' },
      { key: 'services_output', label: 'services_output', type: 'decimal' },
      { key: 'money_supply', label: 'money_supply', type: 'decimal' },
      { key: 'interest_rate', label: 'interest_rate', type: 'decimal' },
      { key: 'exchange_rate', label: 'exchange_rate', type: 'decimal' },
    ],
    list: () => asRows(api.indicators()),
    create: async (f) => {
      await api.createIndicator({ country_id: Number(f.country_id), record_date: f.record_date, CPI: n(f.CPI), industrial_output: n(f.industrial_output), agricultural_output: n(f.agricultural_output), services_output: n(f.services_output), money_supply: n(f.money_supply), interest_rate: n(f.interest_rate), exchange_rate: n(f.exchange_rate) });
    },
    update: async (row, f) => {
      await api.updateIndicator(Number(row.indicator_id), { country_id: Number(f.country_id), record_date: f.record_date, CPI: n(f.CPI), industrial_output: n(f.industrial_output), agricultural_output: n(f.agricultural_output), services_output: n(f.services_output), money_supply: n(f.money_supply), interest_rate: n(f.interest_rate), exchange_rate: n(f.exchange_rate) });
    },
    remove: async (row) => { await api.deleteIndicator(Number(row.indicator_id)); },
    getRowKey: (r) => String(r.indicator_id),
    emptyForm: () => ({ indicator_id: '', country_id: '', record_date: '', CPI: '', industrial_output: '', agricultural_output: '', services_output: '', money_supply: '', interest_rate: '', exchange_rate: '' }),
    rowToForm: (r) => ({ indicator_id: s(r.indicator_id), country_id: s(r.country_id), record_date: s(r.record_date).slice(0, 10), CPI: s(r.CPI), industrial_output: s(r.industrial_output), agricultural_output: s(r.agricultural_output), services_output: s(r.services_output), money_supply: s(r.money_supply), interest_rate: s(r.interest_rate), exchange_rate: s(r.exchange_rate) }),
  },
  {
    id: 'economicrecord',
    label: 'Economic Record',
    pgTable: 'economicrecord',
    canCreate: true,
    canEdit: false,
    canDelete: true,
    columns: [
      { key: 'record_id', label: 'record_id', type: 'number', readOnlyAlways: true },
      { key: 'indicator_id', label: 'indicator_id', type: 'select', required: true, selectFrom: 'indicators' },
      { key: 'GDP', label: 'GDP', type: 'decimal' },
      { key: 'inflation', label: 'inflation', type: 'decimal' },
    ],
    list: () => asRows(api.economicRecords()),
    create: async (f) => { await api.createEconomicRecord({ indicator_id: Number(f.indicator_id), GDP: n(f.GDP), inflation: n(f.inflation) }); },
    remove: async (row) => { await api.deleteEconomicRecord(Number(row.record_id)); },
    getRowKey: (r) => String(r.record_id),
    emptyForm: () => ({ record_id: '', indicator_id: '', GDP: '', inflation: '' }),
    rowToForm: (r) => ({ record_id: s(r.record_id), indicator_id: s(r.indicator_id), GDP: s(r.GDP), inflation: s(r.inflation) }),
  },
  {
    id: 'exchangerate',
    label: 'Exchange Rate',
    pgTable: 'exchangerate',
    canCreate: true,
    canEdit: false,
    canDelete: true,
    columns: [
      { key: 'exchange_rate_id', label: 'exchange_rate_id', type: 'number', readOnlyAlways: true },
      { key: 'from_currency', label: 'from_currency', type: 'select', required: true, selectFrom: 'currencies' },
      { key: 'to_currency', label: 'to_currency', type: 'select', required: true, selectFrom: 'currencies' },
      { key: 'rate', label: 'rate', type: 'decimal', required: true },
      { key: 'rate_date', label: 'rate_date', type: 'date', required: true },
    ],
    list: () => asRows(api.exchangeRates()),
    create: async (f) => {
      await api.createExchangeRate({ from_currency: f.from_currency, to_currency: f.to_currency, rate: Number(f.rate), rate_date: f.rate_date });
    },
    remove: async (row) => { await api.deleteExchangeRate(Number(row.exchange_rate_id)); },
    getRowKey: (r) => String(r.exchange_rate_id),
    emptyForm: () => ({ exchange_rate_id: '', from_currency: '', to_currency: '', rate: '', rate_date: new Date().toISOString().slice(0, 10) }),
    rowToForm: (r) => ({ exchange_rate_id: s(r.exchange_rate_id), from_currency: s(r.from_currency), to_currency: s(r.to_currency), rate: s(r.rate), rate_date: s(r.rate_date).slice(0, 10) }),
  },
  {
    id: 'financialtransaction',
    label: 'Financial Transaction',
    pgTable: 'financialtransaction',
    canCreate: false,
    canEdit: false,
    canDelete: true,
    readOnlyNote: 'Created by disbursement/repayment automation — delete only (admin).',
    columns: [
      { key: 'transaction_id', label: 'transaction_id', type: 'number', readOnlyAlways: true },
      { key: 'user_id', label: 'user_id', type: 'number', readOnlyAlways: true },
      { key: 'imf_account_id', label: 'imf_account_id', type: 'number', readOnlyAlways: true },
      { key: 'currency_code', label: 'currency_code', type: 'text', readOnlyAlways: true },
      { key: 'amount', label: 'amount', type: 'decimal', readOnlyAlways: true },
      { key: 'transaction_type', label: 'transaction_type', type: 'text', readOnlyAlways: true },
      { key: 'transaction_date', label: 'transaction_date', type: 'datetime', readOnlyAlways: true },
      { key: 'reference', label: 'reference', type: 'text', readOnlyAlways: true },
    ],
    list: () => asRows(api.transactions()),
    remove: async (row) => { await api.deleteTransaction(Number(row.transaction_id)); },
    getRowKey: (r) => String(r.transaction_id),
    emptyForm: () => ({}),
    rowToForm: (r) => Object.fromEntries(Object.keys(r).map((k) => [k, s(r[k])])),
  },
  {
    id: 'loandisbursement',
    label: 'Loan Disbursement',
    pgTable: 'loandisbursement',
    canCreate: true,
    canEdit: true,
    canDelete: true,
    readOnlyNote: 'disbursement_no is auto-sequenced. status is set by the financial service (Disbursed on disburse, Completed when loan is fully repaid); edit manually if needed.',
    columns: [
      { key: 'loan_id', label: 'loan_id', type: 'select', required: true, selectFrom: 'loans', hideOnEdit: true },
      { key: 'disbursement_no', label: 'disbursement_no', type: 'number', readOnlyAlways: true },
      { key: 'imf_account_id', label: 'imf_account_id', type: 'select', required: true, selectFrom: 'accounts', hideOnEdit: true },
      { key: 'amount', label: 'amount', type: 'decimal', required: true, hideOnEdit: true },
      { key: 'disbursement_date', label: 'disbursement_date', type: 'date', hideOnEdit: true },
      { key: 'status', label: 'status', type: 'select', hideOnCreate: true, staticOptions: [
        { value: 'Pending', label: 'Pending' }, { value: 'Approved', label: 'Approved' }, { value: 'Disbursed', label: 'Disbursed' }, { value: 'Completed', label: 'Completed' }, { value: 'Cancelled', label: 'Cancelled' },
      ]},
    ],
    list: () => asRows(api.allDisbursements()),
    create: async (f) => {
      await api.createDisbursement({ loan_id: Number(f.loan_id), imf_account_id: Number(f.imf_account_id), amount: Number(f.amount), disbursement_date: f.disbursement_date || undefined });
    },
    update: async (row, f) => {
      if (f.status) await api.updateDisbursementStatus(Number(row.loan_id), Number(row.disbursement_no), f.status);
    },
    remove: async (row) => { await api.deleteDisbursement(Number(row.loan_id), Number(row.disbursement_no)); },
    getRowKey: (r) => `${r.loan_id}-${r.disbursement_no}`,
    emptyForm: () => ({ loan_id: '', disbursement_no: '', imf_account_id: '', amount: '', disbursement_date: '', status: 'Pending' }),
    rowToForm: (r) => ({ loan_id: s(r.loan_id), disbursement_no: s(r.disbursement_no), imf_account_id: s(r.imf_account_id), amount: s(r.amount), disbursement_date: s(r.disbursement_date).slice(0, 10), status: s(r.status) }),
  },
  {
    id: 'repayment',
    label: 'Repayment',
    pgTable: 'repayment',
    canCreate: true,
    canEdit: false,
    canDelete: true,
    readOnlyNote: 'repayment_no and outstanding_balance are computed by the financial service.',
    columns: [
      { key: 'loan_id', label: 'loan_id', type: 'select', required: true, selectFrom: 'loans' },
      { key: 'repayment_no', label: 'repayment_no', type: 'number', readOnlyAlways: true },
      { key: 'amount_paid', label: 'amount_paid', type: 'decimal', required: true },
      { key: 'payment_date', label: 'payment_date', type: 'date' },
      { key: 'outstanding_balance', label: 'outstanding_balance', type: 'decimal', readOnlyAlways: true },
      { key: 'total_paid', label: 'total_paid', type: 'decimal', readOnlyAlways: true },
    ],
    list: () => asRows(api.allRepayments()),
    create: async (f) => {
      await api.createRepayment({ loan_id: Number(f.loan_id), amount_paid: Number(f.amount_paid), payment_date: f.payment_date || undefined });
    },
    remove: async (row) => { await api.deleteRepayment(Number(row.loan_id), Number(row.repayment_no)); },
    getRowKey: (r) => `${r.loan_id}-${r.repayment_no}`,
    emptyForm: () => ({ loan_id: '', repayment_no: '', amount_paid: '', payment_date: '', outstanding_balance: '', total_paid: '' }),
    rowToForm: (r) => ({ loan_id: s(r.loan_id), repayment_no: s(r.repayment_no), amount_paid: s(r.amount_paid), payment_date: s(r.payment_date).slice(0, 10), outstanding_balance: s(r.outstanding_balance), total_paid: s(r.total_paid) }),
  },
  {
    id: 'installment',
    label: 'Installment',
    pgTable: 'installment',
    canCreate: false,
    canEdit: false,
    canDelete: false,
    readOnlyNote: 'Auto-generated on first disbursement — view only.',
    columns: [
      { key: 'loan_id', label: 'loan_id', type: 'number', readOnlyAlways: true },
      { key: 'installment_no', label: 'installment_no', type: 'number', readOnlyAlways: true },
      { key: 'due_date', label: 'due_date', type: 'date', readOnlyAlways: true },
      { key: 'amount_due', label: 'amount_due', type: 'decimal', readOnlyAlways: true },
      { key: 'amount_paid', label: 'amount_paid', type: 'decimal', readOnlyAlways: true },
      { key: 'status', label: 'status', type: 'text', readOnlyAlways: true },
    ],
    list: () => asRows(api.allInstallments()),
    getRowKey: (r) => `${r.loan_id}-${r.installment_no}`,
    emptyForm: () => ({}),
    rowToForm: (r) => Object.fromEntries(Object.keys(r).map((k) => [k, s(r[k])])),
  },
  {
    id: 'disbursementtransaction',
    label: 'Disbursement Transaction',
    pgTable: 'disbursementtransaction',
    canCreate: false,
    canEdit: false,
    canDelete: false,
    readOnlyNote: 'System-generated link table — view only.',
    columns: [
      { key: 'transaction_id', label: 'transaction_id', type: 'number', readOnlyAlways: true },
      { key: 'loan_id', label: 'loan_id', type: 'number', readOnlyAlways: true },
      { key: 'disbursement_no', label: 'disbursement_no', type: 'number', readOnlyAlways: true },
    ],
    list: () => asRows(api.disbursementLinks()),
    getRowKey: (r) => String(r.transaction_id),
    emptyForm: () => ({}),
    rowToForm: (r) => Object.fromEntries(Object.keys(r).map((k) => [k, s(r[k])])),
  },
  {
    id: 'repaymenttransaction',
    label: 'Repayment Transaction',
    pgTable: 'repaymenttransaction',
    canCreate: false,
    canEdit: false,
    canDelete: false,
    readOnlyNote: 'System-generated link table — view only.',
    columns: [
      { key: 'transaction_id', label: 'transaction_id', type: 'number', readOnlyAlways: true },
      { key: 'loan_id', label: 'loan_id', type: 'number', readOnlyAlways: true },
      { key: 'repayment_no', label: 'repayment_no', type: 'number', readOnlyAlways: true },
    ],
    list: () => asRows(api.repaymentLinks()),
    getRowKey: (r) => String(r.transaction_id),
    emptyForm: () => ({}),
    rowToForm: (r) => Object.fromEntries(Object.keys(r).map((k) => [k, s(r[k])])),
  },
  {
    id: 'auditlog',
    label: 'Audit Log',
    pgTable: 'auditlog',
    canCreate: false,
    canEdit: false,
    canDelete: false,
    readOnlyNote: 'Append-only system audit trail — view only.',
    columns: [
      { key: 'user_id', label: 'user_id', type: 'number', readOnlyAlways: true },
      { key: 'log_id', label: 'log_id', type: 'number', readOnlyAlways: true },
      { key: 'action', label: 'action', type: 'textarea', readOnlyAlways: true },
      { key: 'log_timestamp', label: 'log_timestamp', type: 'datetime', readOnlyAlways: true },
      { key: 'entity_affected', label: 'entity_affected', type: 'text', readOnlyAlways: true },
    ],
    list: () => asRows(api.auditLogsAll()),
    getRowKey: (r) => `${r.user_id}-${r.log_id}`,
    emptyForm: () => ({}),
    rowToForm: (r) => Object.fromEntries(Object.keys(r).map((k) => [k, s(r[k])])),
  },
];
