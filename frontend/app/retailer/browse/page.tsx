"use client";

import { AppShell } from "@/components/layout/AppShell";
import { MarketplaceBrowser } from "@/components/products/MarketplaceBrowser";

export default function RetailerBrowsePage() {
  return (
    <AppShell title="Browse Products" allow={["RETAILER"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Browse Products</h2>
        <p className="mt-1 text-sm text-gray-500">
          Bulk stock offered by approved wholesalers. Message a wholesaler directly
          to arrange a purchase.
        </p>
      </div>
      {/* Retailers buy from WHOLESALER_LISTING products. */}
      <MarketplaceBrowser type="wholesaler" basePath="/retailer/browse" />
    </AppShell>
  );
}
