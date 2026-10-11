"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Save } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Button,
  Card,
  CardHeader,
  ErrorBanner,
  Input,
  PageLoader,
  SuccessBanner,
} from "@/components/ui";
import { authApi, superAdminApi } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";
import { BankAccountManager } from "@/components/payments/BankAccountManager";
import { formatDateTime } from "@/lib/format";
import type { PlatformSettings } from "@/lib/types";

/**
 * Regular users get a read-only view of the platform policy. Only
 * `SUPER_ADMIN` sees the editable form (which lives at
 * `/super-admin/settings`).
 */
export default function SettingsPage() {
  const { hasRole, user, logout } = useAuth();
  const [settings, setSettings] = useState<PlatformSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordNotice, setPasswordNotice] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordError("");
    setPasswordNotice("");
    if (newPassword !== confirmPassword) {
      setPasswordError("The new passwords do not match.");
      return;
    }
    setPasswordBusy(true);
    try {
      const result = await authApi.changePassword(currentPassword, newPassword);
      setPasswordNotice(result.message);
      window.setTimeout(async () => {
        await logout();
        window.location.assign("/login?password_changed=true");
      }, 1200);
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : "Could not update your password.");
    } finally {
      setPasswordBusy(false);
    }
  }

  useEffect(() => {
    if (!user || !["SUPER_ADMIN", "FINANCIAL_MANAGER", "USER_ADMIN"].includes(user.role)) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    superAdminApi
      .settings()
      .then((res) => {
        if (!cancelled) setSettings(res.settings);
      })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof Error
              ? err.message
              : "Platform settings are only available to administrators."
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const rows: [string, string][] = settings
    ? [
        ["Registration is open", settings.registration_open ? "Yes" : "No"],
        ["Approval required", settings.require_approval ? "Yes" : "No"],
        ["Maintenance mode", settings.maintenance_mode ? "Active" : "Off"],
      ]
    : [];

  return (
    <AppShell title="Settings" allow={["FARMER", "WHOLESALER", "RETAILER", "USER_ADMIN", "FINANCIAL_MANAGER", "SUPER_ADMIN"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Settings</h2>
        <p className="mt-1 text-sm text-gray-500">
          Platform policy and your account preferences.
        </p>
      </div>

      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} />
        </div>
      )}

      <div className="grid gap-6">
        {user && ["FARMER", "WHOLESALER", "RETAILER"].includes(user.role) && (
          <BankAccountManager />
        )}
        {user && ["SUPER_ADMIN", "FINANCIAL_MANAGER", "USER_ADMIN"].includes(user.role) && <Card>
          <CardHeader
            title="Platform policy"
            subtitle="Set centrally by the Super Admin"
            action={
              hasRole("SUPER_ADMIN") ? (
                <Button
                  size="sm"
                  variant="secondary"
                  icon={<Save className="h-3.5 w-3.5" />}
                  onClick={() => {
                    window.location.href = "/super-admin/settings";
                  }}
                >
                  Edit
                </Button>
              ) : undefined
            }
          />
          {loading ? (
            <PageLoader />
          ) : settings ? (
            <>
              <ul className="divide-y divide-gray-100 text-sm">
                {rows.map(([k, v]) => (
                  <li key={k} className="flex items-center justify-between px-5 py-3">
                    <span className="text-gray-700">{k}</span>
                    <span
                      className={`font-medium ${
                        v === "No" || v === "Active" ? "text-amber-700" : "text-gray-900"
                      }`}
                    >
                      {v}
                    </span>
                  </li>
                ))}
              </ul>
              <div className="border-t border-gray-100 px-5 py-4">
                <p className="text-xs font-medium text-gray-500">Announcement</p>
                <p className="mt-1 text-sm text-gray-700">
                  {settings.announcement || "No announcement is currently running."}
                </p>
                {settings.updated_at && (
                  <p className="mt-2 text-xs text-gray-400">
                    Last updated {formatDateTime(settings.updated_at)}
                    {settings.updated_by ? ` by ${settings.updated_by}` : ""}
                  </p>
                )}
              </div>
            </>
          ) : (
            <div className="p-6 text-sm text-gray-600">No settings available.</div>
          )}
        </Card>}

        {user && <Card>
          <CardHeader title="Your account" subtitle="Change your password securely" />
          <form onSubmit={(event) => void changePassword(event)} className="space-y-4 p-5">
            <p className="text-sm text-gray-600">
              After a successful change, all existing sign-in sessions will be revoked.
            </p>
            {passwordError && <ErrorBanner message={passwordError} />}
            {passwordNotice && <SuccessBanner message={passwordNotice} />}
            <label className="block text-sm font-medium text-gray-700">
              Current password
              <Input
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                required
              />
            </label>
            <label className="block text-sm font-medium text-gray-700">
              New password
              <Input
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                required
              />
            </label>
            <label className="block text-sm font-medium text-gray-700">
              Confirm new password
              <Input
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                required
              />
            </label>
            <Button type="submit" loading={passwordBusy}>
              Update password
            </Button>
          </form>
        </Card>}
      </div>
    </AppShell>
  );
}
