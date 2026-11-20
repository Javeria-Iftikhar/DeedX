import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Header } from '../components/layout/Header';
import { GlassCard } from '../components/ui/GlassCard';
import { StatCard } from '../components/ui/StatCard';
import { FullDataTable } from '../components/ui/FullDataTable';
import { TrendingUp, Activity, DollarSign, BarChart3 } from 'lucide-react';
import { api, type EconomicIndicator, type ExchangeRate, type EconomicSummary, type EconomicRecord, type Country } from '../lib/api';
import { CHART } from '../lib/chartTheme';

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : 'Request failed';
}

export function EconomicPage() {
  const [indicators, setIndicators] = useState<EconomicIndicator[]>([]);
  const [records, setRecords] = useState<EconomicRecord[]>([]);
  const [rates, setRates] = useState<ExchangeRate[]>([]);
  const [countries, setCountries] = useState<Country[]>([]);
  const [summary, setSummary] = useState<EconomicSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setError(null);
      const [indR, recR, erR, cR, sumR] = await Promise.allSettled([
        api.indicators(),
        api.economicRecords().then((r) => r as unknown as EconomicRecord[]),
        api.exchangeRates(),
        api.countries(),
        api.economicSummary(),
      ]);

      const failures: string[] = [];

      if (indR.status === 'fulfilled') setIndicators(indR.value);
      else failures.push(`indicators: ${errMsg(indR.reason)}`);

      if (recR.status === 'fulfilled') setRecords(recR.value);
      else failures.push(`records: ${errMsg(recR.reason)}`);

      if (erR.status === 'fulfilled') setRates(erR.value);
      else failures.push(`exchange rates: ${errMsg(erR.reason)}`);

      if (cR.status === 'fulfilled') setCountries(cR.value);
      else failures.push(`countries: ${errMsg(cR.reason)}`);

      if (sumR.status === 'fulfilled') setSummary(sumR.value);
      else setSummary(null);

      // Only show banner if core economic data failed (not countries alone)
      const coreFailed =
        indR.status === 'rejected' && recR.status === 'rejected' && erR.status === 'rejected';
      if (coreFailed) {
        setError(failures.join(' · '));
      } else if (failures.length > 0) {
        setError(failures.join(' · '));
      }

      setLoading(false);
    };
    load();
  }, []);

  const countryMap = Object.fromEntries(countries.map((c) => [c.country_id, c.name]));

  const chartData = indicators.slice(0, 12).map((ind) => ({
    date: ind.record_date?.slice(5, 10) ?? '',
    CPI: Number(ind.CPI ?? 0),
    rate: Number(ind.interest_rate ?? 0),
  }));

  const fmtNum = (v: unknown) => (v == null || v === '' ? '—' : Number(v).toLocaleString(undefined, { maximumFractionDigits: 4 }));

  return (
    <motion.div>
      <Header title="Economic Indicators" subtitle="Macroeconomic monitoring and fiscal analytics for IMF member countries" />

      {error && (
        <motion.div className="mb-6 neon-card rounded-xl px-4 py-3 border border-amber-500/30 text-amber-200 text-sm">
          {error}
        </motion.div>
      )}

      <motion.div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5 mb-8">
        <StatCard label="Avg CPI" value={Math.round(summary?.averages.avg_CPI ?? 0)} icon={TrendingUp} color="cyan" />
        <StatCard label="Avg Inflation" value={Math.round((summary?.averages.avg_inflation ?? 0) * 100)} suffix="%" icon={Activity} color="royal" />
        <StatCard label="Avg GDP" value={Math.round(summary?.averages.avg_GDP ?? 0)} prefix="$" icon={DollarSign} color="aqua" />
        <StatCard label="Indicators" value={indicators.length} icon={BarChart3} color="cyan" />
      </motion.div>

      <motion.div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <GlassCard title="CPI & Interest Rate Trend" subtitle="Macroeconomic indicator movements">
          {loading ? (
            <motion.div className="h-60 flex items-center justify-center">
              <motion.div className="w-8 h-8 border-2 border-cyan/30 border-t-cyan rounded-full animate-spin" />
            </motion.div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: CHART.axis }} />
                <YAxis tick={{ fontSize: 11, fill: CHART.axis }} />
                <Tooltip />
                <Line type="monotone" dataKey="CPI" stroke="#22D3EE" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="rate" stroke="#1D4ED8" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </GlassCard>

        <GlassCard title="Exchange Rates" subtitle={`${rates.length} rows — all exchangerate columns`}>
          {loading ? (
            <motion.div className="flex justify-center py-12">
              <motion.div className="w-8 h-8 border-2 border-cyan/30 border-t-cyan rounded-full animate-spin" />
            </motion.div>
          ) : (
            <FullDataTable
              rows={rates as unknown as Record<string, unknown>[]}
              rowKey={(row) => String(row.exchange_rate_id)}
              columns={[
                { key: 'exchange_rate_id', label: 'exchange_rate_id' },
                { key: 'from_currency', label: 'from_currency' },
                { key: 'to_currency', label: 'to_currency' },
                { key: 'rate', label: 'rate', render: (v) => Number(v).toFixed(4) },
                { key: 'rate_date', label: 'rate_date' },
              ]}
            />
          )}
        </GlassCard>
      </motion.div>

      <GlassCard title="Economic Indicators" subtitle={`${indicators.length} rows — all economicindicator columns`} className="mb-8">
        {loading ? (
          <motion.div className="flex justify-center py-16">
            <motion.div className="w-8 h-8 border-2 border-cyan/30 border-t-cyan rounded-full animate-spin" />
          </motion.div>
        ) : (
          <FullDataTable
            rows={indicators as unknown as Record<string, unknown>[]}
            rowKey={(row) => String(row.indicator_id)}
            columns={[
              { key: 'indicator_id', label: 'indicator_id' },
              { key: 'country_id', label: 'country_id', render: (v) => (countryMap[Number(v)] ? `${v} (${countryMap[Number(v)]})` : String(v)) },
              { key: 'record_date', label: 'record_date' },
              { key: 'CPI', label: 'CPI', render: fmtNum },
              { key: 'industrial_output', label: 'industrial_output', render: fmtNum },
              { key: 'agricultural_output', label: 'agricultural_output', render: fmtNum },
              { key: 'services_output', label: 'services_output', render: fmtNum },
              { key: 'money_supply', label: 'money_supply', render: fmtNum },
              { key: 'interest_rate', label: 'interest_rate', render: fmtNum },
              { key: 'exchange_rate', label: 'exchange_rate', render: fmtNum },
            ]}
          />
        )}
      </GlassCard>

      <GlassCard title="Economic Records" subtitle={`${records.length} rows — derived GDP & inflation (synced from indicators)`}>
        {loading ? (
          <motion.div className="flex justify-center py-16">
            <motion.div className="w-8 h-8 border-2 border-cyan/30 border-t-cyan rounded-full animate-spin" />
          </motion.div>
        ) : (
          <FullDataTable
            rows={records as unknown as Record<string, unknown>[]}
            rowKey={(row) => String(row.record_id)}
            columns={[
              { key: 'record_id', label: 'record_id' },
              { key: 'indicator_id', label: 'indicator_id' },
              { key: 'GDP', label: 'GDP', render: fmtNum },
              { key: 'inflation', label: 'inflation', render: fmtNum },
            ]}
          />
        )}
      </GlassCard>
    </motion.div>
  );
}
