"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MapPin, MessageSquare, Store, Users } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorBanner,
  PageLoader,
  StatCard,
} from "@/components/ui";
import { dashboardApi } from "@/lib/api/client";
import { formatEtb, formatInt } from "@/lib/format";
import type { RetailerDashboardData } from "@/lib/types";

export default function RetailerDashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<RetailerDashboardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError("");
    try {
      setData(await dashboardApi.retailer());
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
      <AppShell title="Retailer Dashboard" allow={["RETAILER"]}>
        <PageLoader />
      </AppShell>
    );
  }

  const hasLocation = data?.stats.location_available ?? false;

  return (
    <AppShell title="Retailer Dashboard" allow={["RETAILER"]}>
      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} onRetry={() => void load()} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Available Listings"
          value={formatInt(data?.stats.available_listings ?? 0)}
          icon={<Store className="h-6 w-6" />}
          iconBg="bg-green-600"
          sublabel="From verified wholesalers"
          actionLabel="Browse"
          onAction={() => router.push("/retailer/browse")}
        />
        <StatCard
          label="Nearby Listings"
          value={formatInt(data?.stats.nearby_listings ?? 0)}
          icon={<MapPin className="h-6 w-6" />}
          iconBg="bg-blue-500"
          sublabel={
            hasLocation
              ? "Sorted by distance from you"
              : "Add a location to enable this"
          }
        />
        <StatCard
          label="Wholesalers"
          value={formatInt(data?.stats.total_wholesalers ?? 0)}
          icon={<Users className="h-6 w-6" />}
          iconBg="bg-amber-500"
          sublabel="Approved sellers on the platform"
        />
        <StatCard
          label="Active Chats"
          value={formatInt(data?.stats.active_communications ?? 0)}
          icon={<MessageSquare className="h-6 w-6" />}
          iconBg="bg-purple-500"
          sublabel={`${formatInt(data?.stats.unread_messages ?? 0)} unread messages`}
          actionLabel="Open messages"
          onAction={() => router.push("/chat")}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader
            title="Listings Near You"
            action={
              <Link
                href="/retailer/browse"
                className="text-xs font-medium text-green-700 hover:underline"
              >
                Browse All
              </Link>
            }
          />
          {data?.nearby_listings.length ? (
            <ul className="divide-y divide-gray-100">
              {data.nearby_listings.map((p) => (
                <li key={p.id}>
                  <Link
                    href={`/retailer/browse/${p.id}`}
                    className="flex items-center justify-between gap-4 px-5 py-3.5 hover:bg-gray-50"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-gray-900">
                        {p.title}
                      </p>
                      <p className="truncate text-xs text-gray-500">
                        {p.wholesaler} · {p.location}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-sm font-semibold text-gray-900">
                        {formatEtb(p.price_per_unit)}
                      </p>
                      <p className="text-xs text-gray-500">
                        per {p.unit}
                        {p.distance_km !== null && ` · ${p.distance_km} km`}
                      </p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              title={hasLocation ? "No nearby listings" : "Set your location"}
              description={
                hasLocation
                  ? "Try widening your search radius in the marketplace."
                  : "Add a location in your profile to see listings closest to you."
              }
              action={
                !hasLocation && (
                  <Link
                    href="/profile"
                    className="inline-flex h-9 items-center rounded-lg bg-green-600 px-4 text-sm font-medium text-white hover:bg-green-700"
                  >
                    Set location
                  </Link>
                )
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
                description="Messages and listing updates will appear here."
              />
            )}
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
