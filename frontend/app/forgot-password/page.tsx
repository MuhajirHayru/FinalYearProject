"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Button, ErrorBanner, Input, SuccessBanner } from "@/components/ui";
import { authApi } from "@/lib/api/client";

export default function ForgotPasswordPage() {
  const [channel, setChannel] = useState<"email" | "sms">("email");
  const [identifier, setIdentifier] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await authApi.requestPasswordReset(channel, identifier.trim());
      setNotice(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit the request.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 p-6">
      <section className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-bold text-gray-900">Reset your password</h1>
        <p className="mt-2 text-sm text-gray-600">
          We will send a reset link to the contact method on your account, if it matches.
        </p>
        {error && <div className="mt-5"><ErrorBanner message={error} /></div>}
        {notice && <div className="mt-5"><SuccessBanner message={notice} /></div>}
        <form onSubmit={(event) => void submit(event)} className="mt-6 space-y-4">
          <label className="block text-sm font-medium text-gray-700">
            Send reset link by
            <select
              value={channel}
              onChange={(event) => setChannel(event.target.value as "email" | "sms")}
              className="mt-1.5 block w-full rounded-lg border border-gray-300 bg-white px-3 py-2"
            >
              <option value="email">Email</option>
              <option value="sms">SMS</option>
            </select>
          </label>
          <label className="block text-sm font-medium text-gray-700">
            {channel === "email" ? "Email address" : "Phone number with country code"}
            <Input
              type={channel === "email" ? "email" : "tel"}
              autoComplete={channel === "email" ? "email" : "tel"}
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              required
              placeholder={channel === "email" ? "you@example.com" : "+2519..."}
            />
          </label>
          <Button type="submit" loading={busy} className="w-full">
            {busy ? "Sending..." : "Send reset link"}
          </Button>
        </form>
        <p className="mt-5 text-center text-sm text-gray-600">
          <Link href="/login" className="font-medium text-green-700">Back to sign in</Link>
        </p>
      </section>
    </main>
  );
}
