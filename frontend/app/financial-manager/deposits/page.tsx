"use client";

import { AppShell } from "@/components/layout/AppShell";
import { FinancialWorkflowQueue } from "@/components/payments/FinancialWorkflowQueue";

export default function FinancialManagerDepositsPage() {
  return (
    <AppShell title="Deposits" allow={["FINANCIAL_MANAGER"]}>
      <FinancialWorkflowQueue initialTab="funding" showTabs={false} />
    </AppShell>
  );
}
