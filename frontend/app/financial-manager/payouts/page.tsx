"use client";

import { AppShell } from "@/components/layout/AppShell";
import { FinancialWorkflowQueue } from "@/components/payments/FinancialWorkflowQueue";

export default function FinancialManagerPayoutsPage() {
  return (
    <AppShell title="Payouts" allow={["FINANCIAL_MANAGER"]}>
      <FinancialWorkflowQueue initialTab="payouts" showTabs={false} />
    </AppShell>
  );
}
