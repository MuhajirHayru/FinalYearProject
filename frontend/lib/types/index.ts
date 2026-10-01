// ---------------------------------------------------------------------------
// Enum / choice literal values — must match the Django model definitions.
// ---------------------------------------------------------------------------

export type UserRole =
  | "FARMER"
  | "WHOLESALER"
  | "RETAILER"
  | "USER_ADMIN"
  | "FINANCIAL_MANAGER"
  | "SUPER_ADMIN";

export type AccountStatus =
  | "PENDING"
  | "APPROVED"
  | "REJECTED"
  | "SUSPENDED"
  | "DEACTIVATED";

export type ProductStatus = "DRAFT" | "ACTIVE" | "INACTIVE" | "SOLD" | "DELETED";

export type ProductType = "FARMER_LISTING" | "WHOLESALER_LISTING";

export type ProductCategory =
  | "Vegetables"
  | "Fruits"
  | "Grains"
  | "Pulses"
  | "Spices"
  | "Root Crops"
  | "Other";

export type UnitOfMeasure =
  | "kg"
  | "quintal"
  | "ton"
  | "piece"
  | "crate"
  | "bunch"
  | "litre";

/** Title-Case on purpose — matches `payments/models.py`. */
export type OrderStatus =
  | "Processing"
  | "Confirmed"
  | "Shipped"
  | "Delivered"
  | "Cancelled";

export type PaymentStatus = "PENDING" | "VERIFIED" | "FLAGGED" | "DISPUTED";

/** Spaces are part of the stored value. */
export type PaymentMethod =
  | "CBE Birr"
  | "Telebirr"
  | "Bank Transfer"
  | "Chapa"
  | "Cash";

export type NotificationType =
  | "REGISTRATION"
  | "APPROVAL"
  | "REJECTION"
  | "MESSAGE"
  | "PAYMENT"
  | "ORDER"
  | "PRODUCT"
  | "SYSTEM";

export type SuperAdminDecision =
  | "APPROVE"
  | "REJECT"
  | "SUSPEND"
  | "REACTIVATE";

// ---------------------------------------------------------------------------
// Shared transport shapes
// ---------------------------------------------------------------------------

