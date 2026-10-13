"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  CheckCircle,
  Eye,
  EyeOff,
  Leaf,
  Store,
  Truck,
  Warehouse,
} from "lucide-react";
import { ApiRequestError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";
import { Button, ErrorBanner, Input, SuccessBanner } from "@/components/ui";
import { BrandMark } from "@/components/branding/BrandMark";
import { useWebsiteContent } from "@/components/branding/WebsiteContentProvider";

const DEMO_ACCOUNTS = [
  {
    email: "farmer@greenpath.et",
    label: "Demo Farmer",
    role: "Farmer",
    icon: Leaf,
  },
  {
    email: "wholesaler@greenpath.et",
    label: "Demo Wholesaler",
    role: "Wholesaler",
    icon: Warehouse,
  },
  {
    email: "retailer@greenpath.et",
    label: "Demo Retailer",
    role: "Retailer",
    icon: Store,
  },
  {
    email: "admin@greenpath.et",
    label: "Demo User Admin",
    role: "User Admin",
    icon: CheckCircle,
  },
  {
    email: "finance@greenpath.et",
    label: "Demo Finance Manager",
    role: "Finance",
    icon: Truck,
  },
  {
    email: "superadmin@greenpath.et",
    label: "Demo Super Admin",
    role: "Super Admin",
    icon: CheckCircle,
  },
];

const DEMO_PASSWORD = "demo1234";

export default function LoginPage() {
  // `useSearchParams` opts the subtree out of static prerendering, so the form
  // is wrapped in a Suspense boundary to keep the build working.
  return (
    <Suspense fallback={<div className="min-h-screen bg-gray-50" />}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const { website } = useWebsiteContent();
  const copy = website.content;
  const searchParams = useSearchParams();
  const { login, isAuthenticated, isLoading: authLoading, user } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [attemptsRemaining, setAttemptsRemaining] = useState<number | null>(null);
  const [maxAttempts, setMaxAttempts] = useState<number | null>(null);
  const [lockedEmail, setLockedEmail] = useState("");
  const [lockExpiresAt, setLockExpiresAt] = useState<number | null>(null);
  const [countdownNow, setCountdownNow] = useState(Date.now());

  const lockSecondsRemaining =
    lockExpiresAt === null
      ? 0
      : Math.max(0, Math.ceil((lockExpiresAt - countdownNow) / 1000));
  const emailIsLocked =
    email.trim().toLowerCase() === lockedEmail && lockSecondsRemaining > 0;

  useEffect(() => {
    if (lockExpiresAt === null) return;
    const timer = window.setInterval(() => {
      const now = Date.now();
      setCountdownNow(now);
      if (now >= lockExpiresAt) {
        window.clearInterval(timer);
        setLockExpiresAt(null);
        setLockedEmail("");
        setAttemptsRemaining(null);
        setMaxAttempts(null);
        setError("The sign-in lockout has expired. You may try again.");
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [lockExpiresAt]);

  useEffect(() => {
    if (!authLoading && isAuthenticated && user) {
      router.replace("/");
    }
  }, [authLoading, isAuthenticated, user, router]);

  async function attempt(nextEmail: string, nextPassword: string) {
    if (
      nextEmail.trim().toLowerCase() === lockedEmail &&
      lockExpiresAt !== null &&
      lockExpiresAt > Date.now()
    ) {
      return;
    }
    setError("");
    setBusy(true);
    try {
      await login(nextEmail, nextPassword);
      setAttemptsRemaining(null);
      setMaxAttempts(null);
      setLockExpiresAt(null);
      setLockedEmail("");
    } catch (err) {
      if (err instanceof ApiRequestError) {
        const payload = err.payload as {
          error?: unknown;
          attempts_remaining?: unknown;
          max_attempts?: unknown;
          retry_after_seconds?: unknown;
        } | null;
        if (
          typeof payload?.attempts_remaining === "number" &&
          typeof payload.max_attempts === "number"
        ) {
          const remaining = payload.attempts_remaining;
          const maximum = payload.max_attempts;
          const retryAfter = payload.retry_after_seconds;
          setAttemptsRemaining(remaining);
          setMaxAttempts(maximum);
          setLockedEmail(nextEmail.trim().toLowerCase());
          if (typeof payload.error === "string") setError(payload.error);
          if (typeof retryAfter === "number" && retryAfter > 0) {
            setLockExpiresAt(Date.now() + retryAfter * 1000);
            setCountdownNow(Date.now());
          } else {
            setLockExpiresAt(null);
          }
        } else {
          setError(err.message);
        }
      } else {
        setError(
          err instanceof Error
            ? err.message
            : "Login failed. Is the backend running on port 8000?"
        );
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      <div className="hidden w-1/2 flex-col justify-between bg-green-700 p-12 text-white lg:flex">
        <BrandMark
          className="gap-3"
          iconClassName="h-8 w-8 text-white"
          nameClassName="text-2xl font-bold text-white"
        />

        <div className="space-y-8">
          <h1 className="text-4xl font-bold leading-tight">
            {copy.landing_badge}
          </h1>
          <p className="max-w-md text-lg text-green-100">
            {copy.landing_subtitle}
          </p>

          <div className="space-y-4">
            {[
              "Post and manage your product listings",
              "Chat directly with verified buyers",
              "Receive secure, verified payments",
              "Browse and filter nearby products",
            ].map((feature) => (
              <div key={feature} className="flex items-center gap-3 text-green-100">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-green-600">
                  <CheckCircle className="h-4 w-4" />
                </div>
                <span>{feature}</span>
              </div>
            ))}
          </div>
        </div>

        <p className="text-sm text-green-200">
          {copy.footer_text}
        </p>
      </div>

      <div className="flex flex-1 items-center justify-center bg-gray-50 p-6">
        <div className="w-full max-w-md">
          <BrandMark
            className="mb-8 gap-2 lg:hidden"
            iconClassName="h-7 w-7 text-green-600"
            nameClassName="text-xl font-bold text-gray-900"
          />

          <div className="mb-8">
            <h2 className="text-2xl font-bold text-gray-900">Sign in</h2>
            <p className="mt-1 text-sm text-gray-500">
              Welcome back! Enter your credentials to continue.
            </p>
          </div>

          {searchParams.get("registered") === "true" && (
            <div className="mb-6">
              <SuccessBanner message="Registration submitted! Your account is pending admin approval. You'll be able to sign in once approved." />
            </div>
          )}

          {searchParams.get("password_changed") === "true" && (
            <div className="mb-6">
              <SuccessBanner message="Your password was changed. Sign in with the new password." />
            </div>
          )}

          {error && (
            <div className="mb-6">
              <ErrorBanner
                message={
                  attemptsRemaining !== null &&
                  attemptsRemaining > 0 &&
                  lockSecondsRemaining === 0 &&
                  email.trim().toLowerCase() === lockedEmail
                    ? `${error} ${attemptsRemaining} of ${maxAttempts} attempts remain.`
                    : error
                }
              />
            </div>
          )}

          {emailIsLocked && (
            <div
              className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
              role="status"
              aria-live="polite"
            >
              Too many incorrect passwords. Sign-in is disabled for this account.
              Try again in {Math.floor(lockSecondsRemaining / 60)}m{" "}
              {lockSecondsRemaining % 60}s.
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              void attempt(email, password);
            }}
            className="space-y-5"
          >
            <div>
              <label
                htmlFor="email"
                className="mb-1.5 block text-sm font-medium text-gray-700"
              >
                Email address
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setError("");
                }}
                required
                placeholder="you@example.com"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-sm font-medium text-gray-700"
              >
                Password
              </label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setError("");
                  }}
                  required
                  placeholder="............"
                  className="pr-11"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? (
                    <EyeOff className="h-5 w-5" />
                  ) : (
                    <Eye className="h-5 w-5" />
                  )}
                </button>
              </div>
            </div>

            <Button
              type="submit"
              size="lg"
              loading={busy}
              disabled={busy || emailIsLocked}
              className="w-full"
            >
              {busy
                ? "Signing in..."
                : emailIsLocked
                  ? `Try again in ${Math.floor(lockSecondsRemaining / 60)}m ${lockSecondsRemaining % 60}s`
                  : "Sign in"}
            </Button>
          </form>

          <div className="mt-6">
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200" />
              </div>
              <div className="relative flex justify-center text-xs">
                <span className="bg-gray-50 px-3 text-gray-500">
                  Quick access - demo accounts
                </span>
              </div>
            </div>

            <div className="mt-4 grid gap-2 sm:grid-cols-2">
              {DEMO_ACCOUNTS.map((demo) => {
                const Icon = demo.icon;
                return (
                  <button
                    key={demo.email}
                    type="button"
                    disabled={
                      busy ||
                      (demo.email.toLowerCase() === lockedEmail &&
                        lockSecondsRemaining > 0)
                    }
                    onClick={() => void attempt(demo.email, DEMO_PASSWORD)}
                    className="flex items-center gap-2.5 rounded-lg border border-gray-200 bg-white px-3 py-2.5 text-left text-sm text-gray-700 transition-colors hover:border-green-300 hover:bg-green-50/50 disabled:opacity-50"
                  >
                    <Icon className="h-4 w-4 shrink-0 text-green-600" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">
                        {demo.label}
                      </span>
                      <span className="block truncate text-xs text-gray-400">
                        {demo.role}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
            <p className="mt-2 text-center text-xs text-gray-400">
              Seeded by <code>python manage.py seed_greenpath</code> - password{" "}
              <code>{DEMO_PASSWORD}</code>
            </p>
          </div>

          <p className="mt-8 text-center text-sm text-gray-500">
            Don&apos;t have an account?{" "}
            <Link
              href="/register"
              className="font-semibold text-green-700 hover:text-green-800"
            >
              Register as Farmer, Wholesaler or Retailer
            </Link>
          </p>

          <p className="mt-3 text-center text-sm text-gray-500">
            <Link href="/forgot-password" className="font-medium text-green-700 hover:text-green-800">
              Forgot your password?
            </Link>
          </p>

          <p className="mt-3 text-center text-sm text-gray-500">
            <Link href="/registration/resume" className="font-medium text-green-700 hover:text-green-800">
              Finish an incomplete registration
            </Link>
          </p>

          <p className="mt-3 text-center text-sm text-gray-500">
            <Link href="/public-announcement" className="hover:text-gray-700">
              Platform announcement
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
