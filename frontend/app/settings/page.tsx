"use client";

import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Button,
  Card,
  CardHeader,
  ErrorBanner,
  PageLoader,
  SuccessBanner,
} from "@/components/ui";
import { superAdminApi } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";
import { formatDateTime } from "@/lib/format";
import type { PlatformSettings } from "@/lib/types";

/**
 * Regular users get a read-only view of the platform policy. Only
 * `SUPER_ADMIN` sees the editable form (which lives at
 * `/super-admin/settings`).
 */
export default function SettingsPage() {
  const { hasRole } = useAuth();
  const [settings, setSettings] = useState<PlatformSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
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
  }, []);

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

      <div className="grid max-w-3xl gap-6">
        <Card>
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
        </Card>

        <Card>
          <CardHeader
            title="Your account"
            subtitle="Sign-in identity and role are controlled by a User Admin"
          />
          <div className="p-5 text-sm text-gray-600">
            <p>
              To change your password or deactivate your account, contact a User
              Admin. Every privileged action on the platform is recorded in the
              audit log.
            </p>
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
