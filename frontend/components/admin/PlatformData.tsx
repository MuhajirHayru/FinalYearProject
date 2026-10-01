"use client";

import { useCallback, useEffect, useState } from "react";
import { Database, RefreshCw } from "lucide-react";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  PageLoader,
  StatusPill,
  TableWrap,
  Td,
  Th,
} from "@/components/ui";
import { superAdminApi } from "@/lib/api/client";
import { formatEtb, formatNumber, shortRelative } from "@/lib/format";
import type { SuperAdminResource, SuperAdminRow } from "@/lib/types";

const RESOURCES: { value: SuperAdminResource; label: string }[] = [
  { value: "users", label: "Users" },
  { value: "products", label: "Listings" },
  { value: "orders", label: "Orders" },
  { value: "payments", label: "Payments" },
  { value: "chat", label: "Chat channels" },
  { value: "notifications", label: "Notifications" },
];

/**
 * Renders one `/superadmin/data/` row. The endpoint returns a different
 * hand-rolled shape per resource, so each case is narrowed explicitly rather
 * than cast.
 */
function ResourceTable({ resource, rows }: { resource: SuperAdminResource; rows: SuperAdminRow[] }) {
  const first = rows[0];
  if (!first) return null;

  // Chat channels: participants is a list of names.
  if (resource === "chat" && "participants" in first) {
    return (
      <TableWrap>
        <thead>
          <tr>
            <Th>Participants</Th>
            <Th>Messages</Th>
            <Th>Last Activity</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <Td>{"participants" in r ? r.participants.join(", ") : ""}</Td>
              <Td>{"message_count" in r ? r.message_count : 0}</Td>
              <Td className="whitespace-nowrap text-xs text-gray-500">
                {"last_message_at" in r ? shortRelative(r.last_message_at) : "-"}
              </Td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
    );
  }

  // Notifications.
  if (resource === "notifications" && "recipient" in first) {
    return (
      <TableWrap>
        <thead>
          <tr>
            <Th>Recipient</Th>
            <Th>Type</Th>
            <Th>Message</Th>
            <Th>Read</Th>
            <Th>Created</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <Td className="max-w-40 truncate">{"recipient" in r ? r.recipient : ""}</Td>
              <Td>{"type" in r ? <StatusPill value={r.type} kind="neutral" /> : null}</Td>
              <Td className="max-w-80 truncate">{"message" in r ? r.message : ""}</Td>
              <Td>{"is_read" in r ? (r.is_read ? "Yes" : "No") : "-"}</Td>
              <Td className="whitespace-nowrap text-xs text-gray-500">
                {"created_at" in r ? shortRelative(r.created_at) : "-"}
              </Td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
    );
  }

  // Payments.
  if (resource === "payments" && "display_id" in first) {
    return (
      <TableWrap>
        <thead>
          <tr>
            <Th>ID</Th>
            <Th>Wholesaler</Th>
            <Th>Farmer</Th>
            <Th>Amount</Th>
            <Th>Method</Th>
            <Th>Status</Th>
            <Th>Submitted</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <Td className="font-mono text-xs">{"display_id" in r ? r.display_id : ""}</Td>
              <Td className="max-w-32 truncate">{"wholesaler" in r ? r.wholesaler : ""}</Td>
              <Td className="max-w-32 truncate">{"farmer" in r ? r.farmer : ""}</Td>
              <Td className="font-medium">{"amount" in r ? formatEtb(r.amount) : ""}</Td>
              <Td className="whitespace-nowrap text-xs">
                {"payment_method" in r ? r.payment_method : ""}
              </Td>
              <Td>{"status" in r ? <StatusPill value={r.status} /> : null}</Td>
              <Td className="whitespace-nowrap text-xs text-gray-500">
                {"submitted_at" in r ? shortRelative(r.submitted_at) : "-"}
              </Td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
    );
  }

  // Orders.
  if (resource === "orders" && "reference" in first) {
    return (
      <TableWrap>
        <thead>
          <tr>
            <Th>Reference</Th>
            <Th>Wholesaler</Th>
            <Th>Farmer</Th>
            <Th>Product</Th>
            <Th>Total</Th>
            <Th>Status</Th>
            <Th>Created</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <Td className="font-mono text-xs">{"reference" in r ? r.reference : ""}</Td>
              <Td className="max-w-32 truncate">{"wholesaler" in r ? r.wholesaler : ""}</Td>
              <Td className="max-w-32 truncate">{"farmer" in r ? r.farmer : ""}</Td>
              <Td className="max-w-40 truncate">{"product" in r ? r.product : ""}</Td>
              <Td className="font-medium">
                {"total_amount" in r ? formatEtb(r.total_amount) : ""}
              </Td>
              <Td>{"status" in r ? <StatusPill value={r.status} /> : null}</Td>
              <Td className="whitespace-nowrap text-xs text-gray-500">
                {"created_at" in r ? shortRelative(r.created_at) : "-"}
              </Td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
    );
  }

  // Products.
  if (resource === "products" && "title" in first) {
    return (
      <TableWrap>
        <thead>
          <tr>
            <Th>Title</Th>
            <Th>Owner</Th>
            <Th>Type</Th>
            <Th>Category</Th>
            <Th>Quantity</Th>
            <Th>Price / Unit</Th>
            <Th>Status</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <Td className="max-w-48 truncate font-medium text-gray-900">
                {"title" in r ? r.title : ""}
              </Td>
              <Td className="max-w-32 truncate">{"owner" in r ? r.owner : ""}</Td>
              <Td className="whitespace-nowrap text-xs">
                {"product_type" in r ? r.product_type : ""}
              </Td>
              <Td>{"category" in r ? r.category : ""}</Td>
              <Td>{"quantity" in r ? formatNumber(r.quantity) : ""}</Td>
              <Td className="font-medium">
                {"price_per_unit" in r ? formatEtb(r.price_per_unit) : ""}
              </Td>
              <Td>{"status" in r ? <StatusPill value={r.status} /> : null}</Td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
    );
  }

  // Users.
  return (
    <TableWrap>
      <thead>
        <tr>
          <Th>Name</Th>
          <Th>Email</Th>
          <Th>Role</Th>
          <Th>Status</Th>
          <Th>Location</Th>
          <Th>Registered</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id}>
            <Td className="font-medium text-gray-900">{"full_name" in r ? r.full_name : ""}</Td>
            <Td className="text-xs">{"email" in r ? r.email : ""}</Td>
            <Td>{"role" in r ? <StatusPill value={r.role} kind="role" /> : null}</Td>
            <Td>{"status" in r ? <StatusPill value={r.status} /> : null}</Td>
            <Td className="max-w-40 truncate text-xs">{"location" in r ? r.location : "-"}</Td>
            <Td className="whitespace-nowrap text-xs text-gray-500">
              {"created_at" in r ? shortRelative(r.created_at) : "-"}
            </Td>
          </tr>
        ))}
      </tbody>
    </TableWrap>
  );
}

