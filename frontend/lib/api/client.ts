/**
 * API client for GreenPath.
 *
 * The backend is NOT consistent about envelopes, so each call below is typed to
 * match what the view actually returns:
 *
 *   - list endpoints  -> bare `Paginated<T>` (count/next/previous/results)
 *   - most detail     -> bare serializer object, no `success` key
 *   - actions         -> `{ success: true, <resource>: T }`
 *
 * Errors are always `{ success: false, error: string | Record<string, string[]> }`.
 */
import type {
  AdminAccount,
  AdminDashboardData,
  AdminAccount as AdminAccountType,
  AuditLog,
  CategoryUnitMeta,
  ChatChannel,
  DirectoryUser,
  FarmerDashboardData,
  FinancialReport,
  FinancialReportQuery,
  LoginResponse,
  LoginUser,
  MeResponse,
  Message,
  Notification,
  Order,
  OrderStatus,
  Paginated,
  PaymentQuery,
  PaymentRecord,
  PaymentStatus,
  PaymentSummaryData,
  PlatformSettings,
  Product,
  ProductCreate,
  ProductQuery,
  RegisterResponse,
  RetailerDashboardData,
  SuperAdminDecision,
  SuperAdminHealth,
  SuperAdminResource,
  SuperAdminRow,
  TransactionVolume,
  User,
  WholesalerDashboardData,
  WithResource,
} from "@/lib/types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export const WS_BASE = (
  process.env.NEXT_PUBLIC_WS_URL || "http://localhost:8000"
).replace(/^http/, "ws");

const ACCESS_KEY = "greenpath_access";
const REFRESH_KEY = "greenpath_refresh";

// ---------------------------------------------------------------------------
// Token storage — access token in sessionStorage, refresh in an httpOnly cookie
// ---------------------------------------------------------------------------

let accessToken: string | null = null;
let refreshPromise: Promise<string | null> | null = null;
let onAuthFailure: (() => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
  if (typeof window === "undefined") return;
  if (token) {
    sessionStorage.setItem(ACCESS_KEY, token);
  } else {
    sessionStorage.removeItem(ACCESS_KEY);
  }
}

export function getAccessToken() {
  return accessToken;
}

export function clearTokens() {
  accessToken = null;
  if (typeof window !== "undefined") {
    sessionStorage.removeItem(ACCESS_KEY);
  }
}

/** Lets the auth context react to a terminal refresh failure. */
export function setAuthFailureHandler(handler: (() => void) | null) {
  onAuthFailure = handler;
}

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

/** Flattens DRF's `{ field: [messages] }` shape into one readable line. */
export function extractErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const record = payload as Record<string, unknown>;

  for (const key of ["error", "detail", "message"]) {
    const value = record[key];
    if (typeof value === "string" && value) return value;
    if (value && typeof value === "object") {
      const flat = Object.entries(value as Record<string, unknown>)
        .map(([field, messages]) => {
          if (Array.isArray(messages)) {
            return `${field}: ${messages.join(" ")}`;
          }
          return `${field}: ${String(messages)}`;
        })
        .filter(Boolean);
      if (flat.length) return flat.join(" · ");
    }
  }
  return fallback;
}

export class ApiRequestError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.payload = payload;
  }
}

// ---------------------------------------------------------------------------
// Core fetch with silent refresh
// ---------------------------------------------------------------------------

async function rawRequest(
  endpoint: string,
  options: RequestInit = {},
  _retried = false
): Promise<Response> {
  const url = `${API_BASE}${endpoint}`;
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const res = await fetch(url, {
    ...options,
    headers,
    // Required so the httpOnly refresh cookie is sent with every call.
    credentials: "include",
  });

  if (res.status === 401 && !_retried) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      return rawRequest(endpoint, options, true);
    }
  }
  return res;
}

async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const res = await rawRequest(endpoint, options);

  if (!res.ok) {
    let payload: unknown = null;
    try {
      payload = await res.json();
    } catch {
      /* non-JSON error body */
    }
    const message = extractErrorMessage(
      payload,
      `Request failed: ${res.status} ${res.statusText}`
    );
    throw new ApiRequestError(message, res.status, payload);
  }

  if (res.status === 204) return {} as T;

  const text = await res.text();
  if (!text) return {} as T;
  return JSON.parse(text) as T;
}

function qs(params?: Record<string, string | number | undefined | null>) {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const out = search.toString();
  return out ? `?${out}` : "";
}

function toParams<T extends object>(query?: T) {
  if (!query) return undefined;
  return Object.fromEntries(
    Object.entries(query).filter(
      ([, v]) => v !== undefined && v !== null && v !== "" && v !== "ALL"
    )
  ) as Record<string, string>;
}

function get<T>(endpoint: string, params?: Record<string, string | number | undefined>) {
  return apiFetch<T>(`${endpoint}${qs(params)}`);
}

