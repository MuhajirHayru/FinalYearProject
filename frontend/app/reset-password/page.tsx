"use client";

import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Button, ErrorBanner, Input, SuccessBanner } from "@/components/ui";
import { authApi } from "@/lib/api/client";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-gray-50" />}>
      <ResetPasswordForm />
    </Suspense>
  );
}

function ResetPasswordForm() {
  const params = useSearchParams();
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    if (!uid || !token) {
      setError("This password reset link is incomplete.");
      return;
    }
    if (password !== confirmation) {
      setError("The passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const result = await authApi.confirmPasswordReset(uid, token, password);
      setNotice(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset the password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 p-6">
      <section className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-bold text-gray-900">Choose a new password</h1>
        <p className="mt-2 text-sm text-gray-600">
          Use a strong password you have not used before.
        </p>
        {error && <div className="mt-5"><ErrorBanner message={error} /></div>}
        {notice && <div className="mt-5"><SuccessBanner message={notice} /></div>}
        <form onSubmit={(event) => void submit(event)} className="mt-6 space-y-4">
          <label className="block text-sm font-medium text-gray-700">
            New password
            <Input
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          <label className="block text-sm font-medium text-gray-700">
            Confirm new password
            <Input
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              required
            />
          </label>
          <Button type="submit" loading={busy} className="w-full">
            {busy ? "Updating..." : "Update password"}
          </Button>
        </form>
        <p className="mt-5 text-center text-sm text-gray-600">
          <Link href="/login" className="font-medium text-green-700">Back to sign in</Link>
        </p>
      </section>
    </main>
  );
}
