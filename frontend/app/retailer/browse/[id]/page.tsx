"use client";

import { use } from "react";
import { ProductDetail } from "@/components/products/ProductDetail";

export default function RetailerListingDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <ProductDetail id={id} kind="wholesaler" basePath="/retailer/browse" />;
}
