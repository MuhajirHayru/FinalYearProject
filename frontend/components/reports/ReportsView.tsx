"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, FileText, Search, Table } from "lucide-react";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  Field,
  Input,
  PageLoader,
  Select,
} from "@/components/ui";
import { reportsApi } from "@/lib/api/client";
import type {
  FinancialReport,
  FinancialReportQuery,
  PaymentMethod,
  PaymentStatus,
} from "@/lib/types";

const STATUSES: { value: PaymentStatus | "ALL"; label: string }[] = [
  { value: "ALL", label: "All statuses" },
  { value: "PENDING", label: "Pending" },
  { value: "VERIFIED", label: "Verified" },
  { value: "FLAGGED", label: "Flagged" },
  { value: "DISPUTED", label: "Disputed" },
];
const METHODS: { value: PaymentMethod | "ALL"; label: string }[] = [
  { value: "ALL", label: "All methods" },
  { value: "CBE Birr", label: "CBE Birr" },
  { value: "Telebirr", label: "Telebirr" },
  { value: "Bank Transfer", label: "Bank Transfer" },
  { value: "Chapa", label: "Chapa" },
  { value: "Cash", label: "Cash" },
];

export function ReportsView() {
  const [data, setData] = useState<FinancialReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState<"csv" | "pdf" | null>(null);

  const [status, setStatus] = useState<PaymentStatus | "ALL">("ALL");
  const [method, setMethod] = useState<PaymentMethod | "ALL">("ALL");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [userId, setUserId] = useState("");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const query: FinancialReportQuery = {
        status: status === "ALL" ? undefined : status,
        method: method === "ALL" ? undefined : method,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        user_id: userId || undefined,
        search: search || undefined,
      };
      setData(await reportsApi.financialSummary(query));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load report.");
    } finally {
      setLoading(false);
    }
  }, [status, method, dateFrom, dateTo, userId, search]);

  useEffect(() => {
    void load();
  }, [load]);

  async function download(format: "csv" | "pdf") {
    setDownloading(format);
    setError("");
    try {
      const query: FinancialReportQuery = {
        status: status === "ALL" ? undefined : status,
        method: method === "ALL" ? undefined : method,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        user_id: userId || undefined,
        search: search || undefined,
      };
      const res = await reportsApi.download(query, format);
      const url = window.URL.createObjectURL(res.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = res.filename;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed.");
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div className="space-y-6">
      {error && <ErrorBanner message={error} onRetry={() => void load()} />}

      <Card>
        <div className="grid gap-4 border-b border-gray-100 p-5 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Status" htmlFor="status">
            <Select
              id="status"
              value={status}
              onChange={(e) => setStatus(e.target.value as PaymentStatus | "ALL")}
            >
              {STATUSES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Payment method" htmlFor="method">
            <Select
              id="method"
              value={method}
              onChange={(e) => setMethod(e.target.value as PaymentMethod | "ALL")}
            >
              {METHODS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Date from" htmlFor="from">
            <Input
              id="from"
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </Field>

          <Field label="Date to" htmlFor="to">
            <Input
              id="to"
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </Field>

          <Field
            label="User ID"
            htmlFor="user"
            hint="Filter by submitted_by or farmer"
          >
            <Input
              id="user"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="UUID"
            />
          </Field>

          <Field label="Search" htmlFor="search" hint="Product, reference, names">
            <Input
              id="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Fresh onions..."
            />
          </Field>

          <div className="flex items-end gap-2">
            <Button onClick={() => void load()}>Run report</Button>
            <Button
              variant="secondary"
              icon={<Download className="h-4 w-4" />}
              loading={downloading === "csv"}
              onClick={() => void download("csv")}
            >
              CSV
            </Button>
            <Button
              variant="secondary"
              icon={<FileText className="h-4 w-4" />}
              loading={downloading === "pdf"}
              onClick={() => void download("pdf")}
            >
              PDF
            </Button>
          </div>
        </div>
      </Card>

      {loading ? (
        <PageLoader />
      ) : !data ? (
        <EmptyState
          title="No report data"
          description="Adjust the filters and run the report again."
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <div className="p-5">
              <h3 className="text-sm font-semibold text-gray-900">Totals</h3>
              <dl className="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <dt className="text-xs text-gray-500">Transactions</dt>
                  <dd className="text-base font-bold">{data.totals.count}</dd>
                </div>
                <div>
                  <dt className="text-xs text-gray-500">Total amount</dt>
                  <dd className="text-base font-bold">
                    {data.totals.amount.toLocaleString("en-US")} ETB
                  </dd>
                </div>
              </dl>
            </div>
          </Card>

          <Card>
            <div className="p-5">
              <h3 className="text-sm font-semibold text-gray-900">By Status</h3>
              {Object.keys(data.totals.by_status).length === 0 ? (
                <p className="mt-2 text-sm text-gray-500">No data.</p>
              ) : (
                <ul className="mt-2 divide-y divide-gray-100 text-sm">
                  {Object.entries(data.totals.by_status).map(([k, v]) => (
                    <li key={k} className="flex justify-between py-2">
                      <span>{k}</span>
                      <span className="font-medium">
                        {v.count} — {v.total.toLocaleString("en-US")} ETB
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>

          <Card>
            <div className="p-5">
              <h3 className="text-sm font-semibold text-gray-900">By Method</h3>
              {Object.keys(data.totals.by_method).length === 0 ? (
                <p className="mt-2 text-sm text-gray-500">No data.</p>
              ) : (
                <ul className="mt-2 divide-y divide-gray-100 text-sm">
                  {Object.entries(data.totals.by_method).map(([k, v]) => (
                    <li key={k} className="flex justify-between py-2">
                      <span>{k}</span>
                      <span className="font-medium">
                        {v.count} — {v.total.toLocaleString("en-US")} ETB
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>

          <Card>
            <div className="p-5">
              <h3 className="text-sm font-semibold text-gray-900">Top Farmers</h3>
              {data.totals.top_farmers.length === 0 ? (
                <p className="mt-2 text-sm text-gray-500">No data.</p>
              ) : (
                <ul className="mt-2 divide-y divide-gray-100 text-sm">
                  {data.totals.top_farmers.map((f, i) => (
                    <li key={`${f.farmer}-${i}`} className="flex justify-between py-2">
                      <span className="truncate">{f.farmer}</span>
                      <span className="font-medium">
                        {f.count} — {f.total.toLocaleString("en-US")} ETB
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>

          <Card className="lg:col-span-2">
            <div className="p-5">
              <h3 className="text-sm font-semibold text-gray-900">Top Wholesalers</h3>
              {data.totals.top_wholesalers.length === 0 ? (
                <p className="mt-2 text-sm text-gray-500">No data.</p>
              ) : (
                <ul className="mt-2 divide-y divide-gray-100 text-sm">
                  {data.totals.top_wholesalers.map((w, i) => (
                    <li
                      key={`${w.wholesaler}-${i}`}
                      className="flex justify-between py-2"
                    >
                      <span className="truncate">{w.wholesaler}</span>
                      <span className="font-medium">
                        {w.count} — {w.total.toLocaleString("en-US")} ETB
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
