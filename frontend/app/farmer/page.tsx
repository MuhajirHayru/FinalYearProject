"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  Banknote,
  CheckCircle2,
  Eye,
  ListChecks,
  MessageSquare,
  PackagePlus,
  Pencil,
  Settings,
  ShoppingCart,
  Sprout,
  Trash2,
  UserPlus,
  XCircle,
  type LucideIcon,
} from "lucide-react";
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
import { dashboardApi, productsApi } from "@/lib/api/client";
import { formatEtb, formatInt, formatNumber } from "@/lib/format";
import type { FarmerDashboardData, Product } from "@/lib/types";

const ACTIVITY_ICON: Record<string, LucideIcon> = {
  REGISTRATION: UserPlus,
  APPROVAL: CheckCircle2,
  REJECTION: XCircle,
  MESSAGE: MessageSquare,
  PAYMENT: Banknote,
  ORDER: ShoppingCart,
  PRODUCT: Sprout,
  SYSTEM: Settings,
};

export default function FarmerDashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<FarmerDashboardData | null>(null);
  const [listings, setListings] = useState<Product[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [summary, mine] = await Promise.all([
        dashboardApi.farmer(),
        productsApi.myFarmerListings({ page: 1, status: "ACTIVE" }),
      ]);
      setData(summary);
      setListings(mine.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function deactivate(id: string) {
    setBusyId(id);
    try {
      await productsApi.deactivateFarmerListing(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setBusyId("");
    }
  }

  async function remove(id: string, title: string) {
    if (
      !window.confirm(
        `Delete "${title}"? It will be hidden from the marketplace.`
      )
    ) {
      return;
    }
    setBusyId(id);
    try {
      await productsApi.deleteFarmerListing(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setBusyId("");
    }
  }

  if (loading) {
    return (
      <AppShell title="Farmer Dashboard" allow={["FARMER"]}>
        <PageLoader />
      </AppShell>
    );
  }

  return (
    <AppShell title="Farmer Dashboard" allow={["FARMER"]}>
      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} onRetry={() => void load()} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          label="Total Active Listings"
          value={formatInt(data?.stats.total_active_listings ?? 0)}
          icon={<Sprout className="h-6 w-6" />}
          iconBg="bg-green-600"
          actionLabel="View all listings"
          onAction={() => router.push("/farmer/listings")}
          sublabel={`${formatInt(data?.stats.total_listings ?? 0)} listings total`}
        />
        <StatCard
          label="Total Products Sold"
          value={formatInt(data?.stats.total_products_sold ?? 0)}
          icon={<ShoppingCart className="h-6 w-6" />}
          iconBg="bg-blue-500"
          actionLabel="View sales"
          onAction={() => router.push("/farmer/orders")}
          sublabel={`${formatEtb(data?.stats.total_earned ?? 0)} earned (verified)`}
        />
        <StatCard
          label="Unread Messages"
          value={formatInt(data?.stats.unread_messages ?? 0)}
          icon={<MessageSquare className="h-6 w-6" />}
          iconBg="bg-purple-500"
          actionLabel="Open messages"
          onAction={() => router.push("/chat")}
          sublabel={`${formatInt(data?.stats.pending_orders ?? 0)} orders awaiting you`}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-2">
          <CardHeader title="Recent Activity" />
          <div className="p-5">
            {data?.recent_activity.length ? (
              <ul className="flex flex-col gap-4">
                {data.recent_activity.map((entry, i) => {
                  const Icon = ACTIVITY_ICON[entry.type] ?? Sprout;
                  return (
                    <li key={`${entry.time}-${i}`} className="flex items-start gap-3">
                      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-green-50 text-green-700">
                        <Icon className="h-3.5 w-3.5" />
                      </span>
                      <p className="flex-1 text-sm leading-snug text-gray-800">
                        {entry.text}
                      </p>
                      <span className="shrink-0 text-xs text-gray-500">
                        {entry.time}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <EmptyState
                title="No activity yet"
                description="Post a listing or reply to a buyer message to get started."
              />
            )}
          </div>
        </Card>

        <Card className="xl:col-span-3">
          <CardHeader
            title="My Active Listings"
            action={
              <div className="flex gap-2">
                <Link
                  href="/farmer/new-product"
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-green-600 px-3 text-xs font-medium text-white hover:bg-green-700"
                >
                  <PackagePlus className="h-3.5 w-3.5" />
                  Post New
                </Link>
                <Link
                  href="/farmer/listings"
                  className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-gray-200 px-3 text-xs font-medium text-gray-800 hover:bg-gray-50"
                >
                  <ListChecks className="h-3.5 w-3.5" />
                  View All
                </Link>
              </div>
            }
          />

          {listings.length === 0 ? (
            <EmptyState
              title="No active listings"
              description="Post your first product to reach wholesalers."
              icon={<Sprout className="h-8 w-8" />}
              action={
                <Link
                  href="/farmer/new-product"
                  className="inline-flex h-9 items-center rounded-lg bg-green-600 px-4 text-sm font-medium text-white hover:bg-green-700"
                >
                  Post New Product
                </Link>
              }
            />
          ) : (
            <TableWrap>
              <thead>
                <tr>
                  <Th>Product</Th>
                  <Th>Quantity</Th>
                  <Th>Price / Unit</Th>
                  <Th>Status</Th>
                  <Th align="center">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {listings.map((p) => (
                  <tr key={p.id}>
                    <Td>
                      <Link
                        href={`/farmer/listings/${p.id}`}
                        className="font-medium text-gray-900 hover:text-green-700"
                      >
                        {p.title}
                      </Link>
                      <p className="text-xs text-gray-500">
                        {p.category_display}
                      </p>
                    </Td>
                    <Td>
                      {formatNumber(p.quantity)} {p.unit_display}
                    </Td>
                    <Td>{formatEtb(p.price_per_unit)}</Td>
                    <Td>
                      <StatusPill value={p.status} />
                    </Td>
                    <Td align="center">
                      <div className="flex items-center justify-center gap-3">
                        <Link
                          href={`/farmer/listings/${p.id}`}
                          title="View"
                          className="text-gray-500 hover:text-gray-900"
                        >
                          <Eye className="h-4 w-4" />
                        </Link>
                        <Link
                          href={`/farmer/listings/${p.id}?edit=1`}
                          title="Edit"
                          className="text-gray-500 hover:text-gray-900"
                        >
                          <Pencil className="h-4 w-4" />
                        </Link>
                        <button
                          onClick={() => void deactivate(p.id)}
                          disabled={busyId === p.id}
                          title="Deactivate"
                          className="text-gray-500 hover:text-amber-600 disabled:opacity-40"
                        >
                          <ListChecks className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => void remove(p.id, p.title)}
                          disabled={busyId === p.id}
                          title="Delete"
                          className="text-gray-500 hover:text-red-600 disabled:opacity-40"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
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

