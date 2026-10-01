"use client";

import { AppShell } from "@/components/layout/AppShell";
import { MarketplaceBrowser } from "@/components/products/MarketplaceBrowser";

const TABS = [
  { label: "Farmer listings", type: "farmer" as const, base: "/farmer/listings" },
  {
    label: "Wholesaler listings",
    type: "wholesaler" as const,
    base: "/wholesaler/listings",
  },
];

export default function AdminListingsPage() {
  return (
    <AppShell title="Listings" allow={["USER_ADMIN"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Listings</h2>
        <p className="mt-1 text-sm text-gray-500">
          Oversight of everything posted across the marketplace.
        </p>
      </div>

      <div className="space-y-4">
        {TABS.map((tab) => (
          <section key={tab.type}>
            <h3 className="mb-3 text-sm font-semibold text-gray-700">{tab.label}</h3>
            <MarketplaceBrowser
              type={tab.type}
              basePath={tab.base}
              detailBasePath="/products"
            />
          </section>
        ))}
      </div>
    </AppShell>
  );
}
