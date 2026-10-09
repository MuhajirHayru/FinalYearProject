"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Button,
  Card,
  ErrorBanner,
  Field,
  Input,
  PageLoader,
  StatusPill,
  Textarea,
} from "@/components/ui";
import { ordersApi, walletApi } from "@/lib/api/client";
import { FinanciallyVerifiedBadge } from "@/components/users/FinanciallyVerifiedBadge";
import { OnlineStatus } from "@/components/presence/PresenceProvider";
import { useAuth } from "@/lib/auth/context";
import { formatDateTime, formatEtb, formatNumber } from "@/lib/format";
import type { Order, UserRole } from "@/lib/types";

const ROLES: UserRole[] = [
  "FARMER",
  "WHOLESALER",
  "RETAILER",
  "FINANCIAL_MANAGER",
  "SUPER_ADMIN",
];

const ORDER_STAGES = [
  "Pending seller approval",
  "Accepted",
  "Processing",
  "Shipped",
  "Awaiting quality confirmation",
  "Awaiting payment release",
  "Completed",
];

export default function OrderDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { user } = useAuth();
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [settlementReference, setSettlementReference] = useState("");
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewComment, setReviewComment] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setOrder(await ordersApi.get(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this order.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(success);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The order action failed.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <AppShell title="Order details" allow={ROLES}>
        <PageLoader />
      </AppShell>
    );
  }

  if (!order || !user) {
    return (
      <AppShell title="Order details" allow={ROLES}>
        <ErrorBanner message={error || "Order not found."} onRetry={() => void load()} />
      </AppShell>
    );
  }

  const orderId = order.id;
  const buyerId = order.retailer ?? order.wholesaler;
  const sellerId = order.farmer ?? order.wholesaler;
  const isBuyer = user.id === buyerId;
  const isSeller = user.id === sellerId;
  const isFinancial = user.role === "FINANCIAL_MANAGER" || user.role === "SUPER_ADMIN";
  const backPath =
    user.role === "FARMER"
      ? "/farmer/orders"
      : user.role === "RETAILER"
        ? "/retailer/orders"
        : "/wholesaler/orders";
  const canRate = (isBuyer || isSeller) && order.status === "Completed";

  async function submitReview() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await walletApi.createReview(orderId, reviewRating, reviewComment.trim());
      setNotice("Your verified transaction review has been submitted.");
      setReviewComment("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit the review.");
    } finally {
      setBusy(false);
    }
  }

  const page = (
    <div className="mx-auto max-w-5xl space-y-5">
      <Link
        href={backPath}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to orders
      </Link>

      {error && <ErrorBanner message={error} />}
      {notice && (
        <div role="status" className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {notice}
        </div>
      )}

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-gray-100 p-5">
          <div>
            <p className="font-mono text-sm text-gray-500">{order.reference}</p>
            <h2 className="mt-1 text-xl font-bold text-gray-900">{order.product_title}</h2>
            <p className="mt-1 text-sm text-gray-500">
              Created {formatDateTime(order.created_at)}
            </p>
          </div>
          <StatusPill value={order.status_display} />
        </div>
        <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-xs text-gray-500">Buyer</p>
            <p className="mt-1 flex items-center gap-1 text-sm font-medium">
              {order.buyer_name}
              {order.buyer_financially_verified && <FinanciallyVerifiedBadge />}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Seller</p>
            <p className="mt-1 flex items-center gap-1 text-sm font-medium">
              {order.seller_name}
              {(order.farmer || order.wholesaler) && (
                <OnlineStatus
                  userId={order.farmer || order.wholesaler}
                  initiallyOnline={order.seller_is_online}
                />
              )}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Quantity</p>
            <p className="mt-1 text-sm font-medium">{formatNumber(order.quantity)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Order total</p>
            <p className="mt-1 text-sm font-semibold">{formatEtb(order.total_amount)}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Payment</p>
            <p className="mt-1 text-sm font-medium">
              {order.payment_status_display || "No wallet escrow (legacy payment)"}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Agreement</p>
            <p className="mt-1 text-sm font-medium">
              {order.agreement_status ?? "Awaiting seller acceptance"}
            </p>
          </div>
          <div className="sm:col-span-2">
            <p className="text-xs text-gray-500">Delivery information</p>
            <p className="mt-1 whitespace-pre-wrap text-sm font-medium">
              {order.delivery_information || "Not provided"}
            </p>
          </div>
        </div>
      </Card>

      {order.agreement_status && (
        <Card>
          <div className="p-5">
            <h3 className="font-semibold text-gray-900">Business agreement</h3>
            <p className="mt-2 text-sm text-gray-600">
              {order.quantity} units of {order.product_title} for{" "}
              {formatEtb(order.total_amount)}. The agreement is linked only to this order
              and does not reserve the seller&apos;s entire inventory.
            </p>
            <StatusPill value={order.agreement_status} kind="neutral" />
          </div>
        </Card>
      )}

      <Card>
        <div className="p-5">
          <h3 className="font-semibold text-gray-900">Order progress</h3>
          <ol className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {ORDER_STAGES.map((stage) => {
              const currentIndex = ORDER_STAGES.indexOf(order.status);
              const stageIndex = ORDER_STAGES.indexOf(stage);
              const complete =
                currentIndex >= 0 && stageIndex >= 0 && stageIndex <= currentIndex;
              return (
                <li
                  key={stage}
                  className={`flex items-center gap-2 rounded-lg border p-3 text-sm ${
                    complete
                      ? "border-green-200 bg-green-50 text-green-800"
                      : "border-gray-100 text-gray-500"
                  }`}
                >
                  <CheckCircle2 className="h-4 w-4 shrink-0" />
                  {stage}
                </li>
              );
            })}
          </ol>
        </div>
      </Card>

      {order.dispute_reason && (
        <Card>
          <div className="border-l-4 border-red-500 p-5">
            <h3 className="font-semibold text-red-800">Quality dispute</h3>
            <p className="mt-1 text-sm text-gray-700">{order.dispute_reason}</p>
          </div>
        </Card>
      )}

      {(order.allowed_transitions.length > 0 ||
        (isBuyer && order.status === "Awaiting quality confirmation") ||
        (isFinancial &&
          order.payment_status === "RELEASE_PENDING" &&
          order.status === "Awaiting payment release") ||
        (isFinancial && order.status === "Disputed")) && (
        <Card>
          <div className="space-y-4 p-5">
            <h3 className="font-semibold text-gray-900">Available actions</h3>
            {order.allowed_transitions.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {order.allowed_transitions.map((next) => (
                  <Button
                    key={next}
                    loading={busy}
                    variant={["Cancelled", "Rejected"].includes(next) ? "danger" : "primary"}
                    onClick={() =>
                      void run(
                        () => ordersApi.setStatus(order.id, next),
                        `Order updated to ${next}.`
                      )
                    }
                  >
                    {next}
                  </Button>
                ))}
              </div>
            )}
            {isBuyer && order.status === "Awaiting quality confirmation" && (
              <div className="flex flex-wrap gap-2">
                <Button
                  loading={busy}
                  icon={<ShieldCheck className="h-4 w-4" />}
                  onClick={() =>
                    void run(
                      () => ordersApi.confirmQuality(order.id),
                      "Quality confirmed. Escrow is awaiting Financial Manager review."
                    )
                  }
                >
                  Confirm quality
                </Button>
              </div>
            )}
            {isBuyer && order.status === "Awaiting quality confirmation" && (
              <div className="space-y-2">
                <Field label="Dispute reason" htmlFor="dispute-reason">
                  <Textarea
                    id="dispute-reason"
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    placeholder="Describe the product quality issue"
                  />
                </Field>
                <Button
                  variant="danger"
                  loading={busy}
                  disabled={!reason.trim()}
                  onClick={() =>
                    void run(
                      () => ordersApi.dispute(order.id, reason.trim()),
                      "Dispute submitted; escrow is on hold."
                    )
                  }
                >
                  Report quality dispute
                </Button>
              </div>
            )}
            {isFinancial &&
              order.payment_status === "RELEASE_PENDING" &&
              order.status === "Awaiting payment release" && (
                <div className="space-y-3">
                  <Field
                    label="External settlement reference"
                    htmlFor="settlement-ref"
                    hint="Record the manual bank/mobile-money settlement reference reviewed by Finance."
                  >
                    <Input
                      id="settlement-ref"
                      value={settlementReference}
                      onChange={(event) => setSettlementReference(event.target.value)}
                    />
                  </Field>
                  <Button
                    loading={busy}
                    disabled={!settlementReference.trim()}
                    onClick={() =>
                      void run(
                        () => ordersApi.release(order.id, settlementReference.trim()),
                        "Escrow released to the seller's Green Path wallet."
                      )
                    }
                  >
                    Approve escrow release
                  </Button>
                </div>
              )}
            {isFinancial && order.status === "Disputed" && (
              <div className="space-y-3">
                <Field
                  label="External settlement reference (for release)"
                  htmlFor="dispute-ref"
                >
                  <Input
                    id="dispute-ref"
                    value={settlementReference}
                    onChange={(event) => setSettlementReference(event.target.value)}
                  />
                </Field>
                <div className="flex flex-wrap gap-2">
                  <Button
                    loading={busy}
                    disabled={!settlementReference.trim()}
                    onClick={() =>
                      void run(
                        () =>
                          ordersApi.resolveDispute(
                            order.id,
                            "release",
                            settlementReference.trim()
                          ),
                        "Dispute resolved and escrow released."
                      )
                    }
                  >
                    Resolve and release
                  </Button>
                  <Button
                    variant="danger"
                    loading={busy}
                    onClick={() =>
                      void run(
                        () => ordersApi.resolveDispute(order.id, "refund"),
                        "Dispute resolved and funds returned to the buyer."
                      )
                    }
                  >
                    Resolve and refund
                  </Button>
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      {canRate && (
        <Card>
          <div className="space-y-4 p-5">
            <h3 className="font-semibold text-gray-900">Rate this transaction</h3>
            <Field label="Rating" htmlFor="review-rating">
              <select
                id="review-rating"
                className="h-10 rounded-lg border border-gray-300 bg-white px-3"
                value={reviewRating}
                onChange={(event) => setReviewRating(Number(event.target.value))}
              >
                {[5, 4, 3, 2, 1].map((stars) => (
                  <option key={stars} value={stars}>
                    {"★".repeat(stars)} ({stars})
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Review" htmlFor="review-comment">
              <Textarea
                id="review-comment"
                value={reviewComment}
                onChange={(event) => setReviewComment(event.target.value)}
                maxLength={2000}
                placeholder="Share your experience"
              />
            </Field>
            <Button
              loading={busy}
              onClick={() => void submitReview()}
            >
              Submit verified review
            </Button>
          </div>
        </Card>
      )}
    </div>
  );

  return (
    <AppShell title="Order details" allow={ROLES}>
      {page}
    </AppShell>
  );
}
