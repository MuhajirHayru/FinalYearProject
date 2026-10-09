"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button, Card, CardHeader, EmptyState, ErrorBanner, Field, Input, StatusPill } from "@/components/ui";
import { ordersApi, walletApi } from "@/lib/api/client";
import { formatDateTime, formatEtb } from "@/lib/format";
import type { Order, WalletFundingRequest, WalletPayoutRequest } from "@/lib/types";

type QueueTab = "funding" | "payouts" | "escrow";

export function FinancialWorkflowQueue() {
  const searchParams = useSearchParams();
  const initial = searchParams.get("tab");
  const [tab, setTab] = useState<QueueTab>(
    initial === "funding" || initial === "payouts" || initial === "escrow"
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

  const load = useCallback(async () => {
    setError("");
    try {
      const [fundingData, payoutData, releaseData, disputeData] = await Promise.all([
        walletApi.funding(),
        walletApi.payouts(),
        ordersApi.list({ status: "Awaiting payment release" }),
        ordersApi.list({ status: "Disputed" }),
      ]);
      setFunding(fundingData.results);
      setPayouts(payoutData.results.filter((item) => item.status === "PENDING"));
      setOrders([...releaseData.results, ...disputeData.results]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load finance review requests.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

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
        <h2 className="text-lg font-bold text-gray-900">Wallet and escrow verification</h2>
        <p className="mt-1 text-sm text-gray-500">Only confirm transfers after checking the external payment reference.</p>
      </div>
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Finance review queues">
        {(["funding", "payouts", "escrow"] as QueueTab[]).map((item) => (
          <Button key={item} role="tab" aria-selected={tab === item} variant={tab === item ? "primary" : "secondary"} onClick={() => setTab(item)}>
            {item === "funding" ? `Funding (${funding.length})` : item === "payouts" ? `Payouts (${payouts.length})` : `Escrow (${orders.length})`}
          </Button>
        ))}
      </div>
      {error && <ErrorBanner message={error} onRetry={() => void load()} />}
      {notice && <div role="status" className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">{notice}</div>}
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
          )) : <Card><EmptyState title="No pending funding requests" /></Card>)}
          {tab === "payouts" && (payouts.length ? payouts.map((request) => (
            <Card key={request.id}>
              <div className="space-y-3 p-5">
                <div className="flex flex-wrap items-center justify-between gap-2"><div><p className="font-semibold text-gray-900">{request.wallet_owner} · {formatEtb(request.amount)}</p><p className="mt-1 text-sm text-gray-600">Destination: {request.destination}</p><p className="mt-1 text-xs text-gray-500">{formatDateTime(request.submitted_at)}</p></div><StatusPill value={request.status} /></div>
                <Field label="Verified external transfer reference" htmlFor={`payout-ref-${request.id}`}><Input id={`payout-ref-${request.id}`} value={references[request.id] || ""} onChange={(event) => setReferences((prev) => ({ ...prev, [request.id]: event.target.value }))} /></Field>
                <Field label="Review note" htmlFor={`payout-note-${request.id}`}><Input id={`payout-note-${request.id}`} value={notes[request.id] || ""} onChange={(event) => setNotes((prev) => ({ ...prev, [request.id]: event.target.value }))} /></Field>
                <div className="flex gap-2"><Button loading={busyId === request.id} disabled={!references[request.id]?.trim()} onClick={() => void reviewPayout(request.id, true)}>Confirm paid</Button><Button variant="danger" disabled={!!busyId} onClick={() => void reviewPayout(request.id, false)}>Reject and return funds</Button></div>
              </div>
            </Card>
          )) : <Card><EmptyState title="No pending payout requests" /></Card>)}
          {tab === "escrow" && (orders.length ? orders.map((order) => (
            <Card key={order.id}><div className="flex flex-wrap items-center justify-between gap-3 p-5"><div><Link href={`/orders/${order.id}`} className="font-semibold text-green-800 hover:underline">{order.reference} · {order.product_title}</Link><p className="mt-1 text-sm text-gray-600">{order.buyer_name} → {order.seller_name} · {formatEtb(order.total_amount)}</p>{order.dispute_reason && <p className="mt-1 text-sm text-red-700">Dispute: {order.dispute_reason}</p>}</div><StatusPill value={order.status} /></div></Card>
          )) : <Card><EmptyState title="No pending escrow releases or disputes" description="Quality-confirmed orders and disputes will be listed here." /> </Card>)}
        </div>
      )}
    </section>
  );
}
