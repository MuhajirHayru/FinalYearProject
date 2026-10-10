"use client";

import { AppShell } from "@/components/layout/AppShell";
import { ReportsView } from "@/components/reports/ReportsView";
import { WalletActivityAnalytics } from "@/components/reports/WalletActivityAnalytics";

export default function FinancialManagerReportsPage() {
  return (
    <AppShell title="Financial Reports" allow={["FINANCIAL_MANAGER"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Financial Reports</h2>
        <p className="mt-1 text-sm text-gray-500">
          Review wallet deposits and payouts from the immutable wallet ledger.
          Payment-record reports remain available below.
        </p>
      </div>
      <WalletActivityAnalytics />
      <div className="mt-10">
        <h2 className="mb-4 text-lg font-bold text-gray-900">Payment-record reports</h2>
      <ReportsView />
      </div>
    </AppShell>
  );
}
