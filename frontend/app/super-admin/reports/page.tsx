"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader, ErrorBanner, PageLoader, StatCard } from "@/components/ui";
import { BadgeCheck, Banknote, Clock, Coins } from "lucide-react";
import { superAdminApi } from "@/lib/api/client";
import { formatEtb, formatInt, shortRelative } from "@/lib/format";
import type { SuperAdminHealth } from "@/lib/types";

const RESOURCES = [
  { label: "Users", value: "users" },
  { label: "Orders", value: "orders" },
  { label: "Payments", value: "payments" },
] as const;

/**
 * The formal `/reports/*` endpoints are restricted to `IsFinancialManager`, so
 * the Super Admin view is built from the platform-wide aggregates in
 * `/superadmin/health/` instead of re-implementing the report service.
 */
export default function SuperAdminReportsPage() {
  const router = useRouter();
  const [health, setHealth] = useState<SuperAdminHealth | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    superAdminApi
      .health()
      .then((h) => {
        if (!cancelled) setHealth(h);
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Failed to load figures.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <AppShell title="Reports" allow={["SUPER_ADMIN"]}>
        <PageLoader />
      </AppShell>
    );
  }

  const t = health?.transactions;
  const verified = Number(t?.payments_verified_value ?? 0);
  const pending = Number(t?.payments_pending_value ?? 0);
  const total = verified + pending;

  return (
    <AppShell title="Reports" allow={["SUPER_ADMIN"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Platform Reports</h2>
        <p className="mt-1 text-sm text-gray-500">
          Aggregated platform volumes. The filtered financial report and CSV/PDF
          export are scoped to the Financial Manager role.
        </p>
      </div>

      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Gross Order Value"
          value={formatEtb(t?.order_value_total ?? 0)}
          icon={<Coins className="h-6 w-6" />}
          sublabel={`${formatInt(t?.orders_total ?? 0)} orders all time`}
        />
        <StatCard
          label="Verified Payments"
          value={formatEtb(verified)}
          icon={<BadgeCheck className="h-6 w-6" />}
          sublabel={`${formatInt(t?.payments_verified ?? 0)} records`}
        />
        <StatCard
          label="Pending Payments"
          value={formatEtb(pending)}
          icon={<Clock className="h-6 w-6" />}
          sublabel={`${formatInt(t?.payments_pending ?? 0)} awaiting verification`}
        />
        <StatCard
          label="7-Day Volume"
          value={formatEtb(t?.payment_volume_7d ?? 0)}
          icon={<Banknote className="h-6 w-6" />}
          sublabel="Payments submitted in the last week"
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Payment Split" />
          <div className="p-5">
            {total === 0 ? (
              <p className="text-sm text-gray-500">No payment value recorded yet.</p>
            ) : (
              <>
                <div className="flex h-4 overflow-hidden rounded-full">
                  <div
                    className="bg-green-600"
                    style={{ width: `${(verified / total) * 100}%` }}
                  />
                  <div className="bg-amber-500" style={{ width: `${(pending / total) * 100}%` }} />
                </div>
                <ul className="mt-4 space-y-2 text-sm">
                  <li className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-gray-700">
                      <span className="h-3 w-3 rounded-sm bg-green-600" /> Verified
                    </span>
                    <span className="font-medium">
                      {formatEtb(verified)} ({Math.round((verified / total) * 100)}%)
                    </span>
                  </li>
                  <li className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-gray-700">
                      <span className="h-3 w-3 rounded-sm bg-amber-500" /> Pending
                    </span>
                    <span className="font-medium">
                      {formatEtb(pending)} ({Math.round((pending / total) * 100)}%)
                    </span>
                  </li>
                </ul>
              </>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Underlying Records" />
          <div className="p-5">
            <p className="mb-4 text-sm text-gray-600">
              Open the raw rows behind these figures.
            </p>
            <div className="flex flex-wrap gap-2">
              {RESOURCES.map((r) => (
                <button
                  key={r.value}
                  onClick={() =>
                    router.push(
                      r.value === "users"
                        ? "/super-admin/users"
                        : `/super-admin/${r.value}`
                    )
                  }
                  className="rounded-lg border border-gray-200 px-3.5 py-2 text-sm font-medium text-gray-700 hover:border-gray-400 hover:bg-gray-50"
                >
                  {r.label}
                </button>
              ))}
            </div>
            {health?.generated_at && (
              <p className="mt-5 text-xs text-gray-400">
                Figures generated {shortRelative(health.generated_at)}
              </p>
            )}
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
