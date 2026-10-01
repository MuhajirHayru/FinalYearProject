"use client";

import { AppShell } from "@/components/layout/AppShell";
import { OrdersTable } from "@/components/orders/OrdersTable";

export default function FarmerOrdersPage() {
  return (
    <AppShell title="Orders Received" allow={["FARMER"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Orders Received</h2>
        <p className="mt-1 text-sm text-gray-500">
          Confirm, ship and deliver the orders wholesalers have placed against your
          listings.
        </p>
      </div>
      <OrdersTable perspective="farmer" />
    </AppShell>
  );
}
