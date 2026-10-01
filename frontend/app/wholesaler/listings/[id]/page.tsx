"use client";

import { use } from "react";
import { ProductDetail } from "@/components/products/ProductDetail";

export default function WholesalerListingDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <ProductDetail id={id} kind="wholesaler" />;
}
