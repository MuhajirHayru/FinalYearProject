"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Megaphone, Save, Settings as SettingsIcon } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Button,
  Card,
  CardHeader,
  ErrorBanner,
  Field,
  Input,
  PageLoader,
  SuccessBanner,
  Textarea,
} from "@/components/ui";
import { superAdminApi } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import { useWebsiteContent } from "@/components/branding/WebsiteContentProvider";
import type { PlatformSettings, WebsiteContent } from "@/lib/types";

const WEBSITE_COPY_FIELDS = [
  ["landing_badge", "Landing badge", "text"],
  ["landing_title", "Landing page title", "textarea"],
  ["landing_subtitle", "Landing page subtitle", "textarea"],
  ["landing_description", "Landing page description", "textarea"],
  ["landing_primary_button", "Primary button label", "text"],
  ["landing_secondary_button", "Secondary button label", "text"],
  ["about_title", "About section title", "text"],
  ["about_description", "About section content", "textarea"],
  ["marketplace_title", "Marketplace section title", "text"],
  ["marketplace_description", "Marketplace section content", "textarea"],
  ["farmer_description", "Farmer introduction", "textarea"],
  ["wholesaler_description", "Wholesaler introduction", "textarea"],
  ["retailer_description", "Retailer introduction", "textarea"],
  ["feature_verified_title", "Verified accounts feature title", "text"],
  ["feature_verified_description", "Verified accounts feature content", "textarea"],
  ["feature_payments_title", "Payments feature title", "text"],
  ["feature_payments_description", "Payments feature content", "textarea"],
  ["feature_chat_title", "Messaging feature title", "text"],
  ["feature_chat_description", "Messaging feature content", "textarea"],
  ["feature_audit_title", "Audit feature title", "text"],
  ["feature_audit_description", "Audit feature content", "textarea"],
  ["footer_text", "Footer text", "text"],
  ["contact_email", "Contact email", "text"],
  ["contact_phone", "Support phone", "text"],
] as const;

const WEBSITE_ASSETS = [
  ["logo", "Site logo"],
  ["favicon", "Browser favicon"],
  ["hero_image", "Landing hero background"],
] as const;
type WebsiteAsset = (typeof WEBSITE_ASSETS)[number][0];

