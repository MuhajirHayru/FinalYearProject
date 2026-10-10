"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  Bell,
  Leaf,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  ShieldAlert,
  X,
} from "lucide-react";
import { getNavItems, useAuth, usesSidebar, type NavItem } from "@/lib/auth/context";
import { ICONS, shortRelative } from "@/lib/format";
import { authApi, notificationsApi } from "@/lib/api/client";
import { Avatar, Spinner } from "@/components/ui";
import { PresenceProvider } from "@/components/presence/PresenceProvider";
import { cn } from "@/lib/utils";
import type { Notification, UserRole } from "@/lib/types";

// ---------------------------------------------------------------------------
// Shared unread count
//
// The bell and sidebar share one poller instead of each opening their own
// 30-second interval against the same endpoint.
// ---------------------------------------------------------------------------

interface UnreadContextValue {
  count: number;
  refresh: () => void;
}

const UnreadContext = createContext<UnreadContextValue>({
  count: 0,
  refresh: () => undefined,
});

function UnreadProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [count, setCount] = useState(0);
  const [nonce, setNonce] = useState(0);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!isAuthenticated) {
      setCount(0);
      return;
    }
    let cancelled = false;

    const load = async () => {
      try {
        const data = await notificationsApi.unreadCount();
        if (!cancelled) setCount(data.unread_count ?? 0);
      } catch {
        // The badge is best-effort; a failure must not break the shell.
      }
    };

    void load();
    const timer = setInterval(load, 30_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [isAuthenticated, nonce]);

  const value = useMemo(() => ({ count, refresh }), [count, refresh]);
  return <UnreadContext.Provider value={value}>{children}</UnreadContext.Provider>;
}

function useUnread() {
  return useContext(UnreadContext);
}

/**
 * Exposed so pages rendered inside `<AppShell>` (e.g. `/notifications`) can
 * refresh the shared bell/sidebar counter after marking items read.
 */
export function useNotifications() {
  return useUnread();
}

// ---------------------------------------------------------------------------
// Full page loader shown while auth or the role guard resolves
// ---------------------------------------------------------------------------

function FullPageLoader() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <Spinner className="h-8 w-8" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Notification bell with a peek popover (Fig 4.6 header)
// ---------------------------------------------------------------------------

