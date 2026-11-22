import { motion } from 'framer-motion';
import { formatDate } from '../../lib/api';

export interface TableColumn<T extends Record<string, unknown>> {
  key: keyof T & string;
  id?: string;
  label?: string;
  render?: (value: unknown, row: T) => React.ReactNode;
}

function formatCellValue(key: string, val: unknown): string {
  if (val == null || val === '') return '—';
  const str = String(val);
  if (key.includes('date') || key.includes('timestamp') || key === 'last_login' || key === 'created_at') {
    try {
      return formatDate(str);
    } catch {
      return str;
    }
  }
  if (typeof val === 'number' && key === 'population') return val.toLocaleString();
  return str;
}

export function FullDataTable<T extends Record<string, unknown>>({
  rows,
  columns,
  rowKey,
  emptyMessage = 'No records found',
}: {
  rows: T[];
  columns: TableColumn<T>[];
  rowKey: (row: T, index: number) => string;
  emptyMessage?: string;
}) {
  if (rows.length === 0) {
    return <p className="text-slate text-sm text-center py-12">{emptyMessage}</p>;
  }

  return (
    <motion.div className="overflow-x-auto">
      <table className="w-full data-table">
        <thead>
          <tr className="border-b border-slate/10">
            {columns.map((col) => (
              <th key={col.id ?? col.key} className="text-left py-3 px-4 whitespace-nowrap">
                {col.label ?? col.key}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={rowKey(row, i)} className="border-b border-slate/5 hover:bg-cyan/5 transition-colors">
              {columns.map((col) => {
                const raw = row[col.key];
                return (
                  <td key={col.id ?? col.key} className="py-3 px-4 text-sm text-light/90 whitespace-nowrap">
                    {col.render ? col.render(raw, row) : formatCellValue(col.key, raw)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </motion.div>
  );
}
