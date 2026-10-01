"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  MapPin,
  MessageSquare,
  Package,
  Pencil,
  Sprout,
  Tag,
} from "lucide-react";
import { chatApi, ordersApi, paymentsApi, productsApi } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";
import { AppShell } from "@/components/layout/AppShell";
import {
  Button,
  Card,
  ErrorBanner,
  Field,
  Input,
  Modal,
  PageLoader,
  Select,
  StatusPill,
} from "@/components/ui";
import { ProductForm } from "@/components/products/ProductForm";
import {
  formatDate,
  formatDistance,
  formatEtb,
  formatNumber,
  mediaUrl,
} from "@/lib/format";
import type { Product, UserRole } from "@/lib/types";

// The backend's PaymentMethod choices, read from `payments/models.py`.
const PAYMENT_METHODS = [
  { value: "CBE Birr", label: "CBE Birr" },
  { value: "Telebirr", label: "Telebirr" },
  { value: "Bank Transfer", label: "Bank Transfer" },
  { value: "Chapa", label: "Chapa" },
  { value: "Cash", label: "Cash" },
] as const;

/**
 * Listing detail / edit screen.
 *
 * `kind` selects the endpoint family. `viewerRole` drives which actions are
 * offered: owners get edit, wholesalers get order + payment, retailers get chat.
 */
