"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Button, Card, ErrorBanner, Field, Input, PageLoader, Select } from "@/components/ui";
import { superAdminApi, registrationApi } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";
import type { AdminAccount, AdminScope, RegistrationLocation } from "@/lib/types";

export default function AdminScopesPage() {
  const { user } = useAuth();
  const [accounts, setAccounts] = useState<AdminAccount[]>([]);
  const [scopes, setScopes] = useState<AdminScope[]>([]);
  const [levels, setLevels] = useState<RegistrationLocation[][]>([]);
  const [selectedLocations, setSelectedLocations] = useState<string[]>([]);
  const [userId, setUserId] = useState("");
  const [scopeLevel, setScopeLevel] = useState<"GLOBAL" | "LOCATION">(
    user?.role === "SUPER_ADMIN" ? "GLOBAL" : "LOCATION"
  );
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");

  async function load() {
    setError("");
    try {
      const [accountPage, scopePage, options] = await Promise.all([
        superAdminApi.accounts({ status: "ALL" }),
        superAdminApi.scopes(),
        superAdminApi.creationOptions(),
      ]);
      setAccounts(accountPage.results.filter((account) => account.role === "USER_ADMIN"));
      setScopes(scopePage.results);
      setLevels([
        await registrationApi.locations(options.scope_location_id || undefined),
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load administrator scopes.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const visibleScopes = scopes.filter((scope) => {
    const query = search.trim().toLowerCase();
    if (!query) return true;
    return [
      scope.user_name,
      scope.user_email,
      scope.scope_label,
      scope.location_path.join(" "),
    ].some((value) => value.toLowerCase().includes(query));
  });

  async function selectLocation(index: number, location: RegistrationLocation | null) {
    const path = selectedLocations.slice(0, index);
    const choices = levels.slice(0, index + 1);
    if (location) {
      path[index] = location.id;
      if (location.has_children) {
        try {
          choices.push(await registrationApi.locations(location.id));
        } catch (err) {
          setError(err instanceof Error ? err.message : "Could not load child locations.");
        }
      }
    }
    setSelectedLocations(path);
    setLevels(choices);
  }

  async function save() {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      await superAdminApi.saveScope({
        user: userId,
        level: scopeLevel,
        location: scopeLevel === "LOCATION" ? selectedLocations.at(-1) || null : null,
      });
      setNotice("Administrator scope saved.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save administrator scope.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <AppShell title="Administrator scopes" allow={["USER_ADMIN", "SUPER_ADMIN"]}><PageLoader /></AppShell>;

  return (
    <AppShell title="Administrator scopes" allow={["USER_ADMIN", "SUPER_ADMIN"]}>
      <div className="mb-5">
        <h2 className="text-lg font-bold text-gray-900">User Admin geographic scope</h2>
        <p className="mt-1 text-sm text-gray-500">
          Review assignments that you are authorized to manage. Geographic access includes only the selected location and its descendants.
        </p>
      </div>
      {error && <div className="mb-4"><ErrorBanner message={error} onRetry={() => void load()} /></div>}
      {notice && <p role="status" className="mb-4 rounded-lg bg-green-50 p-3 text-sm text-green-800">{notice}</p>}
      <Card className="mb-6 p-5">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="User Admin" htmlFor="scope-admin">
            <Select id="scope-admin" value={userId} onChange={(event) => setUserId(event.target.value)}>
              <option value="">Select administrator</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id} disabled={account.status !== "APPROVED"}>
                  {account.full_name} ({account.email}){account.status !== "APPROVED" ? ` — ${account.status.toLowerCase()}` : ""}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Scope" htmlFor="scope-level">
            <Select id="scope-level" value={scopeLevel} onChange={(event) => {
              setScopeLevel(event.target.value as "GLOBAL" | "LOCATION");
              setSelectedLocations([]);
              setLevels([levels[0] || []]);
            }}>
              {user?.role === "SUPER_ADMIN" && <option value="GLOBAL">Nationwide (Top-Level)</option>}
              <option value="LOCATION">Specific administrative location</option>
            </Select>
          </Field>
        </div>
        {scopeLevel === "LOCATION" && (
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {levels.map((choices, index) => (
              <Field key={`scope-location-${index}`} label={index === 0 ? "Region / first administrative level" : "Child administrative level"}>
                <Select
                  value={selectedLocations[index] || ""}
                  onChange={(event) => void selectLocation(index, choices.find((item) => item.id === event.target.value) || null)}
                >
                  <option value="">Select location</option>
                  {choices.map((location) => <option key={location.id} value={location.id}>{location.name} ({location.level_display})</option>)}
                </Select>
              </Field>
            ))}
            {!levels[0]?.length && <p className="text-sm text-amber-800">No verified location records are loaded. Import the approved location dataset before assigning regional scopes.</p>}
          </div>
        )}
        <Button
          className="mt-4"
          loading={saving}
          disabled={!userId || (scopeLevel === "LOCATION" && !selectedLocations.length)}
          onClick={() => void save()}
        >
          Save scope
        </Button>
      </Card>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 px-5 py-4">
          <h3 className="font-semibold">Current assignments</h3>
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search administrators or locations"
            aria-label="Search administrator assignments"
            className="max-w-sm"
          />
        </div>
        <ul className="divide-y divide-gray-100">
          {visibleScopes.map((scope) => (
            <li key={scope.id} className="flex flex-wrap justify-between gap-2 px-5 py-4 text-sm">
              <div>
                <p className="font-medium text-gray-900">{scope.user_name} · {scope.user_email}</p>
                <p className="mt-1 text-xs text-gray-500">
                  {scope.account_status.toLowerCase()} · {scope.user_count} users · {scope.admin_count} other admin assignment(s) in scope
                </p>
              </div>
              <div className="text-right">
                <p className="font-medium text-gray-800">{scope.scope_label}</p>
                <p className="mt-1 text-xs text-gray-600">
                  {scope.level === "GLOBAL" ? "Nationwide" : scope.location_path.join(" → ")}
                </p>
              </div>
            </li>
          ))}
          {!visibleScopes.length && <li className="px-5 py-4 text-sm text-gray-500">No administrator scopes match this search.</li>}
        </ul>
      </Card>
    </AppShell>
  );
}
