"use client";

import { AppShell } from "@/components/layout/AppShell";
import { UserDirectory } from "@/components/admin/UserDirectory";
import { useAuth } from "@/lib/auth/context";

export default function AdminApprovalsPage() {
  const { user } = useAuth();

  return (
    <AppShell title="Pending Approvals" allow={["USER_ADMIN"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Pending Approvals</h2>
        <p className="mt-1 text-sm text-gray-500">
          New farmer, wholesaler and retailer registrations awaiting review.
        </p>
      </div>
      <UserDirectory mode="approvals" selfId={user?.id ?? ""} />
    </AppShell>
  );
}
