"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BadgeCheck,
  Clock,
  Flag,
  Receipt,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorBanner,
  PageLoader,
  StatCard,
  TableWrap,
  Td,
  Th,
} from "@/components/ui";
import { dashboardApi, paymentsApi, reportsApi } from "@/lib/api/client";
import { formatEtb, formatEtbPrecise, formatInt, shortRelative } from "@/lib/format";
import type {
  FinancialOperationsSummary,
  PaymentRecord,
  PaymentSummaryData,
} from "@/lib/types";

const PERIODS = [
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
];

export default function FinancialManagerDashboardPage() {
  const router = useRouter();
  const [summary, setSummary] = useState<PaymentSummaryData | null>(null);
  const [operations, setOperations] = useState<FinancialOperationsSummary | null>(null);
  const [recent, setRecent] = useState<PaymentRecord[]>([]);
  const [period, setPeriod] = useState("30");
  const [volume, setVolume] = useState<{ date: string; count: number; total: number }[]>(
    []
  );
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const [s, ops, list, vol] = await Promise.all([
        dashboardApi.payments(),
        dashboardApi.financialOperations(),
        paymentsApi.list({ page: 1, status: "PENDING" }),
        reportsApi.transactionVolume(Number(period)),
      ]);
      setSummary(s);
      setOperations(ops);
      setRecent(list.results.slice(0, 6));
      setVolume(vol.series);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <AppShell title="Financial Dashboard" allow={["FINANCIAL_MANAGER"]}>
        <PageLoader />
      </AppShell>
    );
  }

  if (!summary || !operations) {
    return (
      <AppShell title="Financial Dashboard" allow={["FINANCIAL_MANAGER"]}>
        <ErrorBanner
          message={error || "Financial dashboard data is unavailable."}
          onRetry={() => void load()}
        />
      </AppShell>
    );
  }

  const s = summary?.summary;
  const peak = volume.reduce((max, v) => Math.max(max, v.total), 0);
  const totalRecords = Object.values(summary.tabs).reduce(
    (total, count) => total + count,
    0
  );
  const escrowRelease = operations.escrow.AWAITING_PAYMENT_RELEASE;
  const escrowDisputed = operations.escrow.DISPUTED;
  const escrowCount = (escrowRelease?.count ?? 0) + (escrowDisputed?.count ?? 0);

  return (
    <AppShell title="Financial Dashboard" allow={["FINANCIAL_MANAGER"]}>
      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} onRetry={() => void load()} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Pending Verification"
          value={formatEtb(s?.pending_amount ?? 0)}
          icon={<Clock className="h-6 w-6" />}
          iconBg="bg-amber-500"
          sublabel={`${formatInt(s?.pending_count ?? 0)} payments awaiting a decision`}
          actionLabel="Review"
          onAction={() => router.push("/financial-manager/payments")}
        />
        <StatCard
          label="Verified This Month"
          value={formatEtb(s?.verified_amount ?? 0)}
          icon={<BadgeCheck className="h-6 w-6" />}
          iconBg="bg-green-600"
          sublabel={`${formatInt(s?.verified_count ?? 0)} payments verified`}
        />
        <StatCard
          label="Flagged for Review"
          value={formatInt(s?.flagged_count ?? 0)}
          icon={<Flag className="h-6 w-6" />}
          iconBg="bg-red-500"
          sublabel={`${formatEtb(s?.flagged_amount ?? 0)} flagged; disputes are tracked separately`}
        />
        <StatCard
          label="Payment Records"
          value={formatInt(totalRecords)}
          icon={<Wallet className="h-6 w-6" />}
          iconBg="bg-blue-500"
          sublabel={`${formatInt(summary.tabs.PENDING)} pending · ${formatInt(summary.tabs.VERIFIED)} verified · ${formatInt(summary.tabs.FLAGGED)} flagged · ${formatInt(summary.tabs.DISPUTED)} disputed`}
        />
      </div>

      <section className="mt-8 space-y-4" aria-labelledby="wallet-operations-heading">
        <div>
          <h2 id="wallet-operations-heading" className="text-lg font-bold text-gray-900">
            Wallet operations
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            Participant wallet balances are separate from submitted payment records. Funding and payout amounts are request totals, not proof of external settlement.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          <StatCard
            label="Available Wallet Balances"
            value={formatEtbPrecise(operations.wallets.available_balance)}
            icon={<Wallet className="h-6 w-6" />}
            iconBg="bg-indigo-600"
            sublabel={`${formatEtbPrecise(operations.wallets.held_balance)} held across ${formatInt(operations.wallets.count)} participant wallets`}
          />
          <StatCard
            label="Funding Awaiting Review"
            value={formatEtbPrecise(operations.funding.awaiting_review_amount)}
            icon={<Clock className="h-6 w-6" />}
            iconBg="bg-amber-500"
            sublabel={`${formatInt(operations.funding.awaiting_review_count)} requests awaiting a finance decision`}
            actionLabel="Review funding"
            onAction={() => router.push("/financial-manager/payments?tab=funding")}
          />
          <StatCard
            label="Payouts Awaiting Review"
            value={formatEtbPrecise(operations.payouts.pending_amount)}
            icon={<Receipt className="h-6 w-6" />}
            iconBg="bg-orange-600"
            sublabel={`${formatInt(operations.payouts.pending_count)} payout requests`}
            actionLabel="Review payouts"
            onAction={() => router.push("/financial-manager/payments?tab=payouts")}
          />
          <StatCard
            label="Escrow Work Queue"
            value={formatInt(escrowCount)}
            icon={<TrendingUp className="h-6 w-6" />}
            iconBg="bg-violet-600"
            sublabel={`${formatInt(escrowRelease?.count ?? 0)} awaiting release · ${formatInt(escrowDisputed?.count ?? 0)} disputed`}
            actionLabel="Review escrow"
            onAction={() => router.push("/financial-manager/payments?tab=escrow")}
          />
          <StatCard
            label="Beneficiary Accounts to Review"
            value={formatInt(operations.beneficiaries.requires_review_count)}
            icon={<BadgeCheck className="h-6 w-6" />}
            iconBg="bg-teal-600"
            sublabel={`${formatInt(operations.beneficiaries.count)} registered accounts; registration is not verification`}
            actionLabel="View accounts"
            onAction={() => router.push("/financial-manager/bank-accounts")}
          />
        </div>
      </section>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader
            title="Payment Record Volume"
            subtitle="Daily amounts in the payment-record workflow; wallet deposits and payouts are shown separately above"
            action={
              <div className="flex gap-1">
                {PERIODS.map((p) => (
                  <button
                    key={p.value}
                    onClick={() => setPeriod(p.value)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                      period === p.value
                        ? "bg-green-600 text-white"
                        : "text-gray-600 hover:bg-gray-100"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            }
          />
          <div className="p-5">
            {volume.length === 0 ? (
              <EmptyState
                title="No transactions in this window"
                description="Try a longer period."
                icon={<TrendingUp className="h-8 w-8" />}
              />
            ) : (
              <div className="flex h-48 items-end gap-1">
                {volume.map((v) => (
                  <div
                    key={v.date}
                    className="group relative flex-1"
                    title={`${v.date}: ${formatEtb(v.total)} across ${v.count} payments`}
                  >
                    <div
                      className="w-full rounded-t bg-green-500 transition-colors group-hover:bg-green-600"
                      style={{
                        height: `${peak > 0 ? Math.max(4, (v.total / peak) * 100) : 4}%`,
                      }}
                    />
                  </div>
                ))}
              </div>
            )}
            <div className="mt-3 flex justify-between text-xs text-gray-400">
              <span>{volume[0]?.date ?? ""}</span>
              <span>{volume[volume.length - 1]?.date ?? ""}</span>
            </div>
          </div>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader
            title="Awaiting Verification"
            action={
              <button
                onClick={() => router.push("/financial-manager/payments")}
                className="text-xs font-medium text-green-700 hover:underline"
              >
                View All
              </button>
            }
          />
          {recent.length === 0 ? (
            <EmptyState
              title="Nothing pending"
              description="Every submitted payment has been reviewed."
              icon={<Receipt className="h-8 w-8" />}
            />
          ) : (
            <TableWrap>
              <thead>
                <tr>
                  <Th>ID</Th>
                  <Th>Farmer</Th>
                  <Th>Amount</Th>
                  <Th>Submitted</Th>
                </tr>
              </thead>
              <tbody>
                {recent.map((p) => (
                  <tr key={p.id}>
                    <Td className="font-mono text-xs">{p.display_id}</Td>
                    <Td className="max-w-28 truncate">{p.farmer_name}</Td>
                    <Td className="font-medium">{formatEtb(p.amount)}</Td>
                    <Td className="whitespace-nowrap text-xs text-gray-500">
                      {shortRelative(p.submitted_at)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
