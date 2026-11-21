"use client";

import { Clock, Mail, MapPin, Phone } from "lucide-react";
import { useState, type CSSProperties, type FormEvent } from "react";
import type { PublicSite, SiteBlock, Website } from "@/types";
import { captureAttribution, ChatWidget, TrialBooking } from "./PublicWidgets";

export type SiteData = Pick<PublicSite, "gym" | "plans" | "trainers"> & Partial<Pick<PublicSite, "landing_pages">>;

function palette(theme: Website["theme"]) {
  const dark = theme.mode === "dark";
  return {
    "--site-primary": theme.primaryColor ?? "#16a34a",
    "--site-bg": dark ? "#0b0d12" : "#ffffff",
    "--site-surface": dark ? "#151922" : "#f5f6f8",
    "--site-fg": dark ? "#f2f4f7" : "#0f172a",
    "--site-muted": dark ? "#9aa3b2" : "#5b6474",
    "--site-border": dark ? "#262c38" : "#e3e6eb",
    fontFamily: theme.font ? `${theme.font}, system-ui, sans-serif` : undefined,
  } as CSSProperties;
}

const section = "px-5 py-14 sm:px-10";
const heading = "mb-6 text-2xl font-bold tracking-tight sm:text-3xl";

function money(value: number, currency: string) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
}

