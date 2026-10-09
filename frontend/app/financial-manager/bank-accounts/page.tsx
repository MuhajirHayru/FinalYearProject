"use client";

import { AppShell } from "@/components/layout/AppShell";
import { FinancialBankAccounts } from "@/components/payments/FinancialBankAccounts";

export default function FinancialManagerBankAccountsPage() {
  return (
    <AppShell title="Beneficiary Bank Accounts" allow={["FINANCIAL_MANAGER"]}>
      <div className="mx-auto max-w-6xl">
        <FinancialBankAccounts />
      </div>
    </AppShell>
  );
}
