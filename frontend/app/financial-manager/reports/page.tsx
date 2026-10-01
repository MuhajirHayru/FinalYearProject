"use client";

import { AppShell } from "@/components/layout/AppShell";
import { ReportsView } from "@/components/reports/ReportsView";

export default function FinancialManagerReportsPage() {
  return (
    <AppShell title="Financial Reports" allow={["FINANCIAL_MANAGER"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Financial Reports</h2>
        <p className="mt-1 text-sm text-gray-500">
          Aggregate the payment ledger, then export the matching rows as CSV or
          PDF.
        </p>
      </div>
      <ReportsView />
    </AppShell>
  );
}
