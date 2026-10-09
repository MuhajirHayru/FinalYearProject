"use client";

import { AppShell } from "@/components/layout/AppShell";
import { OrdersTable } from "@/components/orders/OrdersTable";

export default function RetailerOrdersPage() {
  return (
    <AppShell title="My Orders" allow={["RETAILER"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">My Orders</h2>
        <p className="mt-1 text-sm text-gray-500">
          Track purchases, delivery, quality confirmation and escrow status.
        </p>
      </div>
      <OrdersTable perspective="retailer" />
    </AppShell>
  );
}