export default function SuperAdminSettingsPage() {
  const { refresh: refreshPublicContent } = useWebsiteContent();
  const [settings, setSettings] = useState<PlatformSettings | null>(null);
  const [website, setWebsite] = useState<WebsiteContent | null>(null);
  const [websiteName, setWebsiteName] = useState("");
  const [websiteCopy, setWebsiteCopy] = useState<Record<string, string>>({});
  const [websiteFiles, setWebsiteFiles] = useState<Partial<Record<WebsiteAsset, File>>>({});
  const [websitePreviews, setWebsitePreviews] = useState<Partial<Record<WebsiteAsset, string>>>({});
  const [removedAssets, setRemovedAssets] = useState<Partial<Record<WebsiteAsset, boolean>>>({});
  const [websiteBusy, setWebsiteBusy] = useState(false);
  const [websiteError, setWebsiteError] = useState("");
  const [websiteNotice, setWebsiteNotice] = useState("");
  const websitePreviewUrls = useRef(new Set<string>());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [form, setForm] = useState({
    registration_open: true,
    require_approval: true,
    maintenance_mode: false,
    announcement: "",
    max_failed_login_attempts: 3,
    lockout_duration_minutes: 180,
    text_messaging_enabled: true,
    voice_messaging_enabled: true,
  });

  const [broadcast, setBroadcast] = useState("");
  const [reason, setReason] = useState("");

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
        max_failed_login_attempts: res.settings.max_failed_login_attempts,
        lockout_duration_minutes: res.settings.lockout_duration_minutes,
        text_messaging_enabled: res.settings.text_messaging_enabled,
        voice_messaging_enabled: res.settings.voice_messaging_enabled,
      });
      setReason("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadWebsite = useCallback(async () => {
    setWebsiteError("");
    try {
      const content = await superAdminApi.websiteContent();
      setWebsite(content);
      setWebsiteName(content.platform_name);
      setWebsiteCopy(content.content);
      setWebsiteFiles({});
      setWebsitePreviews({});
      setRemovedAssets({});
    } catch (err) {
      setWebsiteError(err instanceof Error ? err.message : "Could not load website content.");
    }
  }, []);

  useEffect(() => {
    void load();
    void loadWebsite();
  }, [load, loadWebsite]);

  useEffect(
    () => () => websitePreviewUrls.current.forEach((url) => URL.revokeObjectURL(url)),
    []
  );

  function selectWebsiteAsset(asset: WebsiteAsset, file?: File) {
    setWebsiteError("");
    setWebsiteNotice("");
    const oldPreview = websitePreviews[asset];
    if (oldPreview) {
      URL.revokeObjectURL(oldPreview);
      websitePreviewUrls.current.delete(oldPreview);
    }
    if (!file) {
      setWebsiteFiles((previous) => {
        const next = { ...previous };
        delete next[asset];
        return next;
      });
      setWebsitePreviews((previous) => {
        const next = { ...previous };
        delete next[asset];
        return next;
      });
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setWebsiteError("Website images must be 5 MB or smaller.");
      return;
    }
    const preview = URL.createObjectURL(file);
    websitePreviewUrls.current.add(preview);
    setWebsiteFiles((previous) => ({ ...previous, [asset]: file }));
    setWebsitePreviews((previous) => ({ ...previous, [asset]: preview }));
    setRemovedAssets((previous) => ({ ...previous, [asset]: false }));
  }

  async function saveWebsiteContent() {
    if (!websiteName.trim()) {
      setWebsiteError("Enter a website name.");
      return;
    }
    setWebsiteBusy(true);
    setWebsiteError("");
    setWebsiteNotice("");
    try {
      const payload = new FormData();
      payload.set("platform_name", websiteName.trim());
      payload.set("content", JSON.stringify(websiteCopy));
      Object.entries(websiteFiles).forEach(([asset, file]) => {
        if (file) payload.set(asset, file);
      });
      Object.entries(removedAssets).forEach(([asset, shouldRemove]) => {
        if (shouldRemove) payload.set(`remove_${asset}`, "true");
      });
      const response = await superAdminApi.updateWebsiteContent(payload);
      setWebsite(response.website_content);
      setWebsiteName(response.website_content.platform_name);
      setWebsiteCopy(response.website_content.content);
      setWebsiteFiles({});
      Object.values(websitePreviews).forEach((url) => {
        URL.revokeObjectURL(url);
        websitePreviewUrls.current.delete(url);
      });
      setWebsitePreviews({});
      setRemovedAssets({});
      await refreshPublicContent();
      setWebsiteNotice("Website branding and content saved and published.");
    } catch (err) {
      setWebsiteError(err instanceof Error ? err.message : "Could not save website content.");
    } finally {
      setWebsiteBusy(false);
    }
  }

  function cancelWebsiteChanges() {
    if (!website) return;
    Object.values(websitePreviews).forEach((url) => {
      URL.revokeObjectURL(url);
      websitePreviewUrls.current.delete(url);
    });
    setWebsiteName(website.platform_name);
    setWebsiteCopy(website.content);
    setWebsiteFiles({});
    setWebsitePreviews({});
    setRemovedAssets({});
    setWebsiteError("");
    setWebsiteNotice("");
  }

  async function save() {
    const criticalChange = Boolean(
      settings &&
        (form.maintenance_mode !== settings.maintenance_mode ||
          form.max_failed_login_attempts !== settings.max_failed_login_attempts ||
          form.lockout_duration_minutes !== settings.lockout_duration_minutes ||
          form.text_messaging_enabled !== settings.text_messaging_enabled ||
          form.voice_messaging_enabled !== settings.voice_messaging_enabled)
    );
    if (
      criticalChange &&
      (!reason.trim() ||
        !window.confirm(
          "Apply these security or access policy changes? The change and reason will be recorded in the audit log."
        ))
    ) {
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const res = await superAdminApi.updateSettings({
        ...form,
        ...(criticalChange ? { reason: reason.trim() } : {}),
      });
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
          Global registration, login security, messaging, and operational policies.
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
            title="Website Content and Branding"
            subtitle="Changes are published immediately and shared across the public site and dashboards."
          />
          <div className="space-y-5 p-5">
            {websiteError && <ErrorBanner message={websiteError} onRetry={() => void loadWebsite()} />}
            {websiteNotice && <SuccessBanner message={websiteNotice} />}
            <Field label="Website and platform name" htmlFor="website-platform-name">
              <Input
                id="website-platform-name"
                maxLength={80}
                value={websiteName}
                onChange={(event) => setWebsiteName(event.target.value)}
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-3">
              {WEBSITE_ASSETS.map(([asset, label]) => {
                const preview =
                  websitePreviews[asset] ||
                  (removedAssets[asset] ? "" : website?.[`${asset}_url` as keyof WebsiteContent] as string | null) ||
                  "";
                return (
                  <div key={asset} className="rounded-lg border border-gray-200 p-4">
                    <p className="text-sm font-medium text-gray-800">{label}</p>
                    <div className="my-3 flex h-24 items-center justify-center rounded-md bg-gray-50">
                      {preview ? (
                        <img src={preview} alt={`${label} preview`} className="max-h-20 max-w-full object-contain" />
                      ) : (
                        <span className="text-xs text-gray-400">No image selected</span>
                      )}
                    </div>
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp,image/x-icon"
                      aria-label={`Upload ${label.toLowerCase()}`}
                      onChange={(event) => selectWebsiteAsset(asset, event.target.files?.[0])}
                      className="block w-full text-xs text-gray-600 file:mr-2 file:rounded-md file:border-0 file:bg-green-50 file:px-2.5 file:py-1.5 file:text-xs file:font-medium file:text-green-800"
                    />
                    {preview && (
                      <button
                        type="button"
                        onClick={() => {
                          selectWebsiteAsset(asset);
                          setRemovedAssets((previous) => ({ ...previous, [asset]: true }));
                        }}
                        className="mt-2 text-xs font-medium text-red-700 hover:underline"
                      >
                        Remove image
                      </button>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              {WEBSITE_COPY_FIELDS.map(([key, label, kind]) => (
                <Field key={key} label={label} htmlFor={`website-copy-${key}`}>
                  {kind === "textarea" ? (
                    <Textarea
                      id={`website-copy-${key}`}
                      maxLength={2000}
                      value={websiteCopy[key] ?? ""}
                      onChange={(event) =>
                        setWebsiteCopy((previous) => ({
                          ...previous,
                          [key]: event.target.value,
                        }))
                      }
                    />
                  ) : (
                    <Input
                      id={`website-copy-${key}`}
                      maxLength={2000}
                      value={websiteCopy[key] ?? ""}
                      onChange={(event) =>
                        setWebsiteCopy((previous) => ({
                          ...previous,
                          [key]: event.target.value,
                        }))
                      }
                    />
                  )}
                </Field>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button loading={websiteBusy} onClick={() => void saveWebsiteContent()}>
                Save and publish
              </Button>
              <Button type="button" variant="secondary" disabled={websiteBusy} onClick={cancelWebsiteChanges}>
                Cancel changes
              </Button>
              {website?.updated_at && (
                <p className="text-xs text-gray-500">
                  Last updated {formatDateTime(website.updated_at)}
                  {website.updated_by ? ` by ${website.updated_by}` : ""}
                </p>
              )}
            </div>
            {website && (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Preview</p>
                <p className="mt-2 text-lg font-bold text-gray-900">{websiteCopy.landing_title}</p>
                <p className="mt-1 text-sm text-gray-600">{websiteCopy.landing_subtitle}</p>
                <p className="mt-2 text-xs text-gray-500">{websiteName}</p>
              </div>
            )}
          </div>
        </Card>

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
            title="Login security and communication"
            subtitle="Effective immediately for new login decisions and message sends"
          />
          <div className="space-y-5 p-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Failed password attempts before lockout"
                htmlFor="max-failed-login-attempts"
                hint="Between 1 and 20 consecutive failures. A successful password resets the counter."
              >
                <Input
                  id="max-failed-login-attempts"
                  type="number"
                  min={1}
                  max={20}
                  value={form.max_failed_login_attempts}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      max_failed_login_attempts: Number(event.target.value),
                    })
                  }
                />
              </Field>
              <Field
                label="Lockout duration (minutes)"
                htmlFor="lockout-duration"
                hint="Between 1 and 10,080 minutes (7 days). Existing lockouts keep their original expiry."
              >
                <Input
                  id="lockout-duration"
                  type="number"
                  min={1}
                  max={10080}
                  value={form.lockout_duration_minutes}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      lockout_duration_minutes: Number(event.target.value),
                    })
                  }
                />
              </Field>
            </div>

            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={form.text_messaging_enabled}
                onChange={(event) =>
                  setForm({ ...form, text_messaging_enabled: event.target.checked })
                }
                className="mt-0.5 h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
              />
              <span>
                <span className="block text-sm font-medium text-gray-900">
                  Text messaging enabled
                </span>
                <span className="block text-xs text-gray-500">
                  When disabled, new text messages are rejected over REST and WebSocket.
                </span>
              </span>
            </label>
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={form.voice_messaging_enabled}
                onChange={(event) =>
                  setForm({ ...form, voice_messaging_enabled: event.target.checked })
                }
                className="mt-0.5 h-4 w-4 rounded border-gray-300 text-green-600 focus:ring-green-500"
              />
              <span>
                <span className="block text-sm font-medium text-gray-900">
                  Voice messaging enabled
                </span>
                <span className="block text-xs text-gray-500">
                  When disabled, new voice recordings cannot be submitted.
                </span>
              </span>
            </label>

            <Field
              label="Reason for security or access policy changes"
              htmlFor="settings-reason"
              hint="Required and included in the audit record when changing lockout, maintenance, or messaging policies."
            >
              <Textarea
                id="settings-reason"
                value={reason}
                maxLength={500}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Explain why this policy change is needed."
              />
            </Field>
            <div className="flex flex-wrap items-center gap-3">
              <Button
                loading={busy}
                icon={<Save className="h-4 w-4" />}
                onClick={() => void save()}
              >
                Save policies
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={busy}
                onClick={() => void load()}
              >
                Cancel changes
              </Button>
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
