"use client";

import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Button,
  Card,
  CardHeader,
  ErrorBanner,
  Field,
  Input,
  PageLoader,
  Select,
  Textarea,
} from "@/components/ui";
import { superAdminApi } from "@/lib/api/client";
import type {
  ManagedAdministrativeLocation,
  ManagedRegistrationProductType,
  ProductCategory,
} from "@/lib/types";

const LOCATION_LEVELS = [
  ["REGION", "Region"],
  ["ZONE", "Zone"],
  ["WOREDA", "Woreda"],
  ["KEBELE", "Kebele"],
  ["CITY", "City"],
  ["SUBCITY", "Sub-city"],
  ["DISTRICT", "District"],
  ["OTHER", "Other administrative area"],
];

const PRODUCT_CATEGORIES: { value: ProductCategory; label: string }[] = [
  { value: "Vegetables", label: "Vegetables" },
  { value: "Root Crops", label: "Root crops (displayed under Vegetables)" },
  { value: "Fruits", label: "Fruits" },
];

export default function SuperAdminReferenceDataPage() {
  const [locations, setLocations] = useState<ManagedAdministrativeLocation[]>([]);
  const [products, setProducts] = useState<ManagedRegistrationProductType[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [locationId, setLocationId] = useState("");
  const [locationName, setLocationName] = useState("");
  const [locationLevel, setLocationLevel] = useState("REGION");
  const [locationParent, setLocationParent] = useState("");
  const [locationAliases, setLocationAliases] = useState("");

  const [productId, setProductId] = useState("");
  const [productName, setProductName] = useState("");
  const [productCategory, setProductCategory] =
    useState<ProductCategory>("Vegetables");

  const load = useCallback(async () => {
    setError("");
    try {
      const [locationRows, productRows] = await Promise.all([
        superAdminApi.managedLocations(),
        superAdminApi.managedProductTypes(),
      ]);
      setLocations(locationRows);
      setProducts(productRows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load reference data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function editLocation(location: ManagedAdministrativeLocation) {
    setLocationId(location.id);
    setLocationName(location.name);
    setLocationLevel(location.level);
    setLocationParent(location.parent || "");
    setLocationAliases(location.alternative_names.join(", "));
    setError("");
    setNotice("");
  }

  function resetLocation() {
    setLocationId("");
    setLocationName("");
    setLocationLevel("REGION");
    setLocationParent("");
    setLocationAliases("");
  }

  async function saveLocation(event: React.FormEvent) {
    event.preventDefault();
    if (!locationName.trim()) {
      setError("Enter a location name.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payload = {
        source_id:
          locations.find((location) => location.id === locationId)?.source_id ||
          `admin-${crypto.randomUUID()}`,
        name: locationName.trim(),
        level: locationLevel,
        parent: locationParent || null,
        alternative_names: locationAliases
          .split(",")
          .map((name) => name.trim())
          .filter(Boolean),
      };
      if (locationId) {
        await superAdminApi.updateLocation(locationId, payload);
        setNotice("Location updated.");
      } else {
        await superAdminApi.createLocation(payload);
        setNotice("Location added.");
      }
      resetLocation();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save this location.");
    } finally {
      setSaving(false);
    }
  }

  async function deactivateLocation(location: ManagedAdministrativeLocation) {
    if (!window.confirm(`Deactivate ${location.name}? Existing records will be preserved.`)) {
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await superAdminApi.deactivateLocation(location.id);
      setNotice(`${location.name} deactivated.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not deactivate this location.");
    } finally {
      setSaving(false);
    }
  }

  function editProduct(product: ManagedRegistrationProductType) {
    setProductId(product.id);
    setProductName(product.name);
    setProductCategory(product.category);
    setError("");
    setNotice("");
  }

  function resetProduct() {
    setProductId("");
    setProductName("");
    setProductCategory("Vegetables");
  }

  async function saveProduct(event: React.FormEvent) {
    event.preventDefault();
    const name = productName.trim();
    if (!name) {
      setError("Enter a product name.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      if (productId) {
        await superAdminApi.updateProductType(productId, {
          name,
          category: productCategory,
          active: true,
        });
        setNotice("Registration product option updated.");
      } else {
        const code = `${productCategory}-${name}`
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/(^-|-$)/g, "");
        await superAdminApi.createProductType({
          code,
          name,
          category: productCategory,
        });
        setNotice("Registration product option added.");
      }
      resetProduct();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save this product option.");
    } finally {
      setSaving(false);
    }
  }

  async function deactivateProduct(product: ManagedRegistrationProductType) {
    if (!window.confirm(`Deactivate ${product.name}? Existing registrations are preserved.`)) {
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await superAdminApi.deactivateProductType(product.id);
      setNotice(`${product.name} deactivated.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not deactivate this product option.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <AppShell title="Registration Reference Data" allow={["SUPER_ADMIN"]}>
        <PageLoader />
      </AppShell>
    );
  }

  return (
    <AppShell title="Registration Reference Data" allow={["SUPER_ADMIN"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Registration and Profile Reference Data</h2>
        <p className="mt-1 text-sm text-gray-500">
          Manage location records and agricultural product-interest options used by registration.
          Deactivation preserves existing registrations and audit history.
        </p>
      </div>
      {error && (
        <div className="mb-4">
          <ErrorBanner message={error} onRetry={() => void load()} />
        </div>
      )}
      {notice && (
        <p role="status" className="mb-4 rounded-lg bg-green-50 p-3 text-sm text-green-800">
          {notice}
        </p>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Administrative locations"
            subtitle="Create linked Region, Zone, Woreda, Kebele, City, Sub-city or District records."
          />
          <form onSubmit={(event) => void saveLocation(event)} className="space-y-4 p-5">
            <Field label="Location name" htmlFor="location-name">
              <Input
                id="location-name"
                maxLength={200}
                value={locationName}
                onChange={(event) => setLocationName(event.target.value)}
                placeholder="Enter a location name"
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Administrative level" htmlFor="location-level">
                <Select
                  id="location-level"
                  value={locationLevel}
                  onChange={(event) => setLocationLevel(event.target.value)}
                >
                  {LOCATION_LEVELS.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Parent location" htmlFor="location-parent">
                <Select
                  id="location-parent"
                  value={locationParent}
                  onChange={(event) => setLocationParent(event.target.value)}
                >
                  <option value="">No parent (top-level record)</option>
                  {locations
                    .filter((location) => location.active && location.id !== locationId)
                    .map((location) => (
                      <option key={location.id} value={location.id}>
                        {location.name} · {location.level}
                      </option>
                    ))}
                </Select>
              </Field>
            </div>
            <Field
              label="Alternative names"
              htmlFor="location-aliases"
              hint="Optional aliases separated by commas."
            >
              <Textarea
                id="location-aliases"
                value={locationAliases}
                onChange={(event) => setLocationAliases(event.target.value)}
              />
            </Field>
            <div className="flex gap-2">
              <Button type="submit" loading={saving}>
                {locationId ? "Save location" : "Add location"}
              </Button>
              {locationId && (
                <Button type="button" variant="secondary" onClick={resetLocation}>
                  Cancel edit
                </Button>
              )}
            </div>
          </form>
          <ul className="max-h-[32rem] divide-y divide-gray-100 overflow-y-auto border-t border-gray-100">
            {locations.map((location) => (
              <li key={location.id} className="flex items-center justify-between gap-3 px-5 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-gray-900">
                    {location.name} <span className="font-normal text-gray-500">· {location.level}</span>
                  </p>
                  <p className="truncate text-xs text-gray-500">
                    {location.parent_name || "Top-level"} · {location.active ? "Active" : "Inactive"}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button type="button" variant="secondary" onClick={() => editLocation(location)}>
                    Edit
                  </Button>
                  {location.active && (
                    <Button
                      type="button"
                      variant="danger"
                      disabled={saving}
                      onClick={() => void deactivateLocation(location)}
                    >
                      Deactivate
                    </Button>
                  )}
                </div>
              </li>
            ))}
            {!locations.length && (
              <li className="px-5 py-6 text-center text-sm text-gray-500">
                No administrative location records are configured.
              </li>
            )}
          </ul>
        </Card>

        <Card>
          <CardHeader
            title="Registration product interests"
            subtitle="Only Vegetables and Fruits are top-level choices in registration. Root crops are grouped under Vegetables."
          />
          <form onSubmit={(event) => void saveProduct(event)} className="space-y-4 p-5">
            <Field label="Product display name" htmlFor="interest-product-name">
              <Input
                id="interest-product-name"
                maxLength={200}
                value={productName}
                onChange={(event) => setProductName(event.target.value)}
                placeholder="e.g. Tomato"
              />
            </Field>
            <Field label="Registration category" htmlFor="interest-product-category">
              <Select
                id="interest-product-category"
                value={productCategory}
                onChange={(event) =>
                  setProductCategory(event.target.value as ProductCategory)
                }
              >
                {PRODUCT_CATEGORIES.map(({ value, label }) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </Select>
            </Field>
            <div className="flex gap-2">
              <Button type="submit" loading={saving}>
                {productId ? "Save product option" : "Add product option"}
              </Button>
              {productId && (
                <Button type="button" variant="secondary" onClick={resetProduct}>
                  Cancel edit
                </Button>
              )}
            </div>
          </form>
          <ul className="max-h-[32rem] divide-y divide-gray-100 overflow-y-auto border-t border-gray-100">
            {products.map((product) => (
              <li key={product.id} className="flex items-center justify-between gap-3 px-5 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-gray-900">{product.name}</p>
                  <p className="text-xs text-gray-500">
                    {product.category_display} · {product.active ? "Active" : "Inactive"}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button type="button" variant="secondary" onClick={() => editProduct(product)}>
                    Edit
                  </Button>
                  {product.active && (
                    <Button
                      type="button"
                      variant="danger"
                      disabled={saving}
                      onClick={() => void deactivateProduct(product)}
                    >
                      Deactivate
                    </Button>
                  )}
                </div>
              </li>
            ))}
            {!products.length && (
              <li className="px-5 py-6 text-center text-sm text-gray-500">
                No registration product options are configured.
              </li>
            )}
          </ul>
        </Card>
      </div>
    </AppShell>
  );
}
