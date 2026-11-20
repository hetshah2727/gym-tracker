"use client";

import { ExternalLink, Globe, Inbox, Pencil, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Input, Loading, Modal, PageHeader, Select, Tabs } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDate, formatDateTime } from "@/lib/utils";
import { patch, post } from "@/services/api";
import type { Lead, LeadStatus, Website } from "@/types";

type View = "sites" | "leads";

export default function WebsiteBuilderPage() {
  const router = useRouter();
  const [view, setView] = useState<View>("sites");
  const sites = useApi<Website[]>("/websites");
  const leads = useApi<Lead[]>("/leads");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("Main website");
  const [template, setTemplate] = useState("classic");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const newLeads = leads.data?.filter((l) => l.status === "new").length ?? 0;

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const site = await post<Website>("/websites", { name, template });
      router.push(`/editor/${site.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create site");
      setBusy(false);
    }
  }

  async function setLeadStatus(lead: Lead, status: LeadStatus) {
    await patch(`/leads/${lead.id}`, undefined, { new_status: status });
    leads.reload();
  }

  return (
    <>
      <PageHeader
        title="Website builder"
        description="Build and publish your gym's website. Enquiries land in your leads inbox."
        actions={<Button onClick={() => setCreating(true)}><Plus className="h-4 w-4" /> New website</Button>}
      />
      <Tabs<View> value={view} onChange={setView} tabs={[{ value: "sites", label: "Websites" }, { value: "leads", label: `Leads${newLeads ? ` (${newLeads} new)` : ""}` }]} />

      {view === "sites" ? (
        sites.loading && !sites.data ? (
          <Loading />
        ) : !sites.data?.length ? (
          <Card>
            <EmptyState icon={<Globe className="h-8 w-8" />} title="No website yet"
              description="Start from a template with your plans, trainers and contact form filled in automatically."
              action={<Button onClick={() => setCreating(true)}>Create website</Button>} />
          </Card>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {sites.data.map((s) => (
              <div key={s.id} className="card p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium">{s.name}</p>
                    <p className="mt-0.5 text-xs text-muted">/sites/{s.slug}{s.custom_domain ? ` · ${s.custom_domain}` : ""}</p>
                  </div>
                  <Badge value={s.is_published ? "published" : "draft"} />
                </div>
                <p className="mt-3 text-xs text-muted">
                  {s.blocks.length} sections · {s.is_published ? `Published ${formatDate(s.published_at)}` : "Not published yet"}
                </p>
                <div className="mt-4 flex gap-2">
                  <Link href={`/editor/${s.id}`}><Button size="sm"><Pencil className="h-3.5 w-3.5" /> Edit</Button></Link>
                  {s.is_published && (
                    <a href={`/sites/${s.slug}`} target="_blank" rel="noreferrer"><Button size="sm" variant="secondary"><ExternalLink className="h-3.5 w-3.5" /> View</Button></a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )
      ) : (
        <Card>
          {!leads.data?.length ? (
            <EmptyState icon={<Inbox className="h-8 w-8" />} title="No leads yet" description="Enquiries from your website's contact form appear here." />
          ) : (
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead><tr><th>Name</th><th>Contact</th><th>Message</th><th>Received</th><th>Status</th></tr></thead>
                <tbody>
                  {leads.data.map((l) => (
                    <tr key={l.id}>
                      <td className="font-medium">{l.name}</td>
                      <td className="text-muted">{l.phone}{l.email && <p className="text-xs">{l.email}</p>}</td>
                      <td className="max-w-xs truncate text-muted" title={l.message ?? ""}>{l.message ?? "—"}</td>
                      <td className="whitespace-nowrap text-muted">{formatDateTime(l.created_at)}</td>
                      <td>
                        <Select className="w-32 py-1" value={l.status} onChange={(e) => setLeadStatus(l, e.target.value as LeadStatus)} options={["new", "contacted", "converted", "lost"]} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <Modal open={creating} onClose={() => setCreating(false)} title="New website">
        <div className="space-y-4">
          <ErrorNote message={error} />
          <Field label="Website name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Template">
            <div className="grid grid-cols-3 gap-2">
              {[{ id: "classic", color: "#16a34a", label: "Classic" }, { id: "bold", color: "#f97316", label: "Bold" }, { id: "minimal", color: "#0f172a", label: "Minimal" }].map((t) => (
                <button key={t.id} type="button" onClick={() => setTemplate(t.id)}
                  className={`rounded-lg border p-3 text-left text-sm ${template === t.id ? "border-brand ring-1 ring-brand" : "border-border"}`}>
                  <span className="mb-2 block h-8 rounded" style={{ background: t.color }} />
                  {t.label}
                </button>
              ))}
            </div>
          </Field>
          <div className="flex justify-end"><Button loading={busy} onClick={create}>Create &amp; open editor</Button></div>
        </div>
      </Modal>
    </>
  );
}
