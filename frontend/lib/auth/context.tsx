"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import {
  authApi,
  clearTokens,
  getAccessToken,
  setAccessToken,
  setAuthFailureHandler,
  type RegisterPayload,
} from "@/lib/api/client";
import type { User, UserRole } from "@/lib/types";

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (data: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  hasPermission: (perm: string) => boolean;
  hasRole: (...roles: UserRole[]) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const USER_KEY = "greenpath_user";

function readStoredUser(): User | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
  });

  const hardLogout = useCallback(() => {
    clearTokens();
    localStorage.removeItem(USER_KEY);
    setState({ user: null, isLoading: false, isAuthenticated: false });
    router.push("/login");
  }, [router]);

  // A 401 that survives a refresh attempt means the session is gone.
  useEffect(() => {
    setAuthFailureHandler(() => {
      setState({ user: null, isLoading: false, isAuthenticated: false });
    });
    return () => setAuthFailureHandler(null);
  }, []);

  // Restore on mount, then verify against /auth/me/.
  useEffect(() => {
    let cancelled = false;

    async function restore() {
      setAccessToken(getAccessToken());
      const stored = readStoredUser();

      if (!stored) {
        if (!cancelled) {
          setState({ user: null, isLoading: false, isAuthenticated: false });
        }
        return;
      }

      // Optimistic so the shell can render, then confirm.
      if (!cancelled) {
        setState({ user: stored, isLoading: true, isAuthenticated: true });
      }

      try {
        const data = await authApi.me();
        if (cancelled) return;
        if (data.success && data.user) {
          localStorage.setItem(USER_KEY, JSON.stringify(data.user));
          setState({
            user: data.user,
            isLoading: false,
            isAuthenticated: true,
          });
        } else {
          hardLogout();
        }
      } catch {
        if (!cancelled) {
          clearTokens();
          localStorage.removeItem(USER_KEY);
          setState({ user: null, isLoading: false, isAuthenticated: false });
        }
      }
    }

    void restore();
    return () => {
      cancelled = true;
    };
  }, [hardLogout]);

  const login = useCallback(
    async (email: string, password: string) => {
      const data = await authApi.login(email, password);
      if (!data.success || !data.access || !data.user) {
        throw new Error("Login failed");
      }

      setAccessToken(data.access);

      // The login payload is a 10-key subset; /auth/me/ gives the full record.
      const optimistic = {
        ...data.user,
        latitude: null,
        longitude: null,
        rejection_reason: "",
        privacy_policy_accepted: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      } as User;

      localStorage.setItem(USER_KEY, JSON.stringify(optimistic));
      setState({
        user: optimistic,
        isLoading: false,
        isAuthenticated: true,
      });

      try {
        const me = await authApi.me();
        if (me.success && me.user) {
          localStorage.setItem(USER_KEY, JSON.stringify(me.user));
          setState({ user: me.user, isLoading: false, isAuthenticated: true });
        }
      } catch {
        /* keep the optimistic record */
      }

      router.push(getDashboardRoute(data.user.role));
    },
    [router]
  );

  const register = useCallback(
    async (payload: RegisterPayload) => {
      await authApi.register(payload);
      router.push("/login?registered=true");
    },
    [router]
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      /* ignore — clear locally regardless */
    }
    hardLogout();
  }, [hardLogout]);

  const refreshUser = useCallback(async () => {
    try {
      const data = await authApi.me();
      if (data.success && data.user) {
        localStorage.setItem(USER_KEY, JSON.stringify(data.user));
        setState((prev) => ({ ...prev, user: data.user }));
      }
    } catch {
      /* ignore */
    }
  }, []);

  const permissions = useMemo(
    () => state.user?.permissions ?? [],
    [state.user]
  );

  const hasPermission = useCallback(
    (perm: string) => permissions.includes("*") || permissions.includes(perm),
    [permissions]
  );

  const hasRole = useCallback(
    (...roles: UserRole[]) =>
      state.user ? roles.includes(state.user.role) : false,
    [state.user]
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      ...state,
      login,
      register,
      logout,
      refreshUser,
      hasPermission,
      hasRole,
    }),
    [state, login, register, logout, refreshUser, hasPermission, hasRole]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

