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
  AssistantConversation,
  AssistantLanguage,
  AssistantMessage,
  AdminAccount,
  AdminAccountActivity,
  AdminCreationOptions,
  AdminScope,
  AdminDashboardData,
  AdminAccount as AdminAccountType,
  AuditLog,
  CategoryUnitMeta,
  BankAccount,
  BankAccountFullDetails,
  ChatChannel,
  StaffRecipient,
  DirectoryUser,
  FarmerDashboardData,
  FinancialReport,
  FinancialReportQuery,
  FinancialOperationsSummary,
  LoginResponse,
  LoginUser,
  MeResponse,
  Message,
  Notification,
  BusinessAgreement,
  RegistrationDetails,
  ManagedAdministrativeLocation,
  ManagedRegistrationProductType,
  RegistrationDocument,
  RegistrationFormFieldConfiguration,
  RegistrationLocation,
  RegistrationProductType,
  Order,
  OrderStatus,
  Paginated,
  PaymentQuery,
  PaymentRecord,
  PaymentStatus,
  PaymentSummaryData,
  PayoutBank,
  PlatformSettings,
  Product,
  ProductCreate,
  ProductQuery,
  RegisterResponse,
  RetailerDashboardData,
  Review,
  SuperAdminDecision,
  SuperAdminHealth,
  SuperAdminResource,
  SuperAdminRow,
  TransactionVolume,
  User,
  UserRole,
  Wallet,
  WalletPayoutDetail,
  WalletFundingRequest,
  WalletPayoutRequest,
  WalletRequestQuery,
  WalletActivityReport,
  WalletTransaction,
  WholesalerDashboardData,
  WebsiteContent,
  WithResource,
} from "@/lib/types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export const WS_BASE = (
  process.env.NEXT_PUBLIC_WS_URL || "http://localhost:8000"
).replace(/^http/, "ws");

const ACCESS_KEY = "greenpath_access";
const REFRESH_KEY = "greenpath_refresh";
const REGISTRATION_TOKEN_KEY = "greenpath_registration_completion";

export function setRegistrationCompletionToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) sessionStorage.setItem(REGISTRATION_TOKEN_KEY, token);
  else sessionStorage.removeItem(REGISTRATION_TOKEN_KEY);
}

async function registrationFetch<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const token =
    typeof window === "undefined"
      ? null
      : sessionStorage.getItem(REGISTRATION_TOKEN_KEY);
  if (!token) throw new Error("Registration session expired. Resume registration to continue.");
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE}/registration${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message =
      typeof payload?.error === "string"
        ? payload.error
        : typeof payload?.detail === "string"
          ? payload.detail
          : payload?.error && typeof payload.error === "object"
            ? Object.values(payload.error).flat().join(" ")
            : "Registration request failed.";
    throw new Error(message);
  }
  return payload as T;
}

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

function postFormData<T>(endpoint: string, body: FormData) {
  return apiFetch<T>(endpoint, { method: "POST", body });
}

function postWithHeaders<T>(
  endpoint: string,
  body: unknown,
  headers: Record<string, string>
) {
  return apiFetch<T>(endpoint, {
    method: "POST",
    body: JSON.stringify(body),
    headers,
  });
}

