"use client";

import { AppShell } from "@/components/layout/AppShell";
import { PlatformData } from "@/components/admin/PlatformData";

export default function SuperAdminPaymentsPage() {
  return (
    <AppShell title="Payments" allow={["SUPER_ADMIN"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Payment Oversight</h2>
        <p className="mt-1 text-sm text-gray-500">
          Every payment record across the platform. Verifying, flagging and
          disputing is reserved for the Financial Manager role.
        </p>
      </div>
      <PlatformData resource="payments" />
    </AppShell>
  );
}
