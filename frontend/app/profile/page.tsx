"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, Save, Trash2 } from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import {
  Avatar,
  Button,
  Card,
  CardHeader,
  ErrorBanner,
  Field,
  Input,
  StatusPill,
  SuccessBanner,
} from "@/components/ui";
import { authApi, registrationApi } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/context";
import { OnlineStatus } from "@/components/presence/PresenceProvider";
import { FinanciallyVerifiedBadge } from "@/components/users/FinanciallyVerifiedBadge";
import { formatDate } from "@/lib/format";
import type { RegistrationFormFieldConfiguration, User } from "@/lib/types";

const ROLES: User["role"][] = [
  "FARMER",
  "WHOLESALER",
  "RETAILER",
  "USER_ADMIN",
  "FINANCIAL_MANAGER",
  "SUPER_ADMIN",
];

export default function ProfilePage() {
  const { user, refreshUser } = useAuth();
  const [form, setForm] = useState({
    full_name: user?.full_name ?? "",
    phone: user?.phone ?? "",
  });
  const [fieldConfigurations, setFieldConfigurations] = useState<
    RegistrationFormFieldConfiguration[]
  >([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const photoInput = useRef<HTMLInputElement>(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState("");

  useEffect(
    () => () => {
      if (photoPreview) URL.revokeObjectURL(photoPreview);
    },
    [photoPreview]
  );

  useEffect(() => {
    if (user) setForm({ full_name: user.full_name, phone: user.phone ?? "" });
  }, [user?.id, user?.full_name, user?.phone]);

  useEffect(() => {
    if (!user) return;
    let active = true;
    registrationApi
      .formFields("PROFILE", user.role)
      .then((fields) => {
        if (active) setFieldConfigurations(fields);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load your profile field settings."
          );
        }
      });
    return () => {
      active = false;
    };
  }, [user?.role]);

  if (!user) {
    return (
      <AppShell title="Profile" allow={ROLES}>
        <Card>
          <div className="p-6 text-sm text-gray-600">Loading your profile...</div>
        </Card>
      </AppShell>
    );
  }

  function profileField(fieldKey: string) {
    return fieldConfigurations.find((field) => field.field_key === fieldKey);
  }

  async function save() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const profileData: Partial<Pick<User, "full_name" | "phone">> = {};
      const fullNameField = fieldConfigurations.find(
        (field) => field.field_key === "full_name"
      );
      const phoneField = fieldConfigurations.find(
        (field) => field.field_key === "phone"
      );
      if (fullNameField?.visible && fullNameField.editable_after_approval) {
        profileData.full_name = form.full_name;
      }
      if (phoneField?.visible && phoneField.editable_after_approval) {
        profileData.phone = form.phone;
      }
      await authApi.updateProfile(profileData);
      await refreshUser();
      setNotice("Profile updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save your profile.");
    } finally {
      setBusy(false);
    }

  }

  function changePhoto(file?: File) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Choose a JPG, PNG, or WebP image.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError("Profile images must be 5 MB or smaller.");
      return;
    }
    if (photoPreview) URL.revokeObjectURL(photoPreview);
    setPhotoFile(file);
    setPhotoPreview(URL.createObjectURL(file));
    setError("");
  }

  async function savePhoto() {
    if (!photoFile) return;
    setPhotoBusy(true);
    setError("");
    setNotice("");
    try {
      await authApi.updatePhoto(photoFile);
      await refreshUser();
      setPhotoFile(null);
      setPhotoPreview("");
      setNotice("Profile photo updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update your photo.");
    } finally {
      setPhotoBusy(false);
      if (photoInput.current) photoInput.current.value = "";
    }
  }

  async function removePhoto() {
    setPhotoBusy(true);
    setError("");
    setNotice("");
    try {
      await authApi.removePhoto();
      await refreshUser();
      setNotice("Profile photo removed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove your photo.");
    } finally {
      setPhotoBusy(false);
    }
  }

  const fullNameField = profileField("full_name");
  const phoneField = profileField("phone");
  const locationField = profileField("location");
  const hasEditableContactFields = [fullNameField, phoneField].some(
    (field) => field?.visible && field.editable_after_approval
  );

  return (
    <AppShell title="Profile" allow={ROLES}>
      <div className="mb-6">
        <h2 className="text-lg font-bold text-gray-900">My Profile</h2>
        <p className="mt-1 text-sm text-gray-500">
          Your contact details are visible to counterparties you trade with.
        </p>
      </div>

      {error && (
        <div className="mb-5">
          <ErrorBanner message={error} />
        </div>
      )}
      {notice && (
        <div className="mb-5">
          <SuccessBanner message={notice} />
        </div>
      )}

      <div className="grid max-w-4xl gap-6 lg:grid-cols-[280px_1fr]">
        <Card className="h-fit">
          <div className="flex flex-col items-center gap-3 p-6 text-center">
            {photoPreview ? (
              <img
                src={photoPreview}
                alt="Selected profile photo preview"
                className="h-12 w-12 rounded-full object-cover"
              />
            ) : (
              <Avatar name={user.full_name} size="lg" src={user.profile_photo} />
            )}
            <div>
              <p className="flex items-center justify-center gap-1.5 text-base font-semibold text-gray-900">
                {user.full_name}
                {user.financially_verified && <FinanciallyVerifiedBadge />}
              </p>
              <p className="text-sm text-gray-500">{user.email}</p>
              {(user.role === "FARMER" || user.role === "WHOLESALER") && (
                <div className="mt-1">
                  <OnlineStatus userId={user.id} initiallyOnline={user.is_online} />
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <StatusPill value={user.role} kind="role" />
              <StatusPill value={user.status} />
            </div>
            <input
              ref={photoInput}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="user"
              className="hidden"
              onChange={(event) => changePhoto(event.target.files?.[0])}
            />
            <div className="flex flex-wrap justify-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                loading={photoBusy}
                icon={<Camera className="h-4 w-4" />}
                onClick={() => photoInput.current?.click()}
              >
                Change photo
              </Button>
              {photoFile && (
                <Button
                  size="sm"
                  loading={photoBusy}
                  onClick={() => void savePhoto()}
                >
                  Save photo
                </Button>
              )}
              {user.profile_photo && (
                <Button
                  size="sm"
                  variant="ghost"
                  loading={photoBusy}
                  icon={<Trash2 className="h-4 w-4" />}
                  onClick={() => void removePhoto()}
                >
                  Remove
                </Button>
              )}
            </div>
            <p className="text-xs text-gray-400">Joined {formatDate(user.created_at)}</p>
          </div>
          <ul className="divide-y divide-gray-100 border-t border-gray-100 text-sm">
            <li className="flex items-center justify-between px-5 py-3">
              <span className="text-gray-600">Role</span>
              <span className="font-medium text-gray-900">{user.role_display}</span>
            </li>
            <li className="flex items-center justify-between px-5 py-3">
              <span className="text-gray-600">Status</span>
              <span className="font-medium text-gray-900">{user.status_display}</span>
            </li>
            <li className="flex items-center justify-between px-5 py-3">
              <span className="text-gray-600">Permissions</span>
              <span className="font-medium text-gray-900">{user.permissions.length}</span>
            </li>
            {user.latitude && user.longitude && (
              <li className="flex items-center justify-between px-5 py-3">
                <span className="text-gray-600">Coordinates</span>
                <span className="font-mono text-xs text-gray-700">
                  {Number(user.latitude).toFixed(4)}, {Number(user.longitude).toFixed(4)}
                </span>
              </li>
            )}
          </ul>
        </Card>

        <Card>
          <CardHeader
            title="Contact details"
            subtitle="Email and role are managed by a User Admin and cannot be edited here"
          />
          <div className="space-y-4 p-5">
            {fullNameField?.visible && fullNameField.editable_after_approval && (
              <Field
                label={fullNameField.label}
                htmlFor="full_name"
                hint={fullNameField.description}
              >
                <Input
                  id="full_name"
                  required={fullNameField.required}
                  value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                />
              </Field>
            )}
            <Field label="Email" htmlFor="email" hint="Contact a User Admin to change this.">
              <Input id="email" value={user.email} disabled />
            </Field>
            {phoneField?.visible && phoneField.editable_after_approval && (
              <Field
                label={phoneField.label}
                htmlFor="phone"
                hint={phoneField.description}
              >
                <Input
                  id="phone"
                  required={phoneField.required}
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  placeholder="+251 9xx xxx xxx"
                />
              </Field>
            )}
            {locationField?.visible && (
              <div className="text-sm">
                <p className="font-medium text-gray-700">
                  {locationField.label}
                </p>
                <p className="mt-1 text-gray-600">
                  {user.location || "No location selected"}
                </p>
                {locationField.editable_after_approval &&
                  ["FARMER", "WHOLESALER", "RETAILER"].includes(user.role) && (
                    <Link
                      href="/complete-registration"
                      className="mt-1 inline-block font-medium text-emerald-700 hover:text-emerald-800"
                    >
                      Update in registration details
                    </Link>
                  )}
              </div>
            )}
            <div className="flex items-center gap-3">
              <Button
                loading={busy}
                disabled={!hasEditableContactFields}
                icon={<Save className="h-4 w-4" />}
                onClick={() => void save()}
              >
                Save changes
              </Button>
              {user.rejection_reason && (
                <span className="text-xs text-red-600">
                  Rejection reason: {user.rejection_reason}
                </span>
              )}
            </div>
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
