"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle2, ChevronLeft, ChevronRight, FileUp, Leaf } from "lucide-react";
import {
  registrationApi,
  setRegistrationCompletionToken,
} from "@/lib/api/client";
import {
  Button,
  ErrorBanner,
  Field,
  Input,
  PageLoader,
  Select,
  Textarea,
} from "@/components/ui";
import type {
  RegistrationDetails,
  RegistrationLocation,
  RegistrationProductType,
  UserRole,
} from "@/lib/types";

const STEPS = ["Your details", "Location", "Products", "Documents", "Review"];
const ROLE_INTENTS: Record<UserRole, string[]> = {
  FARMER: ["PRODUCES"],
  WHOLESALER: ["BUYS", "SELLS", "HANDLES"],
  RETAILER: ["BUYS"],
  USER_ADMIN: [],
  FINANCIAL_MANAGER: [],
  SUPER_ADMIN: [],
};

type DraftForm = {
  full_name: string;
  phone: string;
  date_of_birth: string;
  sex: string;
  business_name: string;
  business_address: string;
  location: string;
};

export default function CompleteRegistrationPage() {
  const router = useRouter();
  const [registration, setRegistration] = useState<RegistrationDetails | null>(null);
  const [form, setForm] = useState<DraftForm | null>(null);
  const [productTypes, setProductTypes] = useState<RegistrationProductType[]>([]);
  const [locationLevels, setLocationLevels] = useState<RegistrationLocation[][]>([]);
  const [locationIds, setLocationIds] = useState<string[]>([]);
  const [locationSearch, setLocationSearch] = useState<Record<number, string>>({});
  const [loadingLocationIndex, setLoadingLocationIndex] = useState<number | null>(null);
  const [selections, setSelections] = useState<Record<string, string>>({});
  const [productSearch, setProductSearch] = useState("");
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [complete, setComplete] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const locationRequestId = useRef(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([registrationApi.getDraft(), registrationApi.productTypes(), registrationApi.locations()])
      .then(async ([draft, products, roots]) => {
        if (cancelled) return;
        setRegistration(draft);
        setProductTypes(products);
        setForm({
          full_name: draft.full_name,
          phone: draft.phone,
          date_of_birth: draft.date_of_birth || "",
          sex: draft.sex,
          business_name: draft.business_name,
          business_address: draft.business_address,
          location: draft.location || "",
        });
        setSelections(
          Object.fromEntries(draft.product_selections.map((item) => [item.id, item.intent]))
        );

        const pathIds = draft.location_id_path || [];
        const levels = [roots];
        const selectedIds: string[] = [];
        let parent = "";
        for (const locationId of pathIds) {
          const choices = levels[levels.length - 1];
          const selected = choices.find((item) => item.id === locationId);
          if (!selected) break;
          selectedIds.push(selected.id);
          if (selected.has_children) {
            const children = await registrationApi.locations(selected.id);
            levels.push(children);
            parent = selected.id;
          }
        }
        if (draft.location && !selectedIds.includes(draft.location) && parent) {
          const choices = levels[levels.length - 1];
          if (choices.some((item) => item.id === draft.location)) {
            selectedIds.push(draft.location);
          }
        }
        setLocationLevels(levels);
        setLocationIds(selectedIds);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load your registration.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!complete) return;
    const timeout = window.setTimeout(
      () => router.replace("/login?registered=true"),
      4000
    );
    return () => window.clearTimeout(timeout);
  }, [complete, router]);

  const role = registration?.role || "FARMER";
  const intents = ROLE_INTENTS[role];
  const latestLocationId = locationIds[locationIds.length - 1] || "";
  const filteredProductTypes = useMemo(
    () => productTypes.filter((product) => product.name.toLowerCase().includes(productSearch.toLowerCase().trim())),
    [productSearch, productTypes]
  );
  const availableCategories = useMemo(
    () => Array.from(new Set(filteredProductTypes.map((item) => item.category))),
    [filteredProductTypes]
  );

  function update<K extends keyof DraftForm>(key: K, value: DraftForm[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
  }

  async function chooseLocation(index: number, location: RegistrationLocation | null) {
    const requestId = ++locationRequestId.current;
    const nextIds = locationIds.slice(0, index);
    const nextLevels = locationLevels.slice(0, index + 1);
    if (location) {
      nextIds[index] = location.id;
    }
    setLocationIds(nextIds);
    setLocationLevels(nextLevels);
    setLocationSearch((current) => {
      const next = { ...current };
      for (const key of Object.keys(next)) {
        if (Number(key) >= index) delete next[Number(key)];
      }
      return next;
    });
    update("location", location?.id || "");
    setError("");
    if (location?.has_children) {
      setLoadingLocationIndex(index);
      try {
        const children = await registrationApi.locations(location.id);
        if (requestId !== locationRequestId.current) return;
        setLocationLevels((current) => {
          return [...current.slice(0, index + 1), children];
        });
      } catch (err) {
        if (requestId !== locationRequestId.current) return;
        setError(err instanceof Error ? err.message : "Could not load child locations.");
      } finally {
        if (requestId === locationRequestId.current) setLoadingLocationIndex(null);
      }
    }
  }

  const saveDraft = useCallback(async (announce = true) => {
    if (!form) return;
    setSaving(true);
    if (announce) {
      setError("");
      setNotice("");
    }
    try {
      const saved = await registrationApi.saveDraft({
        date_of_birth: form.date_of_birth || null,
        sex: form.sex,
        business_name: form.business_name.trim(),
        business_address: form.business_address.trim(),
        location: latestLocationId || null,
        product_selections: Object.entries(selections).map(([product_type, intent]) => ({
          product_type,
          intent,
        })),
      });
      setRegistration(saved);
      if (announce) setNotice("Draft saved securely.");
      return saved;
    } catch (err) {
      if (announce) setError(err instanceof Error ? err.message : "Could not save your draft.");
      return null;
    } finally {
      setSaving(false);
    }
  }, [form, latestLocationId, selections]);

  useEffect(() => {
    if (!registration || !form || registration.status === "SUBMITTED" || registration.status === "APPROVED") {
      return;
    }
    const timer = window.setTimeout(() => {
      void saveDraft(false);
    }, 900);
    return () => window.clearTimeout(timer);
  }, [form, locationIds, registration, saveDraft, selections]);

  async function uploadDocument(file?: File) {
    if (!file) return;
    setError("");
    try {
      await registrationApi.uploadDocument(file);
      const updated = await registrationApi.getDraft();
      setRegistration(updated);
      setNotice("Document uploaded to private storage.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not upload the document.");
    }
  }

  async function removeDocument(id: string) {
    setError("");
    try {
      await registrationApi.deleteDocument(id);
      setRegistration(await registrationApi.getDraft());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the document.");
    }
  }

  async function submitRegistration() {
    const saved = await saveDraft();
    if (!saved) return;
    try {
      const result = await registrationApi.submit();
      setRegistration({ ...saved, status: result.status as RegistrationDetails["status"] });
      setRegistrationCompletionToken(null);
      setComplete(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit registration.");
    }
  }

  if (loading) return <PageLoader label="Loading your saved registration..." />;
  if (!form || !registration) {
    return (
      <main className="mx-auto max-w-xl space-y-4 p-6">
        {error && <ErrorBanner message={error} />}
        <p className="text-sm text-gray-600">
          Start a new registration or resume an incomplete application with your email and password.
        </p>
        <Link className="font-medium text-green-700 underline" href="/registration/resume">
          Resume registration
        </Link>
      </main>
    );
  }

  if (complete) {
    return (
      <main className="mx-auto max-w-xl space-y-5 p-6 text-center">
        <CheckCircle2 className="mx-auto h-12 w-12 text-green-600" />
        <h1 className="text-2xl font-bold text-gray-900">Registration submitted</h1>
        <p className="text-sm text-gray-600">
          Your complete profile and license documents are awaiting admin review. You will be redirected to sign in shortly; marketplace access remains restricted until approval.
        </p>
        <Button onClick={() => router.replace("/login?registered=true")}>Continue to sign in</Button>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50 px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-3xl">
        <Link href="/" className="mb-6 inline-flex items-center gap-2 font-semibold text-green-800">
          <Leaf className="h-6 w-6" /> Green Path
        </Link>
        <h1 className="mt-4 text-2xl font-bold text-gray-900">Complete your registration</h1>
        <p className="mt-1 text-sm text-gray-600">
          Complete your {role.toLowerCase()} profile. Your work is saved only to your pending application.
        </p>

        <ol className="my-6 grid grid-cols-5 gap-2" aria-label="Registration steps">
          {STEPS.map((label, index) => (
            <li key={label}>
              <button
                type="button"
                onClick={() => setStep(index)}
                className={`w-full border-t-2 pt-2 text-left text-xs ${
                  step === index ? "border-green-600 font-semibold text-green-800" : "border-gray-200 text-gray-500"
                }`}
              >
                {index + 1}. {label}
              </button>
            </li>
          ))}
        </ol>
        {error && <div className="mb-4"><ErrorBanner message={error} /></div>}
        {notice && <p role="status" className="mb-4 rounded bg-green-50 p-3 text-sm text-green-800">{notice}</p>}

        <section className="space-y-5 rounded-xl border border-gray-200 bg-white p-5 shadow-sm sm:p-7">
          {step === 0 && (
            <>
              <h2 className="text-lg font-semibold">Personal and business information</h2>
              <div className="grid gap-5 sm:grid-cols-2">
                <div>
                  <p className="text-sm font-medium text-gray-700">Full name</p>
                  <p className="mt-1 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
                    {registration.full_name}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-700">Email address</p>
                  <p className="mt-1 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
                    {registration.email}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-700">Phone</p>
                  <p className="mt-1 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
                    {registration.phone || "Not provided"}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-700">Role</p>
                  <p className="mt-1 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
                    {role.toLowerCase()}
                  </p>
                </div>
                {role === "FARMER" ? (
                  <>
                    <Field label="Date of birth" htmlFor="registration-dob">
                      <Input id="registration-dob" type="date" value={form.date_of_birth} onChange={(e) => update("date_of_birth", e.target.value)} />
                    </Field>
                    <Field label="Sex" htmlFor="registration-sex">
                      <Select id="registration-sex" value={form.sex} onChange={(e) => update("sex", e.target.value)}>
                        <option value="">Select</option>
                        <option value="FEMALE">Female</option>
                        <option value="MALE">Male</option>
                        <option value="OTHER">Other</option>
                        <option value="PREFER_NOT_TO_SAY">Prefer not to say</option>
                      </Select>
                    </Field>
                  </>
                ) : (
                  <>
                    <Field label="Business name" htmlFor="registration-business">
                      <Input id="registration-business" value={form.business_name} onChange={(e) => update("business_name", e.target.value)} />
                    </Field>
                    <Field label="Business address" htmlFor="registration-address">
                      <Textarea id="registration-address" value={form.business_address} onChange={(e) => update("business_address", e.target.value)} />
                    </Field>
                  </>
                )}
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <h2 className="text-lg font-semibold">Administrative location</h2>
              {locationLevels.length === 1 && locationLevels[0].length === 0 ? (
                <p className="rounded-lg bg-amber-50 p-4 text-sm text-amber-900">
                  Verified location reference data has not been imported yet. Location selection is unavailable; an administrator must import the approved dataset before you can submit.
                </p>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  {locationLevels.map((choices, index) => (
                    <Field key={`location-${index}`} label={index === 0 ? "Region / first administrative level" : "Child administrative level"}>
                      <Input
                        aria-label={`Search ${index === 0 ? "regions" : "child locations"}`}
                        value={locationSearch[index] || ""}
                        onChange={(event) => setLocationSearch((current) => ({
                          ...current,
                          [index]: event.target.value,
                        }))}
                        placeholder="Search locations"
                      />
                      <Select
                        value={locationIds[index] || ""}
                        disabled={loadingLocationIndex === index}
                        onChange={(e) => void chooseLocation(index, choices.find((item) => item.id === e.target.value) || null)}
                      >
                        <option value="">
                          {loadingLocationIndex === index ? "Loading locations..." : "Select location"}
                        </option>
                        {choices.filter((location) =>
                          [location.name, ...location.alternative_names].some((name) =>
                            name.toLowerCase().includes((locationSearch[index] || "").trim().toLowerCase())
                          )
                        ).map((location) => (
                          <option key={location.id} value={location.id}>{location.name} ({location.level_display})</option>
                        ))}
                      </Select>
                    </Field>
                  ))}
                </div>
              )}
              {loadingLocationIndex !== null && (
                <p role="status" className="text-sm text-gray-500">Loading locations...</p>
              )}
              {latestLocationId && (
                <p className="text-sm text-gray-600">
                  Selected: {locationLevels.map((choices, index) => choices.find((item) => item.id === locationIds[index])?.name).filter(Boolean).join(" → ")}
                </p>
              )}
            </>
          )}

          {step === 2 && (
            <>
              <h2 className="text-lg font-semibold">Agricultural products</h2>
              {!productTypes.length ? (
                <p className="text-sm text-gray-600">No agricultural product catalog is available yet.</p>
              ) : (
                <>
                  <Field label="Search agricultural products" htmlFor="product-search">
                    <Input id="product-search" value={productSearch} onChange={(event) => setProductSearch(event.target.value)} placeholder="Search products" />
                  </Field>
                  {availableCategories.map((category) => (
                  <div key={category} className="space-y-2">
                    <h3 className="font-medium text-gray-800">{category}</h3>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {filteredProductTypes.filter((product) => product.category === category).map((product) => {
                        const intent = selections[product.id];
                        return (
                          <div key={product.id} className="flex items-center gap-3 rounded border border-gray-100 p-3">
                            <input
                              id={`product-${product.id}`}
                              type="checkbox"
                              checked={Boolean(intent)}
                              onChange={(e) => setSelections((current) => {
                                const next = { ...current };
                                if (e.target.checked) next[product.id] = intents[0];
                                else delete next[product.id];
                                return next;
                              })}
                            />
                            <label htmlFor={`product-${product.id}`} className="flex-1 text-sm">{product.name}</label>
                            {intent && intents.length > 1 && (
                              <Select
                                aria-label={`${product.name} intent`}
                                value={intent}
                                className="w-32"
                                onChange={(e) => setSelections((current) => ({ ...current, [product.id]: e.target.value }))}
                              >
                                {intents.map((value) => <option key={value} value={value}>{value.toLowerCase()}</option>)}
                              </Select>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  ))}
                </>
              )}
              <p className="text-xs text-gray-500">This selection records your interests or production only. It does not create marketplace listings.</p>
            </>
          )}

          {step === 3 && (
            <>
              <h2 className="text-lg font-semibold">License / verification document</h2>
              <p className="text-sm text-gray-600">PDF, JPG or PNG; maximum 10 MB. Files are private and only accessible to authorized reviewers.</p>
              <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-gray-300 p-6 text-sm text-green-800 hover:bg-green-50">
                <FileUp className="h-5 w-5" /> Choose document
                <input
                  className="sr-only"
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
                  onChange={(e) => {
                    void uploadDocument(e.target.files?.[0]);
                    e.currentTarget.value = "";
                  }}
                />
              </label>
              <ul className="divide-y divide-gray-100">
                {registration.documents.map((document) => (
                  <li key={document.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                    <span>{document.original_filename} — {document.verification_status.toLowerCase()}</span>
                    <Button type="button" variant="ghost" onClick={() => void removeDocument(document.id)}>Remove</Button>
                  </li>
                ))}
              </ul>
            </>
          )}

          {step === 4 && (
            <>
              <h2 className="text-lg font-semibold">Review and submit</h2>
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <div><dt className="text-gray-500">Name</dt><dd>{form.full_name || "Not provided"}</dd></div>
                <div><dt className="text-gray-500">Phone</dt><dd>{form.phone || "Not provided"}</dd></div>
                <div><dt className="text-gray-500">Business</dt><dd>{form.business_name || "Not applicable"}</dd></div>
                <div><dt className="text-gray-500">Location</dt><dd>{locationIds.length ? `${locationIds.length} level(s) selected` : "Not selected"}</dd></div>
                <div><dt className="text-gray-500">Products</dt><dd>{Object.keys(selections).length} selected</dd></div>
                <div><dt className="text-gray-500">Documents</dt><dd>{registration.documents.length} uploaded</dd></div>
              </dl>
              {registration.review_history.map((review) => (
                <p key={review.id} className="rounded bg-amber-50 p-3 text-sm text-amber-900">
                  {review.action}: {review.reason}
                </p>
              ))}
              <label className="flex items-start gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                  className="mt-1"
                />
                I confirm that these details and documents are accurate.
              </label>
            </>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-100 pt-4">
            <Button type="button" variant="secondary" onClick={() => setStep((current) => Math.max(0, current - 1))} disabled={step === 0}>
              <ChevronLeft className="h-4 w-4" /> Back
            </Button>
            <div className="flex gap-2">
              <Button type="button" variant="secondary" loading={saving} onClick={() => void saveDraft()}>Save draft</Button>
              {step < STEPS.length - 1 ? (
                <Button type="button" onClick={async () => { if (await saveDraft()) setStep((current) => current + 1); }}>
                  Continue <ChevronRight className="h-4 w-4" />
                </Button>
              ) : (
                <Button type="button" loading={saving} disabled={!confirmed} onClick={() => void submitRegistration()}>Submit for review</Button>
              )}
            </div>
          </div>
        </section>
        <p className="mt-4 text-center text-xs text-gray-500">
          You can leave and resume this application with your email and password.{" "}
          <Link className="underline" href="/registration/resume">Resume later</Link>
        </p>
      </div>
    </main>
  );
}
