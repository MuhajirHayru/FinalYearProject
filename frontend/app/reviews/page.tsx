"use client";

import { useCallback, useEffect, useState } from "react";
import { Star } from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader, EmptyState, ErrorBanner, PageLoader, Pagination } from "@/components/ui";
import { walletApi } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { useAuth } from "@/lib/auth/context";
import type { Review } from "@/lib/types";

const ROLES = ["FARMER", "WHOLESALER", "RETAILER", "FINANCIAL_MANAGER", "SUPER_ADMIN"] as const;

export default function ReviewsPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState<Review[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const result = await walletApi.reviews(undefined, page);
      setRows(result.results);
      setCount(result.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load reviews.");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => { void load(); }, [load]);

  return (
    <AppShell title="Reviews" allow={[...ROLES]}>
      <div className="mx-auto max-w-5xl space-y-5">
        <div><h2 className="text-lg font-bold text-gray-900">Transaction reviews</h2><p className="mt-1 text-sm text-gray-500">Reviews are tied to completed orders and verified marketplace activity.</p></div>
        {error && <ErrorBanner message={error} onRetry={() => void load()} />}
        {loading ? <PageLoader /> : <Card>
          <CardHeader title={`${count} review${count === 1 ? "" : "s"}`} />
          {rows.length ? <ul className="divide-y divide-gray-100">{rows.map((row) => (
            <li key={row.id} className="space-y-2 px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-2"><div><span className="font-medium text-gray-900">{row.reviewee === user?.id ? `Review from ${row.reviewer_name}` : `Your review for ${row.reviewee_name}`}</span><p className="mt-1 text-xs text-gray-500">{formatDateTime(row.created_at)} · <Link href={`/orders/${row.order}`} className="text-green-700 hover:underline">{row.order_reference}</Link></p></div><span className="inline-flex items-center gap-1 text-sm font-semibold text-amber-600"><Star className="h-4 w-4 fill-current" />{row.rating}/5</span></div>
              {row.comment && <p className="text-sm text-gray-700">{row.comment}</p>}
            </li>
          ))}</ul> : <EmptyState title="No reviews yet" description="Reviews received and written after completed orders appear here." icon={<Star className="h-8 w-8" />} />}
          <Pagination page={page} count={count} onPage={setPage} />
        </Card>}
      </div>
    </AppShell>
  );
}
