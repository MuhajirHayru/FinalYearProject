"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowDownToLine, ArrowUpFromLine, Wallet as WalletIcon } from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import {
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  PageLoader,
  Select,
  StatusPill,
} from "@/components/ui";
import { walletApi } from "@/lib/api/client";
import { formatDateTime, formatEtb } from "@/lib/format";
import type { BankAccount, Wallet, WalletFundingRequest, WalletPayoutRequest } from "@/lib/types";
import type { WalletTransaction } from "@/lib/types";
import { useAuth } from "@/lib/auth/context";

const METHODS = ["CBE Birr", "Telebirr", "Bank Transfer"];

export default function WalletPage() {
  const { user } = useAuth();
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [funding, setFunding] = useState<WalletFundingRequest[]>([]);
  const [payouts, setPayouts] = useState<WalletPayoutRequest[]>([]);
  const [transactions, setTransactions] = useState<WalletTransaction[]>([]);
  const [bankAccounts, setBankAccounts] = useState<BankAccount[]>([]);
  const [fundingAmount, setFundingAmount] = useState("");
  const [chapaAmount, setChapaAmount] = useState("");
  const [payoutAmount, setPayoutAmount] = useState("");
  const [method, setMethod] = useState(METHODS[0]);
  const [reference, setReference] = useState("");
  const [destination, setDestination] = useState("");
  const [payoutAccountId, setPayoutAccountId] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [walletData, fundingData, payoutData, transactionData, bankAccountData] = await Promise.all([
        walletApi.get(),
        walletApi.funding(),
        walletApi.payouts(),
        walletApi.transactions(),
        walletApi.bankAccounts(),
      ]);
      setWallet(walletData);
      setFunding(fundingData.results);
      setPayouts(payoutData.results);
      setTransactions(transactionData.results);
      setBankAccounts(bankAccountData.results);
      setPayoutAccountId((current) =>
        current || bankAccountData.results.find((account) => account.is_default)?.id || ""
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load your wallet.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!user) return;
    const fundingId = new URLSearchParams(window.location.search).get("funding");
    if (!fundingId) return;

    let cancelled = false;
    setBusy(true);
    walletApi
      .verifyChapaFunding(fundingId)
      .then((deposit) => {
        if (cancelled) return;
        setNotice(
          deposit.status === "AWAITING_APPROVAL"
            ? "Chapa verified the payment. It is awaiting financial admin approval."
            : deposit.status === "APPROVED"
              ? "The deposit was approved and added to your wallet."
              : deposit.status === "FAILED"
                ? "Chapa could not verify this payment. Your wallet was not credited."
                : "Payment verification is pending. Your wallet has not been credited."
        );
        return load();
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not verify the Chapa payment.");
        }
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
        window.history.replaceState(window.history.state, "", window.location.pathname);
      });
    return () => {
      cancelled = true;
    };
  }, [user, load]);

  async function submitFunding(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await walletApi.requestFunding({
        amount: fundingAmount,
        payment_method: method,
        external_reference: reference.trim(),
      });
      setFundingAmount("");
      setReference("");
      setNotice("Funding request submitted. Your wallet is credited after Finance verifies the transfer.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit the funding request.");
    } finally {
      setBusy(false);
    }
  }

  async function startChapaFunding(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const deposit = await walletApi.initializeChapaFunding(chapaAmount);
      setChapaAmount("");
      if (!deposit.checkout_url) {
        setNotice("Deposit created; payment verification is pending. Your wallet was not credited.");
        await load();
        return;
      }
      window.location.assign(deposit.checkout_url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the Chapa payment.");
    } finally {
      setBusy(false);
    }
  }

  async function verifyDeposit(id: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const deposit = await walletApi.verifyChapaFunding(id);
      setNotice(
        deposit.status === "AWAITING_APPROVAL"
          ? "Payment verified and sent to Finance for approval."
          : deposit.status === "FAILED"
            ? "Payment verification failed. No funds were added."
            : "Payment is still being verified. No funds were added."
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not verify the payment.");
    } finally {
      setBusy(false);
    }
  }

  async function submitPayout(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await walletApi.requestPayout({
        amount: payoutAmount,
        ...(payoutAccountId
          ? { payout_account: payoutAccountId }
          : { destination: destination.trim() }),
      });
      setPayoutAmount("");
      setDestination("");
      setNotice("Payout request submitted for Finance review.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit the payout request.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <AppShell title="Wallet" allow={["FARMER", "WHOLESALER", "RETAILER"]}><PageLoader /></AppShell>;
  }

  return (
    <AppShell title="Wallet" allow={["FARMER", "WHOLESALER", "RETAILER"]}>
      <div className="mx-auto max-w-5xl space-y-5">
        <div>
          <h2 className="text-lg font-bold text-gray-900">My Wallet</h2>
          <p className="mt-1 text-sm text-gray-500">
            Manual bank and mobile-money transfers are verified by Finance before balances change.
          </p>
        </div>
        {error && <ErrorBanner message={error} onRetry={() => void load()} />}
        {notice && <div role="status" className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">{notice}</div>}
        {wallet && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Card><div className="p-5"><p className="text-sm text-gray-500">Available balance</p><p className="mt-2 text-2xl font-bold text-gray-900">{formatEtb(wallet.available_balance)}</p></div></Card>
            <Card><div className="p-5"><p className="text-sm text-gray-500">Held in escrow / payout review</p><p className="mt-2 text-2xl font-bold text-gray-900">{formatEtb(wallet.held_balance)}</p></div></Card>
          </div>
        )}
        <div className="grid gap-5 lg:grid-cols-2">
          {(user?.role === "WHOLESALER" || user?.role === "RETAILER") && (
            <Card>
              <CardHeader
                title="Deposit with Chapa"
                subtitle="Test-mode checkout. A deposit is not credited until Chapa verifies it and Finance approves it."
              />
              <form className="space-y-4 p-5" onSubmit={(event) => void startChapaFunding(event)}>
                <Field label="Amount (ETB)" htmlFor="chapa-amount">
                  <Input
                    id="chapa-amount"
                    type="number"
                    min="0.01"
                    step="0.01"
                    required
                    value={chapaAmount}
                    onChange={(event) => setChapaAmount(event.target.value)}
                  />
                </Field>
                <Button loading={busy} icon={<ArrowDownToLine className="h-4 w-4" />}>
                  Continue to Chapa test checkout
                </Button>
              </form>
            </Card>
          )}
          <Card>
            <CardHeader title="Add funds" subtitle="Complete the transfer first, then submit its reference for verification." />
            <form className="space-y-4 p-5" onSubmit={(event) => void submitFunding(event)}>
              <Field label="Amount (ETB)" htmlFor="fund-amount"><Input id="fund-amount" type="number" min="0.01" step="0.01" required value={fundingAmount} onChange={(event) => setFundingAmount(event.target.value)} /></Field>
              <Field label="Transfer method" htmlFor="fund-method"><Select id="fund-method" value={method} onChange={(event) => setMethod(event.target.value)}>{METHODS.map((option) => <option key={option}>{option}</option>)}</Select></Field>
              <Field label="Transfer reference" htmlFor="fund-reference"><Input id="fund-reference" required value={reference} onChange={(event) => setReference(event.target.value)} /></Field>
              <Button loading={busy} icon={<ArrowDownToLine className="h-4 w-4" />}>Submit funding request</Button>
            </form>
          </Card>
          <Card>
            <CardHeader
              title="Request payout"
              subtitle="Finance manually reviews payout requests; saving a bank account does not mean it is verified or paid automatically."
              action={<Link href="/settings#bank-accounts" className="text-xs font-medium text-green-700 hover:underline">Manage payout accounts</Link>}
            />
            <form className="space-y-4 p-5" onSubmit={(event) => void submitPayout(event)}>
              <Field label="Amount (ETB)" htmlFor="payout-amount"><Input id="payout-amount" type="number" min="0.01" step="0.01" required value={payoutAmount} onChange={(event) => setPayoutAmount(event.target.value)} /></Field>
              {bankAccounts.length > 0 && (
                <Field label="Saved payout account (optional)" htmlFor="payout-account">
                  <Select id="payout-account" value={payoutAccountId} onChange={(event) => setPayoutAccountId(event.target.value)}>
                    <option value="">Enter a destination manually</option>
                    {bankAccounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.nickname || account.bank_name} · {account.masked_account_number} · {account.status === "NOT_VERIFIED" ? "not verified" : "review required"}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {!payoutAccountId && (
                <Field label="Bank or mobile-money destination" htmlFor="payout-destination">
                  <Input id="payout-destination" required value={destination} onChange={(event) => setDestination(event.target.value)} placeholder="Account or wallet details" />
                </Field>
              )}
              <Button loading={busy} icon={<ArrowUpFromLine className="h-4 w-4" />}>Request payout</Button>
            </form>
          </Card>
        </div>
        <Card>
          <CardHeader title="Funding requests" />
          {funding.length ? <ul className="divide-y divide-gray-100">{funding.map((request) => <li key={request.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 text-sm"><div><p className="font-medium text-gray-900">{formatEtb(request.amount)} · {request.payment_method}{request.payment_mode === "TEST" ? " · Test mode" : ""}</p><p className="mt-1 text-xs text-gray-500">{request.external_reference} · {formatDateTime(request.submitted_at)}</p>{request.payment_method === "Chapa" && request.verified_amount && <p className="mt-1 text-xs text-gray-500">Chapa confirmed {request.verified_amount} {request.verified_currency} · {request.provider_status}</p>}{request.review_notes && <p className="mt-1 text-xs text-red-700">{request.review_notes}</p>}</div><div className="flex items-center gap-2"><StatusPill value={request.status} />{request.payment_method === "Chapa" && ["AWAITING_PAYMENT", "PAYMENT_VERIFICATION_PENDING"].includes(request.status) && <Button size="sm" variant="secondary" disabled={busy} onClick={() => void verifyDeposit(request.id)}>Verify status</Button>}</div></li>)}</ul> : <EmptyState title="No funding requests yet" icon={<WalletIcon className="h-8 w-8" />} />}
        </Card>
        <Card>
          <CardHeader title="Payout requests" />
          {payouts.length ? <ul className="divide-y divide-gray-100">{payouts.map((request) => <li key={request.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 text-sm"><div><p className="font-medium text-gray-900">{formatEtb(request.amount)} · {request.destination}</p><p className="mt-1 text-xs text-gray-500">{formatDateTime(request.submitted_at)}{request.external_reference ? ` · ${request.external_reference}` : ""}</p></div><StatusPill value={request.status} /></li>)}</ul> : <EmptyState title="No payout requests yet" icon={<WalletIcon className="h-8 w-8" />} />}
        </Card>
        <Card>
          <CardHeader title="Wallet transaction history" />
          {transactions.length ? (
            <ul className="divide-y divide-gray-100">
              {transactions.map((transaction) => (
                <li key={transaction.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 text-sm">
                  <div>
                    <p className="font-medium text-gray-900">{transaction.description || transaction.transaction_type}</p>
                    <p className="mt-1 text-xs text-gray-500">
                      {transaction.reference}
                      {transaction.external_reference ? ` · ${transaction.external_reference}` : ""}
                      {transaction.order_reference ? ` · ${transaction.order_reference}` : ""}
                    </p>
                    <p className="mt-1 text-xs text-gray-500">{formatDateTime(transaction.created_at)}</p>
                  </div>
                  <span className={`font-semibold ${Number(transaction.available_delta) >= 0 ? "text-green-700" : "text-gray-700"}`}>
                    {Number(transaction.available_delta) >= 0 ? "+" : "−"}
                    {formatEtb(Math.abs(Number(transaction.available_delta)))}
                  </span>
                </li>
              ))}
            </ul>
          ) : <EmptyState title="No wallet transactions yet" icon={<WalletIcon className="h-8 w-8" />} />}
        </Card>
      </div>
    </AppShell>
  );
}