/** DRF PageNumberPagination. List endpoints are NOT enveloped. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** Every error from the backend looks like this. */
export interface ApiError {
  success: false;
  error: string | Record<string, string[]>;
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

/** `users/serializers.py` UserSerializer — 16 keys. */
export interface User {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  location: string;
  /** DecimalField serialises to a JSON string. */
  latitude: string | null;
  longitude: string | null;
  role: UserRole;
  status: AccountStatus;
  role_display: string;
  status_display: string;
  rejection_reason: string;
  privacy_policy_accepted: boolean;
  permissions: string[];
  created_at: string;
  updated_at: string;
}

/**
 * `_user_payload` (`users/views.py:32`) — the login `user` is a 10-key subset.
 * Deliberately narrower than `User`.
 */
export interface LoginUser {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  role: UserRole;
  role_display: string;
  status: AccountStatus;
  status_display: string;
  location: string;
  permissions: string[];
}

/** `users/serializers.py` PublicUser — 8 keys, no email by design. */
export interface PublicUser {
  id: string;
  full_name: string;
  phone: string;
  location: string;
  role: UserRole;
  role_display: string;
  status: AccountStatus;
  created_at: string;
}

/** `users/serializers.py` DirectoryUser — 13 keys. */
export interface DirectoryUser {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  location: string;
  role: UserRole;
  role_display: string;
  status: AccountStatus;
  status_display: string;
  rejection_reason: string;
  privacy_policy_accepted: boolean;
  created_at: string;
  updated_at: string;
}

/** `users/serializers.py` AdminAccount — 11 keys. */
export interface AdminAccount {
  id: string;
  full_name: string;
  email: string;
  phone: string;
  location: string;
  role: UserRole;
  role_display: string;
  status: AccountStatus;
  is_staff: boolean;
  created_at: string;
}

/** `users/serializers.py` AuditLog — 7 keys. */
export interface AuditLog {
  id: number;
  actor: string | null;
  actor_name: string | null;
  action: string;
  target: string;
  detail: string;
  created_at: string;
}

export interface LoginResponse {
  success: true;
  access: string;
  user: LoginUser;
}

export interface RegisterResponse {
  success: true;
  message: string;
  user: User;
}

export interface MeResponse {
  success: true;
  user: User;
  permissions: string[];
}

export interface PlatformSettings {
  registration_open: boolean;
  require_approval: boolean;
  announcement: string;
  maintenance_mode: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

export interface SuperAdminHealth {
  success: true;
  generated_at: string;
  users: {
    total: number;
    approved: number;
    pending: number;
    suspended: number;
    by_role: Partial<Record<UserRole, number>>;
  };
  listings: {
    total: number;
    active: number;
    by_type: Partial<Record<ProductType, number>>;
  };
  transactions: {
    orders_total: number;
    orders_24h: number;
    /** Decimal → string. */
    order_value_total: string;
    payments_total: number;
    payments_pending: number;
    payments_pending_value: string;
    payments_verified: number;
    payments_verified_value: string;
    payment_volume_7d: string;
  };
  communication: {
    chat_channels: number;
    messages: number;
    notifications: number;
    unread_notifications: number;
  };
  api: {
    version: string;
    authentication: string;
    token_lifetime: string;
    page_size: number;
    websocket_paths: string[];
  };
}

/** Each `resource` on `/superadmin/data/` has its own hand-rolled row shape. */
export type SuperAdminRow =
  | {
      id: string;
      full_name: string;
      email: string;
      role: UserRole;
      status: AccountStatus;
      location: string;
      created_at: string;
    }
  | {
      id: string;
      title: string;
      owner: string;
      product_type: ProductType;
      category: ProductCategory;
      quantity: string;
      price_per_unit: string;
      status: ProductStatus;
    }
  | {
      id: string;
      reference: string;
      wholesaler: string;
      farmer: string;
      product: string;
      total_amount: string;
      status: OrderStatus;
      created_at: string;
    }
  | {
      id: string;
      display_id: string;
      wholesaler: string;
      farmer: string;
      amount: string;
      payment_method: PaymentMethod;
      status: PaymentStatus;
      submitted_at: string;
    }
  | {
      id: string;
      participants: string[];
      message_count: number;
      last_message_at: string | null;
    }
  | {
      id: string;
      recipient: string;
      type: NotificationType;
      message: string;
      is_read: boolean;
      created_at: string;
    };

export type SuperAdminResource =
  | "users"
  | "products"
  | "orders"
  | "payments"
  | "chat"
  | "notifications";

// ---------------------------------------------------------------------------
// Products
// ---------------------------------------------------------------------------

/** `products/serializers.py` ProductSerializer — 22 keys. */
export interface Product {
  id: string;
  title: string;
  description: string;
  category: ProductCategory;
  category_display: string;
  /** Decimal → JSON string. */
  quantity: string;
  unit_of_measure: UnitOfMeasure;
  unit_display: string;
  price_per_unit: string;
  status: ProductStatus;
  status_display: string;
  product_type: ProductType;
  /** UUID string, not a nested object. */
  owner: string;
  owner_name: string;
  owner_location: string;
  owner_role: string;
  owner_latitude: string | null;
  owner_longitude: string | null;
  /** Flat array of relative URLs beginning with "/media/". */
  images: string[];
  is_owner: boolean;
  /** Only present on proximity-sorted queries. */
  distance_km: number | null;
  total_value: string;
  created_at: string;
  updated_at: string;
}

export interface ProductCreate {
  title: string;
  description: string;
  category: ProductCategory;
  quantity: string;
  unit_of_measure: UnitOfMeasure;
  price_per_unit: string;
  images?: string[];
}

export interface CategoryUnitMeta {
  success: true;
  categories: { value: string; label: string }[];
  units: { value: string; label: string }[];
}

/** Query params accepted by both listing viewsets. */
export interface ProductQuery {
  page?: number;
  search?: string;
  category?: ProductCategory | "ALL";
  location?: string;
  status?: ProductStatus | "ALL";
  unit_of_measure?: UnitOfMeasure | "ALL";
  /** Note: the backend spells these `min_price` / `max_price`. */
  min_price?: string;
  max_price?: string;
  /** Note: the backend spells availability `in_stock`. */
  in_stock?: "1";
  ordering?:
    | "created_at"
    | "-created_at"
    | "price_per_unit"
    | "-price_per_unit"
    | "title"
    | "-title"
    | "quantity"
    | "-quantity"
    | "distance_km";
  near_me?: "1";
  radius_km?: string;
  mine?: "1";
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

/** `chat/serializers.py` Message — 7 keys. */
export interface Message {
  id: string;
  channel: string;
  sender: string;
  sender_name: string;
  content: string;
  /** Note: `sent_at`, not `created_at`. */
  sent_at: string;
  is_read: boolean;
}

/** `chat/serializers.py` ChatChannel — 10 keys. */
export interface ChatChannel {
  id: string;
  participants: PublicUser[];
  /** Product UUID, not an object. */
  related_product: string | null;
  related_product_title: string | null;
  last_message_at: string | null;
  created_at: string;
  last_message: {
    content: string;
    sender_name: string;
    sent_at: string;
  } | null;
  unread_count: number;
}

// ---------------------------------------------------------------------------
// Payments
// ---------------------------------------------------------------------------

/** `payments/serializers.py` PaymentRecord — 23 keys. */
export interface PaymentRecord {
  id: string;
  display_id: string;
  submitted_by: string;
  submitted_by_id: string;
  /** Full name, not an object. */
  wholesaler: string;
  wholesaler_id: string;
  farmer: string;
  farmer_name: string;
  product: string;
  product_title: string;
  /** Decimal → JSON string. */
  amount: string;
  /** Preformatted "1,250.00 ETB". */
  total: string;
  payment_method: PaymentMethod;
  method_display: string;
  reference_number: string;
  status: PaymentStatus;
  status_display: string;
  verified_by: string | null;
  verified_by_name: string | null;
  notes: string;
  submitted_at: string;
  submitted: string;
  verified_at: string | null;
}

export interface PaymentQuery {
  page?: number;
  status?: PaymentStatus | "ALL";
  /** Note: the backend spells this `method`, not `payment_method`. */
  method?: PaymentMethod | "ALL";
  search?: string;
  date_from?: string;
  date_to?: string;
  ordering?:
    | "submitted_at"
    | "-submitted_at"
    | "amount"
    | "-amount"
    | "status";
}

// ---------------------------------------------------------------------------
// Orders
// ---------------------------------------------------------------------------

/** `payments/serializers.py` Order — 15 keys. */
export interface Order {
  id: string;
  reference: string;
  wholesaler: string;
  wholesaler_name: string;
  farmer: string;
  farmer_name: string;
  product: string;
  product_title: string;
  quantity: string;
  total_amount: string;
  total: string;
  status: OrderStatus;
  status_display: string;
  /** Computed legal next states — drives the status buttons. */
  allowed_transitions: OrderStatus[];
  date: string;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

/** `notifications/serializers.py` Notification — 7 keys. */
export interface Notification {
  id: string;
  type: NotificationType;
  type_display: string;
  message: string;
  is_read: boolean;
  /** Actor UUID. There is no `recipient` field. */
  actor: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Dashboards
//
// Each dashboard returns a hand-rolled block whose array members are NOT the
// corresponding full serializer objects.
// ---------------------------------------------------------------------------

export interface ActivityEntry {
  type: string;
  text: string;
  time: string;
}

/** `/dashboard/farmer/` */
export interface FarmerDashboardData {
  success: true;
  stats: {
    total_active_listings: number;
    total_products_sold: number;
    unread_messages: number;
    total_listings: number;
    pending_orders: number;
    total_earned: number;
    pending_payments: number;
  };
  listings: {
    id: string;
    title: string;
    quantity: string;
    /** Note: `unit`, not `unit_of_measure`. */
    unit: string;
    price_per_unit: string;
    status: ProductStatus;
  }[];
  recent_activity: ActivityEntry[];
}

/** `/dashboard/wholesaler/` */
export interface WholesalerDashboardData {
  success: true;
  stats: {
    total_orders: number;
    total_spent: number;
    favorite_sellers: number;
    unread_messages: number;
    active_listings: number;
    pending_orders: number;
    pending_payments: number;
    verified_payments: number;
  };
  orders: {
    id: string;
    reference: string;
    /** Farmer's name. */
    seller: string;
    /** Product title. */
    product: string;
    /** Preformatted "1,250 ETB". */
    total: string;
    status: OrderStatus;
    date: string;
  }[];
  recent_activity: ActivityEntry[];
}

/** `/dashboard/retailer/` */
export interface RetailerDashboardData {
  success: true;
  stats: {
    active_communications: number;
    unread_messages: number;
    total_wholesalers: number;
    available_listings: number;
    nearby_listings: number;
    location_available: boolean;
  };
  nearby_listings: {
    id: string;
    title: string;
    wholesaler: string;
    location: string;
    price_per_unit: string;
    unit: string;
    distance_km: number | null;
  }[];
  recent_activity: ActivityEntry[];
}

/** `/dashboard/admin/` — stats only, no arrays. */
export interface AdminDashboardData {
  success: true;
  stats: {
    pending_users: number;
    total_users: number;
    active_users: number;
    farmers: number;
    wholesalers: number;
    retailers: number;
    active_listings: number;
    pending_payments: number;
    verified_payments: number;
    flagged_payments: number;
    total_orders: number;
  };
}

/** `/dashboard/payments/` */
export interface PaymentSummaryData {
  success: true;
  summary: {
    pending_amount: number;
    pending_count: number;
    /** Month-scoped. */
    verified_amount: number;
    /** Month-scoped. */
    verified_count: number;
    flagged_count: number;
    flagged_amount: number;
  };
  /** All-time, so these disagree with the month-scoped summary above. */
  tabs: Record<PaymentStatus, number>;
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export interface FinancialReport {
  success: true;
  generated_at: string;
  filters: {
    status?: string;
    method?: string;
    date_from?: string;
    date_to?: string;
    user_id?: string;
  };
  totals: {
    count: number;
    amount: number;
    by_status: Record<string, { count: number; total: number }>;
    by_method: Record<string, { count: number; total: number }>;
    top_farmers: { farmer: string; count: number; total: number }[];
    top_wholesalers: {
      wholesaler: string;
      count: number;
      total: number;
    }[];
  };
}

export interface FinancialReportQuery {
  status?: PaymentStatus | "ALL";
  method?: PaymentMethod | "ALL";
  date_from?: string;
  date_to?: string;
  user_id?: string;
  search?: string;
}

export interface TransactionVolume {
  success: true;
  days: number;
  series: { date: string; count: number; total: number }[];
}

// ---------------------------------------------------------------------------
// Envelope helper
// ---------------------------------------------------------------------------

export interface Envelope<T> {
  success: true;
}
export type WithResource<K extends string, T> = { success: true } & {
  [P in K]: T;
};
