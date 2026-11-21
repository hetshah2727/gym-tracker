import { ArrowRight, Check, IndianRupee, MessageCircle, RefreshCcw, Smartphone, UserPlus } from "lucide-react";
import Link from "next/link";
import { DemoButton } from "@/components/marketing/DemoButton";
import { RoiCalculator } from "@/components/marketing/RoiCalculator";

const APP = process.env.NEXT_PUBLIC_APP_NAME || "GymFlow";

const OUTCOMES = [
  { icon: IndianRupee, title: "Collect every fee", text: "See exactly who owes what. Send a WhatsApp reminder in one tap, and mark them paid when the cash or UPI comes in." },
  { icon: RefreshCcw, title: "Renew more members", text: "GymFlow spots memberships ending soon and reminds members at 30, 15 and 7 days – before they quietly stop coming." },
  { icon: UserPlus, title: "Turn enquiries into joins", text: "Every enquiry from Google, Instagram, WhatsApp and walk-ins in one list, with reminders so nobody is forgotten." },
];

const STEPS = [
  ["Add your gym", "Name, timings and your membership prices."],
  ["Add your members", "Type them in or bring them over from Excel."],
  ["Start reminding", "GymFlow shows who owes money today. Tap Remind."],
];

const PLANS = [
  { name: "Starter", promise: "Run my gym", price: "₹999", points: ["Members, plans & payments", "Check-in & attendance", "Automatic reminders", "Member app"] },
  { name: "Growth", promise: "Collect & renew", price: "₹2,499", featured: true, points: ["Everything in Starter", "Who-owes-money list with one-tap reminders", "Renewal follow-ups", "Enquiries & trials", "AI receptionist on WhatsApp"] },
  { name: "Pro", promise: "Fill my gym", price: "₹4,999", points: ["Everything in Growth", "Google Maps listing & reviews", "Gym website & landing pages", "ChatGPT & AI search", "Unlimited members"] },
];

const FAQ = [
  ["Do I need a computer?", "No. GymFlow works on any phone. You can add it to your home screen like an app."],
  ["Can my front-desk staff use it?", "Yes. Give them their own login – they see members, check-in and payments, not your reports."],
  ["Do I need the WhatsApp Business API?", "Not to start. Reminders open WhatsApp on your phone with the message ready. Connect the API later to send them automatically."],
  ["What happens to my data if I stop?", "It's yours. Your members, payments and history stay available, and you can export them."],
];

function PhoneMock() {
  return (
    <div className="mx-auto w-[290px] rounded-[2.5rem] border-[10px] border-fg bg-bg p-4 shadow-soft" aria-hidden>
      <p className="text-[11px] text-muted">Saturday</p>
      <p className="font-display text-lg font-bold">Good morning, Rahul</p>
      <div className="mt-3 rounded-2xl border border-border bg-surface p-3">
        <p className="text-[11px] text-muted">Waiting to be collected</p>
        <p className="font-display text-2xl font-extrabold">₹1,24,500</p>
        <p className="text-[11px] text-muted">39 people · <span className="font-semibold text-danger">14 late</span></p>
      </div>
      <div className="mt-2 rounded-2xl bg-money/10 p-3">
        <p className="text-[11px] text-muted">Brought back by {APP} this month</p>
        <p className="font-display text-2xl font-extrabold text-money">₹38,500</p>
      </div>
      <p className="mt-3 text-xs font-bold">Do these today</p>
      {[["Amit Shah", "membership ends in 2 days", "₹4,000"], ["Priya K", "fee 9 days late", "₹1,500"], ["Rohan M", "trial today 6 pm", ""]].map(([n, w, a]) => (
        <div key={n} className="mt-1.5 flex items-center gap-2 rounded-xl border border-border bg-surface px-2.5 py-2">
          <div className="min-w-0 flex-1"><p className="truncate text-xs font-semibold">{n}</p><p className="truncate text-[10px] text-muted">{w}</p></div>
          {a && <span className="text-[11px] font-bold">{a}</span>}
          <MessageCircle className="h-4 w-4 text-money" />
        </div>
      ))}
    </div>
  );
}

