import { BadgeCheck } from "lucide-react";

export function FinanciallyVerifiedBadge() {
  return (
    <span
      className="inline-flex shrink-0 text-green-600"
      role="img"
      aria-label="Financially Verified"
      title="Financially Verified"
    >
      <BadgeCheck className="h-4 w-4" aria-hidden="true" />
    </span>
  );
}