function post<T>(endpoint: string, body?: unknown) {
  return apiFetch<T>(endpoint, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function patch<T>(endpoint: string, body?: unknown) {
  return apiFetch<T>(endpoint, {
    method: "PATCH",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function del<T>(endpoint: string) {
  return apiFetch<T>(endpoint, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Token refresh
// ---------------------------------------------------------------------------

async function tryRefreshToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/token/refresh/`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        clearTokens();
        onAuthFailure?.();
        return null;
      }
      const data = (await res.json()) as { success?: boolean; access?: string };
      if (data.success && data.access) {
        setAccessToken(data.access);
        return data.access;
      }
      clearTokens();
      onAuthFailure?.();
      return null;
    } catch {
      clearTokens();
      onAuthFailure?.();
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface RegisterPayload {
  full_name: string;
  email: string;
  password: string;
  role: string;
  privacy_policy_accepted: boolean;
  phone?: string;
  location?: string;
  latitude?: string | null;
  longitude?: string | null;
}

export const authApi = {
  register: (data: RegisterPayload) =>
    post<RegisterResponse>("/auth/register/", data),

  login: (email: string, password: string) =>
    post<LoginResponse>("/auth/login/", { email, password }),

  logout: () => post<{ success: true; message: string }>("/auth/logout/"),

  me: () => get<MeResponse>("/auth/me/"),

  updateProfile: (data: Partial<Pick<User, "full_name" | "phone" | "location" | "latitude" | "longitude">>) =>
    patch<{ success: true; user: User }>("/auth/profile/", data),

  announcement: () =>
    get<{ success: true; announcement: string; maintenance_mode: boolean }>(
      "/auth/announcement/"
    ),
};

// ---------------------------------------------------------------------------
// Products
// ---------------------------------------------------------------------------

export const productsApi = {
  // Farmer listings
  farmerListings: (query?: ProductQuery) =>
    get<Paginated<Product>>(
      "/products/farmer-listings/",
      toParams(query)
    ),

  myFarmerListings: (query?: ProductQuery) =>
    get<Paginated<Product>>("/products/farmer-listings/my/", toParams(query)),

  farmerListing: (id: string) => get<Product>(`/products/farmer-listings/${id}/`),

  createFarmerListing: (data: ProductCreate) =>
    post<Product>("/products/farmer-listings/", data),

  updateFarmerListing: (id: string, data: Partial<ProductCreate>) =>
    patch<Product>(`/products/farmer-listings/${id}/`, data),

  deleteFarmerListing: (id: string) =>
    del<{ success: true; message: string }>(`/products/farmer-listings/${id}/`),

  activateFarmerListing: (id: string) =>
    post<WithResource<"product", Product>>(
      `/products/farmer-listings/${id}/activate/`
    ),
  deactivateFarmerListing: (id: string) =>
    post<WithResource<"product", Product>>(
      `/products/farmer-listings/${id}/deactivate/`
    ),
  markFarmerListingSold: (id: string) =>
    post<WithResource<"product", Product>>(
      `/products/farmer-listings/${id}/mark-sold/`
    ),

  uploadFarmerListingImage: (id: string, file: File) => {
    const form = new FormData();
    form.append("image", file);
    return apiFetch<WithResource<"product", Product>>(
      `/products/farmer-listings/${id}/images/`,
      { method: "POST", body: form }
    );
  },

  // Wholesaler listings
  wholesalerListings: (query?: ProductQuery) =>
    get<Paginated<Product>>(
      "/products/wholesaler-listings/",
      toParams(query)
    ),

  myWholesalerListings: (query?: ProductQuery) =>
    get<Paginated<Product>>(
      "/products/wholesaler-listings/my/",
      toParams(query)
    ),

  wholesalerListing: (id: string) =>
    get<Product>(`/products/wholesaler-listings/${id}/`),

  createWholesalerListing: (data: ProductCreate) =>
    post<Product>("/products/wholesaler-listings/", data),

  updateWholesalerListing: (id: string, data: Partial<ProductCreate>) =>
    patch<Product>(`/products/wholesaler-listings/${id}/`, data),

  activateWholesalerListing: (id: string) =>
    post<WithResource<"product", Product>>(
      `/products/wholesaler-listings/${id}/activate/`
    ),
  deactivateWholesalerListing: (id: string) =>
    post<WithResource<"product", Product>>(
      `/products/wholesaler-listings/${id}/deactivate/`
    ),

  uploadWholesalerListingImage: (id: string, file: File) => {
    const form = new FormData();
    form.append("image", file);
    return apiFetch<WithResource<"product", Product>>(
      `/products/wholesaler-listings/${id}/images/`,
      { method: "POST", body: form }
    );
  },

  meta: () => get<CategoryUnitMeta>("/products/categories/"),
};

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export const chatApi = {
  channels: () => get<Paginated<ChatChannel>>("/chat/channels/"),

  channel: (id: string) => get<ChatChannel>(`/chat/channels/${id}/`),

  /** Note the field names: `participant_ids` (array) and `related_product`. */
  openChannel: (participantId: string, relatedProduct?: string | null) =>
    post<WithResource<"channel", ChatChannel>>("/chat/channels/", {
      participant_ids: [participantId],
      related_product: relatedProduct ?? null,
    }),

  messages: (id: string) =>
    get<Paginated<Message>>(`/chat/channels/${id}/messages/`),

  sendMessage: (id: string, content: string) =>
    post<WithResource<"message", Message>>(`/chat/channels/${id}/messages/`, {
      content,
    }),

  markChannelRead: (id: string) =>
    post<{ success: true; updated: number }>(
      `/chat/channels/${id}/mark-read/`
    ),
};

// ---------------------------------------------------------------------------
// Payments
// ---------------------------------------------------------------------------

export const paymentsApi = {
  list: (query?: PaymentQuery) =>
    get<Paginated<PaymentRecord>>("/payments/", toParams(query)),

  get: (id: string) => get<PaymentRecord>(`/payments/${id}/`),

  /** Note: `farmer` and `product` (not `*_id`); `notes` is read-only. */
  submit: (data: {
    submitted_by: string;
    farmer: string;
    product: string;
    amount: string;
    payment_method: string;
    reference_number: string;
  }) => post<PaymentRecord>("/payments/", data),

  verify: (id: string, notes?: string) =>
    patch<WithResource<"payment", PaymentRecord>>(`/payments/${id}/verify/`, {
      notes,
    }),

  /** Note: the backend reads `reason`, not `notes`. */
  flag: (id: string, reason?: string) =>
    patch<WithResource<"payment", PaymentRecord>>(`/payments/${id}/flag/`, {
      reason,
    }),

  dispute: (id: string, reason: string) =>
    patch<WithResource<"payment", PaymentRecord>>(`/payments/${id}/dispute/`, {
      reason,
    }),

  receipt: (id: string) =>
    get<WithResource<"receipt", Record<string, unknown>>>(`/payments/${id}/receipt/`),
};

// ---------------------------------------------------------------------------
// Orders
// ---------------------------------------------------------------------------

export const ordersApi = {
  list: (params?: { page?: number; status?: OrderStatus | "ALL" }) =>
    get<Paginated<Order>>("/orders/", toParams(params)),

  get: (id: string) => get<Order>(`/orders/${id}/`),

  /** Note: only `product` and `quantity`; everything else is server-set. */
  create: (productId: string, quantity: string) =>
    post<WithResource<"order", Order>>("/orders/", {
      product: productId,
      quantity,
    }),

  setStatus: (id: string, status: OrderStatus) =>
    patch<WithResource<"order", Order>>(`/orders/${id}/status/`, { status }),
};

// ---------------------------------------------------------------------------
// User Admin
// ---------------------------------------------------------------------------

export const adminApi = {
  pendingUsers: (params?: {
    page?: number;
    role?: string;
    status?: string;
    search?: string;
    ordering?: string;
  }) => get<Paginated<DirectoryUser>>("/admin/pending-users/", toParams(params)),

  users: (params?: {
    page?: number;
    role?: string;
    status?: string;
    search?: string;
    ordering?: string;
  }) => get<Paginated<DirectoryUser>>("/admin/users/", toParams(params)),

  approve: (id: string) =>
    post<WithResource<"user", DirectoryUser> & { message: string }>(
      `/admin/users/${id}/approve/`
    ),

  reject: (id: string, reason?: string) =>
    post<WithResource<"user", DirectoryUser> & { message: string }>(
      `/admin/users/${id}/reject/`,
      { reason }
    ),

  /** This is a toggle: suspend ⇄ reinstate. */
  suspend: (id: string) =>
    post<WithResource<"user", DirectoryUser> & { message: string }>(
      `/admin/users/${id}/suspend/`
    ),

  broadcast: (message: string, role?: string, userIds?: string[]) =>
    post<{ success: true; message: string; recipients: number }>(
      "/admin/messages/",
      { message, role, user_ids: userIds }
    ),
};

// ---------------------------------------------------------------------------
// Dashboards
// ---------------------------------------------------------------------------

export const dashboardApi = {
  farmer: () => get<FarmerDashboardData>("/dashboard/farmer/"),
  wholesaler: () => get<WholesalerDashboardData>("/dashboard/wholesaler/"),
  retailer: () => get<RetailerDashboardData>("/dashboard/retailer/"),
  admin: () => get<AdminDashboardData>("/dashboard/admin/"),
  payments: () => get<PaymentSummaryData>("/dashboard/payments/"),
};

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

export const notificationsApi = {
  list: (page?: number) =>
    get<Paginated<Notification>>("/notifications/", { page }),

  unreadCount: () =>
    get<{ success: true; unread_count: number }>("/notifications/unread-count/"),

  /** The route is `mark-read`, not `read`. */
  markRead: (id: string) =>
    post<{ success: true; updated: number }>(`/notifications/${id}/mark-read/`),

  markAllRead: () =>
    post<{ success: true; updated: number }>("/notifications/mark-all-read/"),
};

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export const reportsApi = {
  financialSummary: (query?: FinancialReportQuery) =>
    get<FinancialReport>("/reports/financial-summary/", toParams(query)),

  transactionVolume: (days = 30, query?: FinancialReportQuery) =>
    get<TransactionVolume>("/reports/transaction-volume/", {
      days,
      ...toParams(query),
    }),

  /**
   * CSV/PDF download.
   *
   * The param is `file_format`, NOT `format` — DRF reserves `?format=` for
   * content negotiation and would 404 before the view runs.
   */
  exportUrl: (query?: FinancialReportQuery, format: "csv" | "pdf" = "csv") =>
    `${API_BASE}/reports/financial-summary/export/${qs({
      ...toParams(query),
      file_format: format,
    })}`,

  /**
   * Downloads the export as a blob.
   *
   * The endpoint is `IsFinancialManager` and DRF only has `JWTAuthentication`
   * enabled, which reads the Authorization header rather than the refresh
   * cookie, so a plain anchor href would 401. Fetching keeps the bearer token
   * attached and lets us surface the server's error body.
   */
  download: async (
    query?: FinancialReportQuery,
    format: "csv" | "pdf" = "csv"
  ): Promise<{ blob: Blob; filename: string }> => {
    const url = reportsApi.exportUrl(query, format);
    const res = await rawRequest(
      `/reports/financial-summary/export/${qs({
        ...toParams(query),
        file_format: format,
      })}`
    );

    if (!res.ok) {
      let payload: unknown = null;
      try {
        payload = await res.json();
      } catch {
        /* non-JSON error body */
      }
      throw new ApiRequestError(
        extractErrorMessage(payload, `Export failed: ${res.status}`),
        res.status,
        payload
      );
    }

    const disposition = res.headers.get("Content-Disposition") ?? "";
    const match = /filename="?([^";]+)"?/.exec(disposition);
    return {
      blob: await res.blob(),
      filename: match?.[1] ?? `greenpath-report.${format}`,
    };
  },
};

// ---------------------------------------------------------------------------
// Super Admin
// ---------------------------------------------------------------------------

export const superAdminApi = {
  health: () => get<SuperAdminHealth>("/superadmin/health/"),

  data: (resource: SuperAdminResource, limit = 50) =>
    get<{ success: true; resource: string; count: number; results: SuperAdminRow[] }>(
      "/superadmin/data/",
      { resource, limit }
    ),

  settings: () =>
    get<WithResource<"settings", PlatformSettings>>("/superadmin/settings/"),

  updateSettings: (data: Partial<PlatformSettings>) =>
    patch<
      WithResource<"settings", PlatformSettings> & {
        updated: Partial<PlatformSettings>;
      }
    >("/superadmin/settings/", data),

  accounts: (params?: { page?: number; status?: string; search?: string }) =>
    get<Paginated<AdminAccount>>("/superadmin/accounts/", toParams(params)),

  createAccount: (data: {
    full_name: string;
    email: string;
    password: string;
    role: string;
    phone?: string;
    location?: string;
  }) => post<AdminAccountType>("/superadmin/accounts/", data),

  updateAccount: (id: string, data: Partial<AdminAccount> & { password?: string }) =>
    patch<AdminAccountType>(`/superadmin/accounts/${id}/`, data),

  deactivateAccount: (id: string) =>
    post<WithResource<"user", DirectoryUser> & { message: string }>(
      `/superadmin/accounts/${id}/deactivate/`
    ),
  reinstateAccount: (id: string) =>
    post<WithResource<"user", DirectoryUser> & { message: string }>(
      `/superadmin/accounts/${id}/reinstate/`
    ),

  audit: (page?: number) => get<Paginated<AuditLog>>("/superadmin/audit/", { page }),

  override: (id: string, decision: SuperAdminDecision, reason?: string) =>
    post<
      WithResource<"user", DirectoryUser> & {
        message: string;
        previous_status: string;
      }
    >(`/superadmin/users/${id}/override/`, { decision, reason }),

  announcement: (announcement: string) =>
    post<{ success: true; message: string; recipients: number }>(
      "/superadmin/announcement/",
      { announcement }
    ),
};

/** Status union re-exported for convenience. */
export type { PaymentStatus };
export type { LoginUser };
