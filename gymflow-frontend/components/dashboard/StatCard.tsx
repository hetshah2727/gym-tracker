import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon?: LucideIcon;
  tone?: "default" | "brand" | "warning" | "danger";
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-muted">{label}</p>
        {Icon && (
          <Icon
            className={cn(
              "h-4 w-4",
              tone === "brand" && "text-money",
              tone === "warning" && "text-warning",
              tone === "danger" && "text-danger",
              tone === "default" && "text-muted",
            )}
          />
        )}
      </div>
      <p className={cn("num mt-2 font-display text-2xl font-bold", tone === "brand" && "text-money")}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}
