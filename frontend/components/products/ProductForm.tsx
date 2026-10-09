"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Camera, ImagePlus, Loader2, X } from "lucide-react";
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

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_IMAGE_DIMENSION = 1600;
const MAX_PRODUCT_IMAGES = 8;
const ACCEPTED_IMAGE_TYPES = new Set([
  "image/jpeg",
  "image/jpg",
  "image/png",
  "image/webp",
]);

async function prepareProductImage(file: File): Promise<File> {
  const extension = file.name.split(".").pop()?.toLowerCase();
  const acceptedExtension = ["jpg", "jpeg", "png", "webp"].includes(
    extension ?? ""
  );
  if (
    (file.type && !ACCEPTED_IMAGE_TYPES.has(file.type)) ||
    (!file.type && !acceptedExtension)
  ) {
    throw new Error("Choose a JPG, PNG, or WebP image.");
  }

  const objectUrl = URL.createObjectURL(file);
  const image = new Image();
  try {
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("The selected file is not a valid image."));
      image.src = objectUrl;
    });
  } finally {
    URL.revokeObjectURL(objectUrl);
  }

  if (!image.naturalWidth || !image.naturalHeight) {
    throw new Error("The selected file is not a valid image.");
  }

  if (
    file.size <= MAX_IMAGE_BYTES &&
    Math.max(image.naturalWidth, image.naturalHeight) <= MAX_IMAGE_DIMENSION
  ) {
    return file;
  }

  const scale = Math.min(
    1,
    MAX_IMAGE_DIMENSION / Math.max(image.naturalWidth, image.naturalHeight)
  );
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(image.naturalWidth * scale);
  canvas.height = Math.round(image.naturalHeight * scale);
  const context = canvas.getContext("2d");
  if (!context) throw new Error("This browser could not process the image.");
  context.drawImage(image, 0, 0, canvas.width, canvas.height);

  let compressed: Blob | null = null;
  for (const quality of [0.84, 0.7, 0.56]) {
    compressed = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/webp", quality)
    );
    if (!compressed || compressed.size <= MAX_IMAGE_BYTES) break;
  }
  if (!compressed || compressed.size > MAX_IMAGE_BYTES) {
    for (const quality of [0.78, 0.62, 0.5]) {
      compressed = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob(resolve, "image/jpeg", quality)
      );
      if (!compressed || compressed.size <= MAX_IMAGE_BYTES) break;
    }
  }
  if (!compressed || compressed.size > MAX_IMAGE_BYTES) {
    throw new Error("This image is too large to upload. Choose a smaller image.");
  }

  const outputType = compressed.type || "image/jpeg";
  const outputExtension = outputType === "image/webp" ? "webp" : "jpg";
  const baseName = file.name.replace(/\.[^.]+$/, "") || "product-image";
  return new File([compressed], `${baseName}.${outputExtension}`, {
    type: outputType,
  });
}

type ProductImageDraft = {
  key: string;
  url?: string;
  file?: File;
};

