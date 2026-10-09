"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ClipboardList, MessageSquare } from "lucide-react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  PageLoader,
  Pagination,
  Select,
  StatusPill,
  TableWrap,
  Td,
  Th,
} from "@/components/ui";
import { chatApi, ordersApi } from "@/lib/api/client";
import { FinanciallyVerifiedBadge } from "@/components/users/FinanciallyVerifiedBadge";
import { formatNumber } from "@/lib/format";
import type { Order, OrderStatus } from "@/lib/types";

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "ALL", label: "All statuses" },
  { value: "Pending seller approval", label: "Pending seller approval" },
  { value: "Accepted", label: "Accepted" },
  { value: "Processing", label: "Processing" },
  { value: "Confirmed", label: "Confirmed" },
  { value: "Shipped", label: "Shipped" },
  { value: "Delivered", label: "Delivered" },
  { value: "Awaiting quality confirmation", label: "Awaiting quality confirmation" },
  { value: "Awaiting payment release", label: "Awaiting payment release" },
  { value: "Completed", label: "Completed" },
  { value: "Rejected", label: "Rejected" },
  { value: "Disputed", label: "Disputed" },
  { value: "Cancelled", label: "Cancelled" },
];

/**
 * Order table driven by `allowed_transitions`, which the backend computes from
 * `Order.ALLOWED_TRANSITIONS`. Rendering only server-declared transitions keeps
 * the UI from ever offering an illegal state change.
 */
export function OrdersTable({
  /** Whose perspective: wholesalers act on Processing->Confirmed. */
  perspective,
}: {
  perspective: "wholesaler" | "farmer" | "retailer";
}) {
  const router = useRouter();
  const [rows, setRows] = useState<Order[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await ordersApi.list({
        page,
        status: (status === "ALL" ? undefined : status) as OrderStatus | undefined,
      });
      setRows(res.results);
      setCount(res.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load orders.");
    } finally {
      setLoading(false);
    }
  }, [page, status]);

  useEffect(() => {
    void load();
  }, [load]);

  async function transition(order: Order, next: OrderStatus) {
    setBusyId(order.id);
    setError("");
    try {
      await ordersApi.setStatus(order.id, next);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the order.");
    } finally {
      setBusyId("");
    }
  }

  async function message(order: Order) {
    setError("");
    try {
      // A wholesaler opens a channel with the farmer; a farmer replies to the
      // wholesaler that placed the order.
      const other =
        perspective === "wholesaler"
          ? order.retailer ?? order.farmer
          : order.wholesaler;
      if (!other) {
        throw new Error("The counterparty for this order is unavailable.");
      }
      const res = await chatApi.openChannel(other, order.product);
      router.push(`/chat?channel=${res.channel.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open the chat.");
    }
  }

  if (loading) return <PageLoader />;

  return (
    <div className="space-y-5">
      {error && <ErrorBanner message={error} onRetry={() => void load()} />}

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-5 py-4">
          <Select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(1);
            }}
            className="h-9 w-44"
            aria-label="Filter orders by status"
          >
            {STATUS_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </Select>
          <p className="text-xs text-gray-500">{count} order{count === 1 ? "" : "s"}</p>
        </div>

        {rows.length === 0 ? (
          <EmptyState
            title="No orders found"
            description={
              status === "ALL"
                ? perspective === "wholesaler"
                  ? "Browse the marketplace to place your first order."
                  : "Orders placed for your listings will appear here."
                : "No orders match this status."
            }
            icon={<ClipboardList className="h-8 w-8" />}
          />
        ) : (
          <>
            <TableWrap>
              <thead>
                <tr>
                  <Th>Reference</Th>
                  <Th>
                    {perspective === "farmer"
                      ? "Buyer"
                      : perspective === "retailer"
                        ? "Wholesaler"
                        : "Counterparty"}
                  </Th>
                  <Th>Product</Th>
                  <Th>Quantity</Th>
                  <Th>Total</Th>
                  <Th>Status</Th>
                  <Th>Date</Th>
                  <Th align="center">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((o) => (
                  <tr key={o.id}>
                    <Td>
                      <Link
                        href={`/orders/${o.id}`}
                        className="font-mono text-xs font-medium text-green-700 hover:underline"
                      >
                        {o.reference}
                      </Link>
                    </Td>
                    <Td>
                      {perspective === "farmer" ? (
                        <span className="inline-flex items-center gap-1">
                          {o.buyer_name}
                          {o.buyer_financially_verified && <FinanciallyVerifiedBadge />}
                        </span>
                      ) : perspective === "retailer" ? (
                        o.seller_name
                      ) : (
                        o.retailer_name ?? o.farmer_name
                      )}
                    </Td>
                    <Td className="max-w-44 truncate">{o.product_title}</Td>
                    <Td>{formatNumber(o.quantity)}</Td>
                    <Td className="font-medium">{o.total}</Td>
                    <Td>
                      <StatusPill value={o.status} />
                    </Td>
                    <Td className="whitespace-nowrap text-xs text-gray-500">
                      {o.date}
                    </Td>
                    <Td align="center">
                      <div className="flex flex-wrap items-center justify-center gap-2">
                        <Button
                          size="sm"
                          variant="secondary"
                          icon={<MessageSquare className="h-3.5 w-3.5" />}
                          onClick={() => void message(o)}
                        >
                          Chat
                        </Button>
                        {o.allowed_transitions.map((next) => (
                          <Button
                            key={next}
                            size="sm"
                            variant={next === "Cancelled" ? "danger" : "primary"}
                            loading={busyId === o.id}
                            onClick={() => void transition(o, next)}
                          >
                            {next}
                          </Button>
                        ))}
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pagination page={page} count={count} onPage={setPage} />
          </>
        )}
      </Card>
    </div>
  );
}
