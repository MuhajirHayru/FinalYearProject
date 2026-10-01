"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ImagePlus, Loader2, X } from "lucide-react";
import { productsApi } from "@/lib/api/client";
import {
  Button,
  ErrorBanner,
  Field,
  Input,
  Select,
  SuccessBanner,
  Textarea,
} from "@/components/ui";
import { mediaUrl } from "@/lib/format";
import type {
  CategoryUnitMeta,
  Product,
  ProductCategory,
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

/**
 * Create/edit form shared by the farmer and wholesaler listing screens.
 * `kind` selects which endpoint family is used.
 */
export function ProductForm({
  kind,
  product,
}: {
  kind: "farmer" | "wholesaler";
  product?: Product;
}) {
  const router = useRouter();
  const isEdit = Boolean(product);

  const [meta, setMeta] = useState<CategoryUnitMeta | null>(null);
  const [title, setTitle] = useState(product?.title ?? "");
  const [description, setDescription] = useState(product?.description ?? "");
  const [category, setCategory] = useState<ProductCategory | "">(
    product?.category ?? ""
  );
  const [unit, setUnit] = useState<UnitOfMeasure | "">(
    product?.unit_of_measure ?? ""
  );
  const [quantity, setQuantity] = useState(product?.quantity ?? "");
  const [price, setPrice] = useState(product?.price_per_unit ?? "");
  const [images, setImages] = useState<string[]>(product?.images ?? []);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const base = kind === "farmer" ? "/farmer" : "/wholesaler";

  useEffect(() => {
    productsApi
      .meta()
      .then(setMeta)
      .catch(() => undefined);
  }, []);

  const categories = useMemo(
    () =>
      meta?.categories.map((c) => c.value as ProductCategory) ??
      FALLBACK_CATEGORIES,
    [meta]
  );
  const units = useMemo(
    () => meta?.units.map((u) => u.value as UnitOfMeasure) ?? FALLBACK_UNITS,
    [meta]
  );

  const totalValue = useMemo(() => {
    const q = Number(quantity);
    const p = Number(price);
    if (Number.isNaN(q) || Number.isNaN(p) || q <= 0 || p <= 0) return null;
    return (q * p).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }, [quantity, price]);

  function validate() {
    const errs: Record<string, string> = {};
    if (!title.trim()) errs.title = "Title is required.";
    if (!description.trim()) errs.description = "Description is required.";
    if (!category) errs.category = "Choose a category.";
    if (!unit) errs.unit_of_measure = "Choose a unit.";
    if (!(Number(quantity) > 0)) errs.quantity = "Quantity must be greater than 0.";
    if (!(Number(price) > 0)) errs.price_per_unit = "Price must be greater than 0.";
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function upload(file: File) {
    if (!product) return;
    setUploading(true);
    setError("");
    try {
      const res =
        kind === "farmer"
          ? await productsApi.uploadFarmerListingImage(product.id, file)
          : await productsApi.uploadWholesalerListingImage(product.id, file);
      setImages(res.product.images ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Image upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!validate()) return;

    const payload = {
      title: title.trim(),
      description: description.trim(),
      category: category as ProductCategory,
      quantity,
      unit_of_measure: unit as UnitOfMeasure,
      price_per_unit: price,
    };

    setBusy(true);
    try {
      if (isEdit && product) {
        if (kind === "farmer") {
          await productsApi.updateFarmerListing(product.id, payload);
        } else {
          await productsApi.updateWholesalerListing(product.id, payload);
        }
      } else if (kind === "farmer") {
        await productsApi.createFarmerListing(payload);
      } else {
        await productsApi.createWholesalerListing(payload);
      }
      router.push(`${base}/listings`);
      router.refresh();
    } catch (err) {
      if (err && typeof err === "object" && "payload" in err) {
        const payloadErr = (err as { payload: { error?: unknown } }).payload
          ?.error;
        if (payloadErr && typeof payloadErr === "object") {
          setFieldErrors(
            Object.fromEntries(
              Object.entries(payloadErr as Record<string, string[]>).map(
                ([k, v]) => [k, v.join(" ")]
              )
            )
          );
          setError("Please correct the highlighted fields.");
        } else {
          setError(err instanceof Error ? err.message : "Save failed.");
        }
      } else {
        setError(err instanceof Error ? err.message : "Save failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="max-w-3xl space-y-5">
      {error && <ErrorBanner message={error} />}
      {isEdit && !error && (
        <SuccessBanner message="Save your changes to update this listing." />
      )}

      <Field label="Product title" htmlFor="title" error={fieldErrors.title}>
        <Input
          id="title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Fresh Red Onion"
        />
      </Field>

      <Field
        label="Description"
        htmlFor="description"
        error={fieldErrors.description}
        hint="Grade, harvest date, packing details — anything a buyer would ask."
      >
        <Textarea
          id="description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Grade A, harvested this week, packed in 50 kg sacks."
        />
      </Field>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Category" htmlFor="category" error={fieldErrors.category}>
          <Select
            id="category"
            value={category}
            onChange={(e) => setCategory(e.target.value as ProductCategory)}
          >
            <option value="">Select a category</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Unit of measure"
          htmlFor="unit"
          error={fieldErrors.unit_of_measure}
        >
          <Select
            id="unit"
            value={unit}
            onChange={(e) => setUnit(e.target.value as UnitOfMeasure)}
          >
            <option value="">Select a unit</option>
            {units.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Quantity available"
          htmlFor="quantity"
          error={fieldErrors.quantity}
        >
          <Input
            id="quantity"
            type="number"
            step="0.01"
            min="0"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            placeholder="200"
          />
        </Field>

        <Field
          label="Price per unit (ETB)"
          htmlFor="price"
          error={fieldErrors.price_per_unit}
        >
          <Input
            id="price"
            type="number"
            step="0.01"
            min="0"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="25.00"
          />
        </Field>
      </div>

      {totalValue && (
        <p className="rounded-lg bg-green-50 px-4 py-2.5 text-sm text-green-800">
          Total listing value:{" "}
          <span className="font-semibold">{totalValue} ETB</span>
        </p>
      )}

      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <p className="mb-2 text-sm font-medium text-gray-700">Images</p>
        {images.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2">
            {images.map((src) => (
              <div
                key={src}
                className="relative h-20 w-20 overflow-hidden rounded-lg border border-gray-200"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={mediaUrl(src)}
                  alt=""
                  className="h-full w-full object-cover"
                />
                <button
                  type="button"
                  aria-label="Remove image"
                  onClick={() =>
                    setImages((prev) => prev.filter((s) => s !== src))
                  }
                  className="absolute right-0.5 top-0.5 rounded-full bg-gray-900/70 p-0.5 text-white"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}
        {isEdit ? (
          <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50">
            {uploading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ImagePlus className="h-4 w-4" />
            )}
            {uploading ? "Uploading…" : "Upload image"}
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void upload(file);
                e.target.value = "";
              }}
            />
          </label>
        ) : (
          <p className="text-xs text-gray-500">
            Save the listing first, then upload up to 8 images.
          </p>
        )}
      </div>

      <div className="flex gap-2 border-t border-gray-100 pt-4">
        <Button type="submit" loading={busy}>
          {isEdit ? "Save changes" : "Publish listing"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => router.push(`${base}/listings`)}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
