"use client";

import { useCallback, useEffect, useState } from "react";
import { Flag, Receipt, Search, ShieldCheck, TriangleAlert } from "lucide-react";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  Modal,
  PageLoader,
  Pagination,
  Select,
  StatusPill,
  TableWrap,
  Td,
  Textarea,
  Th,
} from "@/components/ui";
import { paymentsApi } from "@/lib/api/client";
import { formatEtb } from "@/lib/format";
import type {
  PaymentMethod,
  PaymentQuery,
  PaymentRecord,
  PaymentStatus,
} from "@/lib/types";

const TABS: { value: PaymentStatus; label: string }[] = [
  { value: "PENDING", label: "Pending" },
  { value: "VERIFIED", label: "Verified" },
  { value: "FLAGGED", label: "Flagged" },
  { value: "DISPUTED", label: "Disputed" },
];

const METHODS: { value: PaymentMethod; label: string }[] = [
  { value: "CBE Birr", label: "CBE Birr" },
  { value: "Telebirr", label: "Telebirr" },
  { value: "Bank Transfer", label: "Bank Transfer" },
  { value: "Chapa", label: "Chapa" },
  { value: "Cash", label: "Cash" },
];

/**
 * Figure 4.10 - payment management for the Financial Manager.
 *
 * `verify` sends `notes`, while `flag` and `dispute` send `reason`; the backend
 * reads different keys for the two paths, so they are separate modals.
 */
