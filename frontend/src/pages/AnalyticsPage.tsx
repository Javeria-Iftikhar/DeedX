import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Sparkles,
  Send,
  Brain,
  Zap,
  Copy,
  ThumbsUp,
  ThumbsDown,
  FileDown,
  FileSpreadsheet,
  RefreshCw,
  MoreHorizontal,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { Header } from '../components/layout/Header';
import { GlassCard } from '../components/ui/GlassCard';
import { Button } from '../components/ui/Button';
import { api, type AnalyticsConversationTurn, type AnalyticsDashboardResponse } from '../lib/api';
import { CHART } from '../lib/chartTheme';

const suggestions = [
  'Generate report on inflation',
  'Generate report on GDP and CPI',
  'Show sovereign loans by status',
  'List member countries with highest IMF loan amounts',
  'Average CPI by member country',
  'Top 5 countries by inflation',
];

const ANALYTICS_START_RE =
  /^\s*(?:show|list|display|get|give\s+me|what\s+(?:is|are)|how\s+many|top\s+\d+|average|total|compare|chart|plot|graph)\b/i;

const REPORT_ACTION_RE =
  /\b(?:generate|create|write|build|prepare|compile|draft)\s+(?:a\s+)?(?:(?:full|detailed|comprehensive)\s+)?report\b/i;

const REPORT_PROMPT_RE =
  /\b(?:generate|create|write|build|produce|prepare|compile|draft)\s+(?:a\s+)?(?:full\s+)?report\b/i;

function isReportPrompt(text: string): boolean {
  const ctx = text.toLowerCase().trim();
  if (!/\breport\b/.test(ctx)) return false;
  if (ANALYTICS_START_RE.test(ctx) && !REPORT_ACTION_RE.test(ctx)) return false;
  return (
    REPORT_PROMPT_RE.test(ctx) ||
    /\b(?:generate|create|write|build|prepare|compile|draft)\s+(?:a\s+)?report\s+on\b/.test(ctx) ||
    /\b(?:full|detailed|comprehensive)\s+(?:economic\s+)?report\s+(?:on|about|for)\b/.test(ctx)
  );
}

function wantsExplicitFileExport(text: string): boolean {
  const ctx = text.toLowerCase().trim();
  return (
    /\b(export|download|save)\b/.test(ctx) ||
    /\bas\s+(?:a\s+)?(?:pdf|csv)\b/.test(ctx) ||
    /\bto\s+(?:a\s+)?(?:pdf|csv)\b/.test(ctx) ||
    /\bgenerate\s+(?:a\s+)?(?:pdf|csv)\b/.test(ctx) ||
    (/\b(pdf|csv)\b/.test(ctx) && /\b(export|download|save|give\s+me|send)\b/.test(ctx))
  );
}

function isStructuredReportResult(result: AnalyticsDashboardResponse | undefined): boolean {
  const mod = result?.metadata && typeof result.metadata === 'object'
    ? String((result.metadata as Record<string, unknown>).module ?? '')
    : '';
  return mod === 'report:economic';
}

function uid() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const PIE_COLORS = ['#22D3EE', '#6366F1', '#10B981', '#F59E0B', '#F472B6', '#A78BFA', '#34D399', '#FB7185'];

function buildConversation(messages: ChatMessage[]): AnalyticsConversationTurn[] {
  return messages
    .filter((m): m is Extract<ChatMessage, { role: 'user' }> | Extract<ChatMessage, { role: 'assistant' }> =>
      m.role === 'user' || (m.role === 'assistant' && !m.error),
    )
    .map((m) => ({
      role: m.role,
      content: m.role === 'user' ? m.text : [m.result?.title, m.result?.summary].filter(Boolean).join('\n'),
    }))
    .filter((t) => t.content.trim().length > 0);
}

function rowsToTsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return '';
  const cols = Object.keys(rows[0]);
  const line = (r: Record<string, unknown>) =>
    cols.map((c) => String(r[c] ?? '').replace(/\t/g, ' ')).join('\t');
  return [cols.join('\t'), ...rows.map(line)].join('\n');
}

type ChatMessage =
  | { id: string; role: 'user'; text: string }
  | { id: string; role: 'assistant'; result?: AnalyticsDashboardResponse; error?: string };

