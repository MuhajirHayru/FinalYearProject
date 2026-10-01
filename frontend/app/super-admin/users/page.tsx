"use client";

import { useCallback, useEffect, useState } from "react";
import { RotateCcw, Search, ShieldCheck, UserCog, UserPlus } from "lucide-react";
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
  Th,
} from "@/components/ui";
import { superAdminApi } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";
import { formatDate, initials } from "@/lib/format";
import type { AdminAccount, SuperAdminDecision, SuperAdminRow, UserRole } from "@/lib/types";

/** `/superadmin/accounts/` only covers the two admin sub-roles. */
const ADMIN_ROLES: { value: UserRole; label: string }[] = [
  { value: "USER_ADMIN", label: "User Admin" },
  { value: "FINANCIAL_MANAGER", label: "Financial Manager" },
];

const STATUSES: { value: string; label: string }[] = [
  { value: "ALL", label: "All statuses" },
  { value: "APPROVED", label: "Approved" },
  { value: "PENDING", label: "Pending" },
  { value: "SUSPENDED", label: "Suspended" },
  { value: "REJECTED", label: "Rejected" },
  { value: "DEACTIVATED", label: "Deactivated" },
];

const DECISIONS: { value: SuperAdminDecision; label: string; variant: "primary" | "secondary" | "danger" }[] = [
  { value: "APPROVE", label: "Approve", variant: "primary" },
  { value: "REACTIVATE", label: "Reactivate", variant: "secondary" },
  { value: "SUSPEND", label: "Suspend", variant: "danger" },
  { value: "REJECT", label: "Reject", variant: "danger" },
];

/**
 * `/superadmin/accounts/` is limited to the admin sub-roles, so this second
 * table reads the full user list from `/superadmin/data/?resource=users` and
 * exposes the override actions the staff table cannot cover (FR-SA-03).
 */
