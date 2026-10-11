"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { FileText, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  PageLoader,
  Pagination,
  TableWrap,
  Td,
  Th,
} from "@/components/ui";
import { superAdminApi } from "@/lib/api/client";
import { formatDateTime, initials } from "@/lib/format";
import type { AuditLog } from "@/lib/types";

type AuditFilters = {
  administrator: string;
  role: string;
  action: string;
  target: string;
  from: string;
  to: string;
  registration_status: string;
  license_status: string;
};

const emptyFilters: AuditFilters = {
  administrator: "",
  role: "",
  action: "",
  target: "",
  from: "",
  to: "",
  registration_status: "",
  license_status: "",
};

export default function SuperAdminAuditPage() {
  const [rows, setRows] = useState<AuditLog[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [draftFilters, setDraftFilters] = useState(emptyFilters);
  const [filters, setFilters] = useState(emptyFilters);

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await superAdminApi.audit(page, filters);
      setRows(res.results);
      setCount(res.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load audit logs.");
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setFilters({ ...draftFilters });
  }

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <AppShell title="Audit Logs" allow={["SUPER_ADMIN", "USER_ADMIN"]}>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Audit Logs</h2>
          <p className="mt-1 text-sm text-gray-500">
            Review actions visible within your assigned administration scope.
          </p>
        </div>
        <Button
          variant="secondary"
          icon={<RefreshCw className="h-4 w-4" />}
          onClick={() => void load()}
        >
          Refresh
        </Button>
      </div>

      <Card className="mb-5">
        <form
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          onSubmit={applyFilters}
        >
          {(
            [
              ["administrator", "Administrator"],
              ["action", "Action"],
              ["target", "Target"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="text-xs font-medium text-gray-600">
              {label}
              <input
                className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                value={draftFilters[key]}
                onChange={(event) =>
                  setDraftFilters((current) => ({
                    ...current,
                    [key]: event.target.value,
                  }))
                }
              />
            </label>
          ))}
          <label className="text-xs font-medium text-gray-600">
            Role
            <select
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
              value={draftFilters.role}
              onChange={(event) =>
                setDraftFilters((current) => ({ ...current, role: event.target.value }))
              }
            >
              <option value="">All roles</option>
              {["SUPER_ADMIN", "USER_ADMIN", "FINANCIAL_MANAGER", "FARMER", "WHOLESALER", "RETAILER"].map(
                (role) => (
                  <option key={role} value={role}>
                    {role.replaceAll("_", " ")}
                  </option>
                ),
              )}
            </select>
          </label>
          <label className="text-xs font-medium text-gray-600">
            Registration status
            <select
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
              value={draftFilters.registration_status}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  registration_status: event.target.value,
                }))
              }
            >
              <option value="">All statuses</option>
              {["DRAFT", "SUBMITTED", "CHANGES_REQUESTED", "APPROVED", "REJECTED"].map(
                (status) => (
                  <option key={status} value={status}>
                    {status.replaceAll("_", " ")}
                  </option>
                ),
              )}
            </select>
          </label>
          <label className="text-xs font-medium text-gray-600">
            License status
            <select
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
              value={draftFilters.license_status}
              onChange={(event) =>
                setDraftFilters((current) => ({
                  ...current,
                  license_status: event.target.value,
                }))
              }
            >
              <option value="">All statuses</option>
              {["PENDING", "VERIFIED", "REJECTED"].map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </label>
          {(["from", "to"] as const).map((key) => (
            <label key={key} className="text-xs font-medium text-gray-600">
              {key === "from" ? "From date" : "To date"}
              <input
                type="date"
                className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                value={draftFilters[key]}
                onChange={(event) =>
                  setDraftFilters((current) => ({
                    ...current,
                    [key]: event.target.value,
                  }))
                }
              />
            </label>
          ))}
          <div className="flex items-end gap-2">
            <Button type="submit">Apply filters</Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setDraftFilters(emptyFilters);
                setPage(1);
                setFilters(emptyFilters);
              }}
            >
              Clear
            </Button>
          </div>
        </form>
      </Card>

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
            title="No audit entries"
            description="Privileged actions will be recorded here."
            icon={<FileText className="h-8 w-8" />}
          />
        </Card>
      ) : (
        <Card>
          <TableWrap>
            <thead>
              <tr>
                <Th>Actor</Th>
                <Th>Action</Th>
                <Th>Target</Th>
                <Th>Detail</Th>
                <Th>When</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr key={a.id}>
                  <Td>
                    <div className="flex items-center gap-2.5">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-100 text-[10px] font-semibold text-gray-600">
                        {initials(a.actor_name ?? a.actor)}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-xs text-gray-700">
                          {a.actor_name ?? a.actor ?? "system"}
                        </span>
                        {a.actor_role && (
                          <span className="text-[10px] text-gray-400">
                            {a.actor_role.replaceAll("_", " ")}
                          </span>
                        )}
                      </span>
                    </div>
                  </Td>
                  <Td>
                    <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-800">
                      {a.action}
                    </code>
                  </Td>
                  <Td className="max-w-40 truncate text-xs">{a.target}</Td>
                  <Td className="max-w-96 text-xs text-gray-600">
                    <span className="line-clamp-2">{a.detail}</span>
                  </Td>
                  <Td className="whitespace-nowrap text-xs text-gray-500">
                    {formatDateTime(a.created_at)}
                  </Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <Pagination page={page} count={count} onPage={setPage} />
        </Card>
      )}
    </AppShell>
  );
}
