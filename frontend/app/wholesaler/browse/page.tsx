"use client";

import { AppShell } from "@/components/layout/AppShell";
import { MarketplaceBrowser } from "@/components/products/MarketplaceBrowser";

export default function WholesalerBrowsePage() {
  return (
    <AppShell title="Browse Products" allow={["WHOLESALER"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Browse Products</h2>
        <p className="mt-1 text-sm text-gray-500">
          Live farmer listings you can order from, filterable by category, price,
          location and distance.
        </p>
      </div>
      {/* Wholesalers buy from FARMER_LISTING products. */}
      <MarketplaceBrowser
      type="farmer"
      basePath="/wholesaler/browse"
      detailBasePath="/products"
    />
    </AppShell>
  );
}
