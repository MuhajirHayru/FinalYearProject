"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeftRight } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Card, CardHeader, EmptyState, ErrorBanner, PageLoader, Pagination } from "@/components/ui";
import { walletApi } from "@/lib/api/client";
import { formatDateTime, formatEtb } from "@/lib/format";
import type { WalletTransaction } from "@/lib/types";

const ROLES = ["FARMER", "WHOLESALER", "RETAILER", "FINANCIAL_MANAGER", "SUPER_ADMIN"] as const;

export default function TransactionsPage() {
  const [rows, setRows] = useState<WalletTransaction[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const result = await walletApi.transactions({ page });
      setRows(result.results);
      setCount(result.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load wallet transactions.");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => { void load(); }, [load]);

  return (
    <AppShell title="Transactions" allow={[...ROLES]}>
      <div className="mx-auto max-w-5xl space-y-5">
        <div><h2 className="text-lg font-bold text-gray-900">Wallet transactions</h2><p className="mt-1 text-sm text-gray-500">A record of funding, escrow, refunds and payouts.</p></div>
        {error && <ErrorBanner message={error} onRetry={() => void load()} />}
        {loading ? <PageLoader /> : (
          <Card>
            <CardHeader title={`${count} transaction${count === 1 ? "" : "s"}`} />
            {rows.length ? <ul className="divide-y divide-gray-100">{rows.map((row) => (
              <li key={row.id} className="flex flex-wrap items-start justify-between gap-3 px-5 py-4">
                <div className="min-w-0"><p className="font-medium text-gray-900">{row.description || row.transaction_type.replaceAll("_", " ")}</p><p className="mt-1 text-xs text-gray-500">{row.reference}{row.order_reference ? ` · ${row.order_reference}` : ""} · {formatDateTime(row.created_at)}</p></div>
                <div className="text-right"><p className="text-sm font-semibold text-gray-900">{formatEtb(row.amount)}</p><p className="mt-1 text-xs text-gray-500">Available {Number(row.available_delta) >= 0 ? "+" : ""}{formatEtb(row.available_delta)} · Held {Number(row.held_delta) >= 0 ? "+" : ""}{formatEtb(row.held_delta)}</p></div>
              </li>
            ))}</ul> : <EmptyState title="No wallet transactions yet" description="Your verified wallet activity will appear here." icon={<ArrowLeftRight className="h-8 w-8" />} />}
            <Pagination page={page} count={count} onPage={setPage} />
          </Card>
        )}
      </div>
    </AppShell>
  );
}
