"use client";

import { AppShell } from "@/components/layout/AppShell";
import { PayoutInvoiceQueue } from "@/components/payments/PayoutInvoiceQueue";

export default function FinancialManagerPayoutsPage() {
  return (
    <AppShell title="Payout Invoices" allow={["FINANCIAL_MANAGER"]}>
      <PayoutInvoiceQueue />
    </AppShell>
  );
}
