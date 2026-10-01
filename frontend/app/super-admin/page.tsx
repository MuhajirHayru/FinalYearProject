"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  BadgeCheck,
  Clock,
  Coins,
  MessageSquare,
  Tag,
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
import { superAdminApi } from "@/lib/api/client";
import { formatEtb, formatInt, shortRelative } from "@/lib/format";
import type { SuperAdminHealth } from "@/lib/types";

export default function SuperAdminDashboardPage() {
  const router = useRouter();
  const [health, setHealth] = useState<SuperAdminHealth | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError("");
    try {
      setHealth(await superAdminApi.health());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load system health.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <AppShell title="Super Admin" allow={["SUPER_ADMIN"]}>
        <PageLoader />
      </AppShell>
    );
  }

  const t = health?.transactions;
  const c = health?.communication;

  return (
    <AppShell title="Super Admin" allow={["SUPER_ADMIN"]}>
      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} onRetry={() => void load()} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Users"
          value={formatInt(health?.users.total ?? 0)}
          icon={<Users className="h-6 w-6" />}
          iconBg="bg-green-600"
          sublabel={`${formatInt(health?.users.pending ?? 0)} pending, ${formatInt(health?.users.suspended ?? 0)} suspended`}
          actionLabel="Manage"
          onAction={() => router.push("/super-admin/users")}
        />
        <StatCard
          label="Listings"
          value={formatInt(health?.listings.total ?? 0)}
          icon={<Tag className="h-6 w-6" />}
          iconBg="bg-blue-500"
          sublabel={`${formatInt(health?.listings.active ?? 0)} active`}
          actionLabel="Oversee"
          onAction={() => router.push("/super-admin/listings")}
        />
        <StatCard
          label="Order Value"
          value={formatEtb(t?.order_value_total ?? 0)}
          icon={<Coins className="h-6 w-6" />}
          iconBg="bg-amber-500"
          sublabel={`${formatInt(t?.orders_total ?? 0)} orders, ${formatInt(t?.orders_24h ?? 0)} in 24h`}
        />
        <StatCard
          label="Payment Volume (7d)"
          value={formatEtb(t?.payment_volume_7d ?? 0)}
          icon={<Activity className="h-6 w-6" />}
          iconBg="bg-purple-500"
          sublabel={`${formatInt(t?.payments_total ?? 0)} records total`}
          actionLabel="Review"
          onAction={() => router.push("/super-admin/payments")}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title="Account Status" />
          <ul className="divide-y divide-gray-100">
            {(
              [
                { label: "Approved", value: health?.users.approved ?? 0, tone: "text-green-700" },
                { label: "Pending", value: health?.users.pending ?? 0, tone: "text-amber-600" },
                { label: "Suspended", value: health?.users.suspended ?? 0, tone: "text-red-600" },
              ] as const
            ).map((row) => (
              <li key={row.label} className="flex items-center justify-between px-5 py-3.5">
                <span className="text-sm text-gray-700">{row.label}</span>
                <span className={`text-sm font-semibold ${row.tone}`}>{row.value}</span>
              </li>
            ))}
          </ul>
          <div className="border-t border-gray-100 px-5 py-3.5">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
              By role
            </p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(health?.users.by_role ?? {}).map(([role, n]) => (
                <span
                  key={role}
                  className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs text-gray-700"
                >
                  {role.replace(/_/g, " ").toLowerCase()}: <b>{n}</b>
                </span>
              ))}
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="Payment Ledger" />
          <ul className="divide-y divide-gray-100">
            <li className="flex items-center justify-between px-5 py-3.5">
              <span className="flex items-center gap-2 text-sm text-gray-700">
                <Clock className="h-4 w-4 text-amber-500" /> Pending
              </span>
              <span className="text-right">
                <span className="block text-sm font-semibold">
                  {formatInt(t?.payments_pending ?? 0)}
                </span>
                <span className="block text-xs text-gray-500">
                  {formatEtb(t?.payments_pending_value ?? 0)}
                </span>
              </span>
            </li>
            <li className="flex items-center justify-between px-5 py-3.5">
              <span className="flex items-center gap-2 text-sm text-gray-700">
                <BadgeCheck className="h-4 w-4 text-green-600" /> Verified
              </span>
              <span className="text-right">
                <span className="block text-sm font-semibold">
                  {formatInt(t?.payments_verified ?? 0)}
                </span>
                <span className="block text-xs text-gray-500">
                  {formatEtb(t?.payments_verified_value ?? 0)}
                </span>
              </span>
            </li>
          </ul>
        </Card>

        <Card>
          <CardHeader title="Communication & API" />
          <ul className="divide-y divide-gray-100 text-sm">
            <li className="flex items-center justify-between px-5 py-3">
              <span className="flex items-center gap-2 text-gray-700">
                <MessageSquare className="h-4 w-4 text-gray-400" /> Chat channels
              </span>
              <span className="font-semibold">{formatInt(c?.chat_channels ?? 0)}</span>
            </li>
            <li className="flex items-center justify-between px-5 py-3">
              <span className="text-gray-700">Messages</span>
              <span className="font-semibold">{formatInt(c?.messages ?? 0)}</span>
            </li>
            <li className="flex items-center justify-between px-5 py-3">
              <span className="text-gray-700">Notifications</span>
              <span className="font-semibold">
                {formatInt(c?.notifications ?? 0)}{" "}
                <span className="text-xs font-normal text-gray-500">
                  ({formatInt(c?.unread_notifications ?? 0)} unread)
                </span>
              </span>
            </li>
            <li className="flex items-center justify-between px-5 py-3">
              <span className="text-gray-700">API version</span>
              <span className="font-mono text-xs">{health?.api.version}</span>
            </li>
            <li className="flex items-center justify-between px-5 py-3">
              <span className="text-gray-700">Auth</span>
              <span className="text-xs">{health?.api.authentication}</span>
            </li>
            <li className="px-5 py-3">
              <span className="text-gray-700">WebSocket paths</span>
              <ul className="mt-1 space-y-0.5">
                {(health?.api.websocket_paths ?? []).map((p) => (
                  <li key={p} className="font-mono text-xs text-gray-500">
                    {p}
                  </li>
                ))}
              </ul>
            </li>
          </ul>
          {health?.generated_at && (
            <p className="border-t border-gray-100 px-5 py-3 text-xs text-gray-400">
              Generated {shortRelative(health.generated_at)}
            </p>
          )}
        </Card>
      </div>
    </AppShell>
  );
}
