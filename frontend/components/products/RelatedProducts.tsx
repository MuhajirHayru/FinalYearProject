"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { MapPin, Sprout } from "lucide-react";
import { productsApi } from "@/lib/api/client";
import { formatEtb, formatNumber, mediaUrl } from "@/lib/format";
import type { Product } from "@/lib/types";

function titleWords(title: string) {
  return new Set(
    title
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter((word) => word.length > 2 && !["fresh", "organic", "local"].includes(word))
  );
}

export function RelatedProducts({
  product,
  kind,
}: {
  product: Product;
  kind: "farmer" | "wholesaler";
}) {
  const [related, setRelated] = useState<Product[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const query = {
      category: product.category,
      in_stock: "1" as const,
      page: 1,
    };
    const load = async () => {
      setError("");
      try {
        const categoryResults =
          kind === "farmer"
            ? product.is_owner
              ? await productsApi.myFarmerListings(query)
              : await productsApi.farmerListings(query)
            : product.is_owner
              ? await productsApi.myWholesalerListings(query)
              : await productsApi.wholesalerListings(query);

        let candidates = categoryResults.results;
        const ownOrCurrentFamily = async (search?: string) => {
          const searchQuery = { search, in_stock: "1" as const, page: 1 };
          return kind === "farmer"
            ? product.is_owner
              ? productsApi.myFarmerListings(searchQuery)
              : productsApi.farmerListings(searchQuery)
            : product.is_owner
              ? productsApi.myWholesalerListings(searchQuery)
              : productsApi.wholesalerListings(searchQuery);
        };
        const matchingWords = titleWords(product.title);
        if (candidates.filter((item) => item.id !== product.id).length < 4) {
          const searchTerm = [...matchingWords].sort(
            (left, right) => right.length - left.length
          )[0];
          if (searchTerm) {
            const nameResults = await ownOrCurrentFamily(searchTerm);
            candidates = [...candidates, ...nameResults.results];
          }
        }

        const unique = new Map(
          candidates
            .filter((item) => item.id !== product.id)
            .map((item) => [item.id, item])
        );
        const ranked = [...unique.values()]
          .map((item) => {
            const overlap = [...titleWords(item.title)].filter((word) =>
              matchingWords.has(word)
            ).length;
            return {
              item,
              score: (item.category === product.category ? 100 : 0) + overlap,
            };
          })
          .filter(({ item, score }) => item.category === product.category || score > 0)
          .sort((left, right) => right.score - left.score)
          .slice(0, 4)
          .map(({ item }) => item);

        if (!cancelled) setRelated(ranked);
      } catch {
        if (!cancelled) setError("Related products could not be loaded.");
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [kind, product.category, product.id, product.is_owner, product.title]);

  if (!related.length && !error) return null;

  return (
    <section className="mt-8" aria-labelledby="related-products-heading">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <h2
            id="related-products-heading"
            className="text-lg font-bold text-gray-900"
          >
            You May Also Like
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            More {product.category.toLowerCase()} from the marketplace.
          </p>
        </div>
      </div>
      {error ? (
        <p role="status" className="text-sm text-gray-500">
          {error}
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {related.map((item) => (
            <Link
              key={item.id}
              href={`/products/${item.id}`}
              className="group overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm transition-shadow hover:shadow-md"
            >
              <div className="h-36 overflow-hidden bg-gray-100">
                {item.images?.[0] ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={mediaUrl(item.images[0])}
                    alt={item.title}
                    className="h-full w-full object-cover transition-transform group-hover:scale-105"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center text-gray-300">
                    <Sprout className="h-8 w-8" />
                  </div>
                )}
              </div>
              <div className="space-y-1.5 p-3">
                <p className="line-clamp-1 text-sm font-semibold text-gray-900 group-hover:text-green-700">
                  {item.title}
                </p>
                <p className="line-clamp-1 text-xs text-gray-500">
                  {item.owner_name}
                </p>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-bold text-gray-900">
                    {formatEtb(item.price_per_unit)}
                    <span className="ml-1 text-xs font-normal text-gray-500">
                      / {item.unit_display}
                    </span>
                  </span>
                  <span className="truncate text-xs text-gray-500">
                    {formatNumber(item.quantity)} {item.unit_display}
                  </span>
                </div>
                <p className="flex items-center gap-1 truncate text-xs text-gray-400">
                  <MapPin className="h-3 w-3 shrink-0" />
                  {item.owner_location || "Location not set"}
                </p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
