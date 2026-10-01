"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Search, UserCheck, X } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  Modal,
  PageLoader,
  Pagination,
  Select,
  StatusPill,
  TableWrap,
  Td,
  Textarea,
  Th,
} from "@/components/ui";
import { adminApi } from "@/lib/api/client";
import { formatDate, initials } from "@/lib/format";
import type { AccountStatus, DirectoryUser, UserRole } from "@/lib/types";

const COMMERCIAL_ROLES: { value: UserRole; label: string }[] = [
  { value: "FARMER", label: "Farmer" },
  { value: "WHOLESALER", label: "Wholesaler" },
  { value: "RETAILER", label: "Retailer" },
];

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: "ALL", label: "All statuses" },
  { value: "PENDING", label: "Pending" },
  { value: "ACTIVE", label: "Active" },
  { value: "SUSPENDED", label: "Suspended" },
  { value: "REJECTED", label: "Rejected" },
];

/**
 * Figure 4.9 - the User Admin approval queue and account directory.
 *
 * `mode="approvals"` is the pending queue (approve / reject only);
 * `mode="users"` is the full directory and additionally allows suspend /
 * reinstate, because the backend exposes that as a single toggle endpoint.
 */
export function UserDirectory({
  mode,
  selfId,
}: {
  mode: "approvals" | "users";
  selfId: string;
}) {
  const router = useRouter();
  const [rows, setRows] = useState<DirectoryUser[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState(mode === "approvals" ? "PENDING" : "ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [notice, setNotice] = useState("");

  const [rejecting, setRejecting] = useState<DirectoryUser | null>(null);
  const [reason, setReason] = useState("");
  const [rejectBusy, setRejectBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const params = {
        page,
        search: search || undefined,
        role: role || undefined,
        status: status === "ALL" ? undefined : status,
      };
      const res =
        mode === "approvals"
          ? await adminApi.pendingUsers(params)
          : await adminApi.users(params);
      setRows(res.results);
      setCount(res.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users.");
    } finally {
      setLoading(false);
    }
  }, [mode, page, search, role, status]);

  useEffect(() => {
    void load();
  }, [load]);

  async function approve(user: DirectoryUser) {
    setBusyId(user.id);
    setError("");
    try {
      const res = await adminApi.approve(user.id);
      setNotice(res.message || `${user.full_name} approved.`);
      await load();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval failed.");
    } finally {
      setBusyId("");
    }
  }

  async function confirmReject() {
    if (!rejecting) return;
    setRejectBusy(true);
    try {
      const res = await adminApi.reject(rejecting.id, reason.trim() || undefined);
      setNotice(res.message || `${rejecting.full_name} rejected.`);
      setRejecting(null);
      setReason("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rejection failed.");
    } finally {
      setRejectBusy(false);
    }
  }

  async function toggleSuspend(user: DirectoryUser) {
    setBusyId(user.id);
    setError("");
    try {
      const res = await adminApi.suspend(user.id);
      setNotice(res.message || "Account status updated.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the account.");
    } finally {
      setBusyId("");
    }
  }

  if (loading) return <PageLoader />;

  const isApprovals = mode === "approvals";

  return (
    <div className="space-y-5">
      {error && <ErrorBanner message={error} onRetry={() => void load()} />}
      {notice && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {notice}
        </div>
      )}

      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b border-gray-100 px-5 py-4">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <Input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search by name or email..."
              className="pl-9"
              aria-label="Search users"
            />
          </div>

          <Select
            value={role}
            onChange={(e) => {
              setRole(e.target.value);
              setPage(1);
            }}
            className="h-10 w-40"
            aria-label="Filter by role"
          >
            <option value="">All roles</option>
            {COMMERCIAL_ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </Select>

          {!isApprovals && (
            <Select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
              className="h-10 w-40"
              aria-label="Filter by status"
            >
              {STATUS_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </Select>
          )}

          <p className="text-xs text-gray-500">
            {count} account{count === 1 ? "" : "s"}
          </p>
        </div>

        {rows.length === 0 ? (
          <EmptyState
            title={isApprovals ? "Approval queue is clear" : "No accounts found"}
            description={
              isApprovals
                ? "New registrations will appear here for review."
                : "Try a different search or filter."
            }
            icon={<UserCheck className="h-8 w-8" />}
          />
        ) : (
          <>
            <TableWrap>
              <thead>
                <tr>
                  <Th>User</Th>
                  <Th>Role</Th>
                  <Th>Location</Th>
                  <Th>Status</Th>
                  <Th>Registered</Th>
                  <Th align="center">Actions</Th>
                </tr>
              </thead>
              <tbody>
                {rows.map((u) => (
                  <tr key={u.id}>
                    <Td>
                      <div className="flex items-center gap-3">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-green-100 text-xs font-semibold text-green-800">
                          {initials(u.full_name)}
                        </span>
                        <div className="min-w-0">
                          <p className="truncate font-medium text-gray-900">
                            {u.full_name}
                          </p>
                          <p className="truncate text-xs text-gray-500">{u.email}</p>
                        </div>
                      </div>
                    </Td>
                    <Td>
                      <StatusPill value={u.role} kind="role" />
                    </Td>
                    <Td className="max-w-40 truncate text-xs text-gray-600">
                      {u.location || "-"}
                    </Td>
                    <Td>
                      <StatusPill value={u.status} />
                      {u.rejection_reason && (
                        <p
                          className="mt-1 max-w-48 truncate text-xs text-red-600"
                          title={u.rejection_reason}
                        >
                          {u.rejection_reason}
                        </p>
                      )}
                    </Td>
                    <Td className="whitespace-nowrap text-xs text-gray-500">
                      {formatDate(u.created_at)}
                    </Td>
                    <Td align="center">
                      {isApprovals ? (
                        <div className="flex items-center justify-center gap-2">
                          <Button
                            size="sm"
                            icon={<Check className="h-3.5 w-3.5" />}
                            loading={busyId === u.id}
                            onClick={() => void approve(u)}
                          >
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="danger"
                            icon={<X className="h-3.5 w-3.5" />}
                            onClick={() => {
                              setRejecting(u);
                              setReason("");
                            }}
                          >
                            Reject
                          </Button>
                        </div>
                      ) : u.status === "PENDING" ? (
                        <span className="text-xs text-gray-400">Awaiting review</span>
                      ) : (
                        <Button
                          size="sm"
                          variant={u.status === "SUSPENDED" ? "secondary" : "danger"}
                          loading={busyId === u.id}
                          disabled={u.id === selfId}
                          title={
                            u.id === selfId
                              ? "You cannot change your own status"
                              : undefined
                          }
                          onClick={() => void toggleSuspend(u)}
                        >
                          {u.status === "SUSPENDED" ? "Reinstate" : "Suspend"}
                        </Button>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pagination page={page} count={count} onPage={setPage} />
          </>
        )}
      </Card>

      <Modal
        open={Boolean(rejecting)}
        onClose={() => setRejecting(null)}
        title="Reject registration"
        description={
          rejecting
            ? `${rejecting.full_name} (${rejecting.email}) will not be able to sign in.`
            : undefined
        }
        footer={
          <>
            <Button variant="secondary" onClick={() => setRejecting(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={rejectBusy}
              onClick={() => void confirmReject()}
            >
              Reject application
            </Button>
          </>
        }
      >
        <Field
          label="Reason"
          htmlFor="reject-reason"
          hint="Shown to the applicant. Leave blank to reject without one."
        >
          <Textarea
            id="reject-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Documents could not be verified."
          />
        </Field>
      </Modal>
    </div>
  );
}
