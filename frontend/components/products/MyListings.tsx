"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Eye, PackagePlus, Pencil, Sprout, Trash2 } from "lucide-react";
import { productsApi } from "@/lib/api/client";
import {
  Card,
  EmptyState,
  ErrorBanner,
  PageLoader,
  Pagination,
  Select,
  StatusPill,
  TableWrap,
  Td,
  Th,
} from "@/components/ui";
import { formatDate, formatEtb, formatNumber, mediaUrl } from "@/lib/format";
import type { Product, ProductStatus } from "@/lib/types";

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "ALL", label: "All statuses" },
  { value: "ACTIVE", label: "Active" },
  { value: "INACTIVE", label: "Inactive" },
  { value: "SOLD", label: "Sold" },
  { value: "DRAFT", label: "Draft" },
];

/**
 * "My Listings" table for farmers and for wholesaler re-listings.
 * Wholesalers cannot delete (no DELETE route on that viewset) but can toggle
 * active/inactive.
 */
export function MyListings({ kind }: { kind: "farmer" | "wholesaler" }) {
  const [rows, setRows] = useState<Product[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("ALL");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");

  const base = kind === "farmer" ? "/farmer" : "/wholesaler";

  const load = useCallback(async () => {
    setError("");
    try {
      const query = {
        page,
        status: status === "ALL" ? undefined : (status as ProductStatus),
        search: search || undefined,
      };
      const res =
        kind === "farmer"
          ? await productsApi.myFarmerListings(query)
          : await productsApi.myWholesalerListings(query);
      setRows(res.results);
      setCount(res.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load listings.");
    } finally {
      setLoading(false);
    }
  }, [kind, page, status, search]);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggle(p: Product) {
    setBusyId(p.id);
    setError("");
    try {
      if (kind === "farmer") {
        if (p.status === "ACTIVE") {
          await productsApi.deactivateFarmerListing(p.id);
        } else {
          await productsApi.activateFarmerListing(p.id);
        }
      } else {
        if (p.status === "ACTIVE") {
          await productsApi.deactivateWholesalerListing(p.id);
        } else {
          await productsApi.activateWholesalerListing(p.id);
        }
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed.");
    } finally {
      setBusyId("");
    }
  }

  async function remove(p: Product) {
    if (!window.confirm(`Delete "${p.title}"?`)) return;
    setBusyId(p.id);
    setError("");
    try {
      await productsApi.deleteFarmerListing(p.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setBusyId("");
    }
  }

  if (loading) return <PageLoader />;

  return (
    <div className="space-y-5">
      {error && <ErrorBanner message={error} onRetry={() => void load()} />}

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-5 py-4">
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search by title or description…"
              className="h-9 w-56 rounded-lg border border-gray-200 px-3 text-sm focus:border-green-500 focus:outline-none focus:ring-2 focus:ring-green-500/20"
            />
            <Select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
              className="h-9 w-40"
              aria-label="Filter by status"
            >
              {STATUS_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </Select>
          </div>

          <Link
            href={`${base}/new-product`}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-green-600 px-3.5 text-sm font-medium text-white hover:bg-green-700"
          >
            <PackagePlus className="h-4 w-4" />
            Post New Product
          </Link>
        </div>

        {rows.length === 0 ? (
          <EmptyState
            title="No listings found"
            description={
              search || status !== "ALL"
                ? "Try a different search or filter."
                : "Post your first product to reach buyers."
            }
            icon={<Sprout className="h-8 w-8" />}
            action={
              <Link
                href={`${base}/new-product`}
                className="inline-flex h-9 items-center rounded-lg bg-green-600 px-4 text-sm font-medium text-white hover:bg-green-700"
              >
                Post New Product
              </Link>
            }
          />
        ) : (
          <>
            <TableWrap>
              <thead>
                <tr>
                  <Th>Product</Th>
                  <Th>Category</Th>
                  <Th>Quantity</Th>
                  <Th>Price / Unit</Th>
                  <Th>Total</Th>
                  <Th>Status</Th>
                  <Th>Posted</Th>
                  <Th align="center">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id}>
                    <Td>
                      <div className="flex items-center gap-3">
                        {p.images.length > 0 ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={mediaUrl(p.images[0])}
                            alt=""
                            className="h-10 w-10 shrink-0 rounded-lg object-cover"
                          />
                        ) : (
                          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-gray-400">
                            <Sprout className="h-4 w-4" />
                          </span>
                        )}
                        <div className="min-w-0">
                          <Link
                            href={`${base}/listings/${p.id}`}
                            className="block truncate font-medium text-gray-900 hover:text-green-700"
                          >
                            {p.title}
                          </Link>
                          <p className="truncate text-xs text-gray-500">
                            {p.description}
                          </p>
                        </div>
                      </div>
                    </Td>
                    <Td>{p.category_display}</Td>
                    <Td>
                      {formatNumber(p.quantity)} {p.unit_display}
                    </Td>
                    <Td>{formatEtb(p.price_per_unit)}</Td>
                    <Td>{formatEtb(p.total_value)}</Td>
                    <Td>
                      <StatusPill value={p.status} />
                    </Td>
                    <Td className="whitespace-nowrap text-xs text-gray-500">
                      {formatDate(p.created_at)}
                    </Td>
                    <Td align="center">
                      <div className="flex items-center justify-center gap-3">
                        <Link
                          href={`${base}/listings/${p.id}`}
                          title="View"
                          className="text-gray-500 hover:text-gray-900"
                        >
                          <Eye className="h-4 w-4" />
                        </Link>
                        <Link
                          href={`${base}/listings/${p.id}?edit=1`}
                          title="Edit"
                          className="text-gray-500 hover:text-gray-900"
                        >
                          <Pencil className="h-4 w-4" />
                        </Link>
                        <button
                          onClick={() => void toggle(p)}
                          disabled={busyId === p.id}
                          title={p.status === "ACTIVE" ? "Deactivate" : "Activate"}
                          className="text-xs font-medium text-gray-500 hover:text-green-700 disabled:opacity-40"
                        >
                          {p.status === "ACTIVE" ? "Deactivate" : "Activate"}
                        </button>
                        {kind === "farmer" && (
                          <button
                            onClick={() => void remove(p)}
                            disabled={busyId === p.id}
                            title="Delete"
                            className="text-gray-500 hover:text-red-600 disabled:opacity-40"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pagination page={page} count={count} onPage={setPage} />
          </>
        )}
      </Card>
    </div>
  );
}
