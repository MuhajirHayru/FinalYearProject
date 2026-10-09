"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, Check, CheckCheck, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Button,
  Card,
  CardHeader,
  EmptyState,
  ErrorBanner,
  PageLoader,
  Pagination,
  StatusPill,
} from "@/components/ui";
import { notificationsApi } from "@/lib/api/client";
import { useNotifications } from "@/components/layout/AppShell";
import { formatDateTime } from "@/lib/format";
import type { Notification } from "@/lib/types";

export default function NotificationsPage() {
  const router = useRouter();
  const { refresh } = useNotifications();
  const [rows, setRows] = useState<Notification[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await notificationsApi.list(page);
      setRows(res.results);
      setCount(res.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load notifications.");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    void load();
  }, [load]);

  async function markAll() {
    setBusy(true);
    try {
      await notificationsApi.markAllRead();
      await load();
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not mark all as read.");
    } finally {
      setBusy(false);
    }
  }

  async function markOne(id: string) {
    setRows((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
    try {
      await notificationsApi.markRead(id);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update notification.");
      void load();
    }
  }

  async function openNotification(notification: Notification) {
    if (!notification.is_read) await markOne(notification.id);
    if (notification.target_url) router.push(notification.target_url);
  }

  const unread = rows.filter((n) => !n.is_read).length;

  return (
    <AppShell title="Notifications" allow={["FARMER", "WHOLESALER", "RETAILER", "USER_ADMIN", "FINANCIAL_MANAGER", "SUPER_ADMIN"]}>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Notifications</h2>
          <p className="mt-1 text-sm text-gray-500">
            {unread > 0 ? `${unread} unread on this page.` : "You are all caught up."}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            icon={<RefreshCw className="h-4 w-4" />}
            onClick={() => void load()}
          >
            Refresh
          </Button>
          <Button
            icon={<CheckCheck className="h-4 w-4" />}
            loading={busy}
            disabled={unread === 0}
            onClick={() => void markAll()}
          >
            Mark all read
          </Button>
        </div>
      </div>

      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} onRetry={() => void load()} />
        </div>
      )}

      {loading ? (
        <PageLoader />
      ) : rows.length === 0 ? (
        <Card>
          <EmptyState
            title="No notifications"
            description="Order, payment, approval and message activity shows up here."
            icon={<Bell className="h-8 w-8" />}
          />
        </Card>
      ) : (
        <Card>
          <ul className="divide-y divide-gray-100">
            {rows.map((n) => (
              <li
                key={n.id}
                className={`flex items-start gap-4 px-5 py-4 ${
                  n.is_read ? "bg-white" : "bg-green-50/40"
                }`}
              >
                <span
                  className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                    n.is_read ? "bg-gray-200" : "bg-green-600"
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusPill value={n.type} kind="neutral" />
                    <span className="text-xs text-gray-400">
                      {formatDateTime(n.created_at)}
                    </span>
                  </div>
                  <p className="mt-1.5 text-sm text-gray-800">{n.message}</p>
                  {n.target_url && (
                    <button
                      type="button"
                      onClick={() => void openNotification(n)}
                      className="mt-1.5 inline-block text-xs font-medium text-green-700 hover:underline"
                    >
                      View
                    </button>
                  )}
                </div>
                {!n.is_read && (
                  <button
                    onClick={() => void markOne(n.id)}
                    title="Mark as read"
                    className="shrink-0 rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
                  >
                    <Check className="h-4 w-4" />
                  </button>
                )}
              </li>
            ))}
          </ul>
          <Pagination page={page} count={count} onPage={setPage} />
        </Card>
      )}
    </AppShell>
  );
}
