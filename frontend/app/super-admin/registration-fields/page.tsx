"use client";

import { useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import {
  Button,
  Card,
  CardHeader,
  ErrorBanner,
  Field,
  Input,
  PageLoader,
  Textarea,
} from "@/components/ui";
import { superAdminApi } from "@/lib/api/client";
import type {
  RegistrationFormFieldConfiguration,
  UserRole,
} from "@/lib/types";

const ROLES: { value: UserRole; label: string }[] = [
  { value: "FARMER", label: "Farmer" },
  { value: "WHOLESALER", label: "Wholesaler" },
  { value: "RETAILER", label: "Retailer" },
  { value: "USER_ADMIN", label: "User Admin" },
  { value: "FINANCIAL_MANAGER", label: "Financial Manager" },
  { value: "SUPER_ADMIN", label: "Super Admin" },
];

export default function RegistrationFieldSettingsPage() {
  const [fields, setFields] = useState<RegistrationFormFieldConfiguration[]>([]);
  const [optionDrafts, setOptionDrafts] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const rows = await superAdminApi.registrationFields();
      setFields(rows);
      setOptionDrafts(
        Object.fromEntries(
          rows.map((field) => [
            field.id,
            field.options.map((option) => `${option.value}|${option.label}`).join("\n"),
          ])
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load registration form settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function updateField<K extends keyof RegistrationFormFieldConfiguration>(
    id: number,
    key: K,
    value: RegistrationFormFieldConfiguration[K]
  ) {
    setFields((current) =>
      current.map((field) => (field.id === id ? { ...field, [key]: value } : field))
    );
  }

  async function save(field: RegistrationFormFieldConfiguration) {
    setSavingId(field.id);
    setError("");
    setNotice("");
    try {
      let options = field.options;
      if (field.field_key === "sex") {
        options = optionDrafts[field.id]
          .split("\n")
          .map((line) => {
            const separator = line.indexOf("|");
            return separator < 0
              ? null
              : {
                  value: line.slice(0, separator).trim(),
                  label: line.slice(separator + 1).trim(),
                };
          })
          .filter((option): option is { value: string; label: string } => Boolean(option));
      }
      const updated = await superAdminApi.updateRegistrationField(field.id, {
        label: field.label,
        description: field.description,
        required: field.required,
        visible: field.visible,
        display_order: field.display_order,
        roles: field.roles,
        options,
        editable_after_approval: field.editable_after_approval,
      });
      setFields((current) =>
        current.map((item) => (item.id === updated.id ? updated : item))
      );
      setOptionDrafts((current) => ({
        ...current,
        [updated.id]: updated.options
          .map((option) => `${option.value}|${option.label}`)
          .join("\n"),
      }));
      setNotice(`${updated.label} settings saved.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save this field configuration.");
    } finally {
      setSavingId(null);
    }
  }

  if (loading) {
    return (
      <AppShell title="Registration Form Settings" allow={["SUPER_ADMIN"]}>
        <PageLoader />
      </AppShell>
    );
  }

  return (
    <AppShell title="Registration Form Settings" allow={["SUPER_ADMIN"]}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">
          Registration and Profile Form Settings
        </h2>
        <p className="mt-1 text-sm text-gray-500">
          Configure existing fields by stage and role. Email, authorization, and required workflow fields stay protected.
        </p>
      </div>
      {error && <div className="mb-4"><ErrorBanner message={error} /></div>}
      {notice && <p role="status" className="mb-4 rounded bg-green-50 p-3 text-sm text-green-800">{notice}</p>}
      <div className="space-y-4">
        {fields.map((field) => (
          <Card key={field.id} className="space-y-5 p-5">
            <CardHeader
              title={field.label}
              subtitle={`${field.stage === "INITIAL" ? "Initial registration" : "Profile completion"} · ${field.field_key}`}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Field label">
                <Input
                  value={field.label}
                  maxLength={100}
                  onChange={(event) => updateField(field.id, "label", event.target.value)}
                />
              </Field>
              <Field label="Display order">
                <Input
                  type="number"
                  min={0}
                  max={32767}
                  value={field.display_order}
                  onChange={(event) =>
                    updateField(field.id, "display_order", Number(event.target.value))
                  }
                />
              </Field>
              <Field label="Helper text">
                <Textarea
                  value={field.description}
                  maxLength={300}
                  onChange={(event) =>
                    updateField(field.id, "description", event.target.value)
                  }
                />
              </Field>
              {field.field_key === "sex" && (
                <Field label="Supported choices" hint="Keep the fixed values before the | and edit only the display labels.">
                  <Textarea
                    value={optionDrafts[field.id] || ""}
                    onChange={(event) =>
                      setOptionDrafts((current) => ({
                        ...current,
                        [field.id]: event.target.value,
                      }))
                    }
                    rows={4}
                  />
                </Field>
              )}
            </div>
            <fieldset>
              <legend className="mb-2 text-sm font-medium text-gray-700">Applicable roles</legend>
              <div className="grid gap-2 sm:grid-cols-3">
                {ROLES.map((role) => (
                  <label key={role.value} className="flex items-center gap-2 text-sm text-gray-700">
                    <input
                      type="checkbox"
                      checked={field.roles.includes(role.value)}
                      onChange={(event) =>
                        updateField(
                          field.id,
                          "roles",
                          event.target.checked
                            ? [...field.roles, role.value]
                            : field.roles.filter((value) => value !== role.value)
                        )
                      }
                    />
                    {role.label}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="flex flex-wrap gap-x-6 gap-y-3">
              {(
                [
                  ["visible", "Visible"],
                  ["required", "Required"],
                  ["editable_after_approval", "Editable after approval"],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={field[key]}
                    onChange={(event) => updateField(field.id, key, event.target.checked)}
                  />
                  {label}
                </label>
              ))}
            </div>
            <div className="flex justify-end">
              <Button loading={savingId === field.id} onClick={() => void save(field)}>
                Save field settings
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