export default function Landing() {
  return (
    <div className="min-h-screen">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5 font-display text-lg font-extrabold">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/icon.svg" alt="" className="h-9 w-9 rounded-xl" /> {APP}
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          <a href="#pricing" className="hidden rounded-lg px-3 py-2 text-muted hover:text-fg sm:block">Pricing</a>
          <Link href="/login" className="rounded-lg px-3 py-2 text-muted hover:text-fg">Log in</Link>
          <Link href="/register" className="rounded-xl bg-brand px-4 py-2 font-semibold text-brand-fg">Start free</Link>
        </nav>
      </header>

      <main>
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-10 sm:px-6 lg:grid-cols-[1.2fr_1fr] lg:pt-16">
          <div>
            <p className="mb-4 inline-flex items-center gap-2 rounded-full bg-money/10 px-3 py-1 text-xs font-semibold text-money">
              <Smartphone className="h-3.5 w-3.5" /> Made for Indian gyms · works on your phone
            </p>
            <h1 className="font-display text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-6xl">
              Stop losing gym fees.
            </h1>
            <p className="mt-5 max-w-xl text-lg text-muted">
              {APP} shows you who owes money, reminds them on WhatsApp in one tap, follows up renewals and enquiries –
              and tells you every month exactly how much it brought back.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href="/register" className="inline-flex items-center gap-2 rounded-xl bg-brand px-6 py-3 text-sm font-semibold text-brand-fg shadow-soft hover:bg-brand/90">
                Start 14-day free trial <ArrowRight className="h-4 w-4" />
              </Link>
              <DemoButton />
            </div>
            <p className="mt-4 text-xs text-muted">No card needed · set up in 10 minutes · cancel any time</p>
          </div>
          <PhoneMock />
        </section>

        <section className="border-y border-border/70 bg-surface py-20">
          <div className="mx-auto grid max-w-6xl gap-10 px-4 sm:px-6 md:grid-cols-3">
            {OUTCOMES.map((o) => (
              <div key={o.title}>
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand/10 text-brand"><o.icon className="h-5 w-5" /></div>
                <h2 className="mt-4 font-display text-xl font-bold">{o.title}</h2>
                <p className="mt-2 text-muted">{o.text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-5xl px-4 py-20 sm:px-6">
          <h2 className="font-display text-3xl font-extrabold tracking-tight sm:text-4xl">How much are late fees costing you?</h2>
          <p className="mt-2 text-muted">Move the sliders to match your gym.</p>
          <div className="mt-8"><RoiCalculator /></div>
        </section>

        <section className="bg-fg py-20 text-bg">
          <div className="mx-auto max-w-6xl px-4 sm:px-6">
            <h2 className="font-display text-3xl font-extrabold tracking-tight sm:text-4xl">Up and running in 10 minutes</h2>
            <ol className="mt-10 grid gap-8 md:grid-cols-3">
              {STEPS.map(([t, d], i) => (
                <li key={t}>
                  <span className="font-display text-5xl font-extrabold text-brand">{i + 1}</span>
                  <p className="mt-2 font-display text-xl font-bold">{t}</p>
                  <p className="mt-1 opacity-70">{d}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="pricing" className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
          <h2 className="text-center font-display text-3xl font-extrabold tracking-tight sm:text-4xl">Simple pricing. Pays for itself.</h2>
          <p className="mt-2 text-center text-muted">Every plan starts with a 14-day free trial. Prices per gym, per month, plus GST.</p>
          <div className="mt-10 grid gap-4 lg:grid-cols-3">
            {PLANS.map((p) => (
              <div key={p.name} className={`card relative flex flex-col p-7 ${p.featured ? "border-2 border-brand shadow-soft" : ""}`}>
                {p.featured && <span className="absolute -top-3 left-7 rounded-full bg-brand px-3 py-0.5 text-xs font-bold text-brand-fg">Recommended</span>}
                <p className="text-sm font-semibold text-brand">{p.promise}</p>
                <p className="font-display text-xl font-bold">{p.name}</p>
                <p className="mt-3"><span className="font-display text-4xl font-extrabold">{p.price}</span><span className="text-sm text-muted"> / month</span></p>
                <ul className="mt-5 flex-1 space-y-2.5 text-sm">
                  {p.points.map((pt) => <li key={pt} className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-money" />{pt}</li>)}
                </ul>
                <Link href="/register" className={`mt-7 rounded-xl py-3 text-center text-sm font-semibold ${p.featured ? "bg-brand text-brand-fg" : "border border-border hover:bg-surface-2"}`}>Start free trial</Link>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-3xl px-4 pb-24 sm:px-6">
          <h2 className="font-display text-3xl font-extrabold tracking-tight">Questions gym owners ask</h2>
          <div className="mt-6 divide-y divide-border/70 border-y border-border/70">
            {FAQ.map(([q, a]) => (
              <details key={q} className="group py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between font-semibold [&::-webkit-details-marker]:hidden">
                  {q}<span className="text-muted transition group-open:rotate-45">+</span>
                </summary>
                <p className="mt-2 text-muted">{a}</p>
              </details>
            ))}
          </div>
        </section>
      </main>

      <footer className="border-t border-border/70 py-8 text-center text-xs text-muted">
        © {new Date().getFullYear()} {APP} · <Link href="/login" className="underline">Log in</Link>
      </footer>
    </div>
  );
}
