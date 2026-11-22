"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { track } from "@/lib/analytics";

/** Sends a page view on every route change (no-op unless NEXT_PUBLIC_POSTHOG_KEY is set). */
export function Analytics() {
  const pathname = usePathname();
  useEffect(() => { track("$pageview"); }, [pathname]);
  return null;
}
