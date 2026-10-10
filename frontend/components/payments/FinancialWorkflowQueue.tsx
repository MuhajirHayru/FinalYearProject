"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { Button, Card, CardHeader, EmptyState, ErrorBanner, Field, Input, Select, StatusPill } from "@/components/ui";
import { ordersApi, walletApi } from "@/lib/api/client";
import { formatDateTime, formatEtb } from "@/lib/format";
import type { Order, WalletFundingRequest, WalletPayoutRequest, WalletRequestQuery } from "@/lib/types";

type QueueTab = "funding" | "payouts" | "escrow";

interface FinancialWorkflowQueueProps {
  initialTab?: QueueTab;
  showTabs?: boolean;
}

export function FinancialWorkflowQueue({
  initialTab,
  showTabs = true,
}: FinancialWorkflowQueueProps) {
  const searchParams = useSearchParams();
  const initial = searchParams.get("tab");
  const [tab, setTab] = useState<QueueTab>(
    initialTab
      ? initialTab
      : initial === "funding" || initial === "payouts" || initial === "escrow"
      ? initial
      : "funding"
  );
  const [funding, setFunding] = useState<WalletFundingRequest[]>([]);
  const [payouts, setPayouts] = useState<WalletPayoutRequest[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [references, setReferences] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filters, setFilters] = useState<WalletRequestQuery>({
    status: "ALL",
    role: "ALL",
  });
  const [appliedFilters, setAppliedFilters] = useState<WalletRequestQuery>({});
  const [page, setPage] = useState(1);
  const [fundingTotal, setFundingTotal] = useState(0);
  const [payoutTotal, setPayoutTotal] = useState(0);
  const [hasPrevious, setHasPrevious] = useState(false);
  const [hasNext, setHasNext] = useState(false);

  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const query = { ...appliedFilters, page };
      const [fundingData, payoutData, releaseData, disputeData] = await Promise.all([
        walletApi.funding(query),
        walletApi.payouts(query),
        ordersApi.list({ status: "Awaiting payment release" }),
        ordersApi.list({ status: "Disputed" }),
      ]);
      setFunding(fundingData.results);
      setPayouts(payoutData.results);
      setFundingTotal(fundingData.count);
      setPayoutTotal(payoutData.count);
      const activePage = tab === "payouts" ? payoutData : fundingData;
      setHasPrevious(!!activePage.previous);
      setHasNext(!!activePage.next);
      setOrders([...releaseData.results, ...disputeData.results]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load finance review requests.");
    } finally {
      setLoading(false);
    }
  }, [appliedFilters, page, tab]);

  useEffect(() => { void load(); }, [load]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setAppliedFilters({
      status: filters.status === "ALL" ? undefined : filters.status,
      role: filters.role === "ALL" ? undefined : filters.role,
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
      search: filters.search?.trim() || undefined,
    });
  }

  function clearFilters() {
    setFilters({ status: "ALL", role: "ALL" });
    setAppliedFilters({});
    setPage(1);
  }

  async function reviewFunding(id: string, approve: boolean) {
    setBusyId(id);
    setError("");
    setNotice("");
    try {
      await walletApi.reviewFunding(id, approve, notes[id] || "");
      setNotice(`Funding request ${approve ? "verified" : "rejected"}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not review funding request.");
    } finally {
      setBusyId("");
    }
  }

  async function reviewPayout(id: string, approve: boolean) {
    setBusyId(id);
    setError("");
    setNotice("");
    try {
      await walletApi.reviewPayout(id, approve, references[id] || "", notes[id] || "");
      setNotice(`Payout request ${approve ? "marked as paid" : "rejected"}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not review payout request.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <section className="mt-8 space-y-4">
      <div>
        <h2 className="text-lg font-bold text-gray-900">
          {tab === "funding" ? "Deposits" : tab === "payouts" ? "Payouts" : "Wallet and escrow verification"}
        </h2>
        <p className="mt-1 text-sm text-gray-500">
          {tab === "escrow"
            ? "Review escrow release and dispute queues."
            : "Filter participant requests. Only confirm transfers after checking the external payment reference."}
        </p>
      </div>
      {showTabs && (
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Finance review queues">
          {(["funding", "payouts", "escrow"] as QueueTab[]).map((item) => (
            <Button key={item} role="tab" aria-selected={tab === item} variant={tab === item ? "primary" : "secondary"} onClick={() => { setTab(item); setPage(1); setFilters((value) => ({ ...value, status: "ALL" })); setAppliedFilters((value) => ({ ...value, status: undefined })); }}>
              {item === "funding" ? `Funding (${fundingTotal})` : item === "payouts" ? `Payouts (${payoutTotal})` : `Escrow (${orders.length})`}
            </Button>
          ))}
        </div>
      )}
      {error && <ErrorBanner message={error} onRetry={() => void load()} />}
      {notice && <div role="status" className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">{notice}</div>}
      {tab !== "escrow" && (
        <Card>
          <form onSubmit={applyFilters} className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-6">
            <Field label="Search name or reference" htmlFor="finance-search">
              <Input id="finance-search" value={filters.search || ""} onChange={(event) => setFilters((value) => ({ ...value, search: event.target.value }))} placeholder="Name or reference" />
            </Field>
            <Field label="Status" htmlFor="finance-status">
              <Select id="finance-status" value={filters.status || "ALL"} onChange={(event) => setFilters((value) => ({ ...value, status: event.target.value }))}>
                <option value="ALL">All statuses</option>
                {(tab === "funding"
                  ? ["PENDING", "AWAITING_PAYMENT", "PAYMENT_VERIFICATION_PENDING", "AWAITING_APPROVAL", "VERIFIED", "APPROVED", "REJECTED", "FAILED"]
                  : ["PENDING", "PAID", "REJECTED"]
                ).map((status) => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}
              </Select>
            </Field>
            <Field label="Participant role" htmlFor="finance-role">
              <Select id="finance-role" value={filters.role || "ALL"} onChange={(event) => setFilters((value) => ({ ...value, role: event.target.value as WalletRequestQuery["role"] }))}>
                <option value="ALL">All roles</option>
                <option value="FARMER">Farmer</option>
                <option value="WHOLESALER">Wholesaler</option>
                <option value="RETAILER">Retailer</option>
              </Select>
            </Field>
            <Field label="Submitted from" htmlFor="finance-date-from">
              <Input id="finance-date-from" type="date" value={filters.date_from || ""} onChange={(event) => setFilters((value) => ({ ...value, date_from: event.target.value }))} />
            </Field>
            <Field label="Submitted to" htmlFor="finance-date-to">
              <Input id="finance-date-to" type="date" value={filters.date_to || ""} onChange={(event) => setFilters((value) => ({ ...value, date_to: event.target.value }))} />
            </Field>
            <div className="flex items-end gap-2">
              <Button type="submit">Apply</Button>
              <Button type="button" variant="secondary" onClick={clearFilters}>Clear</Button>
            </div>
          </form>
        </Card>
      )}
      {loading ? <p className="py-6 text-center text-sm text-gray-500">Loading review queues...</p> : (
        <div className="space-y-3">
          {tab === "funding" && (funding.length ? funding.map((request) => (
            <Card key={request.id}>
              <div className="space-y-3 p-5">
                <div className="flex flex-wrap items-center justify-between gap-2"><div><p className="font-semibold text-gray-900">{request.wallet_owner} · {request.wallet_owner_role} · {formatEtb(request.amount)}</p><p className="mt-1 text-sm text-gray-600">{request.payment_method}{request.payment_mode === "TEST" ? " (test mode)" : ""} · {request.external_reference}</p><p className="mt-1 text-xs text-gray-500">{formatDateTime(request.submitted_at)}</p>{request.payment_method === "Chapa" && <p className="mt-1 text-xs text-gray-600">Chapa result: {request.provider_status || "Not verified"}{request.verified_amount ? ` · ${request.verified_amount} ${request.verified_currency} (requested ${request.amount} ETB)` : ""}{request.payment_verified ? " · server-verified" : ""}</p>}{request.reviewed_at && <p className="mt-1 text-xs text-gray-500">Decision by {request.reviewed_by_name || "former finance admin"} · {formatDateTime(request.reviewed_at)}{request.review_notes ? ` · ${request.review_notes}` : ""}</p>}</div><StatusPill value={request.status} /></div>
                <Field label="Review note" htmlFor={`fund-note-${request.id}`}><Input id={`fund-note-${request.id}`} value={notes[request.id] || ""} onChange={(event) => setNotes((prev) => ({ ...prev, [request.id]: event.target.value }))} /></Field>
                {["PENDING", "AWAITING_PAYMENT", "PAYMENT_VERIFICATION_PENDING", "AWAITING_APPROVAL", "FAILED"].includes(request.status) && <div className="flex gap-2">
                  {(request.status === "PENDING" || (request.status === "AWAITING_APPROVAL" && request.payment_verified && request.verified_amount === request.amount && request.verified_currency === "ETB")) && <Button loading={busyId === request.id} disabled={!!busyId} onClick={() => void reviewFunding(request.id, true)}>{request.payment_method === "Chapa" ? "Approve verified deposit" : "Verify transfer"}</Button>}
                  <Button variant="danger" disabled={!!busyId || !notes[request.id]?.trim()} onClick={() => void reviewFunding(request.id, false)}>Reject with reason</Button>
                </div>}
              </div>
            </Card>
          )) : <Card><EmptyState title="No funding requests match these filters" /></Card>)}
          {tab === "payouts" && (payouts.length ? payouts.map((request) => (
            <Card key={request.id}>
              <div className="space-y-3 p-5">
                <div className="flex flex-wrap items-center justify-between gap-2"><div><p className="font-semibold text-gray-900">{request.wallet_owner} · {formatEtb(request.amount)}</p><p className="mt-1 text-sm text-gray-600">{request.payout_account ? "Registered payout account — details remain masked in this queue" : "Manual destination — details withheld in this queue"}</p><p className="mt-1 text-xs text-gray-500">{formatDateTime(request.submitted_at)}</p>{request.reviewed_at && <p className="mt-1 text-xs text-gray-500">Reviewed · {formatDateTime(request.reviewed_at)}{request.external_reference ? ` · ${request.external_reference}` : ""}{request.review_notes ? ` · ${request.review_notes}` : ""}</p>}</div><StatusPill value={request.status} /></div>
                {request.status === "PENDING" && <>
                  <Field label="Verified external transfer reference" htmlFor={`payout-ref-${request.id}`}><Input id={`payout-ref-${request.id}`} value={references[request.id] || ""} onChange={(event) => setReferences((prev) => ({ ...prev, [request.id]: event.target.value }))} /></Field>
                  <Field label="Review note" htmlFor={`payout-note-${request.id}`}><Input id={`payout-note-${request.id}`} value={notes[request.id] || ""} onChange={(event) => setNotes((prev) => ({ ...prev, [request.id]: event.target.value }))} /></Field>
                  <div className="flex gap-2"><Button loading={busyId === request.id} disabled={!references[request.id]?.trim()} onClick={() => void reviewPayout(request.id, true)}>Confirm paid</Button><Button variant="danger" disabled={!!busyId} onClick={() => void reviewPayout(request.id, false)}>Reject and return funds</Button></div>
                </>}
              </div>
            </Card>
          )) : <Card><EmptyState title="No payout requests match these filters" /></Card>)}
          {tab === "escrow" && (orders.length ? orders.map((order) => (
            <Card key={order.id}><div className="flex flex-wrap items-center justify-between gap-3 p-5"><div><Link href={`/orders/${order.id}`} className="font-semibold text-green-800 hover:underline">{order.reference} · {order.product_title}</Link><p className="mt-1 text-sm text-gray-600">{order.buyer_name} → {order.seller_name} · {formatEtb(order.total_amount)}</p>{order.dispute_reason && <p className="mt-1 text-sm text-red-700">Dispute: {order.dispute_reason}</p>}</div><StatusPill value={order.status} /></div></Card>
          )) : <Card><EmptyState title="No pending escrow releases or disputes" description="Quality-confirmed orders and disputes will be listed here." /> </Card>)}
        </div>
      )}
      {!loading && tab !== "escrow" && (
        <div className="flex items-center justify-between text-sm text-gray-600">
          <span>{tab === "funding" ? fundingTotal : payoutTotal} requests</span>
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" disabled={!hasPrevious} onClick={() => setPage((value) => Math.max(1, value - 1))}>Previous</Button>
            <span className="self-center">Page {page}</span>
            <Button size="sm" variant="secondary" disabled={!hasNext} onClick={() => setPage((value) => value + 1)}>Next</Button>
          </div>
        </div>
      )}
    </section>
  );
}