export function PlatformData({ resource: locked }: { resource?: SuperAdminResource }) {
  const [resource, setResource] = useState<SuperAdminResource>(locked ?? "users");
  const [rows, setRows] = useState<SuperAdminRow[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const res = await superAdminApi.data(resource, 200);
      setRows(res.results);
      setCount(res.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load platform data.");
    } finally {
      setLoading(false);
    }
  }, [resource]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-5 py-4">
        {!locked && (
          <div className="flex flex-wrap gap-1">
            {RESOURCES.map((r) => (
              <button
                key={r.value}
                onClick={() => setResource(r.value)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                  resource === r.value
                    ? "bg-green-600 text-white"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        )}
        <div className="flex items-center gap-3">
          <p className="text-xs text-gray-500">
            {count} row{count === 1 ? "" : "s"}
          </p>
          <Button
            size="sm"
            variant="secondary"
            icon={<RefreshCw className="h-3.5 w-3.5" />}
            onClick={() => void load()}
          >
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="p-5">
          <ErrorBanner message={error} onRetry={() => void load()} />
        </div>
      )}

      {loading ? (
        <PageLoader />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No records"
          description="Nothing has been created for this resource yet."
          icon={<Database className="h-8 w-8" />}
        />
      ) : (
        <ResourceTable resource={resource} rows={rows} />
      )}
    </Card>
  );
}
