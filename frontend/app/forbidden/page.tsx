"use client";

import Link from "next/link";
import { ShieldAlert } from "lucide-react";
import { Button, Card } from "@/components/ui";
import { useAuth } from "@/lib/auth/context";

const ROLE_HOME: Record<string, string> = {
  FARMER: "/farmer",
  WHOLESALER: "/wholesaler",
  RETAILER: "/retailer",
  USER_ADMIN: "/admin",
  FINANCIAL_MANAGER: "/financial-manager",
  SUPER_ADMIN: "/super-admin",
};

export default function ForbiddenPage() {
  const { user } = useAuth();
  const home = user ? (ROLE_HOME[user.role] ?? "/") : "/login";

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <Card className="w-full max-w-md p-8 text-center">
        <span className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-50">
          <ShieldAlert className="h-7 w-7 text-red-600" />
        </span>
        <p className="mt-5 text-sm font-semibold tracking-wide text-red-600">403</p>
        <h1 className="mt-1 text-xl font-bold text-gray-900">Access denied</h1>
        <p className="mt-2 text-sm text-gray-600">
          {user
            ? `Your ${user.role_display} account is not allowed to open that page. If you think this is a mistake, ask a User Admin to review your role.`
            : "You need to be signed in to open that page."}
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <Link href={home}>
            <Button>Go to my dashboard</Button>
          </Link>
          <Link href="/login">
            <Button variant="secondary">Sign in</Button>
          </Link>
        </div>
      </Card>
    </main>
  );
}
