"use client";

import { Plus, Sparkles, Star, Trash2 } from "lucide-react";
import { useState } from "react";
import { FeatureGate, Note, SourceBadge, useAction } from "@/components/shared/growth";
import { Button, Card, EmptyState, Input, Loading, PageHeader, Select } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { humanize } from "@/lib/utils";
import { del, patch, post } from "@/services/api";

interface Kw { id: string; keyword: string; location: string | null; intent: string; category: string; source: string; metrics_verified: boolean; search_volume: number | null; competition: string | null; is_tracked: boolean }

export default function KeywordsPage() {
  const [f, setF] = useState({ location: "", intent: "", category: "", q: "" });
  const list = useApi<Kw[]>("/seo/keywords", f);
  const [add, setAdd] = useState("");
  const { busy, run } = useAction();
  const all = list.data ?? [];
  const locations = Array.from(new Set(all.map((k) => k.location).filter(Boolean))) as string[];
  const categories = Array.from(new Set(all.map((k) => k.category)));

  return (
    <FeatureGate feature="seo_audit">
      <PageHeader title="Local keywords" description="Keyword ideas for the services and areas in your Gym Profile."
        actions={<Button loading={busy === "gen"} onClick={() => run("gen", () => post<Kw[]>("/seo/keywords/generate"), (r) => `${r.length} new ideas`).then(list.reload)}><Sparkles className="h-4 w-4" /> Generate ideas</Button>} />
      <Note className="mb-4">These are suggestions based on your profile. No search-volume, difficulty or ranking data is shown because no verified keyword provider is connected - GymFlow does not invent those numbers.</Note>
      <div className="mb-3 flex flex-col gap-2 sm:flex-row">
        <Input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} placeholder="Filter keywords" />
        <Select className="sm:w-40" value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} placeholder="All locations" options={locations.map((l) => ({ value: l, label: l }))} />
        <Select className="sm:w-44" value={f.intent} onChange={(e) => setF({ ...f, intent: e.target.value })} placeholder="All intents" options={["local", "transactional", "commercial", "informational"]} />
        <Select className="sm:w-44" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} placeholder="All categories" options={categories} />
      </div>
      <Card>
        <form className="flex gap-2 border-b border-border p-3" onSubmit={(e) => { e.preventDefault(); run("add", () => post("/seo/keywords", { keyword: add, location: f.location || undefined }), "Keyword added").then(() => { setAdd(""); list.reload(); }); }}>
          <Input value={add} onChange={(e) => setAdd(e.target.value)} placeholder="Add your own keyword, e.g. crossfit in gotri" />
          <Button type="submit" variant="secondary" disabled={add.length < 2}><Plus className="h-4 w-4" /> Add</Button>
        </form>
        {list.loading ? <Loading /> : !all.length ? <EmptyState title="No keywords" description="Fill in services and service areas in the Gym Profile, then generate ideas." /> : (
          <div className="overflow-x-auto"><table className="table-base">
            <thead><tr><th>Keyword</th><th>Location</th><th>Intent</th><th>Category</th><th>Source</th><th>Volume</th><th></th></tr></thead>
            <tbody>{all.map((k) => (
              <tr key={k.id}>
                <td className="font-medium">{k.keyword}</td><td className="text-xs">{k.location ?? "—"}</td><td className="text-xs">{humanize(k.intent)}</td><td className="text-xs">{humanize(k.category)}</td>
                <td><SourceBadge source={k.source} /></td>
                <td className="text-xs text-muted">{k.metrics_verified && k.search_volume != null ? k.search_volume : "Not available"}</td>
                <td className="whitespace-nowrap text-right">
                  <button aria-label={k.is_tracked ? "Untrack" : "Track"} onClick={() => run(k.id, () => patch(`/seo/keywords/${k.id}`, { is_tracked: !k.is_tracked })).then(list.reload)} className="p-1"><Star className={`h-4 w-4 ${k.is_tracked ? "fill-warning text-warning" : "text-muted"}`} /></button>
                  <button aria-label="Delete" onClick={() => run("d" + k.id, () => del(`/seo/keywords/${k.id}`)).then(list.reload)} className="p-1 text-muted hover:text-danger"><Trash2 className="h-4 w-4" /></button>
                </td>
              </tr>))}</tbody>
          </table></div>
        )}
      </Card>
    </FeatureGate>
  );
}
