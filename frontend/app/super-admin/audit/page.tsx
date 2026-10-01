"use client";

import { useCallback, useEffect, useState } from "react";
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

export default function SuperAdminAuditPage() {
  const [rows, setRows] = useState<AuditLog[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const res = await superAdminApi.audit(page);
      setRows(res.results);
      setCount(res.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load audit logs.");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <AppShell title="Audit Logs" allow={["SUPER_ADMIN"]}>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Audit Logs</h2>
          <p className="mt-1 text-sm text-gray-500">
            Every privileged action, appended immutably by the backend.
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
                      <span className="truncate text-xs text-gray-700">
                        {a.actor_name ?? a.actor ?? "system"}
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
