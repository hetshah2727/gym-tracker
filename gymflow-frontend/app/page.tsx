import { Bot, Dumbbell, Globe, ShoppingBag, Utensils, Workflow } from "lucide-react";
import Link from "next/link";

const MODULES = [
  { icon: Workflow, title: "Automation", text: "Members, fees, renewal reminders, WhatsApp and AI voice calls." },
  { icon: Utensils, title: "AI Nutrition", text: "Personalised diet plans your trainers review and assign." },
  { icon: ShoppingBag, title: "Affiliate Store", text: "Recommend supplements and gear, and share the commission." },
  { icon: Globe, title: "Website Builder", text: "Drag-and-drop gym website with live plans and lead capture." },
];

export default function Landing() {
  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-4 py-6 sm:px-6">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2 font-semibold">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-brand-fg">
            <Dumbbell className="h-4 w-4" />
          </span>
          GymFlow AI
        </div>
        <div className="flex gap-2 text-sm">
          <Link href="/login" className="rounded-lg px-3 py-2 text-muted hover:text-fg">Log in</Link>
          <Link href="/register" className="rounded-lg bg-brand px-3 py-2 font-medium text-brand-fg">Start free trial</Link>
        </div>
      </header>

      <main className="flex flex-1 flex-col justify-center py-16">
        <p className="mb-3 inline-flex w-fit items-center gap-1.5 rounded-full border border-border px-3 py-1 text-xs text-muted">
          <Bot className="h-3.5 w-3.5 text-brand" /> One platform for your whole gym business
        </p>
        <h1 className="max-w-2xl text-4xl font-semibold tracking-tight sm:text-5xl">
          Run your gym on autopilot. Grow it with AI.
        </h1>
        <p className="mt-4 max-w-xl text-muted">
          GymFlow AI handles memberships, fees and reminders, plans your members&apos; diets, earns you affiliate revenue and
          builds your website — all from one dashboard.
        </p>
        <div className="mt-8 flex gap-3">
          <Link href="/register" className="rounded-lg bg-brand px-5 py-2.5 text-sm font-medium text-brand-fg">Create your gym</Link>
          <Link href="/login" className="rounded-lg border border-border px-5 py-2.5 text-sm">I have an account</Link>
        </div>

        <div className="mt-14 grid gap-3 sm:grid-cols-2">
          {MODULES.map((m) => (
            <div key={m.title} className="card p-5">
              <m.icon className="h-5 w-5 text-brand" />
              <h3 className="mt-3 font-medium">{m.title}</h3>
              <p className="mt-1 text-sm text-muted">{m.text}</p>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
