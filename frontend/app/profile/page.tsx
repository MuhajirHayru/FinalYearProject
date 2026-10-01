"use client";

import { useState } from "react";
import { Save, User as UserIcon } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Avatar,
  Button,
  Card,
  CardHeader,
  ErrorBanner,
  Field,
  Input,
  StatusPill,
  SuccessBanner,
} from "@/components/ui";
import { authApi } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";
import { formatDate } from "@/lib/format";
import type { User } from "@/lib/types";

const ROLES: User["role"][] = [
  "FARMER",
  "WHOLESALER",
  "RETAILER",
  "USER_ADMIN",
  "FINANCIAL_MANAGER",
  "SUPER_ADMIN",
];

export default function ProfilePage() {
  const { user, refreshUser } = useAuth();
  const [form, setForm] = useState({
    full_name: user?.full_name ?? "",
    phone: user?.phone ?? "",
    location: user?.location ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  if (!user) {
    return (
      <AppShell title="Profile" allow={ROLES}>
        <Card>
          <div className="p-6 text-sm text-gray-600">Loading your profile...</div>
        </Card>
      </AppShell>
    );
  }

  async function save() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await authApi.updateProfile(form);
      await refreshUser();
      setNotice("Profile updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save your profile.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell title="Profile" allow={ROLES}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">My Profile</h2>
        <p className="mt-1 text-sm text-gray-500">
          Your contact details are visible to counterparties you trade with.
        </p>
      </div>

      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} />
        </div>
      )}
      {notice && (
        <div className="mb-5">
          <SuccessBanner message={notice} />
        </div>
      )}

      <div className="grid max-w-4xl gap-6 lg:grid-cols-[280px_1fr]">
        <Card className="h-fit">
          <div className="flex flex-col items-center gap-3 p-6 text-center">
            <Avatar name={user.full_name} size="lg" />
            <div>
              <p className="text-base font-semibold text-gray-900">{user.full_name}</p>
              <p className="text-sm text-gray-500">{user.email}</p>
            </div>
            <div className="flex items-center gap-2">
              <StatusPill value={user.role} kind="role" />
              <StatusPill value={user.status} />
            </div>
            <p className="text-xs text-gray-400">Joined {formatDate(user.created_at)}</p>
          </div>
          <ul className="divide-y divide-gray-100 border-t border-gray-100 text-sm">
            <li className="flex items-center justify-between px-5 py-3">
              <span className="text-gray-600">Role</span>
              <span className="font-medium text-gray-900">{user.role_display}</span>
            </li>
            <li className="flex items-center justify-between px-5 py-3">
              <span className="text-gray-600">Status</span>
              <span className="font-medium text-gray-900">{user.status_display}</span>
            </li>
            <li className="flex items-center justify-between px-5 py-3">
              <span className="text-gray-600">Permissions</span>
              <span className="font-medium text-gray-900">{user.permissions.length}</span>
            </li>
            {user.latitude && user.longitude && (
              <li className="flex items-center justify-between px-5 py-3">
                <span className="text-gray-600">Coordinates</span>
                <span className="font-mono text-xs text-gray-700">
                  {Number(user.latitude).toFixed(4)}, {Number(user.longitude).toFixed(4)}
                </span>
              </li>
            )}
          </ul>
        </Card>

        <Card>
          <CardHeader
            title="Contact details"
            subtitle="Email and role are managed by a User Admin and cannot be edited here"
          />
          <div className="space-y-4 p-5">
            <Field label="Full name" htmlFor="full_name">
              <Input
                id="full_name"
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              />
            </Field>
            <Field label="Email" htmlFor="email" hint="Contact a User Admin to change this.">
              <Input id="email" value={user.email} disabled />
            </Field>
            <Field label="Phone" htmlFor="phone">
              <Input
                id="phone"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="+251 9xx xxx xxx"
              />
            </Field>
            <Field label="Location" htmlFor="location">
              <Input
                id="location"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
                placeholder="Konga, Yirgalem"
              />
            </Field>
            <div className="flex items-center gap-3">
              <Button
                loading={busy}
                icon={<Save className="h-4 w-4" />}
                onClick={() => void save()}
              >
                Save changes
              </Button>
              {user.rejection_reason && (
                <span className="text-xs text-red-600">
                  Rejection reason: {user.rejection_reason}
                </span>
              )}
            </div>
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
