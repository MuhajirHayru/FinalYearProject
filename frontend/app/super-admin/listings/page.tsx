"use client";

import { AppShell } from "@/components/layout/AppShell";
import { MarketplaceBrowser } from "@/components/products/MarketplaceBrowser";

export default function SuperAdminListingsPage() {
  return (
    <AppShell title="Listings" allow={["SUPER_ADMIN"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Listings</h2>
        <p className="mt-1 text-sm text-gray-500">
          Unrestricted read access to every listing on the platform.
        </p>
      </div>
      <MarketplaceBrowser
        type="farmer"
        basePath="/super-admin/listings"
        detailBasePath="/products"
      />
    </AppShell>
  );
}
