"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Megaphone } from "lucide-react";
import { Button, Card, ErrorBanner, PageLoader } from "@/components/ui";
import { authApi } from "@/lib/api/client";
import { formatDateTime } from "@/lib/format";
import type { PlatformSettings } from "@/lib/types";

/**
 * The public announcement board. Reads the same banner that `AppShell` shows
 * to signed-in users, so the message is identical in both places.
 */
export default function PublicAnnouncementPage() {
  const [announcement, setAnnouncement] = useState("");
  const [maintenance, setMaintenance] = useState(false);
  const [settings, setSettings] = useState<PlatformSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      authApi.announcement(),
      superAdminSettings().catch(() => null),
    ])
      .then(([pub, admin]) => {
        if (cancelled) return;
        setAnnouncement(pub.announcement ?? "");
        setMaintenance(Boolean(pub.maintenance_mode));
        setSettings(admin);
      })
      .catch((err) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Could not load the announcement.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
        <PageLoader label="Loading announcement." />
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <Card className="w-full max-w-2xl p-8">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-green-50">
          <Megaphone className="h-6 w-6 text-green-700" />
        </span>
        <h1 className="mt-4 text-2xl font-bold text-gray-900">Public Announcement</h1>

        {error && (
          <div className="mt-5">
            <ErrorBanner message={error} />
          </div>
        )}

        {maintenance && (
          <div className="mt-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            GreenPath is currently in maintenance mode. Some actions may be
            temporarily unavailable.
          </div>
        )}

        {announcement ? (
          <p className="mt-5 whitespace-pre-wrap text-base leading-relaxed text-gray-700">
            {announcement}
          </p>
        ) : (
          <p className="mt-5 text-sm text-gray-600">
            There is no announcement at the moment. Check back later.
          </p>
        )}

        {settings?.updated_at && (
          <p className="mt-6 text-xs text-gray-400">
            Published {formatDateTime(settings.updated_at)}
            {settings.updated_by ? ` by ${settings.updated_by}` : ""}
          </p>
        )}

        <div className="mt-7">
          <Link href="/">
            <Button variant="secondary">Back to home</Button>
          </Link>
        </div>
      </Card>
    </main>
  );
}

async function superAdminSettings() {
  const { superAdminApi } = await import("@/lib/api/client");
  const res = await superAdminApi.settings();
  return res.settings;
}