export function LeadForm({ slug, preview, landingPage }: { slug?: string; preview?: boolean; landingPage?: string }) {
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [error, setError] = useState("");

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (preview || !slug) return;
    setState("sending");
    const form = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    const data: Record<string, unknown> = { ...captureAttribution(landingPage), ...form,
      wants_trial: form.wants_trial === "on", whatsapp_opt_in: form.whatsapp_opt_in === "on" };
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
    try {
      const res = await fetch(`${base}/public/sites/${slug}/leads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.fromEntries(Object.entries(data).filter(([, v]) => v !== "" && v !== undefined))),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? "Please check your details");
      setState("done");
    } catch (err) {
      setError(typeof err === "object" && err && "message" in err ? String(err.message) : "Something went wrong");
      setState("error");
    }
  }

  if (state === "done") return <p className="rounded-lg p-4" style={{ background: "var(--site-surface)" }}>Thanks! We&apos;ll call you shortly.</p>;
  const input = "w-full rounded-lg border px-3 py-2.5 text-sm outline-none";
  const inputStyle = { background: "var(--site-bg)", borderColor: "var(--site-border)", color: "var(--site-fg)" };
  return (
    <form onSubmit={submit} className="grid gap-3">
      <input name="name" required placeholder="Your name" className={input} style={inputStyle} />
      <input name="phone" required placeholder="Phone number" inputMode="tel" className={input} style={inputStyle} />
      <input name="email" type="email" placeholder="Email (optional)" className={input} style={inputStyle} />
      <textarea name="message" rows={3} placeholder="What would you like to know?" className={input} style={inputStyle} />
      <input name="website" tabIndex={-1} autoComplete="off" aria-hidden className="hidden" />
      <label className="flex items-center gap-2 text-xs" style={{ color: "var(--site-muted)" }}><input type="checkbox" name="wants_trial" /> I&apos;d like a trial session</label>
      <label className="flex items-center gap-2 text-xs" style={{ color: "var(--site-muted)" }}><input type="checkbox" name="whatsapp_opt_in" /> You may contact me on WhatsApp</label>
      {state === "error" && <p className="text-sm text-red-500">{error}</p>}
      <button disabled={state === "sending" || preview} className="rounded-lg px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60" style={{ background: "var(--site-primary)" }}>
        {state === "sending" ? "Sending…" : "Request a callback"}
      </button>
    </form>
  );
}

export function Block({ block, data, slug, preview }: { block: SiteBlock; data: SiteData; slug?: string; preview?: boolean }) {
  const p = block.props;
  switch (block.type) {
    case "hero":
      return (
        <section
          className="relative flex min-h-[340px] flex-col items-start justify-center px-5 py-20 sm:px-10"
          style={{
            background: p.backgroundImage
              ? `linear-gradient(rgba(0,0,0,.55), rgba(0,0,0,.55)), url(${p.backgroundImage}) center/cover`
              : "linear-gradient(135deg, var(--site-primary), #0b0d12)",
            color: "#fff",
          }}
        >
          <h1 className="max-w-2xl text-3xl font-extrabold tracking-tight sm:text-5xl">{p.heading}</h1>
          {p.subheading && <p className="mt-4 max-w-xl text-base opacity-90 sm:text-lg">{p.subheading}</p>}
          {p.ctaText && (
            <a href={p.ctaTarget || "#contact"} className="mt-8 rounded-lg bg-white px-5 py-3 text-sm font-semibold" style={{ color: "#0b0d12" }}>
              {p.ctaText}
            </a>
          )}
        </section>
      );
    case "about":
      return (
        <section className={section}>
          <h2 className={heading}>{p.heading}</h2>
          <p className="max-w-3xl whitespace-pre-line leading-relaxed" style={{ color: "var(--site-muted)" }}>{p.body}</p>
        </section>
      );
    case "plans":
      return (
        <section className={section} style={{ background: "var(--site-surface)" }}>
          <h2 className={heading}>{p.heading}</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {data.plans.map((plan) => (
              <div key={plan.id} className="rounded-xl border p-5" style={{ borderColor: "var(--site-border)", background: "var(--site-bg)" }}>
                <p className="font-semibold">{plan.name}</p>
                <p className="mt-3 text-3xl font-extrabold" style={{ color: "var(--site-primary)" }}>{money(plan.price, data.gym.currency)}</p>
                <p className="mt-1 text-sm" style={{ color: "var(--site-muted)" }}>{plan.duration_days} days</p>
                {plan.description && <p className="mt-3 text-sm" style={{ color: "var(--site-muted)" }}>{plan.description}</p>}
              </div>
            ))}
            {!data.plans.length && <p style={{ color: "var(--site-muted)" }}>Plans coming soon.</p>}
          </div>
        </section>
      );
    case "trainers":
      return (
        <section className={section}>
          <h2 className={heading}>{p.heading}</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.trainers.map((t) => (
              <div key={t.id} className="flex gap-4 rounded-xl border p-4" style={{ borderColor: "var(--site-border)" }}>
                <div className="h-16 w-16 flex-shrink-0 overflow-hidden rounded-full" style={{ background: "var(--site-surface)" }}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {t.photo_url && <img src={t.photo_url} alt={t.name} className="h-full w-full object-cover" />}
                </div>
                <div>
                  <p className="font-semibold">{t.name}</p>
                  {t.specialization && <p className="text-sm" style={{ color: "var(--site-primary)" }}>{t.specialization}</p>}
                  {t.bio && <p className="mt-1 text-sm" style={{ color: "var(--site-muted)" }}>{t.bio}</p>}
                </div>
              </div>
            ))}
          </div>
        </section>
      );
    case "gallery": {
      const images: string[] = p.images ?? [];
      return (
        <section className={section} style={{ background: "var(--site-surface)" }}>
          <h2 className={heading}>{p.heading}</h2>
          {images.length ? (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
              {images.map((src, i) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img key={i} src={src} alt="" className="aspect-[4/3] w-full rounded-lg object-cover" />
              ))}
            </div>
          ) : (
            <p style={{ color: "var(--site-muted)" }}>{preview ? "Add image URLs in the block settings." : "Photos coming soon."}</p>
          )}
        </section>
      );
    }
    case "testimonials": {
      const items: { quote: string; name: string }[] = p.items ?? [];
      return (
        <section className={section}>
          <h2 className={heading}>{p.heading}</h2>
          <div className="grid gap-4 md:grid-cols-3">
            {items.map((t, i) => (
              <blockquote key={i} className="rounded-xl border p-5" style={{ borderColor: "var(--site-border)" }}>
                <p className="leading-relaxed">“{t.quote}”</p>
                <footer className="mt-3 text-sm font-semibold" style={{ color: "var(--site-primary)" }}>{t.name}</footer>
              </blockquote>
            ))}
          </div>
        </section>
      );
    }
    case "timings": {
      const rows: { days: string; hours: string }[] = p.rows ?? [];
      return (
        <section className={section}>
          <h2 className={heading}>{p.heading}</h2>
          <ul className="max-w-md divide-y rounded-xl border" style={{ borderColor: "var(--site-border)" }}>
            {rows.map((r, i) => (
              <li key={i} className="flex items-center justify-between px-4 py-3" style={{ borderColor: "var(--site-border)" }}>
                <span className="flex items-center gap-2"><Clock className="h-4 w-4" style={{ color: "var(--site-primary)" }} />{r.days}</span>
                <span style={{ color: "var(--site-muted)" }}>{r.hours}</span>
              </li>
            ))}
          </ul>
        </section>
      );
    }
    case "cta":
      return (
        <section className="px-5 py-14 text-center text-white sm:px-10" style={{ background: "var(--site-primary)" }}>
          <h2 className="text-2xl font-bold sm:text-3xl">{p.heading}</h2>
          {p.subheading && <p className="mt-2 opacity-90">{p.subheading}</p>}
          {p.buttonText && <a href="#contact" className="mt-6 inline-block rounded-lg bg-white px-5 py-3 text-sm font-semibold" style={{ color: "#0b0d12" }}>{p.buttonText}</a>}
        </section>
      );
    case "contact":
      return (
        <section id="contact" className={section} style={{ background: "var(--site-surface)" }}>
          <h2 className={heading}>{p.heading}</h2>
          <div className="grid gap-8 md:grid-cols-2">
            <ul className="space-y-3 text-sm">
              {(p.phone || data.gym.phone) && <li className="flex items-center gap-2"><Phone className="h-4 w-4" style={{ color: "var(--site-primary)" }} />{p.phone || data.gym.phone}</li>}
              {(p.email || data.gym.email) && <li className="flex items-center gap-2"><Mail className="h-4 w-4" style={{ color: "var(--site-primary)" }} />{p.email || data.gym.email}</li>}
              {(p.address || data.gym.address) && <li className="flex items-start gap-2"><MapPin className="mt-0.5 h-4 w-4" style={{ color: "var(--site-primary)" }} />{p.address || data.gym.address}</li>}
            </ul>
            {p.showLeadForm !== false && <div><LeadForm slug={slug} preview={preview} />{!preview && slug && <TrialBooking slug={slug} />}</div>}
          </div>
        </section>
      );
    default:
      return null;
  }
}

export function SiteRenderer({ blocks, theme, data, slug, preview }: { blocks: SiteBlock[]; theme: Website["theme"]; data: SiteData; slug?: string; preview?: boolean }) {
  return (
    <div style={{ ...palette(theme), background: "var(--site-bg)", color: "var(--site-fg)" }} className="min-h-full">
      {blocks.map((b) => (
        <Block key={b.id} block={b} data={data} slug={slug} preview={preview} />
      ))}
      <footer className="px-5 py-6 text-center text-xs sm:px-10" style={{ color: "var(--site-muted)", borderTop: "1px solid var(--site-border)" }}>
        {!!data.landing_pages?.length && slug && (
          <nav aria-label="Services" className="mb-3 flex flex-wrap justify-center gap-x-4 gap-y-1">
            {data.landing_pages.map((lp) => <a key={lp.slug} href={`/sites/${slug}/${lp.slug}`} className="underline">{lp.title}</a>)}
          </nav>
        )}
        © {new Date().getFullYear()} {data.gym.name} · Powered by GymFlow
      </footer>
      {!preview && slug && <ChatWidget slug={slug} gymName={data.gym.name} />}
    </div>
  );
}
