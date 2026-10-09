"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  MapPin,
  Search,
  SlidersHorizontal,
  Sprout,
  Star,
  X,
} from "lucide-react";
import { Avatar } from "@/components/ui";
import { OnlineStatus } from "@/components/presence/PresenceProvider";
import { FinanciallyVerifiedBadge } from "@/components/users/FinanciallyVerifiedBadge";
import { productsApi } from "@/lib/api/client";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Input,
  PageLoader,
  Pagination,
  Select,
  StatusPill,
} from "@/components/ui";
import { formatDistance, formatEtb, formatNumber, mediaUrl } from "@/lib/format";
import type {
  Product,
  ProductCategory,
  ProductQuery,
  UnitOfMeasure,
} from "@/lib/types";

const FALLBACK_CATEGORIES: ProductCategory[] = [
  "Vegetables",
  "Fruits",
  "Grains",
  "Pulses",
  "Spices",
  "Root Crops",
  "Other",
];
const FALLBACK_UNITS: UnitOfMeasure[] = [
  "kg",
  "quintal",
  "ton",
  "piece",
  "crate",
  "bunch",
  "litre",
];

const ORDERINGS = [
  { value: "-created_at", label: "Newest first" },
  { value: "created_at", label: "Oldest first" },
  { value: "price_per_unit", label: "Price: low to high" },
  { value: "-price_per_unit", label: "Price: high to low" },
  { value: "title", label: "Title A-Z" },
  { value: "distance_km", label: "Nearest first" },
];

/**
 * Marketplace grid with the full filter set the backend supports.
 *
 * `type` picks the endpoint family and `basePath` is the listing area the
 * detail page's "back" link returns to. `detailBasePath` is where the cards
 * themselves link; it defaults to `basePath` but staff and cross-role viewers
 * pass the canonical `/products` route so they are never dropped into an area
 * their role cannot open.
 */
