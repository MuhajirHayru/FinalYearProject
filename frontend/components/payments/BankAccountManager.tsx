"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Landmark, Pencil, Plus, Trash2 } from "lucide-react";
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
import { formatDateTime } from "@/lib/format";
import type { BankAccount, PayoutBank } from "@/lib/types";

type AccountForm = {
  bank: string;
  account_holder_name: string;
  account_number: string;
  confirm_account_number: string;
  branch: string;
  branch_code: string;
  account_type: string;
  nickname: string;
  is_default: boolean;
};

const emptyForm: AccountForm = {
  bank: "",
  account_holder_name: "",
  account_number: "",
  confirm_account_number: "",
  branch: "",
  branch_code: "",
  account_type: "",
  nickname: "",
  is_default: false,
};

export function BankAccountManager() {
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [banks, setBanks] = useState<PayoutBank[]>([]);
  const [bankSearch, setBankSearch] = useState("");
  const [form, setForm] = useState<AccountForm>(emptyForm);
  const [editingId, setEditingId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [accountsData, banksData] = await Promise.all([
        walletApi.bankAccounts(),
        walletApi.banks(),
      ]);
      setAccounts(accountsData.results);
      setBanks(banksData.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load payout accounts.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filteredBanks = useMemo(() => {
    const query = bankSearch.trim().toLocaleLowerCase();
    return query
      ? banks.filter((bank) => bank.name.toLocaleLowerCase().includes(query))
      : banks;
  }, [bankSearch, banks]);

  function updateForm<K extends keyof AccountForm>(key: K, value: AccountForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function startEditing(account: BankAccount) {
    setEditingId(account.id);
    setForm({
      ...emptyForm,
      bank: String(account.bank),
      account_holder_name: account.account_holder_name,
      branch: account.branch,
      branch_code: account.branch_code,
      account_type: account.account_type,
      nickname: account.nickname,
      is_default: account.is_default,
    });
    setBankSearch(account.bank_name);
    setNotice("");
  }

  function resetForm() {
    setEditingId("");
    setForm(emptyForm);
    setBankSearch("");
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = {
        bank: Number(form.bank),
        account_holder_name: form.account_holder_name.trim(),
        branch: form.branch.trim(),
        branch_code: form.branch_code.trim(),
        account_type: form.account_type.trim(),
        nickname: form.nickname.trim(),
        is_default: form.is_default,
      };
      if (editingId) {
        const update: Parameters<typeof walletApi.updateBankAccount>[1] = payload;
        if (form.account_number.trim()) {
          update.account_number = form.account_number;
          update.confirm_account_number = form.confirm_account_number;
        }
        await walletApi.updateBankAccount(editingId, update);
        setNotice("Payout account updated.");
      } else {
        await walletApi.createBankAccount({
          ...payload,
          account_number: form.account_number,
          confirm_account_number: form.confirm_account_number,
        });
        setNotice("Payout account saved. It has not been independently verified.");
      }
      resetForm();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save payout account.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(account: BankAccount) {
    if (!window.confirm(`Remove the ${account.bank_name} account ending ${account.masked_account_number.slice(-4)}?`)) {
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await walletApi.deleteBankAccount(account.id);
      setNotice("Payout account removed.");
      if (editingId === account.id) resetForm();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove payout account.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <PageLoader />;

  return (
    <div id="bank-accounts" className="space-y-5">
      {error && <ErrorBanner message={error} onRetry={() => void load()} />}
      {notice && (
        <div role="status" className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {notice}
        </div>
      )}
      <Card>
        <CardHeader
          title="Bank Accounts & Payout Methods"
          subtitle="Save your payout details. Saving an account does not verify it or connect it to an automated payout provider."
        />
        {accounts.length ? (
          <ul className="divide-y divide-gray-100">
            {accounts.map((account) => (
              <li key={account.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                <div className="min-w-0">
                  <p className="font-medium text-gray-900">
                    {account.nickname || account.bank_name}
                    {account.is_default && <span className="ml-2 text-xs text-green-700">Default</span>}
                  </p>
                  <p className="mt-1 text-sm text-gray-600">
                    {account.account_holder_name} · {account.bank_name} · {account.masked_account_number}
                  </p>
                  <p className="mt-1 text-xs text-gray-500">
                    Saved {formatDateTime(account.created_at)} · Updated {formatDateTime(account.updated_at)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <StatusPill value={account.status} />
                  <Button size="sm" variant="secondary" disabled={busy} icon={<Pencil className="h-3.5 w-3.5" />} onClick={() => startEditing(account)}>Edit</Button>
                  <Button size="sm" variant="danger" disabled={busy} icon={<Trash2 className="h-3.5 w-3.5" />} onClick={() => void remove(account)}>Remove</Button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="px-5">
            <EmptyState title="No payout accounts saved" description="Add a bank account below. The account will remain unverified until a real verification procedure is available." icon={<Landmark className="h-8 w-8" />} />
          </div>
        )}
      </Card>

      <Card>
        <CardHeader
          title={editingId ? "Update payout account" : "Add payout account"}
          subtitle="Bank choices come from the National Bank of Ethiopia bank directory; this list does not mean the bank is supported by Chapa payouts."
        />
        <form className="grid gap-4 p-5 sm:grid-cols-2" onSubmit={(event) => void submit(event)}>
          <Field label="Search banks" htmlFor="payout-bank-search">
            <Input id="payout-bank-search" value={bankSearch} onChange={(event) => setBankSearch(event.target.value)} placeholder="Type a bank name" />
          </Field>
          <Field label="Bank" htmlFor="payout-bank">
            <Select id="payout-bank" required value={form.bank} onChange={(event) => updateForm("bank", event.target.value)}>
              <option value="">Select a bank</option>
              {filteredBanks.map((bank) => <option key={bank.id} value={bank.id}>{bank.name}</option>)}
            </Select>
          </Field>
          <Field label="Account holder's full legal name" htmlFor="payout-holder">
            <Input id="payout-holder" required maxLength={255} value={form.account_holder_name} onChange={(event) => updateForm("account_holder_name", event.target.value)} />
          </Field>
          <Field label="Account nickname (optional)" htmlFor="payout-nickname">
            <Input id="payout-nickname" maxLength={80} value={form.nickname} onChange={(event) => updateForm("nickname", event.target.value)} placeholder="e.g. Farm income" />
          </Field>
          <Field label={editingId ? "New account number (leave blank to keep current)" : "Account number"} htmlFor="payout-account-number" hint="Digits only; spaces and hyphens are normalized.">
            <Input id="payout-account-number" inputMode="numeric" autoComplete="off" minLength={6} maxLength={40} required={!editingId} value={form.account_number} onChange={(event) => updateForm("account_number", event.target.value)} />
          </Field>
          <Field label="Confirm account number" htmlFor="payout-confirm-account">
            <Input id="payout-confirm-account" inputMode="numeric" autoComplete="off" minLength={6} maxLength={40} required={!editingId || !!form.account_number} value={form.confirm_account_number} onChange={(event) => updateForm("confirm_account_number", event.target.value)} />
          </Field>
          <Field label="Branch (optional)" htmlFor="payout-branch">
            <Input id="payout-branch" maxLength={120} value={form.branch} onChange={(event) => updateForm("branch", event.target.value)} />
          </Field>
          <Field label="Branch code (optional)" htmlFor="payout-branch-code">
            <Input id="payout-branch-code" maxLength={40} value={form.branch_code} onChange={(event) => updateForm("branch_code", event.target.value)} />
          </Field>
          <Field label="Account type (optional)" htmlFor="payout-account-type">
            <Select id="payout-account-type" value={form.account_type} onChange={(event) => updateForm("account_type", event.target.value)}>
              <option value="">Not specified</option><option value="Savings">Savings</option><option value="Current">Current</option><option value="Business">Business</option>
            </Select>
          </Field>
          <label className="flex items-center gap-2 self-end pb-2 text-sm text-gray-700">
            <input type="checkbox" checked={form.is_default} onChange={(event) => updateForm("is_default", event.target.checked)} />
            Set as my default payout account
          </label>
          <div className="flex gap-2 sm:col-span-2">
            <Button loading={busy} icon={<Plus className="h-4 w-4" />}>{editingId ? "Save changes" : "Save bank account"}</Button>
            {editingId && <Button type="button" variant="secondary" disabled={busy} onClick={resetForm}>Cancel</Button>}
          </div>
        </form>
      </Card>
      <p className="text-xs text-gray-500">
        Saved account numbers are encrypted in storage and masked in account lists. A Financial Manager must use the protected account-detail action to view the full number; that access is recorded in the audit log. Account registration alone does not establish payout eligibility.
      </p>
    </div>
  );
}