export function getDashboardRoute(role: UserRole): string {
  switch (role) {
    case "FARMER":
      return "/farmer";
    case "WHOLESALER":
      return "/wholesaler";
    case "RETAILER":
      return "/retailer";
    case "USER_ADMIN":
      return "/admin";
    case "FINANCIAL_MANAGER":
      return "/financial-manager";
    case "SUPER_ADMIN":
      return "/super-admin";
    default:
      return "/login";
  }
}

export interface NavItem {
  label: string;
  href: string;
  icon: string;
  group?: string;
}

/** Role-specific navigation data consumed by the shared dashboard sidebar. */
export const farmerNav: NavItem[] = [
  { label: "Dashboard", href: "/farmer", icon: "LayoutDashboard", group: "Overview" },
  { label: "Post New Product", href: "/farmer/new-product", icon: "PackagePlus", group: "Marketplace" },
  { label: "My Listings", href: "/farmer/listings", icon: "ListChecks", group: "Marketplace" },
  { label: "Orders", href: "/farmer/orders", icon: "ClipboardList", group: "Marketplace" },
  { label: "Agreements", href: "/agreements", icon: "FileText", group: "Marketplace" },
  { label: "Wallet", href: "/wallet", icon: "CreditCard", group: "Finance" },
  { label: "Transactions", href: "/transactions", icon: "FileText", group: "Finance" },
  { label: "Reviews", href: "/reviews", icon: "Heart", group: "Communication" },
  { label: "Messages", href: "/chat", icon: "MessageSquare", group: "Communication" },
  { label: "Notifications", href: "/notifications", icon: "Bell", group: "Communication" },
  { label: "Profile", href: "/profile", icon: "User", group: "Account" },
  { label: "Settings", href: "/settings", icon: "Settings", group: "Account" },
];

export const wholesalerNav: NavItem[] = [
  { label: "Dashboard", href: "/wholesaler", icon: "LayoutDashboard", group: "Overview" },
  { label: "Browse Products", href: "/wholesaler/browse", icon: "ShoppingBag", group: "Marketplace" },
  { label: "Orders", href: "/wholesaler/orders", icon: "ClipboardList", group: "Marketplace" },
  { label: "My Listings", href: "/wholesaler/listings", icon: "ListChecks", group: "Marketplace" },
  { label: "Agreements", href: "/agreements", icon: "FileText", group: "Marketplace" },
  { label: "Wallet", href: "/wallet", icon: "CreditCard", group: "Finance" },
  { label: "Transactions", href: "/transactions", icon: "FileText", group: "Finance" },
  { label: "Reviews", href: "/reviews", icon: "Heart", group: "Communication" },
  { label: "Messages", href: "/chat", icon: "MessageSquare", group: "Communication" },
  { label: "Notifications", href: "/notifications", icon: "Bell", group: "Communication" },
  { label: "Profile", href: "/profile", icon: "User", group: "Account" },
  { label: "Settings", href: "/settings", icon: "Settings", group: "Account" },
];

export const retailerNav: NavItem[] = [
  { label: "Dashboard", href: "/retailer", icon: "LayoutDashboard", group: "Overview" },
  { label: "Browse Products", href: "/retailer/browse", icon: "ShoppingBag", group: "Marketplace" },
  { label: "Orders", href: "/retailer/orders", icon: "ClipboardList", group: "Marketplace" },
  { label: "Agreements", href: "/agreements", icon: "FileText", group: "Marketplace" },
  { label: "Wallet", href: "/wallet", icon: "CreditCard", group: "Finance" },
  { label: "Transactions", href: "/transactions", icon: "FileText", group: "Finance" },
  { label: "Reviews", href: "/reviews", icon: "Heart", group: "Communication" },
  { label: "Messages", href: "/chat", icon: "MessageSquare", group: "Communication" },
  { label: "Notifications", href: "/notifications", icon: "Bell", group: "Communication" },
  { label: "Profile", href: "/profile", icon: "User", group: "Account" },
  { label: "Settings", href: "/settings", icon: "Settings", group: "Account" },
];

