"use client";

import { Plus, Trash2 } from "lucide-react";
import { Button, Field, Input, Textarea } from "@/components/shared/ui";
import type { SiteBlock } from "@/types";
import { BLOCKS } from "./blocks";

type Props = SiteBlock["props"];

export function BlockSettings({ block, onChange }: { block: SiteBlock; onChange: (props: Props) => void }) {
  const meta = BLOCKS[block.type];
  const set = (key: string, value: unknown) => onChange({ ...block.props, [key]: value });

  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm font-semibold">{meta.label}</p>
        <p className="text-xs text-muted">{meta.description}</p>
      </div>
      {meta.fields.map((f) => {
        const value = block.props[f.key];
        switch (f.kind) {
          case "text":
          case "url":
            return (
              <Field key={f.key} label={f.label}>
                <Input value={value ?? ""} onChange={(e) => set(f.key, e.target.value)} type={f.kind === "url" ? "url" : "text"} />
              </Field>
            );
          case "textarea":
            return (
              <Field key={f.key} label={f.label}>
                <Textarea rows={4} value={value ?? ""} onChange={(e) => set(f.key, e.target.value)} />
              </Field>
            );
          case "boolean":
            return (
              <label key={f.key} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={value !== false} onChange={(e) => set(f.key, e.target.checked)} /> {f.label}
              </label>
            );
          case "list-url":
            return (
              <Field key={f.key} label={f.label}>
                <Textarea
                  rows={5}
                  value={(value ?? []).join("\n")}
                  onChange={(e) => set(f.key, e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))}
                  placeholder="https://…"
                />
              </Field>
            );
          case "timings": {
            const rows: { days: string; hours: string }[] = value ?? [];
            const update = (i: number, k: "days" | "hours", v: string) => set(f.key, rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
            return (
              <div key={f.key} className="space-y-2">
                <span className="label">{f.label}</span>
                {rows.map((r, i) => (
                  <div key={i} className="flex gap-2">
                    <Input value={r.days} onChange={(e) => update(i, "days", e.target.value)} placeholder="Days" />
                    <Input value={r.hours} onChange={(e) => update(i, "hours", e.target.value)} placeholder="Hours" />
                    <Button type="button" variant="ghost" size="sm" onClick={() => set(f.key, rows.filter((_, j) => j !== i))} aria-label="Remove row"><Trash2 className="h-3.5 w-3.5" /></Button>
                  </div>
                ))}
                <Button type="button" size="sm" variant="secondary" onClick={() => set(f.key, [...rows, { days: "", hours: "" }])}><Plus className="h-3.5 w-3.5" /> Add row</Button>
              </div>
            );
          }
          case "testimonials": {
            const items: { quote: string; name: string }[] = value ?? [];
            const update = (i: number, k: "quote" | "name", v: string) => set(f.key, items.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
            return (
              <div key={f.key} className="space-y-3">
                <span className="label">{f.label}</span>
                {items.map((t, i) => (
                  <div key={i} className="space-y-2 rounded-lg border border-border p-2">
                    <Textarea rows={2} value={t.quote} onChange={(e) => update(i, "quote", e.target.value)} placeholder="Quote" />
                    <div className="flex gap-2">
                      <Input value={t.name} onChange={(e) => update(i, "name", e.target.value)} placeholder="Name" />
                      <Button type="button" variant="ghost" size="sm" onClick={() => set(f.key, items.filter((_, j) => j !== i))} aria-label="Remove"><Trash2 className="h-3.5 w-3.5" /></Button>
                    </div>
                  </div>
                ))}
                <Button type="button" size="sm" variant="secondary" onClick={() => set(f.key, [...items, { quote: "", name: "" }])}><Plus className="h-3.5 w-3.5" /> Add testimonial</Button>
              </div>
            );
          }
        }
      })}
      {block.props.live && <p className="rounded-lg bg-surface-2 p-2 text-xs text-muted">This block always shows your current data — no need to republish when it changes.</p>}
    </div>
  );
}
