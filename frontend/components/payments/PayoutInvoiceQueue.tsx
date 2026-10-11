"use client";

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Eye,
  RefreshCw,
  X,
} from "lucide-react";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  Select,
  StatusPill,
  TableWrap,
  Td,
  Th,
} from "@/components/ui";
import { dashboardApi, walletApi } from "@/lib/api/client";
import { formatDateTime, formatEtb, formatInt } from "@/lib/format";
import type {
  FinancialOperationsSummary,
  WalletPayoutDetail,
  WalletPayoutRequest,
  WalletRequestQuery,
} from "@/lib/types";

const EMPTY_FILTERS: WalletRequestQuery = { status: "ALL", role: "ALL" };

const ROLE_LABELS: Record<string, string> = {
  FARMER: "Farmer",
  WHOLESALER: "Wholesaler",
  RETAILER: "Retailer",
};

export function PayoutInvoiceQueue() {
  const [payouts, setPayouts] = useState<WalletPayoutRequest[]>([]);
  const [summary, setSummary] = useState<FinancialOperationsSummary | null>(null);
  const [filters, setFilters] = useState<WalletRequestQuery>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<WalletRequestQuery>({});
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasPrevious, setHasPrevious] = useState(false);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<WalletPayoutDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [externalReference, setExternalReference] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [payoutData, operations] = await Promise.all([
        walletApi.payouts({ ...appliedFilters, page }),
        dashboardApi.financialOperations(),
      ]);
      setPayouts(payoutData.results);
      setTotal(payoutData.count);
      setHasPrevious(!!payoutData.previous);
      setHasNext(!!payoutData.next);
      setSummary(operations);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load payout invoices.");
    } finally {
      setLoading(false);
    }
  }, [appliedFilters, page]);

  useEffect(() => {
    void load();
  }, [load]);

  async function openDetails(id: string) {
    setSelectedId(id);
    setDetail(null);
    setDetailError("");
    setDetailLoading(true);
    setExternalReference("");
    setReviewNotes("");
    try {
      setDetail(await walletApi.payoutDetail(id));
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : "Could not load payout details.");
    } finally {
      setDetailLoading(false);
    }
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setSelectedId("");
    setAppliedFilters({
      status: filters.status === "ALL" ? undefined : filters.status,
      role: filters.role === "ALL" ? undefined : filters.role,
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
      search: filters.search?.trim() || undefined,
      min_amount: filters.min_amount || undefined,
      max_amount: filters.max_amount || undefined,
      method: filters.method || undefined,
      ordering: filters.ordering || "newest",
    });
  }

  function clearFilters() {
    setFilters(EMPTY_FILTERS);
    setAppliedFilters({});
    setPage(1);
    setSelectedId("");
  }

  async function review(approve: boolean) {
    if (!detail) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await walletApi.reviewPayout(
        detail.payout.id,
        approve,
        externalReference,
        reviewNotes
      );
      setNotice(
        approve
          ? "Payout recorded as paid after manual transfer confirmation."
          : "Payout rejected and reserved funds returned to the requester."
      );
      await load();
      await openDetails(detail.payout.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not review this payout.");
    } finally {
      setBusy(false);
    }
  }

  const statusSummary = summary?.payouts.by_status ?? {};

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Payout Invoices</h2>
          <p className="mt-1 max-w-3xl text-sm text-gray-600">
            Review wallet payout requests. This system records manual settlements; it does
            not initiate or automatically verify bank transfers.
          </p>
        </div>
        <Button type="button" variant="secondary" onClick={() => void load()} disabled={loading}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh
        </Button>
      </div>

      {error && <ErrorBanner message={error} onRetry={() => void load()} />}
      {notice && (
        <div role="status" className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {notice}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          label="Pending review"
          value={formatInt(statusSummary.PENDING?.count ?? 0)}
          detail={`${formatEtb(summary?.payouts.pending_amount ?? 0)} reserved for review`}
        />
        <SummaryCard
          label="Manually confirmed paid"
          value={formatInt(statusSummary.PAID?.count ?? 0)}
          detail={formatEtb(summary?.payouts.paid_amount ?? 0)}
        />
        <SummaryCard
          label="Rejected"
          value={formatInt(statusSummary.REJECTED?.count ?? 0)}
          detail={formatEtb(statusSummary.REJECTED?.amount ?? 0)}
        />
        <SummaryCard
          label="Requests"
          value={formatInt(total)}
          detail="Matching the current filters"
        />
      </div>

      <Card>
        <form onSubmit={applyFilters} className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
          <Field label="Search reference, requester or ID" htmlFor="payout-search">
            <Input
              id="payout-search"
              value={filters.search || ""}
              onChange={(event) => setFilters((value) => ({ ...value, search: event.target.value }))}
              placeholder="Name, payout ID, user ID"
            />
          </Field>
          <Field label="Status" htmlFor="payout-status">
            <Select
              id="payout-status"
              value={filters.status || "ALL"}
              onChange={(event) => setFilters((value) => ({ ...value, status: event.target.value }))}
            >
              <option value="ALL">All payouts</option>
              <option value="PENDING">Pending review</option>
              <option value="PAID">Paid / completed</option>
              <option value="REJECTED">Rejected</option>
            </Select>
          </Field>
          <Field label="Account type" htmlFor="payout-role">
            <Select
              id="payout-role"
              value={filters.role || "ALL"}
              onChange={(event) => setFilters((value) => ({ ...value, role: event.target.value as WalletRequestQuery["role"] }))}
            >
              <option value="ALL">All supported roles</option>
              <option value="FARMER">Farmer</option>
              <option value="WHOLESALER">Wholesaler</option>
              <option value="RETAILER">Retailer</option>
            </Select>
          </Field>
          <Field label="Destination method" htmlFor="payout-method">
            <Select
              id="payout-method"
              value={filters.method || ""}
              onChange={(event) => setFilters((value) => ({ ...value, method: (event.target.value || undefined) as WalletRequestQuery["method"] }))}
            >
              <option value="">All methods</option>
              <option value="REGISTERED">Registered bank account</option>
              <option value="MANUAL">Manual destination</option>
            </Select>
          </Field>
          <Field label="Sort by" htmlFor="payout-order">
            <Select
              id="payout-order"
              value={filters.ordering || "newest"}
              onChange={(event) => setFilters((value) => ({ ...value, ordering: event.target.value as WalletRequestQuery["ordering"] }))}
            >
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="amount_desc">Highest amount</option>
              <option value="amount_asc">Lowest amount</option>
              <option value="status">Status</option>
            </Select>
          </Field>
          <Field label="Requested from (ETB)" htmlFor="payout-min">
            <Input
              id="payout-min"
              type="number"
              min="0"
              step="0.01"
              value={filters.min_amount || ""}
              onChange={(event) => setFilters((value) => ({ ...value, min_amount: event.target.value }))}
            />
          </Field>
          <Field label="Requested to (ETB)" htmlFor="payout-max">
            <Input
              id="payout-max"
              type="number"
              min="0"
              step="0.01"
              value={filters.max_amount || ""}
              onChange={(event) => setFilters((value) => ({ ...value, max_amount: event.target.value }))}
            />
          </Field>
          <Field label="Requested from date" htmlFor="payout-date-from">
            <Input
              id="payout-date-from"
              type="date"
              value={filters.date_from || ""}
              onChange={(event) => setFilters((value) => ({ ...value, date_from: event.target.value }))}
            />
          </Field>
          <Field label="Requested to date" htmlFor="payout-date-to">
            <Input
              id="payout-date-to"
              type="date"
              value={filters.date_to || ""}
              onChange={(event) => setFilters((value) => ({ ...value, date_to: event.target.value }))}
            />
          </Field>
          <div className="flex items-end gap-2">
            <Button type="submit">Apply filters</Button>
            <Button type="button" variant="secondary" onClick={clearFilters}>Clear</Button>
          </div>
        </form>
      </Card>

      <Card>
        {loading ? (
          <p className="p-8 text-center text-sm text-gray-500">Loading payout invoices…</p>
        ) : payouts.length === 0 ? (
          <EmptyState
            title="No payout requests match these filters"
            description="New requests from marketplace users will appear here for financial review."
          />
        ) : (
          <TableWrap>
            <thead>
              <tr>
                <Th>Payout ID / requested</Th>
                <Th>Requester</Th>
                <Th>Amount</Th>
                <Th>Destination</Th>
                <Th>Status</Th>
                <Th>Reviewed</Th>
                <Th align="right">Action</Th>
              </tr>
            </thead>
            <tbody>
              {payouts.map((payout) => (
                <tr key={payout.id}>
                  <Td>
                    <p className="font-medium text-gray-900">{payout.id}</p>
                    <p className="text-xs text-gray-500">{formatDateTime(payout.submitted_at)}</p>
                  </Td>
                  <Td>
                    <p className="font-medium text-gray-900">{payout.wallet_owner}</p>
                    <p className="text-xs text-gray-500">
                      {ROLE_LABELS[payout.wallet_owner_role] || payout.wallet_owner_role} · {payout.wallet_owner_id.slice(0, 8)}
                    </p>
                  </Td>
                  <Td className="font-semibold">{formatEtb(payout.amount)}</Td>
                  <Td>
                    <p>{payout.destination}</p>
                    <p className="text-xs text-gray-500">{payout.payout_account ? "Registered bank account" : "Manual destination"}</p>
                  </Td>
                  <Td><StatusPill value={payout.status} /></Td>
                  <Td>{formatDateTime(payout.reviewed_at || payout.submitted_at)}</Td>
                  <Td align="right">
                    <Button type="button" size="sm" variant="secondary" onClick={() => void openDetails(payout.id)}>
                      <Eye className="mr-1.5 h-4 w-4" />
                      Details
                    </Button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        )}
      </Card>

      {!loading && (
        <div className="flex items-center justify-between text-sm text-gray-600">
          <span>{total} payout requests</span>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" disabled={!hasPrevious} onClick={() => setPage((value) => Math.max(1, value - 1))}>
              <ChevronLeft className="mr-1 h-4 w-4" />
              Previous
            </Button>
            <span>Page {page}</span>
            <Button size="sm" variant="secondary" disabled={!hasNext} onClick={() => setPage((value) => value + 1)}>
              <ChevronRight className="mr-1 h-4 w-4" />
              Next
            </Button>
          </div>
        </div>
      )}

      {selectedId && (
        <Card>
          <div className="flex items-start justify-between gap-3 border-b border-gray-100 p-5">
            <div>
              <h3 className="text-lg font-semibold text-gray-900">Payout review details</h3>
              {detail && <p className="mt-1 text-sm text-gray-500">{detail.payout.id}</p>}
            </div>
            <Button type="button" size="sm" variant="secondary" onClick={() => { setSelectedId(""); setDetail(null); }}>
              <X className="mr-1 h-4 w-4" />
              Close
            </Button>
          </div>
          {detailLoading ? (
            <p className="p-6 text-sm text-gray-500">Loading payout detail…</p>
          ) : detailError ? (
            <div className="p-5"><ErrorBanner message={detailError} onRetry={() => void openDetails(selectedId)} /></div>
          ) : detail ? (
            <PayoutDetails
              detail={detail}
              externalReference={externalReference}
              reviewNotes={reviewNotes}
              busy={busy}
              onReferenceChange={setExternalReference}
              onNotesChange={setReviewNotes}
              onReview={review}
            />
          ) : null}
        </Card>
      )}
    </section>
  );
}

function SummaryCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <Card>
      <div className="p-5">
        <p className="text-sm font-medium text-gray-500">{label}</p>
        <p className="mt-2 text-2xl font-bold text-gray-900">{value}</p>
        <p className="mt-1 text-xs text-gray-500">{detail}</p>
      </div>
    </Card>
  );
}

function PayoutDetails({
  detail,
  externalReference,
  reviewNotes,
  busy,
  onReferenceChange,
  onNotesChange,
  onReview,
}: {
  detail: WalletPayoutDetail;
  externalReference: string;
  reviewNotes: string;
  busy: boolean;
  onReferenceChange: (value: string) => void;
  onNotesChange: (value: string) => void;
  onReview: (approve: boolean) => void;
}) {
  const payout = detail.payout;
  return (
    <div className="space-y-6 p-5">
      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        <DetailGroup title="Requester">
          <DetailRow label="Name" value={detail.requester.name} />
          <DetailRow label="User ID" value={detail.requester.id} />
          <DetailRow label="Account type" value={ROLE_LABELS[detail.requester.role] || detail.requester.role} />
          <DetailRow label="Contact email" value={detail.requester.email} />
        </DetailGroup>
        <DetailGroup title="Payout request">
          <DetailRow label="Reference" value={payout.id} />
          <DetailRow label="Requested" value={`${formatEtb(payout.amount)} ${payout.currency}`} />
          <DetailRow label="Submitted" value={formatDateTime(payout.submitted_at)} />
          <DetailRow label="Status" value={payout.status} />
          <DetailRow label="Transfer reference" value={payout.external_reference || "Not recorded"} />
          {payout.review_notes && <DetailRow label="Review note / reason" value={payout.review_notes} />}
        </DetailGroup>
        <DetailGroup title="Wallet and destination">
          <DetailRow label="Available balance" value={formatEtb(detail.wallet.available_balance)} />
          <DetailRow label="Held balance" value={formatEtb(detail.wallet.held_balance)} />
          <DetailRow label="Requested amount reserved" value={detail.wallet.requested_amount_reserved ? "Yes" : "No"} />
          <DetailRow label="Destination" value={payout.destination} />
          <DetailRow
            label="Saved account"
            value={detail.destination_review.bank_name
              ? `${detail.destination_review.bank_name} ${detail.destination_review.masked_account_number}`
              : "Manual destination"}
          />
          {detail.destination_review.account_holder_name && (
            <DetailRow label="Account holder" value={detail.destination_review.account_holder_name} />
          )}
          <DetailRow label="Destination status" value={detail.destination_review.status.replaceAll("_", " ")} />
          <p className="rounded-md bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-800">
            The app does not verify destination ownership or execute bank transfers. Confirm the transfer with
            your authorized external reconciliation source before marking this request paid.
          </p>
        </DetailGroup>
      </div>

      {payout.status === "PENDING" && (
        <div className="rounded-lg border border-green-200 bg-green-50/50 p-4">
          <h4 className="font-semibold text-gray-900">Financial review actions</h4>
          {!detail.eligible_for_manual_confirmation && (
            <p className="mt-2 text-sm text-red-700">
              This request does not currently meet the server-calculated requirements for settlement. Reconcile
              the reservation before taking action.
            </p>
          )}
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <Field label="Verified bank / transfer reference" htmlFor={`payout-reference-${payout.id}`}>
              <Input
                id={`payout-reference-${payout.id}`}
                value={externalReference}
                onChange={(event) => onReferenceChange(event.target.value)}
                placeholder="Reference from the confirmed transfer"
              />
            </Field>
            <Field label="Review note or rejection reason" htmlFor={`payout-note-${payout.id}`}>
              <Input
                id={`payout-note-${payout.id}`}
                value={reviewNotes}
                onChange={(event) => onNotesChange(event.target.value)}
                placeholder="Record the evidence checked or reason for rejection"
              />
            </Field>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              type="button"
              disabled={busy || !detail.eligible_for_manual_confirmation || !externalReference.trim() || !reviewNotes.trim()}
              loading={busy}
              onClick={() => onReview(true)}
            >
              Confirm transfer and mark paid
            </Button>
            <Button
              type="button"
              variant="danger"
              disabled={busy || !reviewNotes.trim()}
              onClick={() => onReview(false)}
            >
              Reject and return reserved funds
            </Button>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <DetailGroup title="Wallet transaction history">
          {detail.transactions.length ? detail.transactions.map((item) => (
            <div key={item.id} className="border-b border-gray-100 py-3 last:border-0">
              <p className="font-medium text-gray-900">{item.type.replaceAll("_", " ")} · {formatEtb(item.amount)}</p>
              <p className="mt-1 break-all text-xs text-gray-500">{item.reference}{item.external_reference ? ` · ${item.external_reference}` : ""}</p>
              <p className="mt-1 text-xs text-gray-500">{item.description} · {formatDateTime(item.created_at)}</p>
            </div>
          )) : <p className="text-sm text-gray-500">No related wallet transactions were recorded.</p>}
        </DetailGroup>
        <DetailGroup title="Audit timeline">
          {detail.history.length ? detail.history.map((item, index) => (
            <div key={`${item.action}-${item.created_at}-${index}`} className="relative border-l-2 border-green-200 pb-4 pl-4 last:pb-0">
              <span className="absolute -left-[5px] top-1 h-2 w-2 rounded-full bg-green-600" />
              <p className="font-medium text-gray-900">{item.action.replaceAll("_", " ")}</p>
              <p className="mt-1 text-xs text-gray-500">{item.actor || "System"} · {formatDateTime(item.created_at)}</p>
              <p className="mt-1 break-words text-sm text-gray-600">{item.detail}</p>
            </div>
          )) : <p className="text-sm text-gray-500">No audit events are available for this request.</p>}
        </DetailGroup>
      </div>
    </div>
  );
}

function DetailGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2 rounded-lg border border-gray-100 p-4">
      <h4 className="border-b border-gray-100 pb-2 font-semibold text-gray-900">{title}</h4>
      {children}
    </section>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-3 gap-y-1 text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="break-all text-right font-medium text-gray-900">{value}</span>
    </div>
  );
}
