"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authApi, setRegistrationCompletionToken } from "@/lib/api/client";
import { Button, ErrorBanner, Field, Input } from "@/components/ui";

export default function ResumeRegistrationPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function resume(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await authApi.resumeRegistration(email.trim(), password);
      setRegistrationCompletionToken(result.completion_token);
      router.push("/complete-registration");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resume registration.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-5 p-6">
      <div>
        <Link href="/" className="font-semibold text-green-800">Green Path</Link>
        <h1 className="mt-4 text-2xl font-bold text-gray-900">Resume registration</h1>
        <p className="mt-1 text-sm text-gray-600">
          Enter the email and password used to create your pending account.
        </p>
      </div>
      {error && <ErrorBanner message={error} />}
      <form onSubmit={resume} className="space-y-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <Field label="Email address" htmlFor="resume-email">
          <Input id="resume-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
        </Field>
        <Field label="Password" htmlFor="resume-password">
          <Input id="resume-password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
        </Field>
        <Button type="submit" loading={busy}>Continue application</Button>
      </form>
      <Link href="/login" className="text-sm text-green-700 underline">Return to sign in</Link>
    </main>
  );
}
