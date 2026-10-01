"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  BadgeCheck,
  BarChart3,
  CreditCard,
  Flag,
  Store,
  Tag,
  UserCheck,
  Users,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Card,
  CardHeader,
  ErrorBanner,
  PageLoader,
  StatCard,
} from "@/components/ui";
import { dashboardApi } from "@/lib/api/client";
import { formatInt } from "@/lib/format";
import type { AdminDashboardData } from "@/lib/types";

export default function AdminDashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<AdminDashboardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError("");
    try {
      setData(await dashboardApi.admin());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <AppShell title="Admin Dashboard" allow={["USER_ADMIN"]}>
        <PageLoader />
      </AppShell>
    );
  }

  const s = data?.stats;

  return (
    <AppShell title="Admin Dashboard" allow={["USER_ADMIN"]}>
      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} onRetry={() => void load()} />
        </div>
      )}

      {s && s.pending_users > 0 && (
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <p className="flex items-center gap-2 text-sm text-amber-800">
            <UserCheck className="h-4 w-4" />
            <span>
              <span className="font-semibold">{s.pending_users}</span> registration
              {s.pending_users === 1 ? "" : "s"} waiting for review.
            </span>
          </p>
          <button
            onClick={() => router.push("/admin/approvals")}
            className="text-sm font-medium text-amber-900 underline hover:no-underline"
          >
            Open the approval queue
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Pending Approvals"
          value={formatInt(s?.pending_users ?? 0)}
          icon={<UserCheck className="h-6 w-6" />}
          iconBg="bg-amber-500"
          sublabel="Awaiting a decision"
          actionLabel="Review"
          onAction={() => router.push("/admin/approvals")}
        />
        <StatCard
          label="Total Users"
          value={formatInt(s?.total_users ?? 0)}
          icon={<Users className="h-6 w-6" />}
          iconBg="bg-green-600"
          sublabel={`${formatInt(s?.active_users ?? 0)} active accounts`}
          actionLabel="Manage"
          onAction={() => router.push("/admin/users")}
        />
        <StatCard
          label="Active Listings"
          value={formatInt(s?.active_listings ?? 0)}
          icon={<Tag className="h-6 w-6" />}
          iconBg="bg-blue-500"
          sublabel="Across farmers and wholesalers"
          actionLabel="Oversee"
          onAction={() => router.push("/admin/listings")}
        />
        <StatCard
          label="Flagged Payments"
          value={formatInt(s?.flagged_payments ?? 0)}
          icon={<Flag className="h-6 w-6" />}
          iconBg="bg-red-500"
          sublabel={`${formatInt(s?.pending_payments ?? 0)} pending, ${formatInt(s?.verified_payments ?? 0)} verified`}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Registered Accounts by Role" />
          <ul className="divide-y divide-gray-100">
            {[
              { label: "Farmers", value: s?.farmers ?? 0, icon: Store },
              { label: "Wholesalers", value: s?.wholesalers ?? 0, icon: BadgeCheck },
              { label: "Retailers", value: s?.retailers ?? 0, icon: Users },
            ].map((row) => {
              const Icon = row.icon;
              const total = (s?.farmers ?? 0) + (s?.wholesalers ?? 0) + (s?.retailers ?? 0);
              const pct = total > 0 ? Math.round((row.value / total) * 100) : 0;
              return (
                <li key={row.label} className="px-5 py-4">
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2 font-medium text-gray-800">
                      <Icon className="h-4 w-4 text-gray-400" />
                      {row.label}
                    </span>
                    <span className="font-semibold text-gray-900">{row.value}</span>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-gray-100">
                    <div
                      className="h-full rounded-full bg-green-600"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>

        <Card>
          <CardHeader title="Platform Activity" />
          <ul className="divide-y divide-gray-100">
            <li className="flex items-center justify-between px-5 py-4">
              <span className="flex items-center gap-2 text-sm font-medium text-gray-800">
                <CreditCard className="h-4 w-4 text-gray-400" />
                Total orders
              </span>
              <span className="font-semibold text-gray-900">
                {formatInt(s?.total_orders ?? 0)}
              </span>
            </li>
            <li className="flex items-center justify-between px-5 py-4">
              <span className="flex items-center gap-2 text-sm font-medium text-gray-800">
                <AlertTriangle className="h-4 w-4 text-gray-400" />
                Payments pending verification
              </span>
              <span className="font-semibold text-gray-900">
                {formatInt(s?.pending_payments ?? 0)}
              </span>
            </li>
            <li className="flex items-center justify-between px-5 py-4">
              <span className="flex items-center gap-2 text-sm font-medium text-gray-800">
                <BadgeCheck className="h-4 w-4 text-gray-400" />
                Payments verified
              </span>
              <span className="font-semibold text-gray-900">
                {formatInt(s?.verified_payments ?? 0)}
              </span>
            </li>
            <li className="flex items-center justify-between px-5 py-4">
              <span className="flex items-center gap-2 text-sm font-medium text-gray-800">
                <Flag className="h-4 w-4 text-gray-400" />
                Flagged for review
              </span>
              <span className="font-semibold text-red-600">
                {formatInt(s?.flagged_payments ?? 0)}
              </span>
            </li>
            <li className="flex items-center justify-between px-5 py-4">
              <span className="flex items-center gap-2 text-sm font-medium text-gray-800">
                <BarChart3 className="h-4 w-4 text-gray-400" />
                Payment values
              </span>
              <span className="text-xs text-gray-500">
                Counted, not summed, here
              </span>
            </li>
          </ul>
        </Card>
      </div>
    </AppShell>
  );
}
