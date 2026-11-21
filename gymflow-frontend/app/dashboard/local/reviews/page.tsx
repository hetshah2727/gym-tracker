"use client";

import { Copy, QrCode, RefreshCcw, Sparkles, Star } from "lucide-react";
import { useState } from "react";
import { FeatureGate, Note, SourceBadge, useAction, useToast } from "@/components/shared/growth";
import { Badge, Button, Card, EmptyState, Field, Input, Loading, Modal, PageHeader, Select, Tabs, Textarea } from "@/components/shared/ui";
import { useApi } from "@/hooks/useApi";
import { formatDate, humanize } from "@/lib/utils";
import { API_URL, getToken, post, put } from "@/services/api";

interface Review { id: string; source: string; author: string | null; rating: number | null; text: string | null; review_date: string | null; sentiment: string | null; reply_status: string; existing_reply: string | null; draft_reply: string | null; draft_generated_by: string | null }
type Tab = "reviews" | "requests";
const DEFAULT_MSG = "Hi {name}, thank you for training with {gym}. If you have a minute, we'd appreciate an honest review on Google - good or bad, it helps us improve: {link}";

export default function ReviewsPage() {
  const [tab, setTab] = useState<Tab>("reviews");
  const [filter, setFilter] = useState("");
  const reviews = useApi<Review[]>("/local/reviews", { reply_status: filter });
  const overview = useApi<{ connection: string; review_url: string | null }>("/local/overview");
  const requests = useApi<{ total: number; queued_or_sent: number; policy: string }>(tab === "requests" ? "/local/review-requests" : null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [adding, setAdding] = useState(false);
  const [manual, setManual] = useState({ author: "", rating: "5", text: "" });
  const [link, setLink] = useState("");
  const [msg, setMsg] = useState(DEFAULT_MSG);
  const [qr, setQr] = useState<string | null>(null);
  const { busy, run } = useAction();
  const toast = useToast();
  const connected = overview.data?.connection === "connected";

  async function showQr() {
    const res = await fetch(`${API_URL}/local/review-qr.svg`, { headers: { Authorization: `Bearer ${getToken()}` } });
    if (res.ok) setQr(URL.createObjectURL(await res.blob())); else toast("Add your review link first", "error");
  }

  return (
    <FeatureGate feature="local_seo">
      <PageHeader title="Reviews" description="Reply to every review and ask every member for honest feedback."
        actions={<>
          {connected && <Button variant="secondary" loading={busy === "sync"} onClick={() => run("sync", () => post<{ new: number }>("/local/reviews/sync"), (r) => `${r.new} new reviews`).then(reviews.reload)}><RefreshCcw className="h-4 w-4" /> Sync from Google</Button>}
          <Button variant="secondary" onClick={() => setAdding(true)}>Add review manually</Button>
        </>} />
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ value: "reviews", label: "Reviews" }, { value: "requests", label: "Review requests" }]} />

      {tab === "reviews" && <>
        <Select className="mb-3 w-48" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="All reviews" options={["none", "drafted", "approved", "published", "copied"].map((s) => ({ value: s, label: s === "none" ? "No reply" : humanize(s) }))} />
        <Card>
          {reviews.loading ? <Loading /> : !reviews.data?.length ? <EmptyState title="No reviews yet" description={connected ? "Sync from Google to load reviews." : "Connect Google Business Profile, or add reviews by hand."} /> : (
            <ul className="divide-y divide-border/60">{reviews.data.map((r) => {
              const replied = ["published", "copied"].includes(r.reply_status);
              return (
                <li key={r.id} className="space-y-2 px-4 py-4 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="flex" aria-label={`${r.rating} stars`}>{Array.from({ length: 5 }).map((_, i) => <Star key={i} className={`h-3.5 w-3.5 ${i < (r.rating ?? 0) ? "fill-warning text-warning" : "text-border"}`} />)}</span>
                    <span className="font-medium">{r.author ?? "Anonymous"}</span><span className="text-xs text-muted">{formatDate(r.review_date)}</span>
                    <Badge value={r.sentiment === "negative" ? "overdue" : r.sentiment === "neutral" ? "pending" : "paid"} /><SourceBadge source={r.source} />
                  </div>
                  {r.text && <p>{r.text}</p>}
                  {replied ? <p className="rounded-lg bg-surface-2 p-2 text-xs"><span className="text-muted">Your reply:</span> {r.existing_reply}</p> : (
                    <div className="space-y-2">
                      {r.draft_reply || drafts[r.id] ? <>
                        <Textarea value={drafts[r.id] ?? r.draft_reply ?? ""} onChange={(e) => setDrafts({ ...drafts, [r.id]: e.target.value })} />
                        <div className="flex flex-wrap items-center gap-2">
                          {r.draft_generated_by && <SourceBadge source={r.draft_generated_by} />}
                          {r.source === "google_business_profile" && connected && <Button size="sm" loading={busy === "pub" + r.id} onClick={() => run("pub" + r.id, () => post(`/local/reviews/${r.id}/approve`, { text: drafts[r.id] ?? r.draft_reply, publish: true }), "Reply posted on Google").then(reviews.reload)}>Approve & post</Button>}
                          <Button size="sm" variant="secondary" onClick={() => run("cp" + r.id, () => post<{ copy_ready: string }>(`/local/reviews/${r.id}/approve`, { text: drafts[r.id] ?? r.draft_reply, publish: false })).then((x) => { if (x) { navigator.clipboard?.writeText(x.copy_ready); toast("Approved and copied - paste it on Google"); reviews.reload(); } })}><Copy className="h-3.5 w-3.5" /> Approve & copy</Button>
                          <Button size="sm" variant="ghost" onClick={() => run("cd" + r.id, () => post(`/local/reviews/${r.id}/copied`), "Marked as replied").then(reviews.reload)}>I&apos;ve posted it</Button>
                        </div>
                      </> : <Button size="sm" variant="secondary" loading={busy === "d" + r.id} onClick={() => run("d" + r.id, () => post(`/local/reviews/${r.id}/draft`)).then(reviews.reload)}><Sparkles className="h-3.5 w-3.5" /> Draft reply</Button>}
                    </div>
                  )}
                </li>
              );
            })}</ul>
          )}
        </Card>
      </>}

      {tab === "requests" && <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Your Google review link">
          <div className="space-y-3 p-4">
            <p className="text-sm">{overview.data?.review_url ?? <span className="text-muted">Not set</span>}</p>
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); run("link", () => put("/local/review-link", { review_url: link }), "Review link saved").then(overview.reload); }}>
              <Input value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://g.page/r/…/review" />
              <Button type="submit" variant="secondary" disabled={!link.startsWith("https://")}>Save</Button>
            </form>
            <Button variant="secondary" onClick={showQr}><QrCode className="h-4 w-4" /> Show QR code for the front desk</Button>
            {qr && <div className="rounded-lg bg-white p-3">
              {/* eslint-disable-next-line @next/next/no-img-element -- local blob URL */}
              <img src={qr} alt="QR code linking to your Google review page" className="mx-auto h-48 w-48" /></div>}
          </div>
        </Card>
        <Card title="Ask members for a review">
          <div className="space-y-3 p-4">
            <Note>{requests.data?.policy ?? "Every selected member gets the same request; GymFlow never filters by satisfaction or offers incentives for reviews."}</Note>
            <Field label="Message" hint="Use {name}, {gym} and {link}. Mentions of discounts, freebies or rewards are blocked."><Textarea rows={4} value={msg} onChange={(e) => setMsg(e.target.value)} /></Field>
            <Button loading={busy === "req"} onClick={() => run("req", () => post<{ queued: number; skipped_recently_asked: number }>("/local/review-requests", { message: msg, all_active_members: true }), (r) => `${r.queued} requests queued · ${r.skipped_recently_asked} asked recently`).then(requests.reload)}>Send to all active members</Button>
            {requests.data && <p className="text-xs text-muted">{requests.data.total} requests so far ({requests.data.queued_or_sent} queued or sent).</p>}
          </div>
        </Card>
      </div>}

      <Modal open={adding} onClose={() => setAdding(false)} title="Add a review">
        <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); run("add", () => post("/local/reviews", { ...manual, rating: Number(manual.rating) }), "Review added").then(() => { setAdding(false); reviews.reload(); }); }}>
          <Field label="Reviewer"><Input value={manual.author} onChange={(e) => setManual({ ...manual, author: e.target.value })} /></Field>
          <Field label="Rating"><Select value={manual.rating} onChange={(e) => setManual({ ...manual, rating: e.target.value })} options={["5", "4", "3", "2", "1"].map((v) => ({ value: v, label: `${v} stars` }))} /></Field>
          <Field label="Review text"><Textarea value={manual.text} onChange={(e) => setManual({ ...manual, text: e.target.value })} /></Field>
          <div className="flex justify-end"><Button type="submit" loading={busy === "add"}>Add</Button></div>
        </form>
      </Modal>
    </FeatureGate>
  );
}
