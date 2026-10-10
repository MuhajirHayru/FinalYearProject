"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Download, TrendingUp } from "lucide-react";
import { Button, Card, CardHeader, EmptyState, ErrorBanner, Field, Input, StatCard } from "@/components/ui";
import { reportsApi } from "@/lib/api/client";
import { formatEtb, formatInt } from "@/lib/format";
import type { WalletActivityReport } from "@/lib/types";

export function WalletActivityAnalytics() {
  const [report, setReport] = useState<WalletActivityReport | null>(null);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [appliedPeriod, setAppliedPeriod] = useState<{ date_from?: string; date_to?: string }>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await reportsApi.walletActivity({
        date_from: appliedPeriod.date_from,
        date_to: appliedPeriod.date_to,
      });
      setReport(result);
      if (!dateFrom) setDateFrom(result.period.date_from);
      if (!dateTo) setDateTo(result.period.date_to);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load wallet activity.");
    } finally {
      setLoading(false);
    }
  }, [appliedPeriod]);

  useEffect(() => { void load(); }, [load]);

  function applyPeriod(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedPeriod({
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    });
  }

  async function downloadCsv() {
    setExporting(true);
    setError("");
    try {
      const { blob, filename } = await reportsApi.walletActivityExport({
        date_from: appliedPeriod.date_from,
        date_to: appliedPeriod.date_to,
      });
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(href);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not export wallet activity.");
    } finally {
      setExporting(false);
    }
  }

  const peak = Math.max(
    0,
    ...(report?.daily.flatMap((item) => [
      Number(item.deposits),
      Number(item.payouts),
    ]) ?? [])
  );

  return (
    <section className="space-y-6">
      {error && <ErrorBanner message={error} onRetry={() => void load()} />}
      <Card>
        <form onSubmit={applyPeriod} className="flex flex-col gap-4 p-4 md:flex-row md:items-end md:justify-between">
          <div className="grid flex-1 gap-3 sm:grid-cols-2">
            <Field label="From" htmlFor="wallet-report-from">
              <Input id="wallet-report-from" type="date" value={dateFrom} max={dateTo || undefined} onChange={(event) => setDateFrom(event.target.value)} />
            </Field>
            <Field label="To" htmlFor="wallet-report-to">
              <Input id="wallet-report-to" type="date" value={dateTo} min={dateFrom || undefined} onChange={(event) => setDateTo(event.target.value)} />
            </Field>
          </div>
          <div className="flex gap-2">
            <Button type="submit" variant="secondary" loading={loading}>Apply dates</Button>
            <Button type="button" onClick={() => void downloadCsv()} loading={exporting} disabled={!report} icon={<Download className="h-4 w-4" />}>Export wallet CSV</Button>
          </div>
        </form>
      </Card>

      {report && (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            <StatCard
              label="Completed wallet deposits"
              value={formatEtb(report.summary.deposits.amount)}
              icon={<TrendingUp className="h-5 w-5" />}
              iconBg="bg-green-600"
              sublabel={`${formatInt(report.summary.deposits.count)} ledger entries`}
            />
            <StatCard
              label="Completed wallet payouts"
              value={formatEtb(report.summary.payouts.amount)}
              icon={<TrendingUp className="h-5 w-5 rotate-180" />}
              iconBg="bg-blue-600"
              sublabel={`${formatInt(report.summary.payouts.count)} ledger entries`}
            />
          </div>

          <Card>
            <CardHeader
              title="Daily wallet activity"
              subtitle={`${report.period.date_from} through ${report.period.date_to} · completed ledger entries only`}
            />
            {loading ? (
              <p className="p-5 text-sm text-gray-500">Refreshing report…</p>
            ) : report.daily.length === 0 ? (
              <EmptyState title="No daily activity" />
            ) : (
              <>
                <div className="flex h-56 items-end gap-1 overflow-x-auto px-5 pt-5">
                  {report.daily.map((item) => (
                    <div key={item.date} className="group flex h-full min-w-3 flex-1 items-end justify-center gap-0.5" title={`${item.date}: deposits ${formatEtb(item.deposits)} (${item.deposit_count}), payouts ${formatEtb(item.payouts)} (${item.payout_count})`}>
                      <div className="w-1/2 rounded-t bg-green-500" style={{ height: `${peak ? Math.max(Number(item.deposits) ? 3 : 0, Number(item.deposits) / peak * 100) : 0}%` }} />
                      <div className="w-1/2 rounded-t bg-blue-500" style={{ height: `${peak ? Math.max(Number(item.payouts) ? 3 : 0, Number(item.payouts) / peak * 100) : 0}%` }} />
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap justify-between gap-3 px-5 py-3 text-xs text-gray-500">
                  <span>{report.period.date_from}</span>
                  <span className="flex gap-4"><span className="text-green-700">■ Deposits</span><span className="text-blue-700">■ Payouts</span></span>
                  <span>{report.period.date_to}</span>
                </div>
              </>
            )}
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            {(["deposits", "payouts"] as const).map((kind) => (
              <Card key={kind}>
                <CardHeader title={`${kind === "deposits" ? "Deposit" : "Payout"} request statuses`} subtitle="Request totals for submissions in the selected period" />
                <div className="divide-y divide-gray-100 px-5">
                  {Object.entries(report.status_breakdown[kind]).map(([status, values]) => (
                    <div key={status} className="flex items-center justify-between py-3 text-sm">
                      <span className="text-gray-700">{status.replaceAll("_", " ")}</span>
                      <span className="text-right font-medium text-gray-900">{formatInt(values.count)} · {formatEtb(values.amount)}</span>
                    </div>
                  ))}
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
