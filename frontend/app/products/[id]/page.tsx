"use client";

import { use, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth/context";
import { productsApi } from "@/lib/api/client";
import { AppShellFrame, ProductDetail } from "@/components/products/ProductDetail";
import { ErrorBanner, PageLoader } from "@/components/ui";
import type { Product } from "@/lib/types";

/**
 * Canonical listing URL, used by links that cross role boundaries (chat
 * headers, notifications). The `?edit=1` search param is handled inside
 * `ProductDetail`; this wrapper only works out which listing family the id
 * belongs to and which "back" path is safe for the current viewer.
 */
export default function ProductByIdPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { user } = useAuth();
  const [product, setProduct] = useState<Product | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setError("");

    // Try the wholesaler family first, then fall back to farmer listings.
    (async () => {
      try {
        const p = await productsApi.wholesalerListing(id);
        if (!cancelled) setProduct(p);
      } catch (wholesalerErr) {
        try {
          const p = await productsApi.farmerListing(id);
          if (!cancelled) {
            setProduct(p);
            return;
          }
        } catch (farmerErr) {
          if (!cancelled) {
            const e = farmerErr as { status?: number; message?: string };
            setError(
              e?.status === 404
                ? "That listing does not exist, or you no longer have access to it."
                : (e?.message ?? "Could not load this listing.")
            );
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <AppShellFrame title="Listing">
        <PageLoader label="Loading listing." />
      </AppShellFrame>
    );
  }

  if (error || !product) {
    return (
      <AppShellFrame title="Listing">
        <ErrorBanner message={error || "Listing not found."} />
      </AppShellFrame>
    );
  }

  const isWholesalerListing = product.product_type === "WHOLESALER_LISTING";

  // The "back" link must land somewhere the viewer is actually allowed to open,
  // so each role gets the listing area it can reach.
  const backPath = (() => {
    switch (user?.role) {
      case "FARMER":
        return isWholesalerListing ? "/wholesaler/browse" : "/farmer/listings";
      case "WHOLESALER":
        return isWholesalerListing ? "/wholesaler/listings" : "/wholesaler/browse";
      case "RETAILER":
        return "/retailer/browse";
      case "USER_ADMIN":
        return "/admin/listings";
      case "SUPER_ADMIN":
        return "/super-admin/listings";
      default:
        return "/financial-manager";
    }
  })();

  return (
    <ProductDetail
      id={id}
      kind={isWholesalerListing ? "wholesaler" : "farmer"}
      basePath={backPath}
    />
  );
}