export function MarketplaceBrowser({
  type,
  basePath,
  detailBasePath,
  mineOnly = false,
  defaultNearMe = false,
}: {
  type: "farmer" | "wholesaler";
  basePath: string;
  detailBasePath?: string;
  mineOnly?: boolean;
  defaultNearMe?: boolean;
}) {
  const detailHref = (id: string) => `${detailBasePath ?? basePath}/${id}`;
  const [rows, setRows] = useState<Product[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [categories, setCategories] = useState<ProductCategory[]>(FALLBACK_CATEGORIES);
  const [units, setUnits] = useState<UnitOfMeasure[]>(FALLBACK_UNITS);

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<ProductCategory | "">("");
  const [unit, setUnit] = useState<UnitOfMeasure | "">("");
  const [location, setLocation] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [ordering, setOrdering] = useState("-created_at");
  const [nearMe, setNearMe] = useState(defaultNearMe);
  const [radius, setRadius] = useState("25");
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    productsApi
      .meta()
      .then((meta) => {
        setCategories(meta.categories.map((c) => c.value as ProductCategory));
        setUnits(meta.units.map((u) => u.value as UnitOfMeasure));
      })
      .catch(() => undefined);
  }, []);

  const load = useCallback(async () => {
    setError("");
    try {
      const query: ProductQuery = {
        page,
        search: search || undefined,
        category: category || undefined,
        unit_of_measure: unit || undefined,
        location: location || undefined,
        min_price: minPrice || undefined,
        max_price: maxPrice || undefined,
        ordering: ordering as ProductQuery["ordering"],
        in_stock: "1",
        near_me: nearMe ? "1" : undefined,
        radius_km: nearMe ? radius : undefined,
        mine: mineOnly ? "1" : undefined,
      };
      const res =
        type === "farmer"
          ? await productsApi.farmerListings(query)
          : await productsApi.wholesalerListings(query);
      setRows(res.results);
      setCount(res.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load listings.");
    } finally {
      setLoading(false);
    }
  }, [
    type,
    mineOnly,
    page,
    search,
    category,
    unit,
    location,
    minPrice,
    maxPrice,
    ordering,
    nearMe,
    radius,
  ]);

  // Debounce the free-text box so typing does not fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => void load(), search ? 350 : 0);
    return () => clearTimeout(timer);
  }, [load, search]);

  function resetPage<T>(setter: (v: T) => void) {
    return (v: T) => {
      setter(v);
      setPage(1);
    };
  }

  function clearFilters() {
    setSearch("");
    setCategory("");
    setUnit("");
    setLocation("");
    setMinPrice("");
    setMaxPrice("");
    setNearMe(false);
    setPage(1);
  }

  const activeFilters =
    [category, unit, location, minPrice, maxPrice, nearMe].filter(Boolean).length;

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-center gap-2 p-4">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <Input
              value={search}
              onChange={(e) => resetPage(setSearch)(e.target.value)}
              placeholder="Search products, categories or descriptions..."
              className="pl-9"
              aria-label="Search listings"
            />
          </div>

          <Select
            value={category}
            onChange={(e) =>
              resetPage(setCategory)(e.target.value as ProductCategory)
            }
            className="h-10 w-44"
            aria-label="Category"
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>

          <Select
            value={ordering}
            onChange={(e) => resetPage(setOrdering)(e.target.value)}
            className="h-10 w-44"
            aria-label="Sort by"
          >
            {ORDERINGS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>

          <Button
            variant={showFilters ? "primary" : "secondary"}
            onClick={() => setShowFilters((v) => !v)}
            icon={<SlidersHorizontal className="h-4 w-4" />}
          >
            Filters
            {activeFilters > 0 && ` (${activeFilters})`}
          </Button>
        </div>

        {showFilters && (
          <div className="border-t border-gray-100 bg-gray-50 p-4">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-gray-600">
                  Unit of measure
                </span>
                <Select
                  value={unit}
                  onChange={(e) =>
                    resetPage(setUnit)(e.target.value as UnitOfMeasure)
                  }
                >
                  <option value="">Any unit</option>
                  {units.map((u) => (
                    <option key={u} value={u}>
                      {u}
                    </option>
                  ))}
                </Select>
              </label>

              <label className="block">
                <span className="mb-1 block text-xs font-medium text-gray-600">
                  Location contains
                </span>
                <Input
                  value={location}
                  onChange={(e) => resetPage(setLocation)(e.target.value)}
                  placeholder="e.g. Adama"
                />
              </label>

              <label className="block">
                <span className="mb-1 block text-xs font-medium text-gray-600">
                  Min price
                </span>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={minPrice}
                  onChange={(e) => resetPage(setMinPrice)(e.target.value)}
                  placeholder="0"
                />
              </label>

              <label className="block">
                <span className="mb-1 block text-xs font-medium text-gray-600">
                  Max price
                </span>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  value={maxPrice}
                  onChange={(e) => resetPage(setMaxPrice)(e.target.value)}
                  placeholder="Any"
                />
              </label>

              <div className="flex items-end">
                <label className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={nearMe}
                    onChange={(e) => {
                      setNearMe(e.target.checked);
                      setPage(1);
                    }}
                    className="h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
                  />
                  Near me
                </label>
                {nearMe && (
                  <Input
                    type="number"
                    min="1"
                    value={radius}
                    onChange={(e) => setRadius(e.target.value)}
                    className="ml-2 w-20"
                    aria-label="Radius in km"
                  />
                )}
              </div>
            </div>

            {activeFilters > 0 && (
              <button
                onClick={clearFilters}
                className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-gray-600 hover:text-gray-900"
              >
                <X className="h-3.5 w-3.5" />
                Clear all filters
              </button>
            )}
          </div>
        )}
      </Card>

      {error && <ErrorBanner message={error} onRetry={() => void load()} />}

      {loading ? (
        <PageLoader />
      ) : rows.length === 0 ? (
        <Card>
          <EmptyState
            title="No listings match"
            description={
              activeFilters || search
                ? "Try widening your filters or clearing the search."
                : "Nothing has been listed here yet."
            }
            icon={<Sprout className="h-8 w-8" />}
            action={
              (activeFilters > 0 || search) && (
                <Button variant="secondary" onClick={clearFilters}>
                  Clear filters
                </Button>
              )
            }
          />
        </Card>
      ) : (
        <>
          <p className="text-xs text-gray-500">
            Showing {rows.length} of {count} listing{count === 1 ? "" : "s"}
          </p>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {rows.map((p) => (
              <Link
                key={p.id}
                href={detailHref(p.id)}
                className="group flex flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm transition-shadow hover:shadow-md"
              >
                <div className="relative h-40 overflow-hidden bg-gray-100">
                  {p.images.length > 0 ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={mediaUrl(p.images[0])}
                      alt={p.title}
                      className="h-full w-full object-cover transition-transform group-hover:scale-105"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-gray-300">
                      <Sprout className="h-9 w-9" />
                    </div>
                  )}
                  <div className="absolute left-2 top-2">
                    <StatusPill value={p.status} />
                  </div>
                </div>

                <div className="flex flex-1 flex-col p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-gray-400">
                    {p.category_display}
                  </p>
                  <h3 className="mt-0.5 line-clamp-1 text-sm font-semibold text-gray-900 group-hover:text-green-700">
                    {p.title}
                  </h3>
                  <p className="mt-1 line-clamp-2 flex-1 text-xs text-gray-500">
                    {p.description}
                  </p>

                  <div className="mt-3 flex items-end justify-between">
                    <div>
                      <p className="text-base font-bold text-gray-900">
                        {formatEtb(p.price_per_unit)}
                      </p>
                      <p className="text-xs text-gray-500">
                        per {p.unit_display}
                      </p>
                    </div>
                    <p className="text-xs font-medium text-gray-600">
                      {formatNumber(p.quantity)} {p.unit_display} available
                    </p>
                  </div>

                  <div className="mt-2 flex min-w-0 items-center gap-2">
                    <Avatar name={p.owner_name} size="sm" src={p.owner_profile_photo} />
                    <div className="min-w-0">
                      <p className="flex items-center gap-1 truncate text-xs font-medium text-gray-600">
                        {p.owner_name}
                        {p.owner_financially_verified && <FinanciallyVerifiedBadge />}
                      </p>
                      {(p.owner_role === "Farmer" || p.owner_role === "Wholesaler") && (
                        <OnlineStatus
                          userId={p.owner}
                          initiallyOnline={p.owner_is_online}
                        />
                      )}
                      <p className="flex items-center gap-1 truncate text-xs text-gray-400">
                        <MapPin className="h-3 w-3 shrink-0" />
                        {p.owner_location || "Location not set"}
                        {p.distance_km !== null && ` - ${formatDistance(p.distance_km)}`}
                      </p>
                    </div>
                  </div>
                  {p.owner_average_rating !== null && (
                    <p className="mt-1 flex items-center gap-1 text-xs text-amber-600">
                      <Star className="h-3 w-3 fill-current" />
                      {p.owner_average_rating.toFixed(1)} ({p.owner_review_count} review{p.owner_review_count === 1 ? "" : "s"})
                    </p>
                  )}
                </div>
              </Link>
            ))}
          </div>

          <Pagination page={page} count={count} onPage={setPage} />
        </>
      )}
    </div>
  );
}
