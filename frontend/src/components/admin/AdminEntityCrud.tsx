import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { GlassCard } from '../ui/GlassCard';
import { Modal, Field, inputClass } from './Modal';
import { ThemedSelect } from './ThemedSelect';
import type { AdminColumn, AdminTableConfig, LookupKey } from '../../lib/adminTables';
import { formatDate } from '../../lib/api';

export interface AdminLookups {
  currencies: { currency_code: string; currency_name?: string }[];
  countries: { country_id: number; name: string }[];
  programs: { program_id: number; program_name: string }[];
  accounts: { imf_account_id: number; account_number: string }[];
  users: { user_id: number; name: string; email: string }[];
  loans: { loan_id: number }[];
  conditions: { condition_id: number; condition_type?: string }[];
  indicators: { indicator_id: number; country_id?: number; record_date?: string }[];
}

function Btn({ children, onClick, variant = 'primary' }: { children: React.ReactNode; onClick: () => void; variant?: 'primary' | 'danger' }) {
  const cls = variant === 'danger' ? 'text-red-400 hover:bg-red-500/10 border-red-500/30' : 'text-cyan hover:bg-cyan/10 border-cyan/30';
  return (
    <button type="button" onClick={onClick} className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors ${cls}`}>
      {children}
    </button>
  );
}

function formatCell(key: string, val: unknown): string {
  if (val == null || val === '') return '—';
  const str = String(val);
  if (key.includes('date') || key.includes('timestamp') || key === 'last_login' || key === 'created_at') {
    try { return formatDate(str); } catch { return str; }
  }
  if (typeof val === 'number' && key === 'population') return val.toLocaleString();
  return str.length > 80 ? `${str.slice(0, 77)}…` : str;
}

function lookupOptions(key: LookupKey, lookups: AdminLookups): { value: string; label: string }[] {
  switch (key) {
    case 'currencies':
      return lookups.currencies.map((c) => ({ value: c.currency_code, label: `${c.currency_code}${c.currency_name ? ` — ${c.currency_name}` : ''}` }));
    case 'countries':
      return lookups.countries.map((c) => ({ value: String(c.country_id), label: `${c.country_id} — ${c.name}` }));
    case 'programs':
      return lookups.programs.map((p) => ({ value: String(p.program_id), label: `${p.program_id} — ${p.program_name}` }));
    case 'accounts':
      return lookups.accounts.map((a) => ({ value: String(a.imf_account_id), label: `${a.imf_account_id} — ${a.account_number}` }));
    case 'users':
      return lookups.users.map((u) => ({ value: String(u.user_id), label: `${u.user_id} — ${u.name} (${u.email})` }));
    case 'loans':
      return lookups.loans.map((l) => ({ value: String(l.loan_id), label: `Loan #${l.loan_id}` }));
    case 'conditions':
      return lookups.conditions.map((c) => ({ value: String(c.condition_id), label: `#${c.condition_id}${c.condition_type ? ` — ${c.condition_type}` : ''}` }));
    case 'indicators':
      return lookups.indicators.map((i) => ({ value: String(i.indicator_id), label: `Indicator #${i.indicator_id}` }));
    default:
      return [];
  }
}

function visibleColumns(config: AdminTableConfig, mode: 'table' | 'create' | 'edit'): AdminColumn[] {
  return config.columns.filter((col) => {
    if (mode === 'table' && col.hideInTable) return false;
    if (mode === 'create' && (col.hideOnCreate || col.readOnlyAlways)) return false;
    if (mode === 'edit' && (col.hideOnEdit || col.readOnlyAlways)) return false;
    return true;
  });
}

function FieldInput({
  col,
  form,
  setForm,
  lookups,
  mode,
}: {
  col: AdminColumn;
  form: Record<string, string>;
  setForm: (f: Record<string, string>) => void;
  lookups: AdminLookups;
  mode: 'create' | 'edit';
}) {
  const disabled = col.readOnlyAlways || (mode === 'edit' && col.hideOnEdit);
  const value = form[col.key] ?? '';

  if (col.type === 'select') {
    const opts = col.staticOptions ?? (col.selectFrom ? lookupOptions(col.selectFrom, lookups) : []);
    return (
      <ThemedSelect
        value={value}
        disabled={disabled}
        onChange={(v) => setForm({ ...form, [col.key]: v })}
        options={opts}
        placeholder="Select…"
        menuZIndex={110}
      />
    );
  }
  if (col.type === 'textarea') {
    return <textarea className={`${inputClass} min-h-[72px]`} value={value} disabled={disabled} onChange={(e) => setForm({ ...form, [col.key]: e.target.value })} />;
  }
  const inputType = col.type === 'password' ? 'password' : col.type === 'number' || col.type === 'decimal' ? 'number' : col.type === 'date' ? 'date' : col.type === 'datetime' ? 'datetime-local' : 'text';
  return (
    <input
      type={inputType}
      step={col.type === 'decimal' ? '0.0001' : undefined}
      className={inputClass}
      value={col.type === 'date' || col.type === 'datetime' ? value.slice(0, col.type === 'date' ? 10 : 16) : value}
      disabled={disabled}
      onChange={(e) => setForm({ ...form, [col.key]: e.target.value })}
    />
  );
}

