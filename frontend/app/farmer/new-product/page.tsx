"use client";

import { AppShell } from "@/components/layout/AppShell";
import { ProductForm } from "@/components/products/ProductForm";

export default function NewFarmerProductPage() {
  return (
    <AppShell title="Post New Product" allow={["FARMER"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Post a new product</h2>
        <p className="mt-1 text-sm text-gray-500">
          Wholesalers browsing the marketplace will see this listing immediately
          once it is active.
        </p>
      </div>
      <ProductForm kind="farmer" />
    </AppShell>
  );
}