function NotificationBell() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const { count, refresh } = useUnread();

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);

    notificationsApi
      .list(1)
      .then((data) => {
        if (!cancelled) setItems(data.results.slice(0, 8));
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open]);

  async function markAll() {
    try {
      await notificationsApi.markAllRead();
      setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
      refresh();
    } catch {
      // Ignore: the next poll will correct the badge.
    }
  }

  async function openNotification(notification: Notification) {
    try {
      if (!notification.is_read) {
        await notificationsApi.markRead(notification.id);
        setItems((prev) =>
          prev.map((item) =>
            item.id === notification.id ? { ...item, is_read: true } : item
          )
        );
        refresh();
      }
      setOpen(false);
      router.push(notification.target_url || "/notifications");
    } catch {
      setOpen(false);
      router.push("/notifications");
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label={`Notifications${count ? `, ${count} unread` : ""}`}
        aria-expanded={open}
        className="relative flex h-10 w-10 items-center justify-center rounded-lg text-gray-600 hover:bg-gray-100"
      >
        <Bell className="h-5 w-5" />
        {count > 0 && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} aria-hidden />
          <div className="absolute right-0 z-30 mt-2 w-80 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
              <p className="text-sm font-semibold text-gray-900">Notifications</p>
              {count > 0 && (
                <button
                  onClick={markAll}
                  className="text-xs font-medium text-green-700 hover:underline"
                >
                  Mark all read
                </button>
              )}
            </div>
            <div className="max-h-80 overflow-y-auto">
              {loading ? (
                <p className="px-4 py-6 text-center text-sm text-gray-500">Loading...</p>
              ) : items.length === 0 ? (
                <p className="px-4 py-6 text-center text-sm text-gray-500">
                  You&apos;re all caught up.
                </p>
              ) : (
                <ul className="divide-y divide-gray-100">
                  {items.map((n) => (
                    <li
                      key={n.id}
                      className={cn("px-4 py-3", !n.is_read && "bg-green-50/50")}
                    >
                      <button
                        type="button"
                        className="w-full text-left"
                        onClick={() => void openNotification(n)}
                      >
                        <span className="block text-sm text-gray-800">{n.message}</span>
                        <span className="mt-0.5 block text-xs text-gray-500">
                          {shortRelative(n.created_at)}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <Link
              href="/notifications"
              onClick={() => setOpen(false)}
              className="block border-t border-gray-100 px-4 py-2.5 text-center text-sm font-medium text-green-700 hover:bg-gray-50"
            >
              View all
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// User chip with profile / settings / logout
// ---------------------------------------------------------------------------

function UserChip() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  if (!user) return null;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 hover:bg-gray-100"
      >
        <Avatar name={user.full_name} size="sm" src={user.profile_photo} />
        <span className="hidden text-left leading-tight sm:block">
          <span className="block text-sm font-semibold text-gray-900">
            {user.full_name}
          </span>
          <span className="block text-xs text-gray-500">{user.role_display}</span>
        </span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-20" onClick={() => setOpen(false)} aria-hidden />
          <div className="absolute right-0 z-30 mt-2 w-56 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl">
            <div className="border-b border-gray-100 px-4 py-3">
              <p className="truncate text-sm font-semibold text-gray-900">
                {user.full_name}
              </p>
              <p className="truncate text-xs text-gray-500">{user.email}</p>
            </div>
            <Link
              href="/profile"
              onClick={() => setOpen(false)}
              className="block px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50"
            >
              Profile
            </Link>
            <Link
              href="/settings"
              onClick={() => setOpen(false)}
              className="block px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50"
            >
              Settings
            </Link>
            <button
              onClick={() => {
                setOpen(false);
                void logout();
              }}
              className="flex w-full items-center gap-2 border-t border-gray-100 px-4 py-2.5 text-left text-sm text-red-600 hover:bg-red-50"
            >
              <LogOut className="h-4 w-4" />
              Logout
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared nav link rendering
// ---------------------------------------------------------------------------

function useNavState() {
  const pathname = usePathname();

  return useCallback(
    (item: NavItem) =>
      pathname === item.href ||
      (item.href !== "/" && pathname.startsWith(`${item.href}/`)),
    [pathname]
  );
}

const BADGED_LABELS = new Set(["Notifications"]);

function NavBadge({ label }: { label: string }) {
  const { count } = useUnread();
  if (!BADGED_LABELS.has(label) || count <= 0) return null;
  return (
    <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
      {count > 99 ? "99+" : count}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Shared green sidebar for every authenticated dashboard role
// ---------------------------------------------------------------------------

function Sidebar({
  items,
  collapsed,
  mobileOpen,
  onClose,
  onToggleCollapsed,
}: {
  items: NavItem[];
  collapsed: boolean;
  mobileOpen: boolean;
  onClose: () => void;
  onToggleCollapsed: () => void;
}) {
  const isActive = useNavState();
  const { logout } = useAuth();
  let previousGroup: string | undefined;

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-40 bg-gray-950/40 md:hidden"
          onClick={onClose}
        />
      )}
      <aside
        id="dashboard-sidebar"
        aria-label="Main navigation"
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-60 shrink-0 flex-col border-r border-green-800 bg-green-700 transition-[width,transform] duration-200 md:static md:z-auto md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          collapsed ? "md:w-20" : "md:w-60 xl:w-64"
        )}
      >
        <div
          className={cn(
            "flex h-16 shrink-0 items-center gap-2 border-b border-green-800 px-5 text-white",
            collapsed && "md:justify-center md:px-2"
          )}
        >
          <Link href="/" onClick={onClose} className="flex min-w-0 items-center gap-2">
            <Leaf className="h-6 w-6 shrink-0" />
            <span className={cn("truncate text-lg font-semibold", collapsed && "md:hidden")}>
              Green Path
            </span>
          </Link>
          <button
            type="button"
            onClick={onToggleCollapsed}
            className="ml-auto hidden rounded-lg p-2 text-green-50 hover:bg-green-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white md:block"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto rounded-lg p-2 text-green-50 hover:bg-green-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white md:hidden"
            aria-label="Close navigation"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex flex-1 flex-col gap-1 overflow-y-auto p-3">
          {items.map((item) => {
            const Icon = ICONS[item.icon] ?? ICONS.LayoutDashboard;
            const active = isActive(item);
            const showGroup = item.group && item.group !== previousGroup;
            previousGroup = item.group;

            return (
              <div key={item.href}>
                {showGroup && (
                  <p
                    className={cn(
                      "px-3 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-green-200",
                      collapsed && "md:sr-only"
                    )}
                  >
                    {item.group}
                  </p>
                )}
                <Link
                  href={item.href}
                  onClick={onClose}
                  aria-current={active ? "page" : undefined}
                  aria-label={collapsed ? item.label : undefined}
                  title={collapsed ? item.label : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors hover:bg-green-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white",
                    active ? "bg-white text-green-800 hover:bg-white" : "text-green-50",
                    collapsed && "md:justify-center md:px-2"
                  )}
                >
                  <Icon className="h-5 w-5 shrink-0" />
                  <span className={cn("flex-1 truncate", collapsed && "md:hidden")}>
                    {item.label}
                  </span>
                  <span className={cn(collapsed && "md:hidden")}>
                    <NavBadge label={item.label} />
                  </span>
                </Link>
              </div>
            );
          })}

          <button
            onClick={() => void logout()}
            className={cn(
              "mt-auto flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-green-50 transition-colors hover:bg-green-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white",
              collapsed && "md:justify-center md:px-2"
            )}
            aria-label={collapsed ? "Logout" : undefined}
            title={collapsed ? "Logout" : undefined}
          >
            <LogOut className="h-5 w-5 shrink-0" />
            <span className={cn(collapsed && "md:hidden")}>Logout</span>
          </button>
        </nav>
      </aside>
    </>
  );
}

// ---------------------------------------------------------------------------
// Header for sidebar roles
// ---------------------------------------------------------------------------

function Header({
  title,
  onOpenNavigation,
}: {
  title: string;
  onOpenNavigation: () => void;
}) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-gray-200 bg-white px-5 lg:px-8">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onOpenNavigation}
          className="rounded-lg p-2 text-gray-600 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-600 md:hidden"
          aria-label="Open navigation"
          aria-controls="dashboard-sidebar"
        >
          <Menu className="h-5 w-5" />
        </button>
        <h1 className="truncate text-lg font-bold text-gray-900 lg:text-xl">{title}</h1>
      </div>
      <div className="flex items-center gap-2 lg:gap-4">
        <NotificationBell />
        <UserChip />
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// Super-admin announcement banner
// ---------------------------------------------------------------------------

function Announcement() {
  const [text, setText] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    authApi
      .announcement()
      .then((data) => {
        if (!cancelled && data.announcement) setText(data.announcement);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (!text) return null;

  return (
    <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-5 py-2 text-sm text-amber-800 lg:px-8">
      <ShieldAlert className="h-4 w-4 shrink-0" />
      <span className="min-w-0 flex-1 truncate">{text}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AppShell: auth gate + role guard + role-appropriate chrome
// ---------------------------------------------------------------------------

export function AppShell({
  title,
  children,
  allow,
}: {
  title: string;
  children: ReactNode;
  allow: UserRole[];
}) {
  const { user, isLoading, isAuthenticated } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Pages pass `allow` as an inline array literal, so it changes identity on
  // every render. The guard is driven off the serialised key instead, which
  // keeps the effect and the render check in sync without re-firing.
  const allowKey = allow.join(",");
  const allowed = allowKey ? (allowKey.split(",") as UserRole[]) : [];

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      router.replace("/login");
    } else if (user && !allowKey.split(",").includes(user.role)) {
      router.replace("/forbidden");
    }
  }, [isLoading, isAuthenticated, user, allowKey, router]);

  useEffect(() => {
    setMobileNavigationOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileNavigationOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileNavigationOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [mobileNavigationOpen]);

  if (isLoading || !isAuthenticated || !user) {
    return <FullPageLoader />;
  }
  if (!allowed.includes(user.role)) {
    return <FullPageLoader />;
  }

  const items = getNavItems(user.role);
  const sidebar = usesSidebar(user.role);

  return (
    <PresenceProvider>
      <UnreadProvider>
        <div className="flex h-screen overflow-hidden bg-gray-50 text-gray-900">
          {sidebar && (
            <Sidebar
              items={items}
              collapsed={sidebarCollapsed}
              mobileOpen={mobileNavigationOpen}
              onClose={() => setMobileNavigationOpen(false)}
              onToggleCollapsed={() => setSidebarCollapsed((value) => !value)}
            />
          )}
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
            <Header
              title={title}
              onOpenNavigation={() => setMobileNavigationOpen(true)}
            />
            <Announcement />
            <main className="flex-1 overflow-y-auto p-5 lg:p-8">{children}</main>
          </div>
        </div>
      </UnreadProvider>
    </PresenceProvider>
  );
}
