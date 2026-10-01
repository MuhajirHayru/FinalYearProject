"use client";

import { AppShell } from "@/components/layout/AppShell";
import { MyListings } from "@/components/products/MyListings";

export default function WholesalerListingsPage() {
  return (
    <AppShell title="My Re-listings" allow={["WHOLESALER"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">My Re-listings</h2>
        <p className="mt-1 text-sm text-gray-500">
          Products you have offered to retailers.
        </p>
      </div>
      <MyListings kind="wholesaler" />
    </AppShell>
  );
}
