"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, FileCheck2, Search } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Button, Card, EmptyState, ErrorBanner, Input, PageLoader, Textarea } from "@/components/ui";
import { registrationAdminApi } from "@/lib/api/client";
import type { RegistrationDetails } from "@/lib/types";

const requiredLicenseTypes: Partial<Record<RegistrationDetails["role"], string>> = {
  FARMER: "FARMER_LICENSE",
  WHOLESALER: "WHOLESALER_LICENSE",
  RETAILER: "RETAILER_LICENSE",
};

export default function AdminRegistrationsPage() {
  const [rows, setRows] = useState<RegistrationDetails[]>([]);
  const [search, setSearch] = useState("");
  const [reason, setReason] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const result = await registrationAdminApi.list({
        search: search.trim() || undefined,
      });
      setRows(result.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load registration applications.");
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    void load();
  }, [load]);

  async function verify(documentId: string, verified: boolean, registrationId: string) {
    setBusy(documentId);
    setError("");
    try {
      await registrationAdminApi.verifyDocument(
        documentId,
        verified,
        verified ? "" : reason[registrationId] || ""
      );
      setNotice(verified ? "License verified." : "License marked for correction.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update license verification.");
    } finally {
      setBusy("");
    }
  }

  async function decide(
    registration: RegistrationDetails,
    action: "APPROVE" | "REJECT" | "REQUEST_CHANGES"
  ) {
    setBusy(registration.id);
    setError("");
    try {
      await registrationAdminApi.decision(
        registration.id,
        action,
        reason[registration.id] || ""
      );
      setNotice(`Registration ${action.toLowerCase().replace("_", " ")}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not record the review decision.");
    } finally {
      setBusy("");
    }
  }

  if (loading) return <AppShell title="Registration review" allow={["USER_ADMIN", "SUPER_ADMIN"]}><PageLoader /></AppShell>;

  return (
    <AppShell title="Registration review" allow={["USER_ADMIN", "SUPER_ADMIN"]}>
      <div className="mb-5">
        <h2 className="text-lg font-bold text-gray-900">Registration applications</h2>
        <p className="mt-1 text-sm text-gray-500">
          Review submitted profiles, verify their licenses, and record decisions.
        </p>
      </div>
      {error && <div className="mb-4"><ErrorBanner message={error} onRetry={() => void load()} /></div>}
      {notice && <p role="status" className="mb-4 rounded-lg bg-green-50 p-3 text-sm text-green-800">{notice}</p>}
      <Card>
        <div className="border-b border-gray-100 p-4">
          <div className="relative max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="pl-9"
              placeholder="Search name, email, phone, or location"
              aria-label="Search registration applications"
            />
          </div>
        </div>
        {rows.length === 0 ? (
          <EmptyState title="No submitted applications" description="New completed registrations will appear here." icon={<FileCheck2 className="h-8 w-8" />} />
        ) : (
          <div className="divide-y divide-gray-100">
            {rows.map((row) => {
              const requiredLicenseType = requiredLicenseTypes[row.role];
              const canApprove = row.legacy_registration || row.documents.some(
                (doc) => doc.document_type === requiredLicenseType && doc.verification_status === "VERIFIED"
              );
              return (
                <article key={row.id} className="space-y-4 p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="font-semibold text-gray-900">{row.full_name} <span className="font-normal text-gray-500">— {row.role.toLowerCase()}</span></h3>
                      <p className="text-sm text-gray-600">{row.email} · {row.phone}</p>
                      {row.business_name && <p className="mt-1 text-sm text-gray-700">{row.business_name}{row.business_address ? ` · ${row.business_address}` : ""}</p>}
                      <p className="mt-1 text-sm text-gray-600">{row.location_path.join(" / ") || row.location_name || "Location not provided"}</p>
                    </div>
                    <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">{row.status.replaceAll("_", " ")}</span>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {row.product_selections.map((item) => (
                      <span key={`${item.id}-${item.intent}`} className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-700">
                        {item.name} · {item.intent.toLowerCase()}
                      </span>
                    ))}
                  </div>

                  <div className="space-y-2">
                    <p className="text-sm font-medium text-gray-800">Private verification documents</p>
                    {row.documents.length === 0 && <p className="text-sm text-red-700">No document uploaded.</p>}
                    {row.documents.map((doc) => (
                      <div key={doc.id} className="flex flex-wrap items-center gap-2 text-sm">
                        <Button
                          type="button"
                          variant="ghost"
                          className="h-auto px-2 py-1"
                          onClick={() => void registrationAdminApi.downloadDocument(doc.id, doc.original_filename).catch((err: unknown) => setError(err instanceof Error ? err.message : "Download failed."))}
                        >
                          <Download className="h-4 w-4" /> {doc.original_filename}
                        </Button>
                        <span className="text-gray-600">{doc.document_type.replaceAll("_", " ")}</span>
                        <span className="text-gray-500">{doc.verification_status.toLowerCase()}</span>
                        {doc.verification_status !== "VERIFIED" && (
                          <Button type="button" size="sm" loading={busy === doc.id} onClick={() => void verify(doc.id, true, row.id)}>Verify license</Button>
                        )}
                        {doc.verification_status !== "REJECTED" && (
                          <Button type="button" variant="secondary" size="sm" loading={busy === doc.id} onClick={() => void verify(doc.id, false, row.id)}>Request correction</Button>
                        )}
                        {doc.verification_note && <span className="text-xs text-red-700">{doc.verification_note}</span>}
                      </div>
                    ))}
                  </div>

                  <div className="space-y-2">
                    <Textarea
                      value={reason[row.id] || ""}
                      onChange={(event) => setReason((current) => ({ ...current, [row.id]: event.target.value }))}
                      placeholder="Reason (required for rejection or requested changes)"
                      aria-label={`Review reason for ${row.full_name}`}
                    />
                    <div className="flex flex-wrap gap-2">
                      <Button type="button" loading={busy === row.id} disabled={!canApprove} onClick={() => void decide(row, "APPROVE")}>Approve</Button>
                      <Button type="button" variant="secondary" loading={busy === row.id} disabled={!reason[row.id]?.trim()} onClick={() => void decide(row, "REQUEST_CHANGES")}>Request changes</Button>
                      <Button type="button" variant="danger" loading={busy === row.id} disabled={!reason[row.id]?.trim()} onClick={() => void decide(row, "REJECT")}>Reject</Button>
                    </div>
                    {!canApprove && <p className="text-xs text-amber-800">A license must be verified before approval.</p>}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </Card>
    </AppShell>
  );
}