export function PaymentsTable({
  initialStatus = "PENDING",
  counts,
}: {
  initialStatus?: PaymentStatus;
  counts?: Record<PaymentStatus, number>;
}) {
  const [rows, setRows] = useState<PaymentRecord[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<PaymentStatus | "ALL">(initialStatus);
  const [method, setMethod] = useState<PaymentMethod | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");

  const [verifying, setVerifying] = useState<PaymentRecord | null>(null);
  const [notes, setNotes] = useState("");
  const [flagging, setFlagging] = useState<{ row: PaymentRecord; disputed: boolean } | null>(
    null
  );
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const query: PaymentQuery = {
        page,
        status: status === "ALL" ? undefined : status,
        method: method === "ALL" ? undefined : method,
        search: search || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      };
      const res = await paymentsApi.list(query);
      setRows(res.results);
      setCount(res.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load payments.");
    } finally {
      setLoading(false);
    }
  }, [page, status, method, search, dateFrom, dateTo]);

  useEffect(() => {
    void load();
  }, [load]);

  async function confirmVerify() {
    if (!verifying) return;
    setBusyId(verifying.id);
    setError("");
    try {
      await paymentsApi.verify(verifying.id, notes.trim() || undefined);
      setNotice(`Payment ${verifying.display_id} verified.`);
      setVerifying(null);
      setNotes("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed.");
    } finally {
      setBusyId("");
    }
  }

  async function confirmFlag() {
    if (!flagging) return;
    setBusyId(flagging.row.id);
    setError("");
    try {
      // The backend reads `reason` for both flag and dispute.
      if (flagging.disputed) {
        await paymentsApi.dispute(flagging.row.id, reason.trim());
      } else {
        await paymentsApi.flag(flagging.row.id, reason.trim() || undefined);
      }
      setNotice(
        `Payment ${flagging.row.display_id} ${
          flagging.disputed ? "disputed" : "flagged"
        }.`
      );
      setFlagging(null);
      setReason("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the payment.");
    } finally {
      setBusyId("");
    }
  }

  async function showReceipt(row: PaymentRecord) {
    setError("");
    try {
      const res = await paymentsApi.receipt(row.id);
      setNotice(`Receipt ${row.display_id}: ${JSON.stringify(res.receipt)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the receipt.");
    }
  }

  if (loading) return <PageLoader />;

  return (
    <div className="space-y-5">
      {error && <ErrorBanner message={error} onRetry={() => void load()} />}
      {notice && (
        <div className="break-words rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {notice}
        </div>
      )}

      {counts && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => {
                setStatus(tab.value);
                setPage(1);
              }}
              className={`rounded-xl border p-4 text-left transition-colors ${
                status === tab.value
                  ? "border-green-600 bg-green-50"
                  : "border-gray-200 bg-white hover:border-gray-300"
              }`}
            >
              <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
                {tab.label}
              </p>
              <p className="mt-1 text-2xl font-bold text-gray-900">
                {counts[tab.value] ?? 0}
              </p>
            </button>
          ))}
        </div>
      )}

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-gray-100 px-5 py-4">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <Input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search reference, product or party..."
              className="pl-9"
              aria-label="Search payments"
            />
          </div>

          <Select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as PaymentStatus | "ALL");
              setPage(1);
            }}
            className="h-10 w-36"
            aria-label="Filter by status"
          >
            <option value="ALL">All statuses</option>
            {TABS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </Select>

          <Select
            value={method}
            onChange={(e) => {
              setMethod(e.target.value as PaymentMethod | "ALL");
              setPage(1);
            }}
            className="h-10 w-40"
            aria-label="Filter by method"
          >
            <option value="ALL">All methods</option>
            {METHODS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </Select>

          <Input
            type="date"
            value={dateFrom}
            onChange={(e) => {
              setDateFrom(e.target.value);
              setPage(1);
            }}
            className="h-10 w-40"
            aria-label="From date"
          />
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => {
              setDateTo(e.target.value);
              setPage(1);
            }}
            className="h-10 w-40"
            aria-label="To date"
          />
        </div>

        {rows.length === 0 ? (
          <EmptyState
            title="No payments found"
            description="Nothing matches these filters."
            icon={<Receipt className="h-8 w-8" />}
          />
        ) : (
          <>
            <TableWrap>
              <thead>
                <tr>
                  <Th>ID</Th>
                  <Th>Wholesaler</Th>
                  <Th>Farmer</Th>
                  <Th>Product</Th>
                  <Th>Amount</Th>
                  <Th>Method</Th>
                  <Th>Reference</Th>
                  <Th>Status</Th>
                  <Th>Submitted</Th>
                  <Th align="center">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id}>
                    <Td className="font-mono text-xs">{p.display_id}</Td>
                    <Td className="max-w-32 truncate">{p.wholesaler}</Td>
                    <Td className="max-w-32 truncate">{p.farmer_name}</Td>
                    <Td className="max-w-40 truncate">{p.product_title}</Td>
                    <Td className="font-medium">{formatEtb(p.amount)}</Td>
                    <Td className="whitespace-nowrap text-xs">{p.method_display}</Td>
                    <Td className="font-mono text-xs">{p.reference_number}</Td>
                    <Td>
                      <StatusPill value={p.status} />
                    </Td>
                    <Td className="whitespace-nowrap text-xs text-gray-500">
                      {p.submitted}
                    </Td>
                    <Td align="center">
                      <div className="flex flex-wrap items-center justify-center gap-2">
                        {p.status !== "VERIFIED" && (
                          <Button
                            size="sm"
                            icon={<ShieldCheck className="h-3.5 w-3.5" />}
                            loading={busyId === p.id}
                            onClick={() => {
                              setVerifying(p);
                              setNotes("");
                            }}
                          >
                            Verify
                          </Button>
                        )}
                        {p.status !== "FLAGGED" && p.status !== "DISPUTED" && (
                          <Button
                            size="sm"
                            variant="secondary"
                            icon={<Flag className="h-3.5 w-3.5" />}
                            onClick={() => {
                              setFlagging({ row: p, disputed: false });
                              setReason("");
                            }}
                          >
                            Flag
                          </Button>
                        )}
                        {p.status !== "DISPUTED" && (
                          <Button
                            size="sm"
                            variant="danger"
                            icon={<TriangleAlert className="h-3.5 w-3.5" />}
                            onClick={() => {
                              setFlagging({ row: p, disputed: true });
                              setReason("");
                            }}
                          >
                            Dispute
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={<Receipt className="h-3.5 w-3.5" />}
                          onClick={() => void showReceipt(p)}
                        >
                          Receipt
                        </Button>
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

      <Modal
        open={Boolean(verifying)}
        onClose={() => setVerifying(null)}
        title="Verify payment"
        description={
          verifying
            ? `${verifying.display_id} - ${formatEtb(verifying.amount)} from ${verifying.wholesaler}`
            : undefined
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setVerifying(null)}>
              Cancel
            </Button>
            <Button loading={busyId === verifying?.id} onClick={() => void confirmVerify()}>
              Confirm verification
            </Button>
          </>
        }
      >
        <Field
          label="Notes"
          htmlFor="verify-notes"
          hint="Recorded against the payment for the audit trail."
        >
          <Textarea
            id="verify-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Confirmed with the wholesaler's bank statement."
          />
        </Field>
      </Modal>

      <Modal
        open={Boolean(flagging)}
        onClose={() => setFlagging(null)}
        title={flagging?.disputed ? "Raise a dispute" : "Flag payment"}
        description={
          flagging
            ? `${flagging.row.display_id} - ${formatEtb(flagging.row.amount)}`
            : undefined
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setFlagging(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={busyId === flagging?.row.id}
              onClick={() => void confirmFlag()}
            >
              {flagging?.disputed ? "Raise dispute" : "Flag payment"}
            </Button>
          </>
        }
      >
        <Field
          label="Reason"
          htmlFor="flag-reason"
          hint={
            flagging?.disputed
              ? "Required. A dispute cannot be reconciled."
              : "Optional, but helps the audit trail."
          }
        >
          <Textarea
            id="flag-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Amount does not match the reference."
          />
        </Field>
      </Modal>
    </div>
  );
}