export function ProductDetail({
  id,
  kind,
  basePath,
}: {
  id: string;
  kind: "farmer" | "wholesaler";
  /**
   * Where the "back" and "manage" links point. Retailers read wholesaler
   * listings but must not be sent into the wholesaler area, so their route
   * passes "/retailer/browse" instead of the default.
   */
  basePath?: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const editMode = searchParams.get("edit") === "1";
  const base = basePath ?? (kind === "farmer" ? "/farmer" : "/wholesaler");
  const viewerRole = user?.role;

  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [orderOpen, setOrderOpen] = useState(false);
  const [orderQty, setOrderQty] = useState("1");
  const [orderBusy, setOrderBusy] = useState(false);
  const [orderError, setOrderError] = useState("");

  const [payOpen, setPayOpen] = useState(false);
  const [payAmount, setPayAmount] = useState("");
  const [payMethod, setPayMethod] = useState("CBE Birr");
  const [payRef, setPayRef] = useState("");
  const [payBusy, setPayBusy] = useState(false);
  const [payError, setPayError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const p =
        kind === "farmer"
          ? await productsApi.farmerListing(id)
          : await productsApi.wholesalerListing(id);
      setProduct(p);
      setPayAmount(p.total_value);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load listing.");
    } finally {
      setLoading(false);
    }
  }, [id, kind]);

  useEffect(() => {
    void load();
  }, [load]);

  async function placeOrder() {
    if (!product) return;
    setOrderBusy(true);
    setOrderError("");
    try {
      await ordersApi.create(product.id, orderQty);
      setOrderOpen(false);
      router.push("/wholesaler/orders");
    } catch (err) {
      setOrderError(err instanceof Error ? err.message : "Order failed.");
    } finally {
      setOrderBusy(false);
    }
  }

  async function submitPayment() {
    if (!product || !user) return;
    setPayBusy(true);
    setPayError("");
    try {
      // The backend requires `submitted_by` to be the acting wholesaler, and
      // validates that `farmer` owns `product`.
      await paymentsApi.submit({
        submitted_by: user.id,
        farmer: product.owner,
        product: product.id,
        amount: payAmount,
        payment_method: payMethod,
        reference_number: payRef,
      });
      setPayOpen(false);
      router.push("/wholesaler/orders");
    } catch (err) {
      setPayError(err instanceof Error ? err.message : "Payment failed.");
    } finally {
      setPayBusy(false);
    }
  }

  async function contactSeller() {
    if (!product) return;
    setError("");
    try {
      const res = await chatApi.openChannel(product.owner, product.id);
      router.push(`/chat?channel=${res.channel.id}`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not open a conversation."
      );
    }
  }

  if (loading) {
    return (
      <AppShellFrame title="Listing">
        <PageLoader />
      </AppShellFrame>
    );
  }

  if (!product) {
    return (
      <AppShellFrame title="Listing">
        <ErrorBanner
          message={error || "Listing not found."}
          onRetry={() => void load()}
        />
        <Link
          href={`${base}/listings`}
          className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-green-700"
        >
          <ArrowLeft className="h-4 w-4" /> Back to listings
        </Link>
      </AppShellFrame>
    );
  }

  const isOwner = product.is_owner;
  const canOrder = viewerRole === "WHOLESALER" && kind === "farmer" && !isOwner;
  const canPay = viewerRole === "WHOLESALER" && kind === "farmer" && !isOwner;
  const canChat = !isOwner;

  return (
    <AppShellFrame title={product.title}>
      <div className="mb-5">
        <Link
          href={`${base}/listings`}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-gray-600 hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4" /> Back to listings
        </Link>
      </div>

      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} />
        </div>
      )}

      {editMode && isOwner ? (
        <div>
          <h2 className="mb-4 text-lg font-bold text-gray-900">Edit listing</h2>
          <ProductForm kind={kind} product={product} />
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <div className="p-5">
              {product.images.length > 0 ? (
                <div className="mb-5 flex flex-wrap gap-3">
                  {product.images.map((src) => (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      key={src}
                      src={mediaUrl(src)}
                      alt={product.title}
                      className="h-40 w-40 rounded-xl object-cover"
                    />
                  ))}
                </div>
              ) : (
                <div className="mb-5 flex h-40 items-center justify-center rounded-xl bg-gray-100 text-gray-300">
                  <Sprout className="h-10 w-10" />
                </div>
              )}

              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">
                    {product.title}
                  </h2>
                  <p className="mt-1 flex items-center gap-1.5 text-sm text-gray-500">
                    <MapPin className="h-3.5 w-3.5" />
                    {product.owner_location || "Location not set"}
                    {product.distance_km !== null &&
                      ` · ${formatDistance(product.distance_km)}`}
                  </p>
                </div>
                <StatusPill value={product.status} />
              </div>

              <p className="mt-4 whitespace-pre-line text-sm leading-relaxed text-gray-700">
                {product.description}
              </p>

              <dl className="mt-6 grid grid-cols-2 gap-4 border-t border-gray-100 pt-5 sm:grid-cols-4">
                <div>
                  <dt className="text-xs text-gray-500">Category</dt>
                  <dd className="mt-0.5 text-sm font-medium text-gray-900">
                    {product.category_display}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-gray-500">Available</dt>
                  <dd className="mt-0.5 text-sm font-medium text-gray-900">
                    {formatNumber(product.quantity)} {product.unit_display}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-gray-500">Price / unit</dt>
                  <dd className="mt-0.5 text-sm font-medium text-gray-900">
                    {formatEtb(product.price_per_unit)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-gray-500">Total value</dt>
                  <dd className="mt-0.5 text-sm font-medium text-gray-900">
                    {formatEtb(product.total_value)}
                  </dd>
                </div>
              </dl>
            </div>
          </Card>

          <div className="space-y-5">
            <Card>
              <div className="p-5">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Seller
                </p>
                <p className="mt-1.5 text-base font-semibold text-gray-900">
                  {product.owner_name}
                </p>
                <p className="text-sm text-gray-500">{product.owner_role}</p>
                <p className="mt-2 flex items-center gap-1.5 text-sm text-gray-500">
                  <MapPin className="h-3.5 w-3.5" />
                  {product.owner_location || "—"}
                </p>
                <p className="mt-3 flex items-center gap-1.5 text-xs text-gray-400">
                  <Tag className="h-3.5 w-3.5" />
                  Listed {formatDate(product.created_at)}
                </p>
              </div>
            </Card>

            <Card>
              <div className="space-y-2 p-5">
                {isOwner ? (
                  <>
                    <Button
                      variant="secondary"
                      className="w-full"
                      icon={<Pencil className="h-4 w-4" />}
                      onClick={() => router.push(`${base}/listings/${id}?edit=1`)}
                    >
                      Edit listing
                    </Button>
                    {basePath === undefined && (
                      <Button
                        className="w-full"
                        onClick={() => router.push(`${base}/listings`)}
                      >
                        Manage all listings
                      </Button>
                    )}
                  </>
                ) : (
                  <>
                    {canChat && (
                      <Button
                        variant="secondary"
                        className="w-full"
                        icon={<MessageSquare className="h-4 w-4" />}
                        onClick={() => void contactSeller()}
                      >
                        Contact seller
                      </Button>
                    )}
                    {canOrder && product.status === "ACTIVE" && (
                      <Button
                        className="w-full"
                        icon={<Package className="h-4 w-4" />}
                        onClick={() => {
                          setOrderQty("1");
                          setOrderOpen(true);
                        }}
                      >
                        Place order
                      </Button>
                    )}
                    {canPay && (
                      <Button
                        variant="secondary"
                        className="w-full"
                        onClick={() => {
                          setPayAmount(product.total_value);
                          setPayOpen(true);
                        }}
                      >
                        Submit payment record
                      </Button>
                    )}
                  </>
                )}
              </div>
            </Card>
          </div>
        </div>
      )}

      <Modal
        open={orderOpen}
        onClose={() => setOrderOpen(false)}
        title="Place order"
        description={product ? `${product.title} — ${formatEtb(product.price_per_unit)}/${product.unit_display}` : ""}
        footer={
          <>
            <Button variant="secondary" onClick={() => setOrderOpen(false)}>
              Cancel
            </Button>
            <Button loading={orderBusy} onClick={() => void placeOrder()}>
              Confirm order
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {orderError && <ErrorBanner message={orderError} />}
          <Field
            label={`Quantity (${product?.unit_display ?? "unit"})`}
            htmlFor="order-qty"
            hint={`${formatNumber(product?.quantity ?? "0")} available`}
          >
            <Input
              id="order-qty"
              type="number"
              step="0.01"
              min="0.01"
              max={product?.quantity}
              value={orderQty}
              onChange={(e) => setOrderQty(e.target.value)}
            />
          </Field>
          <p className="text-sm text-gray-600">
            Order total:{" "}
            <span className="font-semibold text-gray-900">
              {formatEtb(
                (Number(orderQty) || 0) * (Number(product?.price_per_unit) || 0)
              )}
            </span>
          </p>
        </div>
      </Modal>

      <Modal
        open={payOpen}
        onClose={() => setPayOpen(false)}
        title="Submit payment record"
        description="A financial manager will verify this before it counts as settled."
        footer={
          <>
            <Button variant="secondary" onClick={() => setPayOpen(false)}>
              Cancel
            </Button>
            <Button loading={payBusy} onClick={() => void submitPayment()}>
              Submit for verification
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {payError && <ErrorBanner message={payError} />}
          <Field label="Amount (ETB)" htmlFor="pay-amount">
            <Input
              id="pay-amount"
              type="number"
              step="0.01"
              min="0"
              value={payAmount}
              onChange={(e) => setPayAmount(e.target.value)}
            />
          </Field>
          <Field label="Payment method" htmlFor="pay-method">
            <Select
              id="pay-method"
              value={payMethod}
              onChange={(e) => setPayMethod(e.target.value)}
            >
              {PAYMENT_METHODS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Reference number"
            htmlFor="pay-ref"
            hint="The transaction reference from your bank or telebirr."
          >
            <Input
              id="pay-ref"
              value={payRef}
              onChange={(e) => setPayRef(e.target.value)}
              placeholder="CBE-1234567"
            />
          </Field>
        </div>
      </Modal>
    </AppShellFrame>
  );
}

// A listing is visible to any authenticated role: a wholesaler reads farmer
// listings, a retailer reads wholesaler listings, and admins review both.
const ANY_ROLE: UserRole[] = [
  "FARMER",
  "WHOLESALER",
  "RETAILER",
  "USER_ADMIN",
  "FINANCIAL_MANAGER",
  "SUPER_ADMIN",
];

export function AppShellFrame({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <AppShell title={title} allow={ANY_ROLE}>
      <div className="mx-auto max-w-6xl">{children}</div>
    </AppShell>
  );
}
