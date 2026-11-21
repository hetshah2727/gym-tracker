"use client";

import { MapPin, Phone } from "lucide-react";
import type { CSSProperties } from "react";
import type { PublicSite } from "@/types";
import { LeadForm } from "./BlockRenderer";
import { ChatWidget, JsonLd, TrialBooking } from "./PublicWidgets";

export function LandingPageView({ data, slug }: { data: PublicSite; slug: string }) {
  const page = data.page!;
  const dark = data.site.theme.mode === "dark";
  const vars = {
    "--site-primary": data.site.theme.primaryColor ?? "#16a34a", "--site-bg": dark ? "#0b0d12" : "#ffffff",
    "--site-surface": dark ? "#151922" : "#f5f6f8", "--site-fg": dark ? "#f2f4f7" : "#0f172a",
    "--site-muted": dark ? "#9aa3b2" : "#5b6474", "--site-border": dark ? "#262c38" : "#e3e6eb",
  } as CSSProperties;
  return (
    <div style={{ ...vars, background: "var(--site-bg)", color: "var(--site-fg)" }} className="min-h-screen">
      <JsonLd data={page.json_ld} />
      <header className="flex items-center justify-between px-5 py-4 sm:px-10" style={{ borderBottom: "1px solid var(--site-border)" }}>
        <a href={`/sites/${slug}`} className="font-bold">{data.gym.name}</a>
        {data.gym.phone && <a href={`tel:${data.gym.phone}`} className="flex items-center gap-1 text-sm" style={{ color: "var(--site-primary)" }}><Phone className="h-4 w-4" /> {data.gym.phone}</a>}
      </header>
      <section className="px-5 py-14 text-white sm:px-10" style={{ background: "linear-gradient(135deg, var(--site-primary), #0b0d12)" }}>
        <h1 className="max-w-3xl text-3xl font-extrabold tracking-tight sm:text-5xl">{page.h1}</h1>
        {page.content.intro && <p className="mt-4 max-w-2xl text-base opacity-90 sm:text-lg">{page.content.intro}</p>}
        <a href="#enquire" className="mt-8 inline-block rounded-lg bg-white px-5 py-3 text-sm font-semibold" style={{ color: "#0b0d12" }}>{page.content.cta ?? "Enquire now"}</a>
      </section>
      <main className="mx-auto max-w-5xl space-y-10 px-5 py-12 sm:px-10">
        {page.content.sections?.map((s) => (
          <section key={s.heading}><h2 className="mb-3 text-2xl font-bold">{s.heading}</h2><p className="whitespace-pre-line leading-relaxed" style={{ color: "var(--site-muted)" }}>{s.body}</p></section>
        ))}
        {!!data.plans.length && <section><h2 className="mb-3 text-2xl font-bold">Membership plans</h2>
          <ul className="grid gap-3 sm:grid-cols-2">{data.plans.map((p) => <li key={p.id} className="rounded-xl border p-4" style={{ borderColor: "var(--site-border)" }}><p className="font-semibold">{p.name}</p><p style={{ color: "var(--site-primary)" }} className="text-xl font-bold">{new Intl.NumberFormat("en-IN", { style: "currency", currency: data.gym.currency, maximumFractionDigits: 0 }).format(p.price)}</p></li>)}</ul></section>}
        {!!page.content.faqs?.length && <section><h2 className="mb-3 text-2xl font-bold">Frequently asked questions</h2>
          <dl className="space-y-4">{page.content.faqs.map((f) => <div key={f.q}><dt className="font-semibold">{f.q}</dt><dd style={{ color: "var(--site-muted)" }}>{f.a}</dd></div>)}</dl></section>}
        <section id="enquire" className="grid gap-8 rounded-2xl p-6 md:grid-cols-2" style={{ background: "var(--site-surface)" }}>
          <div><h2 className="text-2xl font-bold">Enquire about {page.service.toLowerCase()}</h2>
            {data.gym.address && <p className="mt-3 flex items-start gap-2 text-sm" style={{ color: "var(--site-muted)" }}><MapPin className="mt-0.5 h-4 w-4" /> {data.gym.address}</p>}
            <TrialBooking slug={slug} landingPage={page.slug} />
          </div>
          <LeadForm slug={slug} landingPage={page.slug} />
        </section>
      </main>
      <footer className="px-5 py-6 text-center text-xs" style={{ color: "var(--site-muted)", borderTop: "1px solid var(--site-border)" }}>
        <a href={`/sites/${slug}`} className="underline">Home</a>{data.landing_pages?.filter((l) => l.slug !== page.slug).map((l) => <span key={l.slug}> · <a href={`/sites/${slug}/${l.slug}`} className="underline">{l.title}</a></span>)}
        <p className="mt-2">© {new Date().getFullYear()} {data.gym.name}</p>
      </footer>
      <ChatWidget slug={slug} gymName={data.gym.name} landingPage={page.slug} />
    </div>
  );
}
