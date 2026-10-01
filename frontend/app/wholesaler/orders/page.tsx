"use client";

import { AppShell } from "@/components/layout/AppShell";
import { OrdersTable } from "@/components/orders/OrdersTable";

export default function WholesalerOrdersPage() {
  return (
    <AppShell title="My Orders" allow={["WHOLESALER"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">My Orders</h2>
        <p className="mt-1 text-sm text-gray-500">
          Every order you have placed, with the status changes the platform
          currently allows.
        </p>
      </div>
      <OrdersTable perspective="wholesaler" />
    </AppShell>
  );
}
