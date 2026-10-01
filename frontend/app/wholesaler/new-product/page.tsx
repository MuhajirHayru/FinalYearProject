"use client";

import { AppShell } from "@/components/layout/AppShell";
import { ProductForm } from "@/components/products/ProductForm";

export default function NewWholesalerProductPage() {
  return (
    <AppShell title="Re-list a Product" allow={["WHOLESALER"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Re-list a product</h2>
        <p className="mt-1 text-sm text-gray-500">
          Stock you have bought can be offered to retailers as a new listing.
        </p>
      </div>
      <ProductForm kind="wholesaler" />
    </AppShell>
  );
}
