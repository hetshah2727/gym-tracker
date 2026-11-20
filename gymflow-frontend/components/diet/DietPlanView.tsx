import { Sparkles } from "lucide-react";
import { Badge } from "@/components/shared/ui";
import { humanize } from "@/lib/utils";
import type { DietPlan } from "@/types";

export function MacroBar({ macros, calories }: { macros: DietPlan["macros"]; calories: number }) {
  const parts = [
    { label: "Protein", grams: macros.protein_g, kcal: macros.protein_g * 4, color: "bg-brand" },
    { label: "Carbs", grams: macros.carbs_g, kcal: macros.carbs_g * 4, color: "bg-sky-500" },
    { label: "Fat", grams: macros.fat_g, kcal: macros.fat_g * 9, color: "bg-warning" },
  ];
  const total = parts.reduce((s, p) => s + p.kcal, 0) || 1;
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-surface-2">
        {parts.map((p) => (
          <div key={p.label} className={p.color} style={{ width: `${(p.kcal / total) * 100}%` }} />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span className="font-medium text-fg">{calories} kcal/day</span>
        {parts.map((p) => (
          <span key={p.label} className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${p.color}`} /> {p.label} {p.grams} g
          </span>
        ))}
      </div>
    </div>
  );
}

export function DietPlanView({ plan, showStatus = true }: { plan: DietPlan; showStatus?: boolean }) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        {showStatus && <Badge value={plan.status} />}
        <span className="text-xs text-muted">{humanize(plan.goal)} · {humanize(plan.diet_type)}</span>
        {plan.ai_generated && (
          <span className="inline-flex items-center gap-1 text-xs text-brand"><Sparkles className="h-3 w-3" /> AI generated</span>
        )}
      </div>
      <MacroBar macros={plan.macros} calories={plan.daily_calories} />
      <div className="space-y-3">
        {plan.meals.map((meal, i) => {
          const kcal = meal.items.reduce((s, it) => s + it.calories, 0);
          return (
            <div key={i} className="rounded-lg border border-border">
              <div className="flex items-center justify-between border-b border-border bg-surface-2/60 px-3 py-2 text-sm">
                <span className="font-medium">{meal.name}</span>
                <span className="text-xs text-muted">{meal.time} · {kcal} kcal</span>
              </div>
              <ul className="divide-y divide-border/60">
                {meal.items.map((item, j) => (
                  <li key={j} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                    <span>
                      {item.food} <span className="text-muted">— {item.quantity}</span>
                    </span>
                    <span className="whitespace-nowrap text-xs tabular-nums text-muted">
                      {item.calories} kcal · {item.protein_g} g P
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
      {plan.notes && (
        <div className="rounded-lg bg-surface-2 p-3 text-sm">
          <p className="mb-1 text-xs font-medium text-muted">Notes</p>
          <p className="whitespace-pre-line">{plan.notes}</p>
        </div>
      )}
    </div>
  );
}
