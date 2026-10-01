"use client";

import { AppShell } from "@/components/layout/AppShell";
import { PaymentsTable } from "@/components/payments/PaymentsTable";

export default function FinancialManagerPaymentsPage() {
  return (
    <AppShell title="Payments" allow={["FINANCIAL_MANAGER"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Payment Management</h2>
        <p className="mt-1 text-sm text-gray-500">
          Verify, flag or dispute payments submitted by wholesalers.
        </p>
      </div>
      <PaymentsTable />
    </AppShell>
  );
}
