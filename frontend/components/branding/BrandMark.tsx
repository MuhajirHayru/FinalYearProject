"use client";

import { Leaf } from "lucide-react";
import { useWebsiteContent } from "@/components/branding/WebsiteContentProvider";
import { cn } from "@/lib/utils";

export function BrandMark({
  className,
  iconClassName,
  nameClassName,
  hideName = false,
}: {
  className?: string;
  iconClassName?: string;
  nameClassName?: string;
  hideName?: boolean;
}) {
  const { website } = useWebsiteContent();
  const name = website.platform_name || "Green Path";
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-2", className)}>
      {website.logo_url ? (
        <img
          src={website.logo_url}
          alt={`${name} logo`}
          className={cn("h-7 w-7 shrink-0 object-contain", iconClassName)}
        />
      ) : (
        <Leaf className={cn("h-7 w-7 shrink-0 text-green-600", iconClassName)} />
      )}
      {!hideName && (
        <span className={cn("truncate font-semibold", nameClassName)}>{name}</span>
      )}
    </span>
  );
}
