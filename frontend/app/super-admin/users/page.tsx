"use client";

import { useCallback, useEffect, useState } from "react";
import { Eye, RotateCcw, Search, ShieldCheck, UnlockKeyhole, UserCog, UserPlus } from "lucide-react";
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
import { registrationApi, superAdminApi } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";
import { formatDate, formatDateTime, initials } from "@/lib/format";
import type {
  AdminAccount,
  AdminAccountActivity,
  AdminCreationOptions,
  DirectoryUser,
  RegistrationLocation,
  SuperAdminDecision,
  UserRole,
} from "@/lib/types";

const ADMIN_SCOPE_TYPES: Record<string, { label: string; levels: string[] }> = {
  TOP_LEVEL: { label: "Top-Level User Admin", levels: [] },
  REGIONAL: { label: "Regional Admin", levels: ["REGION"] },
  CITY: { label: "City Administration Admin", levels: ["CITY"] },
  ZONAL: { label: "Zonal Admin", levels: ["ZONE"] },
  WOREDA: { label: "Woreda Admin", levels: ["WOREDA"] },
  SUBCITY: { label: "Sub-city Admin", levels: ["SUBCITY"] },
  DISTRICT: { label: "District Admin", levels: ["DISTRICT"] },
  ADMIN_DIVISION: { label: "Administrative Division Admin", levels: ["OTHER"] },
};

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
  const [rows, setRows] = useState<DirectoryUser[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");

  const load = useCallback(async () => {
    setError("");
    setLoading(true);
    try {
      const res = await superAdminApi.users({
        page,
        search: search || undefined,
        role: role || undefined,
        status: status || undefined,
        created_from: createdFrom || undefined,
        created_to: createdTo || undefined,
      });
      setRows(res.results);
      setCount(res.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users.");
    } finally {
      setLoading(false);
    }
  }, [page, search, role, status, createdFrom, createdTo]);

  useEffect(() => {
    void load();
  }, [load]);

  async function override(row: DirectoryUser, decision: SuperAdminDecision) {
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

  async function unlockLogin(row: DirectoryUser) {
    if (row.id === user?.id || !row.locked_until) return;
    const reason = window.prompt(`Why are you unlocking ${row.full_name}'s sign-in?`);
    if (!reason?.trim()) return;
    if (!window.confirm(`Clear the active login lockout for ${row.full_name}?`)) return;
    setBusyId(row.id);
    setError("");
    try {
      const result = await superAdminApi.unlockLogin(row.id, reason.trim());
      setNotice(result.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not unlock this account.");
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
        <div className="grid gap-2 border-b border-gray-100 px-5 py-4 sm:grid-cols-2 lg:grid-cols-5">
          <Input
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
            placeholder="Search name, email, or phone"
            aria-label="Search platform users"
          />
          <Select
            value={role}
            onChange={(event) => {
              setRole(event.target.value);
              setPage(1);
            }}
            aria-label="Filter platform users by role"
          >
            <option value="">All roles</option>
            <option value="FARMER">Farmer</option>
            <option value="WHOLESALER">Wholesaler</option>
            <option value="RETAILER">Retailer</option>
            <option value="USER_ADMIN">User Admin</option>
            <option value="FINANCIAL_MANAGER">Financial Manager</option>
            <option value="SUPER_ADMIN">Super Admin</option>
          </Select>
          <Select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
            aria-label="Filter platform users by status"
          >
            <option value="">All statuses</option>
            <option value="PENDING">Pending</option>
            <option value="APPROVED">Approved</option>
            <option value="SUSPENDED">Suspended</option>
            <option value="REJECTED">Rejected</option>
            <option value="DEACTIVATED">Deactivated</option>
          </Select>
          <Input
            type="date"
            value={createdFrom}
            onChange={(event) => {
              setCreatedFrom(event.target.value);
              setPage(1);
            }}
            aria-label="Created from"
          />
          <Input
            type="date"
            value={createdTo}
            onChange={(event) => {
              setCreatedTo(event.target.value);
              setPage(1);
            }}
            aria-label="Created to"
          />
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
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-5 py-8 text-center text-sm text-gray-500">
                  No users match these filters.
                </td>
              </tr>
            ) : rows.map((r) => {
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
                    {r.locked_until && (
                      <p className="mt-1 text-xs text-amber-700">
                        Login locked until {formatDateTime(r.locked_until)}
                      </p>
                    )}
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
                      {r.locked_until && (
                        <Button
                          size="sm"
                          variant="secondary"
                          icon={<UnlockKeyhole className="h-3.5 w-3.5" />}
                          disabled={isSelf || busyId === r.id}
                          onClick={() => void unlockLogin(r)}
                        >
                          Unlock login
                        </Button>
                      )}
                    </div>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </TableWrap>
        <Pagination page={page} count={count} onPage={setPage} />
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
  const [roleFilter, setRoleFilter] = useState("");
  const [scopeTypeFilter, setScopeTypeFilter] = useState("");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [lastActiveFrom, setLastActiveFrom] = useState("");
  const [lastActiveTo, setLastActiveTo] = useState("");
  const [staffLocationLevels, setStaffLocationLevels] = useState<RegistrationLocation[][]>([]);
  const [staffLocationIds, setStaffLocationIds] = useState<string[]>([]);
  const [loadingStaffLocationIndex, setLoadingStaffLocationIndex] = useState<number | null>(null);
  const [selectedStaff, setSelectedStaff] = useState<AdminAccount | null>(null);
  const [activity, setActivity] = useState<AdminAccountActivity | null>(null);
  const [activityLoading, setActivityLoading] = useState(false);
  const [activityError, setActivityError] = useState("");
  const [activityPeriod, setActivityPeriod] = useState<"7" | "30" | "90" | "custom">("30");
  const [activityFrom, setActivityFrom] = useState("");
  const [activityTo, setActivityTo] = useState("");
  const [activityPage, setActivityPage] = useState(1);
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
    scope_type: "REGIONAL",
    phone: "",
    location: "",
  });
  const [creationOptions, setCreationOptions] = useState<AdminCreationOptions | null>(null);
  const [scopeLevels, setScopeLevels] = useState<RegistrationLocation[][]>([]);
  const [scopeLocations, setScopeLocations] = useState<string[]>([]);
  const [loadingScopeIndex, setLoadingScopeIndex] = useState<number | null>(null);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState("");
  const [creationOptionsLoading, setCreationOptionsLoading] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await superAdminApi.accounts({
        page,
        search: search || undefined,
        status: status === "ALL" ? undefined : status,
        role: roleFilter || undefined,
        scope_type: scopeTypeFilter || undefined,
        location_id: staffLocationIds.at(-1) || undefined,
        created_from: createdFrom || undefined,
        created_to: createdTo || undefined,
        last_active_from: lastActiveFrom || undefined,
        last_active_to: lastActiveTo || undefined,
      });
      setRows(res.results);
      setCount(res.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin accounts.");
    } finally {
      setLoading(false);
    }
  }, [
    page,
    search,
    status,
    roleFilter,
    scopeTypeFilter,
    staffLocationIds,
    createdFrom,
    createdTo,
    lastActiveFrom,
    lastActiveTo,
  ]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void registrationApi.locations()
      .then((roots) => setStaffLocationLevels([roots]))
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Could not load geographic filters.");
      });
  }, []);

  useEffect(() => {
    if (!selectedStaff) {
      setActivity(null);
      return;
    }
    let cancelled = false;
    setActivityLoading(true);
    setActivityError("");
    const query = activityPeriod === "custom"
      ? { from: activityFrom || undefined, to: activityTo || undefined, page: activityPage }
      : { days: activityPeriod, page: activityPage };
    void superAdminApi.accountActivity(selectedStaff.id, query)
      .then((result) => {
        if (!cancelled) setActivity(result);
      })
      .catch((err) => {
        if (!cancelled) {
          setActivityError(err instanceof Error ? err.message : "Could not load staff activity.");
        }
      })
      .finally(() => {
        if (!cancelled) setActivityLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedStaff, activityPeriod, activityFrom, activityTo, activityPage]);

  async function selectStaffLocation(index: number, location: RegistrationLocation | null) {
    const nextIds = staffLocationIds.slice(0, index);
    const nextLevels = staffLocationLevels.slice(0, index + 1);
    if (location) nextIds[index] = location.id;
    setStaffLocationIds(nextIds);
    setStaffLocationLevels(nextLevels);
    setPage(1);
    if (location?.has_children) {
      setLoadingStaffLocationIndex(index);
      try {
        const children = await registrationApi.locations(location.id);
        setStaffLocationLevels((current) => [
          ...current.slice(0, index + 1),
          children,
        ]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load child locations.");
      } finally {
        setLoadingStaffLocationIndex(null);
      }
    }
  }

  function clearStaffFilters() {
    setSearch("");
    setStatus("ALL");
    setRoleFilter("");
    setScopeTypeFilter("");
    setCreatedFrom("");
    setCreatedTo("");
    setLastActiveFrom("");
    setLastActiveTo("");
    setStaffLocationIds([]);
    setStaffLocationLevels((current) => current.slice(0, 1));
    setPage(1);
  }

  function showStaffActivity(account: AdminAccount) {
    setActivity(null);
    setActivityPeriod("30");
    setActivityFrom("");
    setActivityTo("");
    setActivityPage(1);
    setSelectedStaff(account);
  }

  async function beginCreate() {
    if (creationOptionsLoading || createBusy) return;
    setCreating(true);
    setCreateError("");
    setCreationOptionsLoading(true);
    try {
      const options = await superAdminApi.creationOptions();
      setCreationOptions(options);
      const roots = await registrationApi.locations(options.scope_location_id || undefined);
      setScopeLevels([roots]);
      setScopeLocations([]);
      const firstType = options.scope_types[0] || "";
      setForm((current) => ({
        ...current,
        role: "USER_ADMIN",
        scope_type: firstType,
      }));
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Could not load staff options.");
    } finally {
      setCreationOptionsLoading(false);
    }
  }

  async function selectScopeLocation(index: number, location: RegistrationLocation | null) {
    const path = scopeLocations.slice(0, index);
    const levels = scopeLevels.slice(0, index + 1);
    if (location) path[index] = location.id;
    setScopeLocations(path);
    setScopeLevels(levels);
    const selectedScopeType = ADMIN_SCOPE_TYPES[form.scope_type];
    const matchesType = Boolean(
      location && selectedScopeType?.levels.includes(location.level)
    );
    if (location?.has_children && !matchesType) {
      setLoadingScopeIndex(index);
      try {
        const children = await registrationApi.locations(location.id);
        setScopeLevels((current) => [...current.slice(0, index + 1), children]);
      } catch (err) {
        setCreateError(err instanceof Error ? err.message : "Could not load child locations.");
      } finally {
        setLoadingScopeIndex(null);
      }
    }
  }

  async function createAccount() {
    if (createBusy) return;
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
        ...(form.role === "USER_ADMIN"
          ? {
              scope_level: form.scope_type === "TOP_LEVEL" ? "GLOBAL" : "LOCATION",
              scope_location:
                form.scope_type !== "TOP_LEVEL"
                  ? scopeLocations.at(-1) || null
                  : null,
              scope_type: form.scope_type,
            }
          : {}),
      });
      const scopeDescription =
        form.role === "USER_ADMIN"
          ? form.scope_type === "TOP_LEVEL"
            ? " with nationwide scope"
            : ` as ${ADMIN_SCOPE_TYPES[form.scope_type]?.label || "scoped User Admin"}`
          : "";
      setNotice(`${form.full_name} can now sign in as ${form.role}${scopeDescription}.`);
      setCreating(false);
      setScopeLocations([]);
      setScopeLevels(scopeLevels.slice(0, 1));
      setForm({
        full_name: "",
        email: "",
        password: "",
        role: "USER_ADMIN",
        scope_type: creationOptions?.scope_types[0] || "",
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
        row.status === "DEACTIVATED" || row.status === "SUSPENDED"
          ? await superAdminApi.reinstateAccount(row.id)
          : await superAdminApi.suspendAccount(row.id);
      setNotice(res.message || "Account updated.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the account.");
    } finally {
      setBusyId("");
    }
  }

  return (
    <AppShell title="Staff accounts" allow={["USER_ADMIN", "SUPER_ADMIN"]}>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Staff Accounts</h2>
          <p className="mt-1 text-sm text-gray-500">
            Create and manage staff accounts permitted by your role and geographic assignment.
          </p>
        </div>
        <Button
          icon={<UserPlus className="h-4 w-4" />}
          onClick={() => void beginCreate()}
        >
          New Staff Account
        </Button>
      </div>

      <div className="mb-6 flex gap-1 border-b border-gray-200">
        {(user?.role === "SUPER_ADMIN" ? (["staff", "all"] as const) : (["staff"] as const)).map((tab) => (
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
          <div className="grid gap-3 border-b border-gray-100 p-4 sm:grid-cols-2 xl:grid-cols-4">
            <label className="text-xs font-medium text-gray-600 xl:col-span-2">
              Search name, email, or phone
              <div className="relative mt-1">
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
            </label>
            <label className="text-xs font-medium text-gray-600">
              Account status
              <Select
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setPage(1);
                }}
                className="mt-1"
                aria-label="Filter by status"
              >
                {STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </label>
            <label className="text-xs font-medium text-gray-600">
              Administrator type
              <Select
                value={scopeTypeFilter}
                onChange={(event) => {
                  setScopeTypeFilter(event.target.value);
                  setPage(1);
                }}
                className="mt-1"
                aria-label="Filter by administrator type"
              >
                <option value="">All staff types</option>
                {[
                  "TOP_LEVEL",
                  "REGIONAL",
                  "CITY",
                  "ZONAL",
                  "WOREDA",
                  "SUBCITY",
                  "DISTRICT",
                  "ADMIN_DIVISION",
                  "FINANCIAL_MANAGER",
                ].map((type) => (
                  <option key={type} value={type}>
                    {type === "FINANCIAL_MANAGER"
                      ? "Financial Manager"
                      : ADMIN_SCOPE_TYPES[type]?.label || type}
                  </option>
                ))}
              </Select>
            </label>
            <label className="text-xs font-medium text-gray-600">
              Staff role
              <Select
                value={roleFilter}
                onChange={(event) => {
                  setRoleFilter(event.target.value);
                  setPage(1);
                }}
                className="mt-1"
                aria-label="Filter by staff role"
              >
                <option value="">All roles</option>
                <option value="USER_ADMIN">User Admin</option>
                {user?.role === "SUPER_ADMIN" && (
                  <option value="FINANCIAL_MANAGER">Financial Manager</option>
                )}
              </Select>
            </label>
            {staffLocationLevels.map((choices, index) => (
              <label
                key={`staff-location-filter-${index}`}
                className="text-xs font-medium text-gray-600"
              >
                {index === 0 ? "Region / city" : "Child geographic area"}
                <Select
                  value={staffLocationIds[index] || ""}
                  disabled={loadingStaffLocationIndex === index}
                  onChange={(event) =>
                    void selectStaffLocation(
                      index,
                      choices.find((location) => location.id === event.target.value) || null,
                    )
                  }
                  className="mt-1"
                  aria-label={`Filter staff by ${index === 0 ? "region or city" : "child geographic area"}`}
                >
                  <option value="">
                    {loadingStaffLocationIndex === index ? "Loading…" : "All areas"}
                  </option>
                  {choices.map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name} ({location.level_display})
                    </option>
                  ))}
                </Select>
              </label>
            ))}
            {(
              [
                ["createdFrom", "Created from", createdFrom, setCreatedFrom],
                ["createdTo", "Created to", createdTo, setCreatedTo],
                ["lastActiveFrom", "Last active from", lastActiveFrom, setLastActiveFrom],
                ["lastActiveTo", "Last active to", lastActiveTo, setLastActiveTo],
              ] as const
            ).map(([key, label, value, setter]) => (
              <label key={key} className="text-xs font-medium text-gray-600">
                {label}
                <Input
                  type="date"
                  value={value}
                  onChange={(event) => {
                    setter(event.target.value);
                    setPage(1);
                  }}
                  className="mt-1"
                />
              </label>
            ))}
            <div className="flex flex-wrap items-end justify-between gap-2 xl:col-span-4">
              <p className="text-xs text-gray-500">
                {count} account{count === 1 ? "" : "s"}
              </p>
              <Button size="sm" variant="secondary" onClick={clearStaffFilters}>
                Clear filters
              </Button>
            </div>
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
                    <Th>Administrator type</Th>
                    <Th>Status</Th>
                    <Th>Geographic assignment</Th>
                    <Th>Created / last active</Th>
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
                          <span className="text-sm text-gray-700">
                            {a.scope_label || a.role_display}
                          </span>
                        </Td>
                        <Td>
                          <StatusPill value={a.status} />
                        </Td>
                        <Td className="max-w-36 truncate text-xs text-gray-600">
                          {a.location_name || a.location || "-"}
                        </Td>
                        <Td className="whitespace-nowrap text-xs text-gray-500">
                          <span className="block">{formatDate(a.created_at)}</span>
                          <span className="mt-1 block text-gray-400">
                            Last active: {formatDate(a.last_login)}
                          </span>
                        </Td>
                        <Td align="center">
                          <div className="flex flex-wrap items-center justify-center gap-2">
                            <Button
                              size="sm"
                              variant="secondary"
                              icon={<Eye className="h-3.5 w-3.5" />}
                              onClick={() => showStaffActivity(a)}
                            >
                              Details
                            </Button>
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
                              title={isSelf ? "You cannot suspend your own account" : undefined}
                              onClick={() => void toggleStatus(a)}
                            >
                              {a.status === "DEACTIVATED" || a.status === "SUSPENDED"
                                ? "Reactivate"
                                : "Suspend"}
                            </Button>
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
        open={Boolean(selectedStaff)}
        onClose={() => setSelectedStaff(null)}
        title={selectedStaff ? `${selectedStaff.full_name} — staff details` : "Staff details"}
        description="Current account and geographic scope totals are separate from actions attributed to this administrator."
        size="lg"
      >
        {selectedStaff && (
          <div className="space-y-5">
            {activityError && <ErrorBanner message={activityError} />}
            <section className="grid gap-3 rounded-lg border border-gray-100 p-4 sm:grid-cols-2">
              <div>
                <p className="text-xs text-gray-500">Staff identifier</p>
                <p className="font-mono text-sm text-gray-800">{selectedStaff.id}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Administrator type</p>
                <p className="text-sm text-gray-800">
                  {selectedStaff.scope_label || selectedStaff.role_display}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Account status</p>
                <StatusPill value={selectedStaff.status} />
              </div>
              <div>
                <p className="text-xs text-gray-500">Assigned scope</p>
                <p className="text-sm text-gray-800">
                  {activity?.staff.scope || selectedStaff.location_name || "Loading…"}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Created</p>
                <p className="text-sm text-gray-800">{formatDate(selectedStaff.created_at)}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500">Last login</p>
                <p className="text-sm text-gray-800">{formatDate(selectedStaff.last_login)}</p>
              </div>
              <div className="sm:col-span-2">
                <p className="text-xs text-gray-500">Created by</p>
                <p className="text-sm text-gray-800">
                  {activity?.staff.created_by
                    ? `${activity.staff.created_by.name} (${activity.staff.created_by.email})`
                    : activityLoading
                      ? "Loading…"
                      : "Not recorded in the audit history"}
                </p>
              </div>
              {activity?.staff.permissions.length ? (
                <div className="sm:col-span-2">
                  <p className="text-xs text-gray-500">Role permissions</p>
                  <p className="text-sm text-gray-700">
                    {activity.staff.permissions.join(", ")}
                  </p>
                </div>
              ) : null}
            </section>

            <section>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <h3 className="font-semibold text-gray-900">Administrative performance</h3>
                <div className="flex flex-wrap items-center gap-2">
                  <Select
                    aria-label="Activity date range"
                    value={activityPeriod}
                    onChange={(event) => {
                      setActivityPeriod(event.target.value as "7" | "30" | "90" | "custom");
                      setActivityPage(1);
                    }}
                    className="w-auto"
                  >
                    <option value="7">Last 7 days</option>
                    <option value="30">Last 30 days</option>
                    <option value="90">Last 90 days</option>
                    <option value="custom">Custom range</option>
                  </Select>
                  {activityPeriod === "custom" && (
                    <>
                      <Input
                        type="date"
                        aria-label="Activity start date"
                        value={activityFrom}
                        onChange={(event) => {
                          setActivityFrom(event.target.value);
                          setActivityPage(1);
                        }}
                      />
                      <Input
                        type="date"
                        aria-label="Activity end date"
                        value={activityTo}
                        onChange={(event) => {
                          setActivityTo(event.target.value);
                          setActivityPage(1);
                        }}
                      />
                    </>
                  )}
                </div>
              </div>
              {activityLoading ? (
                <PageLoader label="Loading staff activity…" />
              ) : activity ? (
                <>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
                    {(
                      [
                        ["Actions performed", activity.statistics.actions],
                        ["Users approved", activity.statistics.approved],
                        ["Users rejected", activity.statistics.rejected],
                        ["Users suspended", activity.statistics.suspended],
                        ["Users reactivated", activity.statistics.reactivated],
                        ["Staff created", activity.statistics.staff_created],
                        ["Users in current scope", activity.statistics.current_scope_users],
                        ["Pending in current scope", activity.statistics.pending_approvals_in_scope],
                        ["Farmers in current scope", activity.statistics.current_scope_farmers],
                        ["Wholesalers in current scope", activity.statistics.current_scope_wholesalers],
                        ["Retailers in current scope", activity.statistics.current_scope_retailers],
                      ] as const
                    ).map(([label, value]) => (
                      <div key={label} className="rounded-lg bg-gray-50 p-3">
                        <p className="text-xs text-gray-500">{label}</p>
                        <p className="mt-1 text-xl font-semibold text-gray-900">{value}</p>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4">
                    <h4 className="mb-2 text-sm font-semibold text-gray-800">Activity history</h4>
                    {activity.results.length ? (
                      <div className="space-y-2">
                        {activity.results.map((entry) => (
                          <article key={entry.id} className="rounded-lg border border-gray-100 p-3">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="text-sm font-medium text-gray-800">
                                {entry.action.replaceAll("_", " ")}
                              </span>
                              <span className="text-xs text-gray-500">
                                {formatDateTime(entry.created_at)}
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-gray-500">
                              Actor: {entry.actor_name || entry.actor_role || "System"}
                            </p>
                            <p className="mt-1 break-all text-xs text-gray-600">
                              Affected account: {entry.target || "—"}
                            </p>
                            {entry.detail && (
                              <p className="mt-1 whitespace-pre-wrap text-xs text-gray-500">
                                Reason / detail: {entry.detail}
                              </p>
                            )}
                          </article>
                        ))}
                        <Pagination
                          page={activityPage}
                          count={activity.count}
                          onPage={setActivityPage}
                        />
                      </div>
                    ) : (
                      <EmptyState
                        title="No recorded actions in this period"
                        description="Only actions present in the audit log are counted."
                      />
                    )}
                    <p className="mt-3 text-xs text-gray-400">
                      Geographic scope at the time of an action and historical status snapshots are not stored in the current audit records.
                    </p>
                  </div>
                </>
              ) : null}
            </section>
          </div>
        )}
      </Modal>

      <Modal
        open={creating}
        onClose={() => {
          if (!createBusy) setCreating(false);
        }}
        title="New staff account"
        description="Choose the staff type first; available assignments are limited by your authority."
        size="lg"
        footer={
          <>
            <Button
              variant="secondary"
              disabled={createBusy}
              onClick={() => setCreating(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              form="create-staff-account"
              loading={createBusy || creationOptionsLoading}
              disabled={creationOptionsLoading}
            >
              Create account
            </Button>
          </>
        }
      >
        <form
          id="create-staff-account"
          className="grid grid-cols-1 gap-4 sm:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            void createAccount();
          }}
        >
          {createError && (
            <div className="sm:col-span-2">
              <ErrorBanner message={createError} />
            </div>
          )}
          <Field label="Staff type *" htmlFor="sa-role">
            <Select
              id="sa-role"
              required
              value={form.role === "FINANCIAL_MANAGER" ? "FINANCIAL_MANAGER" : form.scope_type}
              onChange={(e) => {
                const selected = e.target.value;
                setForm({
                  ...form,
                  role: selected === "FINANCIAL_MANAGER" ? "FINANCIAL_MANAGER" : "USER_ADMIN",
                  scope_type: selected,
                });
                setScopeLocations([]);
                setScopeLevels((current) => current.slice(0, 1));
              }}
            >
              {creationOptions?.scope_types.map((scopeType) => (
                <option key={scopeType} value={scopeType}>
                  {ADMIN_SCOPE_TYPES[scopeType]?.label || scopeType}
                </option>
              ))}
              {creationOptions?.can_create_financial_manager && (
                <option value="FINANCIAL_MANAGER">Financial Manager</option>
              )}
            </Select>
          </Field>
          <Field label="Full name *" htmlFor="sa-name">
            <Input
              id="sa-name"
              required
              autoComplete="name"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              placeholder="Hana Bekele"
            />
          </Field>
          <Field label="Email *" htmlFor="sa-email">
            <Input
              id="sa-email"
              type="email"
              required
              autoComplete="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="hana@greenpath.et"
            />
          </Field>
          <Field label="Password *" htmlFor="sa-password" hint="Minimum 8 characters.">
            <Input
              id="sa-password"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </Field>
          {form.role === "USER_ADMIN" && form.scope_type === "TOP_LEVEL" && (
            <p className="rounded-lg bg-blue-50 p-3 text-sm text-blue-800 sm:col-span-2">
              This account will have nationwide operational scope.
            </p>
          )}
          {form.role === "USER_ADMIN" && form.scope_type !== "TOP_LEVEL" && (
              <div className="space-y-3 rounded-lg border border-gray-200 p-3 sm:col-span-2">
                  <p className="text-xs text-gray-600">
                    Select the exact administrative unit for this assignment. Access is limited to that unit and its descendants.
                  </p>
                  {creationOptionsLoading && (
                    <p className="text-sm text-gray-500">Loading authorized staff options…</p>
                  )}
                  {scopeLevels.map((choices, index) => (
                    <Field
                      key={`new-admin-location-${index}`}
                      label={index === 0 ? "Region / city administration *" : "Child administrative division *"}
                    >
                      <Select
                        value={scopeLocations[index] || ""}
                        required
                        disabled={loadingScopeIndex === index}
                        onChange={(event) => void selectScopeLocation(
                          index,
                          choices.find((item) => item.id === event.target.value) || null
                        )}
                      >
                        <option value="">
                          {loadingScopeIndex === index ? "Loading locations..." : "Select location"}
                        </option>
                        {choices
                          .filter((location) => {
                            const targetLevels = ADMIN_SCOPE_TYPES[form.scope_type]?.levels || [];
                            return targetLevels.includes(location.level) || location.has_children;
                          })
                          .map((location) => (
                          <option key={location.id} value={location.id}>
                            {location.name} ({location.level_display})
                          </option>
                          ))}
                      </Select>
                    </Field>
                  ))}
                  {!creationOptionsLoading && !scopeLevels[0]?.length && (
                    <p className="text-sm text-amber-800">
                      No verified locations are loaded. Import the approved reference dataset before creating a scoped User Admin.
                    </p>
                  )}
              </div>
          )}
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
        </form>
      </Modal>
    </AppShell>
  );
}