export function AnalyticsPage() {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState<'pdf' | 'csv' | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  const runQuestion = async (q: string) => {
    const text = q.trim();
    if (!text) return;

    const userMsg: ChatMessage = { id: uid(), role: 'user', text };
    setMessages((m) => [...m, userMsg]);
    setLoading(true);
    const conversation = buildConversation([...messages, userMsg]);
    try {
      const result = await api.analyticsQuery(text, conversation);
      setMessages((m) => [...m, { id: uid(), role: 'assistant', result }]);
      const fmt = result.export_format?.toLowerCase();
      // Full economic report PDF — only for explicit "Generate report on …" prompts
      const shouldGenerateReport = isReportPrompt(text) || isStructuredReportResult(result);
      const shouldExportChartPdf = fmt === 'pdf' && wantsExplicitFileExport(text) && !shouldGenerateReport;
      const shouldExportCsv = fmt === 'csv' && wantsExplicitFileExport(text);
      if (shouldGenerateReport || shouldExportChartPdf || shouldExportCsv) {
        setExporting(shouldGenerateReport || shouldExportChartPdf ? 'pdf' : 'csv');
        try {
          if (shouldGenerateReport) await api.generateReport(text);
          else if (shouldExportChartPdf) await api.analyticsExportPdf(text, conversation);
          else await api.analyticsExportCsv(text, conversation);
        } catch (exportErr) {
          const msg = exportErr instanceof Error ? exportErr.message : 'Export failed';
          setMessages((m) => [
            ...m,
            { id: uid(), role: 'assistant', error: `Export failed: ${msg}` },
          ]);
        } finally {
          setExporting(null);
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Query failed';
      setMessages((m) => [...m, { id: uid(), role: 'assistant', error: msg }]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = () => {
    if (loading) return;
    const text = query.trim();
    if (!text) return;
    setQuery('');
    runQuestion(text);
  };

  const copyText = async (value: string, label: string) => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      window.alert(`Could not copy ${label}.`);
    }
  };

  const lastUserQuestion = (): string => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === 'user') return m.text;
    }
    return '';
  };

  /** Download the current Q&A result as PDF/CSV (chart + table). Not the full economic report. */
  const handleExport = async (format: 'pdf' | 'csv', question: string) => {
    const q = question.trim();
    if (!q) {
      window.alert('Run a query first, then use export to download that result.');
      return;
    }
    const conversation = buildConversation(messages);
    setExporting(format);
    try {
      if (format === 'pdf') {
        await api.analyticsExportPdf(q, conversation);
      } else {
        await api.analyticsExportCsv(q, conversation);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Export failed';
      window.alert(msg);
    } finally {
      setExporting(null);
    }
  };

  const renderChart = (result: AnalyticsDashboardResponse) => {
    const chartData =
      result.labels?.map((label, i) => ({
        name: label,
        value: result.values?.[i] ?? 0,
      })) ?? [];
    if (!chartData.length || !result.chart_type || result.chart_type === 'table') return null;

    const chartType = result.chart_type.toLowerCase();

    if (chartType === 'line' || chartType === 'area') {
      return (
        <div className="mb-4">
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: CHART.axis }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: CHART.axis }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={CHART.tooltip.contentStyle} />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#22D3EE"
                strokeWidth={2}
                dot={{ r: 3, fill: '#22D3EE' }}
                fill={chartType === 'area' ? 'url(#lineArea)' : undefined}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      );
    }

    if (chartType === 'pie') {
      return (
        <div className="mb-4">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={chartData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={CHART.tooltip.contentStyle} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      );
    }

    return (
      <div className="mb-4">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
            <XAxis dataKey="name" tick={{ fontSize: 11, fill: CHART.axis }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: CHART.axis }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={CHART.tooltip.contentStyle} />
            <Bar dataKey="value" fill="#22D3EE" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  };

  const renderAssistantToolbar = (
    result: AnalyticsDashboardResponse | undefined,
    error: string | undefined,
    userQuestion: string,
  ) => {
    const summary = error ?? result?.summary ?? '';
    const rows = result?.rows ?? [];
    const block = [summary, rows.length ? rowsToTsv(rows) : ''].filter(Boolean).join('\n\n');

    return (
      <div className="flex items-center gap-0.5 mt-3 pt-2 border-t border-cyan/10">
        <button
          type="button"
          title="Copy"
          aria-label="Copy response"
          disabled={!block}
          onClick={() => copyText(block, 'response')}
          className="p-1.5 rounded-lg text-slate hover:text-cyan hover:bg-cyan/5 disabled:opacity-40 transition-colors"
        >
          <Copy size={16} strokeWidth={1.75} />
        </button>
        <button
          type="button"
          title="Helpful"
          aria-label="Mark helpful"
          className="p-1.5 rounded-lg text-slate hover:text-cyan hover:bg-cyan/5 transition-colors"
        >
          <ThumbsUp size={16} strokeWidth={1.75} />
        </button>
        <button
          type="button"
          title="Not helpful"
          aria-label="Mark not helpful"
          className="p-1.5 rounded-lg text-slate hover:text-cyan hover:bg-cyan/5 transition-colors"
        >
          <ThumbsDown size={16} strokeWidth={1.75} />
        </button>
        <button
          type="button"
          title="Download this answer as PDF (chart and table)"
          aria-label="Download result as PDF"
          disabled={!userQuestion || exporting !== null}
          onClick={() => void handleExport('pdf', userQuestion)}
          className="p-1.5 rounded-lg text-slate hover:text-cyan hover:bg-cyan/5 disabled:opacity-40 transition-colors"
        >
          <FileDown size={16} strokeWidth={1.75} />
        </button>
        <button
          type="button"
          title="Download this answer as CSV"
          aria-label="Download result as CSV"
          disabled={!userQuestion || exporting !== null}
          onClick={() => void handleExport('csv', userQuestion)}
          className="p-1.5 rounded-lg text-slate hover:text-cyan hover:bg-cyan/5 disabled:opacity-40 transition-colors"
        >
          <FileSpreadsheet size={16} strokeWidth={1.75} />
        </button>
        <button
          type="button"
          title="Regenerate"
          aria-label="Regenerate"
          onClick={() => {
            const q = lastUserQuestion();
            if (q) runQuestion(q);
          }}
          className="p-1.5 rounded-lg text-slate hover:text-cyan hover:bg-cyan/5 transition-colors"
        >
          <RefreshCw size={16} strokeWidth={1.75} />
        </button>
        <button
          type="button"
          title="More"
          aria-label="More"
          className="p-1.5 rounded-lg text-slate hover:text-cyan hover:bg-cyan/5 transition-colors"
        >
          <MoreHorizontal size={16} strokeWidth={1.75} />
        </button>
      </div>
    );
  };

  return (
    <motion.div>
      <Header title="Fiscal Analytics" subtitle="AI-driven sovereign finance and macroeconomic intelligence" />

      <GlassCard variant="ai" className="mb-8" delay={50}>
        <motion.div className="flex items-start gap-4 mb-4 relative z-10">
          <motion.div
            animate={{ boxShadow: ['0 0 20px rgba(34,211,238,0.2)', '0 0 40px rgba(34,211,238,0.35)', '0 0 20px rgba(34,211,238,0.2)'] }}
            transition={{ duration: 2.5, repeat: Infinity }}
            className="p-3 rounded-2xl bg-gradient-to-br from-cyan/20 to-royal/20 border border-cyan/30"
          >
            <Brain size={24} className="text-cyan" />
          </motion.div>
          <motion.div className="flex-1">
            <motion.div className="flex items-center gap-2 mb-1">
              <h3 className="font-bold text-lg font-[family-name:var(--font-display)] text-light">Fiscala Intelligence</h3>
              <span className="text-[10px] font-semibold uppercase tracking-widest px-2 py-0.5 rounded-full bg-cyan/10 text-cyan border border-cyan/25">AI Engine</span>
            </motion.div>
            <p className="text-sm text-slate">
              Ask free-form questions about loans, indicators, repayments, and transactions.
              Use <span className="text-cyan/90">Generate report on …</span> for a full economic PDF;
              the toolbar download icon exports the chart and table for the current answer.
            </p>
          </motion.div>
          <motion.div className="hidden md:flex items-center gap-1.5 text-xs text-cyan/60">
            <Zap size={14} />
            <span>Groq + LangChain</span>
          </motion.div>
        </motion.div>

        <div
          ref={scrollRef}
          className="space-y-5 max-h-[min(520px,calc(100vh-300px))] overflow-y-auto pr-1 mb-5 relative z-10"
        >
          {messages.length === 0 && !loading && (
            <p className="text-sm text-slate/80 text-center py-6">
              Start a conversation — your questions appear on the right; analysis and tables on the left.
            </p>
          )}

          {messages.map((msg) => {
            if (msg.role === 'user') {
              return (
                <div key={msg.id} className="flex justify-end">
                  <div className="max-w-[88%] rounded-2xl px-4 py-3 bg-navy-light/75 border border-cyan/15 text-light text-sm leading-relaxed">
                    {msg.text}
                  </div>
                </div>
              );
            }

            const { result, error } = msg;
            let userQuestion = '';
            const msgIndex = messages.findIndex((m) => m.id === msg.id);
            if (msgIndex > 0) {
              const prev = messages[msgIndex - 1];
              if (prev.role === 'user') userQuestion = prev.text;
            }

            return (
              <div key={msg.id} className="flex justify-start">
                <div className="max-w-[96%] w-full min-w-0">
                  {error && (
                    <p className="text-red-400 text-sm mb-2">{error}</p>
                  )}

                  {!error && result?.title && (
                    <h4 className="text-sm font-semibold text-light/95 mb-2">{result.title}</h4>
                  )}

                  {!error && result?.summary && (
                    <blockquote className="border-l-2 border-cyan/25 pl-4 text-sm text-slate leading-relaxed mb-4 whitespace-pre-wrap">
                      {result.summary}
                    </blockquote>
                  )}

                  {!error && result && renderChart(result)}

                  {!error && result?.rows && result.rows.length > 0 && (
                    <div className="overflow-x-auto rounded-xl border border-cyan/10 bg-white/[0.02]">
                      <table className="w-full data-table">
                        <thead>
                          <tr className="border-b border-cyan/10 bg-white/[0.03]">
                            {Object.keys(result.rows[0]).map((k) => (
                              <th key={k} className="text-left py-3 px-4 text-xs font-medium text-slate">
                                {k}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {result.rows.map((row, i) => (
                            <tr key={i} className="border-b border-cyan/5 last:border-b-0">
                              {Object.values(row).map((v, j) => (
                                <td key={j} className="py-3 px-4 text-sm text-light/90">
                                  {String(v)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {!error &&
                    !(result?.rows && result.rows.length > 0) &&
                    !(result?.labels?.length && result.chart_type && result.chart_type !== 'table') && (
                      <p className="text-sm text-slate">No tabular rows for this question (check filters or wording).</p>
                    )}

                  {renderAssistantToolbar(result, error, userQuestion)}
                </div>
              </div>
            );
          })}

          {loading && (
            <div className="flex justify-start text-sm text-slate animate-pulse">Thinking…</div>
          )}
        </div>

        <motion.div className="flex gap-3 relative z-10 border-t border-cyan/10 pt-4">
          <motion.div className="flex-1 relative">
            <Sparkles size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-cyan/50" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
              placeholder="Ask anything — e.g. Top 5 countries by average GDP…"
              className="ai-input w-full rounded-xl pl-11 pr-4 py-3.5 text-sm"
              disabled={loading}
            />
          </motion.div>
          <Button onClick={handleSubmit} loading={loading} disabled={loading}>
            <Send size={16} /> Analyze
          </Button>
        </motion.div>

        <motion.div className="flex flex-wrap gap-2 mt-4 relative z-10">
          <p className="text-[10px] uppercase tracking-widest text-slate w-full mb-1">Suggested queries</p>
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              disabled={loading}
              onClick={() => { void runQuestion(s); }}
              className="text-xs px-3 py-1.5 rounded-full bg-cyan/5 text-slate border border-cyan/15 hover:bg-cyan/10 hover:text-aqua hover:border-cyan/30 hover:shadow-[0_0_12px_rgba(34,211,238,0.15)] transition-all disabled:opacity-40"
            >
              {s}
            </button>
          ))}
        </motion.div>
      </GlassCard>
    </motion.div>
  );
}