/** User Admin navigation uses the existing role-protected admin routes. */
export const adminNav: NavItem[] = [
  { label: "Dashboard", href: "/admin", icon: "Gauge", group: "Overview" },
  { label: "Pending Approvals", href: "/admin/approvals", icon: "UserCheck", group: "User Administration" },
  { label: "Users", href: "/admin/users", icon: "Users", group: "User Administration" },
  { label: "Listings", href: "/admin/listings", icon: "Tag", group: "Marketplace" },
  { label: "Messages", href: "/chat", icon: "MessageSquare", group: "Communication" },
  { label: "Notifications", href: "/notifications", icon: "Bell", group: "Communication" },
  { label: "Profile", href: "/profile", icon: "User", group: "Account" },
  { label: "Settings", href: "/settings", icon: "Settings", group: "Account" },
];

export const finManagerNav: NavItem[] = [
  { label: "Dashboard", href: "/financial-manager", icon: "Gauge", group: "Overview" },
  { label: "Payments", href: "/financial-manager/payments", icon: "CreditCard", group: "Operations" },
  { label: "Deposits", href: "/financial-manager/deposits", icon: "CreditCard", group: "Operations" },
  { label: "Payouts", href: "/financial-manager/payouts", icon: "CreditCard", group: "Operations" },
  { label: "Wallet Activity", href: "/transactions", icon: "CreditCard", group: "Operations" },
  { label: "Bank Accounts", href: "/financial-manager/bank-accounts", icon: "Landmark", group: "Operations" },
  { label: "Reports & Analytics", href: "/financial-manager/reports", icon: "BarChart3", group: "Reporting" },
  { label: "Messages", href: "/chat", icon: "MessageSquare", group: "Communication" },
  { label: "Notifications", href: "/notifications", icon: "Bell", group: "Communication" },
  { label: "Profile", href: "/profile", icon: "User", group: "Account" },
  { label: "Settings", href: "/settings", icon: "Settings", group: "Account" },
];

export const superAdminNav: NavItem[] = [
  { label: "Dashboard", href: "/super-admin", icon: "Gauge", group: "Overview" },
  { label: "Users", href: "/super-admin/users", icon: "Users", group: "Administration" },
  { label: "Listings", href: "/super-admin/listings", icon: "Tag", group: "Marketplace" },
  { label: "Payments", href: "/super-admin/payments", icon: "CreditCard", group: "Marketplace" },
  { label: "Reports", href: "/super-admin/reports", icon: "BarChart3", group: "Reporting" },
  { label: "Audit Logs", href: "/super-admin/audit", icon: "FileText", group: "Reporting" },
  { label: "Messages", href: "/chat", icon: "MessageSquare", group: "Communication" },
  { label: "Notifications", href: "/notifications", icon: "Bell", group: "Communication" },
  { label: "Profile", href: "/profile", icon: "User", group: "Account" },
  { label: "Settings", href: "/super-admin/settings", icon: "Settings", group: "Account" },
];

export function getNavItems(role: UserRole): NavItem[] {
  switch (role) {
    case "FARMER":
      return farmerNav;
    case "WHOLESALER":
      return wholesalerNav;
    case "RETAILER":
      return retailerNav;
    case "USER_ADMIN":
      return adminNav;
    case "FINANCIAL_MANAGER":
      return finManagerNav;
    case "SUPER_ADMIN":
      return superAdminNav;
    default:
      return farmerNav;
  }
}

/** All authenticated dashboard roles use the shared sidebar shell. */
export function usesSidebar(role: UserRole): boolean {
  return [
    "FARMER",
    "WHOLESALER",
    "RETAILER",
    "USER_ADMIN",
    "FINANCIAL_MANAGER",
    "SUPER_ADMIN",
  ].includes(role);
}