function imageDraftKey() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

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
  const [imageDrafts, setImageDrafts] = useState<ProductImageDraft[]>(() =>
    (product?.images ?? []).map((url) => ({ key: imageDraftKey(), url }))
  );
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [cameraReady, setCameraReady] = useState(false);
  const [createdProduct, setCreatedProduct] = useState<Product | null>(null);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const videoRef = useRef<HTMLVideoElement>(null);

  const base = kind === "farmer" ? "/farmer" : "/wholesaler";

  useEffect(() => {
    const urls = Object.fromEntries(
      imageDrafts
        .filter((image): image is ProductImageDraft & { file: File } =>
          Boolean(image.file)
        )
        .map((image) => [image.key, URL.createObjectURL(image.file)])
    );
    setPreviewUrls(urls);
    return () => Object.values(urls).forEach((url) => URL.revokeObjectURL(url));
  }, [imageDrafts]);

  useEffect(() => {
    if (!cameraOpen) return;

    let active = true;
    let stream: MediaStream | null = null;
    setCameraError("");
    setCameraReady(false);

    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Camera access is unavailable in this browser. Upload an image instead.");
      return () => undefined;
    }

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false })
      .then((cameraStream) => {
        if (!active) {
          cameraStream.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = cameraStream;
        if (videoRef.current) videoRef.current.srcObject = cameraStream;
      })
      .catch(() => {
        if (active) {
          setCameraError(
            "Camera could not be opened. Check camera permission or upload an image instead."
          );
        }
      });

    return () => {
      active = false;
      stream?.getTracks().forEach((track) => track.stop());
      if (videoRef.current) videoRef.current.srcObject = null;
    };
  }, [cameraOpen]);

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

  async function chooseImages(files: File[], replaceKey?: string) {
    setError("");
    try {
      const prepared = await Promise.all(files.map(prepareProductImage));
      if (replaceKey) {
        const replacement = prepared[0];
        if (!replacement) return;
        setImageDrafts((current) =>
          current.map((image) =>
            image.key === replaceKey
              ? { key: image.key, file: replacement }
              : image
          )
        );
        return;
      }
      if (imageDrafts.length + prepared.length > MAX_PRODUCT_IMAGES) {
        setError(`A product can have at most ${MAX_PRODUCT_IMAGES} images.`);
        return;
      }
      setImageDrafts((current) => [
        ...current,
        ...prepared.map((file) => ({ key: imageDraftKey(), file })),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not use this image.");
    }
  }

  function removeImage(key: string) {
    setImageDrafts((current) => current.filter((image) => image.key !== key));
  }

  async function capturePhoto() {
    const video = videoRef.current;
    if (!video?.videoWidth || !video.videoHeight) {
      setCameraError("The camera is not ready yet. Please wait or upload an image.");
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) {
      setCameraError("This browser could not capture the photo.");
      return;
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const photo = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.9)
    );
    if (!photo) {
      setCameraError("The photo could not be captured. Please try again.");
      return;
    }
    const file = new File([photo], "product-photo.jpg", { type: "image/jpeg" });
    await chooseImages([file]);
    setCameraOpen(false);
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
      let target: Product;
      if (createdProduct) {
        if (kind === "farmer") {
          await productsApi.updateFarmerListing(createdProduct.id, payload);
        } else {
          await productsApi.updateWholesalerListing(createdProduct.id, payload);
        }
        target = createdProduct;
      } else if (isEdit && product) {
        if (kind === "farmer") {
          await productsApi.updateFarmerListing(product.id, payload);
        } else {
          await productsApi.updateWholesalerListing(product.id, payload);
        }
        target = product;
      } else if (kind === "farmer") {
        target = await productsApi.createFarmerListing(payload);
        setCreatedProduct(target);
      } else {
        target = await productsApi.createWholesalerListing(payload);
        setCreatedProduct(target);
      }

      const isPersistedListing = Boolean(product || createdProduct);
      const keptImages = imageDrafts
        .filter((image) => image.url && !image.file)
        .map((image) => image.url!);
      if (isPersistedListing || keptImages.length > 0) {
        const response =
          kind === "farmer"
            ? await productsApi.replaceFarmerListingImages(target.id, keptImages)
            : await productsApi.replaceWholesalerListingImages(target.id, keptImages);
        target = response.product;
      }

      let currentDrafts = imageDrafts;
      const pendingEntries = currentDrafts.filter((image) => image.file);
      for (const pending of pendingEntries) {
        setUploading(true);
        try {
          const response =
            kind === "farmer"
              ? await productsApi.uploadFarmerListingImage(target.id, pending.file!)
              : await productsApi.uploadWholesalerListingImage(target.id, pending.file!);
          const uploadedUrl = response.product.images.at(-1);
          if (!uploadedUrl) throw new Error("The upload response did not include the saved image.");
          currentDrafts = currentDrafts.map((image) =>
            image.key === pending.key
              ? { key: image.key, url: uploadedUrl }
              : image
          );
          setImageDrafts(currentDrafts);
        } catch (err) {
          setError(
            `Listing saved, but an image could not be uploaded. ${
              err instanceof Error ? err.message : "Please try again."
            }`
          );
          return;
        } finally {
          setUploading(false);
        }
      }

      const finalImages = currentDrafts
        .map((image) => image.url)
        .filter((url): url is string => Boolean(url));
      if (finalImages.length) {
        const response =
          kind === "farmer"
            ? await productsApi.replaceFarmerListingImages(target.id, finalImages)
            : await productsApi.replaceWholesalerListingImages(target.id, finalImages);
        target = response.product;
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
        <p className="mb-2 text-sm font-medium text-gray-700">
          Product images ({imageDrafts.length}/{MAX_PRODUCT_IMAGES})
        </p>
        {imageDrafts.length > 0 && (
          <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {imageDrafts.map((image, index) => {
              const src = image.file
                ? previewUrls[image.key]
                : mediaUrl(image.url);
              return (
                <div key={image.key} className="space-y-1.5">
                  <div className="relative aspect-square overflow-hidden rounded-lg border border-gray-200 bg-gray-50">
                    {src && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={src}
                        alt={`Product image ${index + 1}`}
                        className="h-full w-full object-cover"
                      />
                    )}
                    <span className="absolute bottom-1 left-1 rounded bg-gray-900/70 px-1.5 py-0.5 text-xs text-white">
                      {index === 0 ? "Primary" : index + 1}
                    </span>
                    <button
                      type="button"
                      aria-label={`Remove image ${index + 1}`}
                      disabled={busy || uploading}
                      onClick={() => removeImage(image.key)}
                      className="absolute right-1 top-1 rounded-full bg-gray-900/70 p-1 text-white hover:bg-gray-900"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <label className="inline-flex h-8 cursor-pointer items-center gap-1 rounded-lg border border-gray-200 px-2 text-xs font-medium text-gray-700 hover:bg-gray-50">
                    <ImagePlus className="h-3.5 w-3.5" />
                    Replace
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
                      className="hidden"
                      disabled={busy || uploading}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) void chooseImages([file], image.key);
                        e.target.value = "";
                      }}
                    />
                  </label>
                </div>
              );
            })}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          {imageDrafts.length < MAX_PRODUCT_IMAGES && (
            <>
              <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-lg border border-gray-200 px-3 text-sm font-medium text-gray-700 hover:bg-gray-50">
                {uploading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ImagePlus className="h-4 w-4" />
                )}
                {uploading
                  ? "Uploading…"
                  : imageDrafts.length
                    ? "Add Image"
                    : "Upload Image"}
                <input
                  type="file"
                  multiple
                  accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
                  className="hidden"
                  disabled={busy || uploading}
                  onChange={(e) => {
                    const files = Array.from(e.target.files ?? []);
                    if (files.length) void chooseImages(files);
                    e.target.value = "";
                  }}
                />
              </label>
              <Button
                type="button"
                variant="secondary"
                disabled={busy || uploading}
                onClick={() => {
                  setError("");
                  setCameraOpen(true);
                }}
                icon={<Camera className="h-4 w-4" />}
              >
                Take Photo
              </Button>
            </>
          )}
        </div>
        <p className="mt-2 text-xs text-gray-500">
          {imageDrafts.length === MAX_PRODUCT_IMAGES
            ? "You have reached the 8-image limit."
            : "JPG, PNG, or WebP. Large images are resized before upload."}
        </p>
        {cameraOpen && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
            role="dialog"
            aria-modal="true"
            aria-label="Take product photo"
          >
            <div className="w-full max-w-lg rounded-xl bg-white p-4 shadow-xl">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-base font-semibold text-gray-900">Take a product photo</h3>
                <button
                  type="button"
                  aria-label="Close camera"
                  onClick={() => setCameraOpen(false)}
                  className="rounded-lg p-1 text-gray-500 hover:bg-gray-100"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              {cameraError ? (
                <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{cameraError}</p>
              ) : (
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  onLoadedMetadata={() => setCameraReady(true)}
                  className="max-h-[60vh] w-full rounded-lg bg-black object-contain"
                />
              )}
              <div className="mt-3 flex justify-end gap-2">
                <Button type="button" variant="secondary" onClick={() => setCameraOpen(false)}>
                  Cancel
                </Button>
                <Button
                  type="button"
                  disabled={!cameraReady || Boolean(cameraError)}
                  onClick={() => void capturePhoto()}
                  icon={<Camera className="h-4 w-4" />}
                >
                  Capture Photo
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="flex gap-2 border-t border-gray-100 pt-4">
        <Button type="submit" loading={busy}>
          {createdProduct && imageDrafts.some((image) => image.file)
            ? "Retry image uploads"
            : isEdit
              ? "Save changes"
              : "Publish listing"}
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
