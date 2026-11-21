"use client";

import { Play } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { demoLogin, homeFor } from "@/services/auth";

export const DEMO_ENABLED = process.env.NEXT_PUBLIC_DEMO_LOGIN_ENABLED === "true";

/** Logs the visitor into the IronCore sample gym, so they can click around real-looking data in one tap. */
export function DemoButton({ className, label = "See a live demo gym" }: { className?: string; label?: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!DEMO_ENABLED) return null;
  return (
    <span className="inline-flex flex-col">
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            const user = await demoLogin();
            router.replace(homeFor(user.role));
            router.refresh();
          } catch {
            setError("The demo isn't available right now.");
            setBusy(false);
          }
        }}
        className={cn("inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-surface px-5 py-3 text-sm font-semibold transition hover:bg-surface-2 disabled:opacity-60", className)}
      >
        <Play className="h-4 w-4 text-brand" /> {busy ? "Opening the demo…" : label}
      </button>
      {error && <span className="mt-1 text-xs text-danger">{error}</span>}
    </span>
  );
}
