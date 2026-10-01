"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle, Leaf, Store, Warehouse } from "lucide-react";
import { authApi } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";
import {
  Button,
  ErrorBanner,
  Field,
  Input,
  Select,
  SuccessBanner,
} from "@/components/ui";

const ROLES = [
  {
    value: "FARMER",
    label: "Farmer",
    blurb: "Post produce, manage listings, chat with buyers.",
    icon: Leaf,
  },
  {
    value: "WHOLESALER",
    label: "Wholesaler",
    blurb: "Source stock, place orders, submit payment records.",
    icon: Warehouse,
  },
  {
    value: "RETAILER",
    label: "Retailer",
    blurb: "Discover nearby wholesale stock and chat with sellers.",
    icon: Store,
  },
];

interface Form {
  full_name: string;
  email: string;
  phone: string;
  location: string;
  role: string;
  password: string;
  password_confirm: string;
  privacy_policy_accepted: boolean;
}

const EMPTY: Form = {
  full_name: "",
  email: "",
  phone: "",
  location: "",
  role: "FARMER",
  password: "",
  password_confirm: "",
  privacy_policy_accepted: false,
};

export default function RegisterPage() {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();
  const [form, setForm] = useState<Form>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    if (!isLoading && isAuthenticated) router.replace("/");
  }, [isLoading, isAuthenticated, router]);

  useEffect(() => {
    authApi
      .announcement()
      .then((data) => setAnnouncement(data.announcement))
      .catch(() => undefined);
  }, []);

  function set<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setFieldErrors((prev) => {
      if (!prev[key as string]) return prev;
      const next = { ...prev };
      delete next[key as string];
      return next;
    });
  }

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!form.full_name.trim()) errs.full_name = "Full name is required.";
    if (!/^\S+@\S+\.\S+$/.test(form.email)) errs.email = "Enter a valid email.";
    if (form.password.length < 8)
      errs.password = "Password must be at least 8 characters.";
    if (form.password !== form.password_confirm)
      errs.password_confirm = "Passwords do not match.";
    if (!form.location.trim()) errs.location = "Location is required.";
    if (!form.privacy_policy_accepted)
      errs.privacy_policy_accepted = "You must accept the privacy policy.";
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!validate()) return;

    setBusy(true);
    try {
      await authApi.register({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        password: form.password,
        role: form.role,
        privacy_policy_accepted: form.privacy_policy_accepted,
        phone: form.phone.trim() || undefined,
        location: form.location.trim(),
      });
      router.push("/login?registered=true");
    } catch (err) {
      // Reuse the same field-map shape the backend returns.
      if (err && typeof err === "object" && "payload" in err) {
        const payload = (err as { payload: unknown }).payload as {
          error?: Record<string, string[]>;
        };
        if (payload?.error && typeof payload.error === "object") {
          setFieldErrors(
            Object.fromEntries(
              Object.entries(payload.error).map(([k, v]) => [k, v.join(" ")])
            )
          );
          setError("Please correct the highlighted fields.");
        } else {
          setError(
            err instanceof Error ? err.message : "Registration failed."
          );
        }
      } else {
        setError(err instanceof Error ? err.message : "Registration failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  const selectedRole = ROLES.find((r) => r.value === form.role)!;

  return (
    <div className="flex min-h-screen bg-gray-50">
      <div className="hidden w-1/3 flex-col justify-between bg-green-700 p-10 text-white lg:flex">
        <Link href="/" className="flex items-center gap-3">
          <Leaf className="h-8 w-8" />
          <span className="text-2xl font-bold">Green Path</span>
        </Link>
        <div>
          <h1 className="text-3xl font-bold leading-tight">
            Join the marketplace
          </h1>
          <p className="mt-4 text-green-100">
            New farmer, wholesaler and retailer accounts are reviewed by a User
            Admin before they can sign in. This keeps every trade counterparty
            verified.
          </p>
        </div>
        <p className="text-sm text-green-200">(c) 2025 Green Path</p>
      </div>

      <div className="flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-2xl">
          <div className="mb-6 flex items-center gap-2 lg:hidden">
            <Leaf className="h-7 w-7 text-green-600" />
            <span className="text-xl font-bold text-gray-900">Green Path</span>
          </div>

          <h2 className="text-2xl font-bold text-gray-900">Create account</h2>
          <p className="mt-1 text-sm text-gray-500">
            Register as a Farmer, Wholesaler or Retailer.
          </p>

          {announcement && (
            <div className="mt-4">
              <SuccessBanner message={announcement} />
            </div>
          )}

          {error && (
            <div className="mt-4">
              <ErrorBanner message={error} />
            </div>
          )}

          <form
            onSubmit={submit}
            className="mt-6 space-y-5 rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
          >
            <div>
              <p className="mb-2 text-sm font-medium text-gray-700">
                I am registering as
              </p>
              <div className="grid gap-3 sm:grid-cols-3">
                {ROLES.map((role) => {
                  const Icon = role.icon;
                  const active = form.role === role.value;
                  return (
                    <button
                      key={role.value}
                      type="button"
                      onClick={() => set("role", role.value)}
                      className={`rounded-lg border p-3 text-left transition-colors ${
                        active
                          ? "border-green-500 bg-green-50 ring-1 ring-green-500"
                          : "border-gray-200 bg-white hover:border-gray-300"
                      }`}
                    >
                      <Icon
                        className={`h-5 w-5 ${active ? "text-green-600" : "text-gray-400"}`}
                      />
                      <p className="mt-1.5 text-sm font-semibold text-gray-900">
                        {role.label}
                      </p>
                      <p className="mt-0.5 text-xs text-gray-500">
                        {role.blurb}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="Full name" htmlFor="full_name" error={fieldErrors.full_name}>
                <Input
                  id="full_name"
                  value={form.full_name}
                  onChange={(e) => set("full_name", e.target.value)}
                  placeholder="Abebe Mengesha"
                  autoComplete="name"
                />
              </Field>

              <Field label="Email address" htmlFor="email" error={fieldErrors.email}>
                <Input
                  id="email"
                  type="email"
                  value={form.email}
                  onChange={(e) => set("email", e.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                />
              </Field>

              <Field label="Phone" htmlFor="phone" error={fieldErrors.phone}>
                <Input
                  id="phone"
                  value={form.phone}
                  onChange={(e) => set("phone", e.target.value)}
                  placeholder="+251 9xx xxx xxx"
                  autoComplete="tel"
                />
              </Field>

              <Field
                label="Location"
                htmlFor="location"
                error={fieldErrors.location}
                hint="Used for proximity ranking. City or woreda is enough."
              >
                <Input
                  id="location"
                  value={form.location}
                  onChange={(e) => set("location", e.target.value)}
                  placeholder="Adama"
                />
              </Field>
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <Field
                label="Password"
                htmlFor="password"
                error={fieldErrors.password}
                hint="Minimum 8 characters."
              >
                <Input
                  id="password"
                  type="password"
                  value={form.password}
                  onChange={(e) => set("password", e.target.value)}
                  autoComplete="new-password"
                />
              </Field>

              <Field
                label="Confirm password"
                htmlFor="password_confirm"
                error={fieldErrors.password_confirm}
              >
                <Input
                  id="password_confirm"
                  type="password"
                  value={form.password_confirm}
                  onChange={(e) => set("password_confirm", e.target.value)}
                  autoComplete="new-password"
                />
              </Field>
            </div>

            <label className="flex items-start gap-2.5 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={form.privacy_policy_accepted}
                onChange={(e) => set("privacy_policy_accepted", e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
              />
              <span>
                I accept the privacy policy and consent to my location being used
                for proximity ranking.{" "}
                <span className="text-red-600">
                  {fieldErrors.privacy_policy_accepted}
                </span>
              </span>
            </label>

            <div className="flex items-center justify-between gap-4 border-t border-gray-100 pt-4">
              <p className="text-xs text-gray-500">
                Registering as <span className="font-medium">{selectedRole.label}</span> -
                approval required before first sign-in.
              </p>
              <Button type="submit" loading={busy}>
                Create account
              </Button>
            </div>
          </form>

          <p className="mt-6 text-center text-sm text-gray-500">
            Already registered?{" "}
            <Link
              href="/login"
              className="font-semibold text-green-700 hover:text-green-800"
            >
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}