function patch<T>(endpoint: string, body?: unknown) {
  return apiFetch<T>(endpoint, {
    method: "PATCH",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function put<T>(endpoint: string, body: unknown) {
  return apiFetch<T>(endpoint, {
    method: "PUT",
    body: JSON.stringify(body),
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

  resumeRegistration: (email: string, password: string) =>
    post<{ success: true; completion_token: string }>(
      "/auth/registration/resume/",
      { email, password }
    ),

  login: (email: string, password: string) =>
    post<LoginResponse>("/auth/login/", { email, password }),

  requestPasswordReset: (channel: "email" | "sms", identifier: string) =>
    post<{ success: true; message: string }>("/auth/password-reset/request/", {
      channel,
      identifier,
    }),

  confirmPasswordReset: (uid: string, token: string, new_password: string) =>
    post<{ success: true; message: string }>("/auth/password-reset/confirm/", {
      uid,
      token,
      new_password,
    }),

  changePassword: (current_password: string, new_password: string) =>
    post<{ success: true; message: string }>("/auth/password/change/", {
      current_password,
      new_password,
    }),

  logout: () => post<{ success: true; message: string }>("/auth/logout/"),

  me: () => get<MeResponse>("/auth/me/"),

  updateProfile: (data: Partial<Pick<User, "full_name" | "phone">>) =>
    patch<{ success: true; user: User }>("/auth/profile/", data),

  updatePhoto: (file: File) => {
    const form = new FormData();
    form.append("profile_photo", file);
    return apiFetch<{ success: true; user: User }>("/auth/profile/photo/", {
      method: "POST",
      body: form,
    });
  },

  removePhoto: () =>
    del<{ success: true; user: User }>("/auth/profile/photo/"),

  announcement: () =>
    get<{ success: true; announcement: string; maintenance_mode: boolean }>(
      "/auth/announcement/"
    ),
};

export const registrationApi = {
  formFields: (stage: "INITIAL" | "PROFILE", role: UserRole) =>
    get<{ results: RegistrationFormFieldConfiguration[] }>(
      "/registration/form-fields/",
      { stage, role }
    ).then((response) => response.results),
  locations: (parentId?: string) =>
    apiFetch<RegistrationLocation[]>(
      `/registration/locations/${parentId ? `?parent_id=${encodeURIComponent(parentId)}` : ""}`
    ),
  productTypes: () =>
    apiFetch<RegistrationProductType[]>("/registration/product-types/"),
  getDraft: () =>
    typeof window !== "undefined" &&
    sessionStorage.getItem(REGISTRATION_TOKEN_KEY)
      ? registrationFetch<RegistrationDetails>("/me/")
      : get<RegistrationDetails>("/registration/me/"),
  saveDraft: (data: Partial<{
    full_name: string;
    phone: string;
    date_of_birth: string | null;
    sex: string;
    business_name: string;
    business_address: string;
    location: string | null;
    product_selections: { product_type: string; intent: string }[];
  }>) => {
    const hasCompletionToken =
      typeof window !== "undefined" &&
      Boolean(sessionStorage.getItem(REGISTRATION_TOKEN_KEY));
    return hasCompletionToken
      ? registrationFetch<RegistrationDetails>("/me/", {
          method: "PATCH",
          body: JSON.stringify(data),
        })
      : patch<RegistrationDetails>("/registration/me/", data);
  },
  uploadDocument: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return registrationFetch<RegistrationDocument>("/me/documents/", {
      method: "POST",
      body,
    });
  },
  deleteDocument: (id: string) =>
    registrationFetch<void>(`/me/documents/${id}/`, { method: "DELETE" }),
  submit: () =>
    registrationFetch<{ success: true; message: string; status: string }>(
      "/me/submit/",
      { method: "POST", body: JSON.stringify({ confirm: true }) }
    ),
};

export const websiteContentApi = {
  public: () => apiFetch<WebsiteContent>("/auth/website-content/"),
};

export const registrationAdminApi = {
  list: (params?: { page?: number; role?: string; status?: string; search?: string }) =>
    get<Paginated<RegistrationDetails>>("/admin/registrations/", toParams(params)),
  decision: (id: string, action: "APPROVE" | "REJECT" | "REQUEST_CHANGES", reason?: string) =>
    post<{ success: true; registration: RegistrationDetails }>(
      `/admin/registrations/${id}/decision/`,
      { action, reason }
    ),
  verifyDocument: (id: string, verified: boolean, note?: string) =>
    post<RegistrationDocument>(
      `/admin/registration-documents/${id}/verification/`,
      { verified, note }
    ),
  downloadDocument: async (id: string, filename: string) => {
    const token =
      typeof window === "undefined"
        ? null
        : sessionStorage.getItem(ACCESS_KEY);
    if (!token) throw new Error("Sign in again to access this document.");
    const response = await fetch(
      `${API_BASE}/admin/registration-documents/${id}/file/`,
      { headers: { Authorization: `Bearer ${token}` }, credentials: "include" }
    );
    if (!response.ok) throw new Error("The document is unavailable or you are not authorized to access it.");
    const objectUrl = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(objectUrl);
  },
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
  replaceFarmerListingImages: (id: string, images: string[]) =>
    apiFetch<WithResource<"product", Product>>(
      `/products/farmer-listings/${id}/images/`,
      { method: "PUT", body: JSON.stringify({ images }) }
    ),

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
  replaceWholesalerListingImages: (id: string, images: string[]) =>
    apiFetch<WithResource<"product", Product>>(
      `/products/wholesaler-listings/${id}/images/`,
      { method: "PUT", body: JSON.stringify({ images }) }
    ),

  meta: () => get<CategoryUnitMeta>("/products/categories/"),
};

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

export const chatApi = {
  channels: () => get<Paginated<ChatChannel>>("/chat/channels/"),
  staffRecipients: (search?: string) =>
    get<{ results: StaffRecipient[] }>("/chat/staff-recipients/", { search }),

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
  sendVoice: (id: string, audio: File) => {
    const body = new FormData();
    body.append("kind", "VOICE");
    body.append("audio", audio);
    return postFormData<WithResource<"message", Message>>(
      `/chat/channels/${id}/messages/`,
      body
    );
  },
  downloadVoice: async (channelId: string, messageId: string) => {
    const response = await rawRequest(
      `/chat/channels/${channelId}/messages/${messageId}/audio/`
    );
    if (!response.ok) {
      let payload: unknown = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
      throw new Error(extractErrorMessage(payload, "Voice message is unavailable."));
    }
    return response.blob();
  },
  pendingVoiceMessages: () =>
    get<Paginated<Message>>("/chat/voice-moderation/"),
  reviewVoice: (id: string, decision: "APPROVE" | "BLOCK", reason: string) =>
    post<WithResource<"message", Message>>(
      `/chat/voice-moderation/${id}/review/`,
      { decision, reason }
    ),

  markChannelRead: (id: string) =>
    post<{ success: true; updated: number }>(
      `/chat/channels/${id}/mark-read/`
    ),
};

// ---------------------------------------------------------------------------
// AI assistant
// ---------------------------------------------------------------------------

export const assistantApi = {
  conversations: () => get<Paginated<AssistantConversation>>("/assistant/conversations/"),
  createConversation: (language: AssistantLanguage) =>
    post<AssistantConversation>("/assistant/conversations/", { language }),
  deleteConversation: (id: string) =>
    del<void>(`/assistant/conversations/${id}/`),
  messages: (id: string) =>
    get<Paginated<AssistantMessage>>(`/assistant/conversations/${id}/messages/`),
  sendMessage: (id: string, content: string, language: AssistantLanguage) =>
    post<{
      user_message: AssistantMessage;
      assistant_message: AssistantMessage;
    }>(`/assistant/conversations/${id}/messages/`, { content, language }),
  transcribe: (audio: File, language: AssistantLanguage) => {
    const body = new FormData();
    body.append("audio", audio);
    body.append("language", language);
    return postFormData<{ text: string }>("/assistant/transcribe/", body);
  },
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

  create: (
    productId: string,
    quantity: string,
    delivery_information = ""
  ) =>
    postWithHeaders<WithResource<"order", Order>>(
      "/orders/",
      { product: productId, quantity, delivery_information },
      { "Idempotency-Key": crypto.randomUUID() }
    ),

  setStatus: (id: string, status: OrderStatus) =>
    patch<WithResource<"order", Order>>(`/orders/${id}/status/`, { status }),
  discloseContact: (
    id: string,
    recipient_id: string,
    fields: string[],
    reason: string
  ) =>
    post<WithResource<"order", Order> & { disclosure_id: string }>(
      `/orders/${id}/disclose-contact/`,
      { recipient_id, fields, reason }
    ),
  confirmQuality: (id: string) =>
    post<WithResource<"order", Order>>(`/orders/${id}/confirm-quality/`),
  dispute: (id: string, reason: string) =>
    post<WithResource<"order", Order>>(`/orders/${id}/dispute/`, { reason }),
  release: (id: string, external_reference: string) =>
    post<WithResource<"order", Order>>(`/orders/${id}/release/`, {
      external_reference,
    }),
  resolveDispute: (
    id: string,
    decision: "release" | "refund",
    external_reference = ""
  ) =>
    post<WithResource<"order", Order>>(`/orders/${id}/resolve-dispute/`, {
      decision,
      external_reference,
    }),
};

export const walletApi = {
  get: () => get<Wallet>("/wallet/"),
  transactions: (params?: {
    page?: number;
    type?: string;
    date_from?: string;
    date_to?: string;
  }) => get<Paginated<WalletTransaction>>("/wallet/transactions/", toParams(params)),
  funding: (params?: WalletRequestQuery) =>
    get<Paginated<WalletFundingRequest>>("/wallet/funding/", toParams(params)),
  requestFunding: (data: {
    amount: string;
    payment_method: string;
    external_reference: string;
  }) => post<WalletFundingRequest>("/wallet/funding/", data),
  initializeChapaFunding: (amount: string) =>
    postWithHeaders<WalletFundingRequest>(
      "/wallet/funding/chapa/",
      { amount },
      { "Idempotency-Key": crypto.randomUUID() }
    ),
  verifyChapaFunding: (id: string) =>
    post<WalletFundingRequest>(`/wallet/funding/${id}/verify/`),
  reviewFunding: (id: string, approve: boolean, notes = "") =>
    post<{ success: true; funding_request: WalletFundingRequest }>(
      `/wallet/funding/${id}/review/`,
      { approve, notes }
    ),
  payouts: (params?: WalletRequestQuery) =>
    get<Paginated<WalletPayoutRequest>>("/wallet/payouts/", toParams(params)),
  payoutDetail: (id: string) =>
    get<WalletPayoutDetail>(`/wallet/payouts/${id}/`),
  requestPayout: (data: {
    amount: string;
    destination?: string;
    payout_account?: string;
  }) =>
    postWithHeaders<WalletPayoutRequest>(
      "/wallet/payouts/",
      data,
      { "Idempotency-Key": crypto.randomUUID() }
    ),
  banks: (search?: string) =>
    get<Paginated<PayoutBank>>("/wallet/banks/", toParams({ search })),
  bankAccounts: (params?: {
    page?: number;
    search?: string;
    role?: string;
    bank?: string;
    status?: string;
  }) => get<Paginated<BankAccount>>("/wallet/bank-accounts/", toParams(params)),
  createBankAccount: (data: {
    bank: number;
    account_holder_name: string;
    account_number: string;
    confirm_account_number: string;
    branch?: string;
    branch_code?: string;
    account_type?: string;
    nickname?: string;
    is_default: boolean;
  }) => post<BankAccount>("/wallet/bank-accounts/", data),
  updateBankAccount: (
    id: string,
    data: Partial<{
      bank: number;
      account_holder_name: string;
      account_number: string;
      confirm_account_number: string;
      branch: string;
      branch_code: string;
      account_type: string;
      nickname: string;
      is_default: boolean;
    }>
  ) => patch<BankAccount>(`/wallet/bank-accounts/${id}/`, data),
  deleteBankAccount: (id: string) =>
    del<Record<string, never>>(`/wallet/bank-accounts/${id}/`),
  fullBankAccountDetails: (id: string) =>
    get<BankAccountFullDetails>(`/wallet/bank-accounts/${id}/full-details/`),
  requestBankAccountReview: (id: string, notes: string) =>
    post<BankAccount>(`/wallet/bank-accounts/${id}/require-review/`, { notes }),
  reviewPayout: (
    id: string,
    approve: boolean,
    external_reference = "",
    notes = ""
  ) =>
    post<{ success: true; payout_request: WalletPayoutRequest }>(
      `/wallet/payouts/${id}/review/`,
      { approve, external_reference, notes }
    ),
  agreements: (params?: { page?: number }) =>
    get<Paginated<BusinessAgreement>>("/wallet/agreements/", toParams(params)),
  reviews: (userId?: string, page?: number) =>
    get<Paginated<Review>>(
      "/wallet/reviews/",
      toParams({ user: userId, page })
    ),
  createReview: (order: string, rating: number, comment: string) =>
    post<Review>("/wallet/reviews/", { order, rating, comment }),
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
    created_from?: string;
    created_to?: string;
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
  financialOperations: () =>
    get<FinancialOperationsSummary>("/dashboard/financial-operations/"),
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
  walletActivity: (query?: Pick<FinancialReportQuery, "date_from" | "date_to">) =>
    get<WalletActivityReport>("/dashboard/wallet-activity/", toParams(query)),

  walletActivityExport: async (
    query?: Pick<FinancialReportQuery, "date_from" | "date_to">
  ): Promise<{ blob: Blob; filename: string }> => {
    const res = await rawRequest(
      `/dashboard/wallet-activity/export/${qs(toParams(query))}`
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
      filename: match?.[1] ?? "wallet-activity.csv",
    };
  },

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
  users: (params?: {
    page?: number;
    search?: string;
    role?: string;
    status?: string;
    created_from?: string;
    created_to?: string;
  }) => get<Paginated<DirectoryUser>>("/superadmin/users/", toParams(params)),

  settings: () =>
    get<WithResource<"settings", PlatformSettings>>("/superadmin/settings/"),

  websiteContent: () =>
    get<WebsiteContent>("/superadmin/website-content/"),

  updateWebsiteContent: (data: FormData) =>
    apiFetch<{ success: true; website_content: WebsiteContent }>(
      "/superadmin/website-content/",
      { method: "PATCH", body: data }
    ),

  managedLocations: () =>
    get<ManagedAdministrativeLocation[]>("/superadmin/locations/"),
  createLocation: (data: {
    source_id: string;
    name: string;
    level: string;
    parent: string | null;
    alternative_names: string[];
  }) => post<ManagedAdministrativeLocation>("/superadmin/locations/", data),
  updateLocation: (
    id: string,
    data: Partial<ManagedAdministrativeLocation>
  ) => patch<ManagedAdministrativeLocation>(`/superadmin/locations/${id}/`, data),
  deactivateLocation: (id: string) =>
    del<Record<string, never>>(`/superadmin/locations/${id}/`),
  managedProductTypes: () =>
    get<ManagedRegistrationProductType[]>("/superadmin/product-types/"),
  createProductType: (data: {
    code: string;
    name: string;
    category: string;
  }) => post<ManagedRegistrationProductType>("/superadmin/product-types/", data),
  updateProductType: (
    id: string,
    data: Partial<ManagedRegistrationProductType>
  ) => patch<ManagedRegistrationProductType>(`/superadmin/product-types/${id}/`, data),
  deactivateProductType: (id: string) =>
    del<Record<string, never>>(`/superadmin/product-types/${id}/`),
  registrationFields: () =>
    get<RegistrationFormFieldConfiguration[]>(
      "/superadmin/registration-fields/"
    ),
  updateRegistrationField: (
    id: number,
    data: Partial<
      Pick<
        RegistrationFormFieldConfiguration,
        | "label"
        | "description"
        | "required"
        | "visible"
        | "display_order"
        | "roles"
        | "options"
        | "editable_after_approval"
      >
    >
  ) =>
    patch<RegistrationFormFieldConfiguration>(
      `/superadmin/registration-fields/${id}/`,
      data
    ),

  updateSettings: (data: Partial<PlatformSettings> & { reason?: string }) =>
    patch<
      WithResource<"settings", PlatformSettings> & {
        updated: Partial<PlatformSettings>;
      }
    >("/superadmin/settings/", data),

  scopes: () => get<Paginated<AdminScope>>("/superadmin/admin-scopes/"),

  saveScope: (data: {
    user: string;
    level: "GLOBAL" | "LOCATION";
    location: string | null;
  }) =>
    post<AdminScope>("/superadmin/admin-scopes/", data),

  accounts: (params?: {
    page?: number;
    status?: string;
    search?: string;
    role?: string;
    scope_type?: string;
    location_id?: string;
    created_from?: string;
    created_to?: string;
    last_active_from?: string;
    last_active_to?: string;
  }) =>
    get<Paginated<AdminAccount>>("/superadmin/accounts/", toParams(params)),
  accountActivity: (
    id: string,
    params?: { days?: string; from?: string; to?: string; page?: number },
  ) =>
    get<AdminAccountActivity>(
      `/superadmin/accounts/${id}/activity/`,
      toParams(params),
    ),
  creationOptions: () =>
    get<AdminCreationOptions>("/superadmin/accounts/creation-options/"),

  createAccount: (data: {
    full_name: string;
    email: string;
    password: string;
    role: string;
    phone?: string;
    location?: string;
    scope_level?: "GLOBAL" | "LOCATION";
    scope_location?: string | null;
    scope_type?: string;
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
  suspendAccount: (id: string, reason?: string) =>
    post<WithResource<"user", DirectoryUser> & { message: string }>(
      `/superadmin/accounts/${id}/suspend/`,
      { reason }
    ),

  audit: (
    page?: number,
    filters?: {
      administrator?: string;
      role?: string;
      action?: string;
      target?: string;
      from?: string;
      to?: string;
      registration_status?: string;
      license_status?: string;
      location_id?: string;
    },
  ) =>
    get<Paginated<AuditLog>>("/superadmin/audit/", {
      page,
      ...filters,
    }),

  override: (id: string, decision: SuperAdminDecision, reason?: string) =>
    post<
      WithResource<"user", DirectoryUser> & {
        message: string;
        previous_status: string;
      }
    >(`/superadmin/users/${id}/override/`, { decision, reason }),

  unlockLogin: (id: string, reason: string) =>
    post<
      WithResource<"user", DirectoryUser> & {
        message: string;
      }
    >(`/superadmin/users/${id}/unlock-login/`, { reason }),

  announcement: (announcement: string) =>
    post<{ success: true; message: string; recipients: number }>(
      "/superadmin/announcement/",
      // The endpoint's body contract is AnnouncementSerializer { message }.
      { message: announcement }
    ),
};

/** Status union re-exported for convenience. */
export type { PaymentStatus };
export type { LoginUser };
