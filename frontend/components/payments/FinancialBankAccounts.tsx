"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, Landmark, MessageSquare } from "lucide-react";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  Select,
  StatusPill,
} from "@/components/ui";
import { chatApi, walletApi } from "@/lib/api/client";
import { formatDateTime, formatEtb } from "@/lib/format";
import type { BankAccount, BankAccountFullDetails } from "@/lib/types";

export function FinancialBankAccounts() {
  const router = useRouter();
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [count, setCount] = useState(0);
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [bank, setBank] = useState("");
  const [status, setStatus] = useState("");
  const [selectedDetails, setSelectedDetails] = useState<BankAccountFullDetails | null>(null);
  const [busyId, setBusyId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [banks, setBanks] = useState<{ id: number; code: string; name: string }[]>([]);

  const load = useCallback(async () => {
    setError("");
    try {
      const [accountData, bankData] = await Promise.all([
        walletApi.bankAccounts({ search, role, bank, status }),
        walletApi.banks(),
      ]);
      setAccounts(accountData.results);
      setCount(accountData.count);
      setBanks(bankData.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load beneficiary accounts.");
    } finally {
      setLoading(false);
    }
  }, [search, role, bank, status]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 250);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function showDetails(account: BankAccount) {
    if (selectedDetails?.id === account.id) {
      setSelectedDetails(null);
      return;
    }
    setBusyId(account.id);
    setError("");
    try {
      setSelectedDetails(await walletApi.fullBankAccountDetails(account.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not access protected account details.");
    } finally {
      setBusyId("");
    }
  }

  async function requestFurtherReview(account: BankAccount) {
    const notes = window.prompt(
      `Why does the ${account.bank_name} payout account need further review?`
    );
    if (!notes?.trim()) return;
    setBusyId(account.id);
    setError("");
    try {
      await walletApi.requestBankAccountReview(account.id, notes.trim());
      setSelectedDetails(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not flag the account for review.");
    } finally {
      setBusyId("");
    }
  }

  async function messageAccountHolder(account: BankAccount) {
    setBusyId(account.id);
    setError("");
    try {
      const result = await chatApi.openChannel(account.user_id);
      router.push(`/chat?channel=${encodeURIComponent(result.channel.id)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open a conversation.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <section className="space-y-5">
      <div>
        <h2 className="text-lg font-bold text-gray-900">Beneficiary Bank Accounts</h2>
        <p className="mt-1 text-sm text-gray-500">
          Account numbers are masked by default. Viewing a full account number is permission-checked and audit logged. Registration does not verify an account or establish automated payout support.
        </p>
      </div>
      {error && <ErrorBanner message={error} onRetry={() => void load()} />}
      <Card>
        <div className="grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Search name or user ID" htmlFor="bank-account-search">
            <Input id="bank-account-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search users or holder" />
          </Field>
          <Field label="User role" htmlFor="bank-account-role">
            <Select id="bank-account-role" value={role} onChange={(event) => setRole(event.target.value)}>
              <option value="">All marketplace roles</option>
              <option value="FARMER">Farmer</option><option value="WHOLESALER">Wholesaler</option><option value="RETAILER">Retailer</option>
            </Select>
          </Field>
          <Field label="Bank" htmlFor="bank-account-bank">
            <Select id="bank-account-bank" value={bank} onChange={(event) => setBank(event.target.value)}>
              <option value="">All banks</option>
              {banks.map((item) => <option key={item.id} value={item.code}>{item.name}</option>)}
            </Select>
          </Field>
          <Field label="Review status" htmlFor="bank-account-status">
            <Select id="bank-account-status" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">All statuses</option>
              <option value="NOT_VERIFIED">Not verified</option>
              <option value="REQUIRES_REVIEW">Requires further review</option>
            </Select>
          </Field>
        </div>
      </Card>
      <p className="text-sm text-gray-600">{count} registered account{count === 1 ? "" : "s"}</p>
      {loading ? (
        <p className="py-8 text-center text-sm text-gray-500">Loading beneficiary accounts...</p>
      ) : accounts.length ? (
        <div className="space-y-3">
          {accounts.map((account) => (
            <Card key={account.id}>
              <div className="space-y-3 p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-gray-900">{account.account_holder_name}</p>
                    <p className="mt-1 text-sm text-gray-600">
                      {account.user_name} · {account.user_id} · <StatusPill value={account.user_role} kind="role" />
                    </p>
                    <p className="mt-1 text-sm text-gray-600">{account.bank_name} · {account.masked_account_number}{account.is_default ? " · Default" : ""}</p>
                    <p className="mt-1 text-xs text-gray-500">Registered {formatDateTime(account.created_at)} · Updated {formatDateTime(account.updated_at)}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusPill value={account.status} />
                    {account.user_role !== "RETAILER" && (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={!!busyId}
                        loading={busyId === account.id}
                        icon={<MessageSquare className="h-4 w-4" />}
                        onClick={() => void messageAccountHolder(account)}
                      >
                        Message
                      </Button>
                    )}
                    {account.status === "NOT_VERIFIED" && (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={!!busyId}
                        onClick={() => void requestFurtherReview(account)}
                      >
                        Request further review
                      </Button>
                    )}
                    <Button size="sm" variant="secondary" loading={busyId === account.id} icon={selectedDetails?.id === account.id ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />} onClick={() => void showDetails(account)}>
                      {selectedDetails?.id === account.id ? "Hide full number" : "View protected details"}
                    </Button>
                  </div>
                </div>
                {selectedDetails?.id === account.id && (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm">
                    <p className="font-medium text-amber-900">Protected account details (access recorded)</p>
                    <p className="mt-2 text-amber-900">{selectedDetails.account_number}</p>
                    <p className="mt-1 text-xs text-amber-800">{selectedDetails.branch || "Branch not supplied"}{selectedDetails.branch_code ? ` · ${selectedDetails.branch_code}` : ""}</p>
                  </div>
                )}
                {account.payout_requests?.length ? (
                  <div className="border-t border-gray-100 pt-3">
                    <p className="text-xs font-semibold text-gray-600">Associated recent payout requests</p>
                    {account.payout_requests.map((request) => (
                      <p key={request.id} className="mt-1 text-xs text-gray-600">
                        {formatEtb(request.amount)} · {request.status} · {formatDateTime(request.submitted_at)}
                      </p>
                    ))}
                  </div>
                ) : null}
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <Card><EmptyState title="No beneficiary accounts found" description="Try changing the filters." icon={<Landmark className="h-8 w-8" />} /></Card>
      )}
    </section>
  );
}
