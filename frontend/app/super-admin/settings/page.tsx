"use client";

import { useCallback, useEffect, useState } from "react";
import { Megaphone, Save, Settings as SettingsIcon } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Button,
  Card,
  CardHeader,
  ErrorBanner,
  Field,
  PageLoader,
  SuccessBanner,
  Textarea,
} from "@/components/ui";
import { superAdminApi } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import type { PlatformSettings } from "@/lib/types";

export default function SuperAdminSettingsPage() {
  const [settings, setSettings] = useState<PlatformSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [form, setForm] = useState({
    registration_open: true,
    require_approval: true,
    maintenance_mode: false,
    announcement: "",
  });

  const [broadcast, setBroadcast] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await superAdminApi.settings();
      setSettings(res.settings);
      setForm({
        registration_open: res.settings.registration_open,
        require_approval: res.settings.require_approval,
        maintenance_mode: res.settings.maintenance_mode,
        announcement: res.settings.announcement ?? "",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const res = await superAdminApi.updateSettings(form);
      setSettings(res.settings);
      setNotice(
        `Saved. ${res.updated ? Object.keys(res.updated).length : 0} field(s) changed.`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save settings.");
    } finally {
      setBusy(false);
    }
  }

  async function sendAnnouncement() {
    if (!broadcast.trim()) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const res = await superAdminApi.announcement(broadcast.trim());
      setNotice(`${res.message} Delivered to ${res.recipients} user(s).`);
      setBroadcast("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Broadcast failed.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <AppShell title="Platform Settings" allow={["SUPER_ADMIN"]}>
        <PageLoader />
      </AppShell>
    );
  }

  return (
    <AppShell title="Platform Settings" allow={["SUPER_ADMIN"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">Platform Settings</h2>
        <p className="mt-1 text-sm text-gray-500">
          Registration policy and the announcement banner shown to every signed-in
          user.
        </p>
      </div>

      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} onRetry={() => void load()} />
        </div>
      )}
      {notice && (
        <div className="mb-5">
          <SuccessBanner message={notice} />
        </div>
      )}

      <div className="grid max-w-4xl gap-6">
        <Card>
          <CardHeader
            title="Registration Policy"
            subtitle="Applies to new public registrations only"
          />
          <div className="space-y-4 p-5">
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={form.registration_open}
                onChange={(e) =>
                  setForm({ ...form, registration_open: e.target.checked })
                }
                className="mt-0.5 h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
              />
              <span>
                <span className="block text-sm font-medium text-gray-900">
                  Registration is open
                </span>
                <span className="block text-xs text-gray-500">
                  When off, <code>/auth/register/</code> returns 403.
                </span>
              </span>
            </label>

            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={form.require_approval}
                onChange={(e) =>
                  setForm({ ...form, require_approval: e.target.checked })
                }
                className="mt-0.5 h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
              />
              <span>
                <span className="block text-sm font-medium text-gray-900">
                  Require User Admin approval
                </span>
                <span className="block text-xs text-gray-500">
                  New accounts start as PENDING and cannot sign in until a User
                  Admin approves them.
                </span>
              </span>
            </label>

            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={form.maintenance_mode}
                onChange={(e) =>
                  setForm({ ...form, maintenance_mode: e.target.checked })
                }
                className="mt-0.5 h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
              />
              <span>
                <span className="block text-sm font-medium text-gray-900">
                  Maintenance mode
                </span>
                <span className="block text-xs text-gray-500">
                  Flags the platform as under maintenance.
                </span>
              </span>
            </label>

            <Field
              label="Announcement banner"
              htmlFor="announcement"
              hint="Displayed at the top of every authenticated screen. Leave blank to clear."
            >
              <Textarea
                id="announcement"
                value={form.announcement}
                onChange={(e) => setForm({ ...form, announcement: e.target.value })}
                placeholder="Scheduled maintenance this Sunday from 02:00 to 04:00 EAT."
              />
            </Field>

            <div className="flex items-center gap-3">
              <Button loading={busy} icon={<Save className="h-4 w-4" />} onClick={() => void save()}>
                Save settings
              </Button>
              {settings?.updated_at && (
                <p className="text-xs text-gray-500">
                  Last updated {formatDateTime(settings.updated_at)}
                  {settings.updated_by ? ` by ${settings.updated_by}` : ""}
                </p>
              )}
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Broadcast an announcement"
            subtitle="Immediately pushes the banner to every registered user"
          />
          <div className="space-y-4 p-5">
            <Field
              label="Message"
              htmlFor="broadcast"
              hint="Use the announcement field above if you want it persisted too."
            >
              <Textarea
                id="broadcast"
                value={broadcast}
                onChange={(e) => setBroadcast(e.target.value)}
                placeholder="New payment verification SLA starts Monday."
              />
            </Field>
            <Button
              variant="secondary"
              icon={<Megaphone className="h-4 w-4" />}
              loading={busy}
              disabled={!broadcast.trim()}
              onClick={() => void sendAnnouncement()}
            >
              Broadcast to all users
            </Button>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="API configuration"
            subtitle="Reported by the system health endpoint"
            action={<SettingsIcon className="h-4 w-4 text-gray-400" />}
          />
          <ul className="divide-y divide-gray-100 text-sm">
            {[
              ["Authentication", "JWT (HS256)"],
              ["Token lifetime", "access 1h / refresh 7d"],
              ["Page size", "20"],
            ].map(([k, v]) => (
              <li key={k} className="flex items-center justify-between px-5 py-3">
                <span className="text-gray-700">{k}</span>
                <span className="font-mono text-xs text-gray-600">{v}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </AppShell>
  );
}
