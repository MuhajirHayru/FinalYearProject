"use client";

import { useCallback, useEffect, useState } from "react";
import { ClipboardList, MessageSquare, ShoppingBag, Wallet } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorBanner,
  PageLoader,
  StatCard,
  StatusPill,
  TableWrap,
  Td,
  Th,
} from "@/components/ui";
import { dashboardApi } from "@/lib/api/client";
import { formatEtb, formatInt, formatNumber } from "@/lib/format";
import type { WholesalerDashboardData } from "@/lib/types";

const ACTIVITY_ICON: Record<string, string> = {
  ORDER: "order",
  PAYMENT: "payment",
  MESSAGE: "message",
  PRODUCT: "product",
  SYSTEM: "system",
  APPROVAL: "approval",
};

export default function WholesalerDashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<WholesalerDashboardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError("");
    try {
      setData(await dashboardApi.wholesaler());
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
      <AppShell title="Wholesaler Dashboard" allow={["WHOLESALER"]}>
        <PageLoader />
      </AppShell>
    );
  }

  return (
    <AppShell title="Wholesaler Dashboard" allow={["WHOLESALER"]}>
      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} onRetry={() => void load()} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Orders"
          value={formatInt(data?.stats.total_orders ?? 0)}
          icon={<ShoppingBag className="h-6 w-6" />}
          iconBg="bg-green-600"
          sublabel={`${formatInt(data?.stats.pending_orders ?? 0)} awaiting action`}
          actionLabel="View orders"
          onAction={() => router.push("/wholesaler/orders")}
        />
        <StatCard
          label="Total Spent"
          value={formatEtb(data?.stats.total_spent ?? 0)}
          icon={<Wallet className="h-6 w-6" />}
          iconBg="bg-blue-500"
          sublabel="All recorded orders"
        />
        <StatCard
          label="Unread Messages"
          value={formatInt(data?.stats.unread_messages ?? 0)}
          icon={<MessageSquare className="h-6 w-6" />}
          iconBg="bg-purple-500"
          sublabel="From farmers and retailers"
          actionLabel="Open messages"
          onAction={() => router.push("/chat")}
        />
        <StatCard
          label="My Active Listings"
          value={formatInt(data?.stats.active_listings ?? 0)}
          icon={<ClipboardList className="h-6 w-6" />}
          iconBg="bg-amber-500"
          sublabel={`${formatEtb(data?.stats.verified_payments ?? 0)} verified payments`}
          actionLabel="Manage listings"
          onAction={() => router.push("/wholesaler/listings")}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader
            title="My Recent Orders"
            action={
              <Link
                href="/wholesaler/orders"
                className="text-xs font-medium text-green-700 hover:underline"
              >
                View All
              </Link>
            }
          />
          {data?.orders.length ? (
            <TableWrap>
              <thead>
                <tr>
                  <Th>Reference</Th>
                  <Th>Seller</Th>
                  <Th>Product</Th>
                  <Th>Total</Th>
                  <Th>Status</Th>
                  <Th>Date</Th>
                </tr>
              </thead>
              <tbody>
                {data.orders.map((o) => (
                  <tr key={o.id}>
                    <Td className="font-mono text-xs">{o.reference}</Td>
                    <Td>{o.seller}</Td>
                    <Td className="max-w-40 truncate">{o.product}</Td>
                    <Td className="font-medium">{o.total}</Td>
                    <Td>
                      <StatusPill value={o.status} />
                    </Td>
                    <Td className="whitespace-nowrap text-xs text-gray-500">
                      {o.date}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          ) : (
            <EmptyState
              title="No orders yet"
              description="Browse the marketplace and place your first order."
              action={
                <Link
                  href="/wholesaler/browse"
                  className="inline-flex h-9 items-center rounded-lg bg-green-600 px-4 text-sm font-medium text-white hover:bg-green-700"
                >
                  Browse Products
                </Link>
              }
            />
          )}
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader title="Recent Activity" />
          <div className="p-5">
            {data?.recent_activity.length ? (
              <ul className="flex flex-col gap-4">
                {data.recent_activity.map((entry, i) => (
                  <li
                    key={`${entry.time}-${i}`}
                    className="flex items-start gap-3"
                  >
                    <span
                      aria-hidden
                      data-kind={ACTIVITY_ICON[entry.type] ?? "system"}
                      className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-green-500"
                    />
                    <p className="flex-1 text-sm leading-snug text-gray-800">
                      {entry.text}
                    </p>
                    <span className="shrink-0 text-xs text-gray-500">
                      {entry.time}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                title="No activity yet"
                description="Actions on your orders and listings will show up here."
              />
            )}
          </div>
        </Card>
      </div>

      <p className="mt-6 text-xs text-gray-400">
        {formatInt(data?.stats.favorite_sellers ?? 0)} seller
        {(data?.stats.favorite_sellers ?? 0) === 1 ? "" : "s"} you have ordered
        from · {formatInt(data?.stats.pending_payments ?? 0)} payments awaiting
        verification
      </p>
    </AppShell>
  );
}
