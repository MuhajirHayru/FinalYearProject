"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  BadgeCheck,
  CreditCard,
  LayoutDashboard,
  Leaf,
  Megaphone,
  MessageSquare,
  ShieldCheck,
  ShoppingBag,
  Store,
  Truck,
  UserCheck,
} from "lucide-react";
import { getDashboardRoute, useAuth } from "@/lib/auth/context";

const ROLES = [
  {
    role: "Farmers",
    icon: Leaf,
    tone: "bg-green-600",
    blurb:
      "List your produce, track orders as they arrive, negotiate in chat and get paid through verified bank transfers.",
  },
  {
    role: "Wholesalers",
    icon: Truck,
    tone: "bg-blue-600",
    blurb:
      "Source directly from farmers, place bulk orders, follow fulfilment status and keep every receipt on file.",
  },
  {
    role: "Retailers",
    icon: Store,
    tone: "bg-purple-600",
    blurb:
      "Discover wholesale listings ranked by proximity to your registered location and contact the supplier directly.",
  },
];

const FEATURES = [
  {
    icon: BadgeCheck,
    title: "Verified accounts",
    body: "Every commercial account is reviewed by a User Admin before it can trade.",
  },
  {
    icon: CreditCard,
    title: "Verified payments",
    body: "Financial Managers verify bank transfer references, flag mismatches and resolve disputes.",
  },
  {
    icon: MessageSquare,
    title: "Real-time chat",
    body: "Every conversation is attached to a listing or order, so the whole trade is on the record.",
  },
  {
    icon: ShieldCheck,
    title: "Audited staff actions",
    body: "Approvals, suspensions, verifications and overrides are written to an immutable audit log.",
  },
];

const SCREENS = [
  { href: "/farmer", label: "Farmer", icon: LayoutDashboard },
  { href: "/wholesaler", label: "Wholesaler", icon: ShoppingBag },
  { href: "/retailer", label: "Retailer", icon: Store },
  { href: "/admin", label: "User Admin", icon: UserCheck },
  { href: "/financial-manager", label: "Financial Manager", icon: CreditCard },
  { href: "/super-admin", label: "Super Admin", icon: ShieldCheck },
];

export default function HomePage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (user) router.replace(getDashboardRoute(user.role));
  }, [user, router]);

  return (
    <div className="min-h-screen bg-white text-gray-900">
      <header className="border-b border-gray-100">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2">
            <Leaf className="h-6 w-6 text-green-600" />
            <span className="text-lg font-bold">GreenPath</span>
          </div>
          <nav className="flex items-center gap-2">
            <Link
              href="/public-announcement"
              className="hidden rounded-lg px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 sm:block"
            >
              Announcement
            </Link>
            {user ? (
              <Link
                href={getDashboardRoute(user.role)}
                className="rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-700"
              >
                My dashboard
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  className="rounded-lg px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  Sign in
                </Link>
                <Link
                  href="/register"
                  className="rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-700"
                >
                  Create account
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <section className="mx-auto max-w-6xl px-6 py-20 text-center">
        {isLoading ? (
          <p className="text-sm text-gray-400">Loading...</p>
        ) : (
          <>
            <span className="inline-flex items-center gap-2 rounded-full bg-green-50 px-4 py-1.5 text-xs font-semibold text-green-700">
              <Leaf className="h-3.5 w-3.5" />
              AI-integrated farm-to-marketplace
            </span>
            <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-bold leading-tight sm:text-5xl">
              Connect Ethiopian farmers directly to wholesale buyers
            </h1>
            <p className="mx-auto mt-5 max-w-2xl text-base leading-relaxed text-gray-600">
              GreenPath replaces middlemen with a single audited platform: farmers
              publish produce, wholesalers and retailers order in bulk, and every
              payment is verified before it is released.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Link
                href="/register"
                className="inline-flex items-center gap-2 rounded-lg bg-green-600 px-6 py-3 text-sm font-semibold text-white hover:bg-green-700"
              >
                Start trading
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="/login"
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-6 py-3 text-sm font-semibold text-gray-700 hover:border-gray-400"
              >
                Sign in
              </Link>
            </div>
            <p className="mt-4 text-xs text-gray-500">
              Commercial accounts are approved by a User Admin before trading is
              enabled.
            </p>
          </>
        )}
      </section>

      <section className="bg-gray-50 py-16">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center text-2xl font-bold">Built for every side of the trade</h2>
          <p className="mx-auto mt-3 max-w-2xl text-center text-sm text-gray-600">
            One platform, three commercial roles, and the staff oversight that keeps it
            trustworthy.
          </p>
          <div className="mt-10 grid gap-6 md:grid-cols-3">
            {ROLES.map((r) => {
              const Icon = r.icon;
              return (
                <div
                  key={r.role}
                  className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
                >
                  <span
                    className={`flex h-12 w-12 items-center justify-center rounded-lg text-white ${r.tone}`}
                  >
                    <Icon className="h-6 w-6" />
                  </span>
                  <h3 className="mt-4 text-lg font-bold">{r.role}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-gray-600">{r.blurb}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="py-16">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center text-2xl font-bold">How GreenPath is kept honest</h2>
          <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <div key={f.title} className="rounded-xl border border-gray-200 p-5">
                  <Icon className="h-6 w-6 text-green-600" />
                  <h3 className="mt-3 text-base font-semibold">{f.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-gray-600">{f.body}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="bg-gray-50 py-16">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-center text-2xl font-bold">Role dashboards</h2>
          <p className="mx-auto mt-3 max-w-2xl text-center text-sm text-gray-600">
            Each role gets its own workspace. Sign in to reach the one assigned to you.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            {SCREENS.map((s) => {
              const Icon = s.icon;
              return (
                <Link
                  key={s.href}
                  href={s.href}
                  className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 hover:border-gray-400"
                >
                  <Icon className="h-4 w-4 text-gray-400" />
                  {s.label}
                </Link>
              );
            })}
          </div>
          <p className="mt-6 text-center text-xs text-gray-500">
            Opening a role dashboard you are not assigned to returns a 403 page.
          </p>
        </div>
      </section>

      <footer className="border-t border-gray-100 py-8">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 text-xs text-gray-500">
          <span>GreenPath &mdash; Django, DRF, Channels, React and Next.js.</span>
          <Link
            href="/public-announcement"
            className="inline-flex items-center gap-1.5 font-medium text-gray-600 hover:text-green-700"
          >
            <Megaphone className="h-3.5 w-3.5" />
            Public announcement
          </Link>
        </div>
      </footer>
    </div>
  );
}
