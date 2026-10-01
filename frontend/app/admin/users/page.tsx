"use client";

import { AppShell } from "@/components/layout/AppShell";
import { UserDirectory } from "@/components/admin/UserDirectory";
import { useAuth } from "@/lib/auth/context";

export default function AdminUsersPage() {
  const { user } = useAuth();

  return (
    <AppShell title="Users" allow={["USER_ADMIN"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Users</h2>
        <p className="mt-1 text-sm text-gray-500">
          Every commercial account, with suspend and reinstate controls.
        </p>
      </div>
      <UserDirectory mode="users" selfId={user?.id ?? ""} />
    </AppShell>
  );
}