function AllUsersOverrideTable() {
  const { user } = useAuth();
  const [rows, setRows] = useState<SuperAdminRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");

  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const res = await superAdminApi.data("users", 200);
      setRows(res.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function override(row: SuperAdminRow, decision: SuperAdminDecision) {
    if (!("full_name" in row)) return;
    if (row.id === user?.id) {
      setError("You cannot override your own account.");
      return;
    }
    setBusyId(row.id);
    setError("");
    try {
      const res = await superAdminApi.override(row.id, decision);
      setNotice(res.message || "Decision overridden.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Override failed.");
    } finally {
      setBusyId("");
    }
  }

  if (loading) return <PageLoader />;
  if (error)
    return (
      <Card className="p-5">
        <ErrorBanner message={error} onRetry={() => void load()} />
      </Card>
    );
  if (rows.length === 0)
    return (
      <Card>
        <EmptyState title="No users" description="No accounts exist yet." />
      </Card>
    );

  return (
    <div className="space-y-4">
      {notice && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {notice}
        </div>
      )}
      <Card>
        <div className="flex items-center justify-between gap-3 border-b border-gray-100 px-5 py-4">
          <p className="text-sm font-semibold text-gray-900">All Platform Users</p>
          <Button
            size="sm"
            variant="secondary"
            icon={<RotateCcw className="h-3.5 w-3.5" />}
            onClick={() => void load()}
          >
            Refresh
          </Button>
        </div>
        <TableWrap>
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Email</Th>
              <Th>Role</Th>
              <Th>Status</Th>
              <Th>Location</Th>
              <Th align="center">Override</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              if (!("full_name" in r)) return null;
              const isSelf = r.id === user?.id;
              return (
                <tr key={r.id}>
                  <Td className="font-medium text-gray-900">
                    {r.full_name}
                    {isSelf && <span className="ml-1.5 text-xs text-gray-400">(you)</span>}
                  </Td>
                  <Td className="text-xs">{r.email}</Td>
                  <Td>
                    <StatusPill value={r.role} kind="role" />
                  </Td>
                  <Td>
                    <StatusPill value={r.status} />
                  </Td>
                  <Td className="max-w-36 truncate text-xs text-gray-600">
                    {r.location || "-"}
                  </Td>
                  <Td align="center">
                    <div className="flex flex-wrap items-center justify-center gap-2">
                      {DECISIONS.map((d) => (
                        <Button
                          key={d.value}
                          size="sm"
                          variant={d.variant}
                          disabled={isSelf || busyId === r.id}
                          title={
                            isSelf ? "You cannot override your own account" : undefined
                          }
                          onClick={() => void override(r, d.value)}
                        >
                          {d.label}
                        </Button>
                      ))}
                    </div>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </TableWrap>
      </Card>
    </div>
  );
}

export default function SuperAdminUsersPage() {
  const { user } = useAuth();
  const [view, setView] = useState<"staff" | "all">("staff");
  const [rows, setRows] = useState<AdminAccount[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");

  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    role: "USER_ADMIN" as UserRole,
    phone: "",
    location: "",
  });
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await superAdminApi.accounts({
        page,
        search: search || undefined,
        status: status === "ALL" ? undefined : status,
      });
      setRows(res.results);
      setCount(res.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin accounts.");
    } finally {
      setLoading(false);
    }
  }, [page, search, status]);

  useEffect(() => {
    void load();
  }, [load]);

  async function createAccount() {
    setCreateBusy(true);
    setCreateError("");
    try {
      await superAdminApi.createAccount({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        password: form.password,
        role: form.role,
        phone: form.phone.trim() || undefined,
        location: form.location.trim() || undefined,
      });
      setNotice(`${form.full_name} can now sign in as ${form.role}.`);
      setCreating(false);
      setForm({
        full_name: "",
        email: "",
        password: "",
        role: "USER_ADMIN",
        phone: "",
        location: "",
      });
      await load();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Could not create the account.");
    } finally {
      setCreateBusy(false);
    }
  }

  async function toggleStatus(row: AdminAccount) {
    setBusyId(row.id);
    setError("");
    try {
      const res =
        row.status === "DEACTIVATED"
          ? await superAdminApi.reinstateAccount(row.id)
          : await superAdminApi.deactivateAccount(row.id);
      setNotice(res.message || "Account updated.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the account.");
    } finally {
      setBusyId("");
    }
  }

  async function override(row: AdminAccount, decision: SuperAdminDecision) {
    if (row.id === user?.id) {
      setError("You cannot override your own account.");
      return;
    }
    setBusyId(row.id);
    setError("");
    try {
      const res = await superAdminApi.override(row.id, decision);
      setNotice(res.message || "Decision overridden.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Override failed.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <AppShell title="Users" allow={["SUPER_ADMIN"]}>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Staff Accounts</h2>
          <p className="mt-1 text-sm text-gray-500">
            Only the Super Admin can grant admin sub-roles. Manage them here, and
            override any User Admin decision from the platform view.
          </p>
        </div>
        <Button
          icon={<UserPlus className="h-4 w-4" />}
          onClick={() => setCreating(true)}
        >
          New Staff Account
        </Button>
      </div>

      <div className="mb-6 flex gap-1 border-b border-gray-200">
        {(["staff", "all"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setView(tab)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${
              tab === view
                ? "border-green-600 text-green-700"
                : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700"
            }`}
          >
            {tab === "staff" ? "Staff accounts" : "All users"}
          </button>
        ))}
      </div>

      {view === "all" ? (
        <AllUsersOverrideTable />
      ) : (
        <>
      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} onRetry={() => void load()} />
        </div>
      )}
      {notice && (
        <div className="mb-5 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {notice}
        </div>
      )}

      {loading ? (
        <PageLoader />
      ) : (
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
                placeholder="Search staff by name or email..."
                className="pl-9"
                aria-label="Search staff"
              />
            </div>
            <Select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
              className="h-10 w-40"
              aria-label="Filter by status"
            >
              {STATUSES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
            <p className="text-xs text-gray-500">{count} account{count === 1 ? "" : "s"}</p>
          </div>

          {rows.length === 0 ? (
            <EmptyState
              title="No staff accounts"
              description="Create a User Admin or Financial Manager to delegate work."
              icon={<UserCog className="h-8 w-8" />}
            />
          ) : (
            <>
              <TableWrap>
                <thead>
                  <tr>
                    <Th>Name</Th>
                    <Th>Role</Th>
                    <Th>Status</Th>
                    <Th>Location</Th>
                    <Th>Created</Th>
                    <Th align="center">Actions</Th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((a) => {
                    const isSelf = a.id === user?.id;
                    return (
                      <tr key={a.id}>
                        <Td>
                          <div className="flex items-center gap-3">
                            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-purple-100 text-xs font-semibold text-purple-800">
                              {initials(a.full_name)}
                            </span>
                            <div className="min-w-0">
                              <p className="truncate font-medium text-gray-900">
                                {a.full_name}
                                {isSelf && (
                                  <span className="ml-1.5 text-xs font-normal text-gray-400">
                                    (you)
                                  </span>
                                )}
                              </p>
                              <p className="truncate text-xs text-gray-500">{a.email}</p>
                            </div>
                          </div>
                        </Td>
                        <Td>
                          <StatusPill value={a.role} kind="role" />
                        </Td>
                        <Td>
                          <StatusPill value={a.status} />
                        </Td>
                        <Td className="max-w-36 truncate text-xs text-gray-600">
                          {a.location || "-"}
                        </Td>
                        <Td className="whitespace-nowrap text-xs text-gray-500">
                          {formatDate(a.created_at)}
                        </Td>
                        <Td align="center">
                          <div className="flex flex-wrap items-center justify-center gap-2">
                            <Button
                              size="sm"
                              variant="secondary"
                              icon={
                                a.status === "DEACTIVATED" ? (
                                  <RotateCcw className="h-3.5 w-3.5" />
                                ) : (
                                  <ShieldCheck className="h-3.5 w-3.5" />
                                )
                              }
                              loading={busyId === a.id}
                              disabled={isSelf}
                              title={isSelf ? "You cannot deactivate your own account" : undefined}
                              onClick={() => void toggleStatus(a)}
                            >
                              {a.status === "DEACTIVATED" ? "Reinstate" : "Deactivate"}
                            </Button>
                            {DECISIONS.map((d) => (
                              <Button
                                key={d.value}
                                size="sm"
                                variant={d.variant}
                                disabled={isSelf || busyId === a.id}
                                title={
                                  isSelf ? "You cannot override your own account" : undefined
                                }
                                onClick={() => void override(a, d.value)}
                              >
                                {d.label}
                              </Button>
                            ))}
                          </div>
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </TableWrap>
              <Pagination page={page} count={count} onPage={setPage} />
            </>
          )}
        </Card>
      )}

        </>
      )}

      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title="New staff account"
        description="Admin sub-roles can only be granted here, never through public registration."
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button loading={createBusy} onClick={() => void createAccount()}>
              Create account
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {createError && <ErrorBanner message={createError} />}
          <Field label="Full name" htmlFor="sa-name">
            <Input
              id="sa-name"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              placeholder="Hana Bekele"
            />
          </Field>
          <Field label="Email" htmlFor="sa-email">
            <Input
              id="sa-email"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="hana@greenpath.et"
            />
          </Field>
          <Field label="Password" htmlFor="sa-password" hint="Minimum 8 characters.">
            <Input
              id="sa-password"
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </Field>
          <Field label="Role" htmlFor="sa-role">
            <Select
              id="sa-role"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })}
            >
              {ADMIN_ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </Select>
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Phone" htmlFor="sa-phone">
              <Input
                id="sa-phone"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
              />
            </Field>
            <Field label="Location" htmlFor="sa-location">
              <Input
                id="sa-location"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
                placeholder="Addis Ababa"
              />
            </Field>
          </div>
        </div>
      </Modal>
    </AppShell>
  );
}