interface Props {
  config: AdminTableConfig;
  lookups: AdminLookups;
  onError: (msg: string | null) => void;
  onFlash: (msg: string) => void;
}

export function AdminEntityCrud({ config, lookups, onError, onFlash }: Props) {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<'create' | 'edit' | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [editRow, setEditRow] = useState<Record<string, unknown> | null>(null);
  const [saving, setSaving] = useState(false);

  const tableCols = visibleColumns(config, 'table');

  const load = useCallback(async () => {
    setLoading(true);
    onError(null);
    try {
      const data = await config.list();
      setRows(data as Record<string, unknown>[]);
    } catch (e) {
      onError(e instanceof Error ? e.message : `Failed to load ${config.label}`);
    } finally {
      setLoading(false);
    }
  }, [config, onError]);

  useEffect(() => { load(); }, [load]);

  const closeModal = () => { setModal(null); setEditRow(null); };

  const openCreate = () => {
    setForm(config.emptyForm());
    setEditRow(null);
    setModal('create');
  };

  const openEdit = (row: Record<string, unknown>) => {
    setEditRow(row);
    setForm(config.rowToForm(row));
    setModal('edit');
  };

  const save = async () => {
    setSaving(true);
    onError(null);
    try {
      if (modal === 'create' && config.create) {
        await config.create(form);
        onFlash(`${config.label} created`);
      } else if (modal === 'edit' && config.update && editRow) {
        await config.update(editRow, form);
        onFlash(`${config.label} updated`);
      }
      closeModal();
      await load();
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const del = async (row: Record<string, unknown>) => {
    if (!config.remove) return;
    const label = config.getRowKey(row);
    if (!window.confirm(`Delete ${config.label} record ${label}?`)) return;
    onError(null);
    try {
      await config.remove(row);
      onFlash(`${config.label} deleted`);
      await load();
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Delete failed');
    }
  };

  const formCols = visibleColumns(config, modal === 'edit' ? 'edit' : 'create');
  const showAdd = config.canCreate && config.create;
  const showActions = config.canEdit || config.canDelete;

  return (
    <>
    <GlassCard
      title={config.label}
      subtitle={`PostgreSQL: ${config.pgTable} · ${rows.length} row(s)`}
      action={showAdd ? <Btn onClick={openCreate}><Plus size={14} /> Add</Btn> : undefined}
    >
      {config.readOnlyNote && (
        <p className="text-xs text-slate mb-4 border border-cyan/10 rounded-lg px-3 py-2 bg-cyan/5">{config.readOnlyNote}</p>
      )}

      {loading ? (
        <motion.div className="flex justify-center py-16">
          <motion.div className="w-8 h-8 border-2 border-cyan/30 border-t-cyan rounded-full animate-spin" />
        </motion.div>
      ) : (
        <div className="overflow-x-auto max-h-[min(70vh,640px)] overflow-y-auto">
          <table className="w-full data-table text-sm">
            <thead className="sticky top-0 bg-[#050816]/95 backdrop-blur z-10">
              <tr className="border-b border-slate/10">
                {tableCols.map((c) => (
                  <th key={c.key} className="text-left py-2.5 px-3 whitespace-nowrap text-xs uppercase tracking-wide text-slate">{c.label}</th>
                ))}
                {showActions && <th className="text-left py-2.5 px-3 w-28" />}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr><td colSpan={tableCols.length + (showActions ? 1 : 0)} className="py-12 text-center text-slate">No records</td></tr>
              ) : rows.map((row) => (
                <tr key={config.getRowKey(row)} className="border-b border-slate/5 hover:bg-cyan/5">
                  {tableCols.map((c) => (
                    <td key={c.key} className="py-2.5 px-3 text-light whitespace-nowrap max-w-[200px] truncate" title={String(row[c.key] ?? '')}>
                      {formatCell(c.key, row[c.key])}
                    </td>
                  ))}
                  {showActions && (
                    <td className="py-2.5 px-3 flex gap-1.5">
                      {config.canEdit && config.update && (
                        <Btn onClick={() => openEdit(row)}><Pencil size={12} /> Edit</Btn>
                      )}
                      {config.canDelete && config.remove && (
                        <Btn variant="danger" onClick={() => del(row)}><Trash2 size={12} /></Btn>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

    </GlassCard>

    <Modal
      open={modal != null}
      title={modal === 'edit' ? `Edit ${config.label}` : `Add ${config.label}`}
      onClose={closeModal}
    >
      {formCols.map((col) => (
        <Field key={col.key} label={col.label}>
          <FieldInput col={col} form={form} setForm={setForm} lookups={lookups} mode={modal === 'edit' ? 'edit' : 'create'} />
        </Field>
      ))}
      <button type="button" disabled={saving} onClick={save} className="btn-primary w-full mt-2">
        {saving ? 'Saving…' : 'Save'}
      </button>
    </Modal>
    </>
  );
}
