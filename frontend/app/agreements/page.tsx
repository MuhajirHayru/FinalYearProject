"use client";

import { useCallback, useEffect, useState } from "react";
import { FileText } from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader, EmptyState, ErrorBanner, PageLoader, Pagination, StatusPill } from "@/components/ui";
import { walletApi } from "@/lib/api/client";
import { formatDateTime, formatEtb } from "@/lib/format";
import type { BusinessAgreement } from "@/lib/types";

const ROLES = ["FARMER", "WHOLESALER", "RETAILER", "FINANCIAL_MANAGER", "SUPER_ADMIN"] as const;

export default function AgreementsPage() {
  const [rows, setRows] = useState<BusinessAgreement[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const result = await walletApi.agreements({ page });
      setRows(result.results);
      setCount(result.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load agreements.");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => { void load(); }, [load]);

  return (
    <AppShell title="Agreements" allow={[...ROLES]}>
      <div className="mx-auto max-w-5xl space-y-5">
        <div><h2 className="text-lg font-bold text-gray-900">Business agreements</h2><p className="mt-1 text-sm text-gray-500">Agreements are created when the seller accepts an order.</p></div>
        {error && <ErrorBanner message={error} onRetry={() => void load()} />}
        {loading ? <PageLoader /> : <Card>
          <CardHeader title={`${count} agreement${count === 1 ? "" : "s"}`} />
          {rows.length ? <ul className="divide-y divide-gray-100">{rows.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
              <div className="min-w-0"><Link href={`/orders/${row.order}`} className="font-semibold text-green-800 hover:underline">{row.product_title} · {row.order_reference}</Link><p className="mt-1 text-sm text-gray-600">{row.buyer_name} ↔ {row.seller_name} · {formatEtb(row.total_amount)}</p><p className="mt-1 text-xs text-gray-500">{row.terms || "Order terms recorded."} · {formatDateTime(row.activated_at)}</p></div>
              <StatusPill value={row.status} />
            </li>
          ))}</ul> : <EmptyState title="No agreements yet" description="Accepted orders will appear here." icon={<FileText className="h-8 w-8" />} />}
          <Pagination page={page} count={count} onPage={setPage} />
        </Card>}
      </div>
    </AppShell>
  );
}
