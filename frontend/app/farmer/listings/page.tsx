"use client";

import { AppShell } from "@/components/layout/AppShell";
import { MyListings } from "@/components/products/MyListings";

export default function FarmerListingsPage() {
  return (
    <AppShell title="My Listings" allow={["FARMER"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">My Listings</h2>
        <p className="mt-1 text-sm text-gray-500">
          Every product you have posted, with quick actions to view, edit,
          deactivate or delete.
        </p>
      </div>
      <MyListings kind="farmer" />
    </AppShell>
  );
}
