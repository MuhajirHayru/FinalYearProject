"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Spinner } from "@/components/ui";

/**
 * Legacy route kept so older links and bookmarks still land somewhere useful.
 * The payment screens live under the Financial Manager area (Fig 4.10).
 */
export default function PaymentsRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/financial-manager/payments");
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <Spinner className="h-8 w-8" />
    </div>
  );
}
