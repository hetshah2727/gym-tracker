# GymFlow: UI/UX Revamp Plan (5/10 → 9.5/10)

> **Goal:** make GymFlow something a non-technical gym owner understands in 10 seconds, trusts in 2 minutes and pays for in one demo.
> **Status:** mostly implemented – see [Implementation status](#11-implementation-status) at the end.
> **Date:** 22 Nov 2026

---

## 0. TL;DR

The backend is strong: multi-tenant, honest numbers, 79 tests, a real recovery engine. The frontend shows the **engineering** to the owner instead of the **outcome**.

| Problem today | Fix |
|---|---|
| **52 sidebar links in 9 sections**, several of them duplicates | **5 main tabs**: Today · Members · Enquiries · Money · Grow (plus Settings) |
| The home page shows **16 KPIs, 2 charts, 8 AI prompts, actions and recommendations** | **One headline number** (₹ waiting to be collected), **one to-do list** and **one proof number** (₹ GymFlow recovered) |
| Developer terms on screen ("JSON-LD", "GPT readiness", "Simulation", "ENABLE_SCHEDULER", "Phone number ID (from Meta)") | Plain owner language, with technical detail kept for the admin console |
| Daily work (Members, Payments, Check-in) is **collapsed under "Gym management"** | Daily work is the first thing on screen |
| Generic "AI SaaS" look (dark slate, Tailwind green, Inter, Sparkles icons, identical cards) | A distinct brand: light-first, bold numerals, one accent colour, real gym imagery, motion only where it means something |
| The landing page sells affiliate, diet and voice features, which the product has since deprioritised | The landing page sells **"Get back the fees you're losing"**, with an ROI calculator and a one-click demo |
| No onboarding: a new owner lands in an empty 52-link dashboard | A 10-minute setup wizard: gym → plans → import members (Excel) → WhatsApp → done |

The commercial argument that justifies the price: **Indian gym software with WhatsApp reminders already sells for ₹200–₹1,000/month.** GymFlow costs ₹999–₹4,999, so it can't win as "another gym register". It has to show, on the home screen every day, **"GymFlow recovered ₹38,500 for you this month. You paid ₹2,499."** Every UI decision below supports that one sentence.

---

## 1. Who we are selling to

### Primary buyer: the independent gym owner
- Runs 1–2 gyms with **150–600 members**, in a tier-1 or tier-2 Indian city (the demo gym is IronCore, Vadodara).
- Today they use a **paper register or Excel, WhatsApp on their own phone, and UPI/cash**.
- Uses the product **mainly on their phone**, often standing in a bright gym. Opens it for a few minutes, a few times a day.
- Comfortable with WhatsApp, Google Pay and Instagram, but **not** with "CRM", "pipeline", "SEO" or "entity consistency".
- Cares about three things: **fees collected, renewals, new joins.** Everything else is secondary.
- Buys on **trust plus visible money**. Asks "how much will this give me back?" and "will my front-desk boy be able to use it?"

### Secondary users
| User | Needs | Where they spend time |
|---|---|---|
| Front desk / manager | Check members in fast, take payments, add enquiries, send reminders | Tablet or phone at the counter |
| Trainer | Their own members, trials, tasks | Phone |
| Member | Days left, dues, diet plan, pay online | Phone (member app) |

### Design implication
> **Design for a 45-year-old owner on a ₹15,000 Android phone in sunlight, who has 90 seconds.** If a screen works for them, it works for everyone.

---

## 2. Market and competitor analysis

### 2.1 What the market charges (India, Nov 2026, from listing sites; check with the vendors before quoting)

| Product | Entry price | Positioning | WhatsApp |
|---|---|---|---|
| GymPilot | ~₹199/mo Starter, ~₹499/mo Pro | Cheap register + reminders | Included |
| Okfit | from ~₹500/mo | India-focused gym management | Included |
| GymBoss | ~₹499 (billing terms unclear) | Renewal reminders | Yes |
| MyGymDesk | ~₹829–₹999/mo | Gym and studio management | Auto reminders, birthdays, expiry |
| iGymsoft | ₹999 / ₹1,799/mo plus ₹2,000 setup | Classic management | **Paid add-on** |
| CRM VEDA | ~₹1,499/mo (6-month billing) | CRM + payment links on WhatsApp | Verified WABA built in |
| Wellyx | $99–$299/mo | Premium all-in-one (international) | Yes |
| FitnessForce | quote-based | Enterprise / chains | n/a |
| **Biggest competitor** | **₹0** | **Register + Excel + personal WhatsApp** | Manual |

Sources: [GymPilot (Capterra)](https://www.capterra.com/p/10040239/GymPilot/), [Okfit](https://okfit.in/blog/okfit-vs-gymforce-facts), [GymBoss (Capterra)](https://www.capterra.com/p/10048972/GymBoss/), [MyGymDesk (G2)](https://www.g2.com/sellers/mygymdesk), [MyGymDesk (Techjockey)](https://www.techjockey.com/detail/mygymdesk), [iGymsoft](https://freedom251.com/apps/igymsoft/), [CRM VEDA (Capterra)](https://www.capterra.com/p/10056716/CRM-VEDA/), [Wellyx (ToolRadar)](https://toolradar.com/compare/fitfaat-vs-wellyx), [FitnessForce (Capterra IN)](https://www.capterra.in/software/128172/fitnessforce), [Gym software pricing in India](https://easygymsoftware.com/blog/gym-software-pricing-in-india)

### 2.2 What this means
1. **Member management and WhatsApp reminders are table stakes.** Everyone has them and they're cheap. Don't lead with them.
2. **No one in the cheap tier proves ROI.** They send reminders but never show "₹ recovered because of this reminder". GymFlow already has that data (`recovered_payment_id`, won opportunities), which is a **real moat**.
3. **No one in the cheap tier does growth** (Google Maps, reviews, website, AI receptionist for enquiries). That's GymFlow's upsell, but only **after** the owner trusts the money side.
4. **The owner's real alternative is doing nothing.** So the demo must answer "what do I gain this month?", not "what features do I get?"

### 2.3 Positioning

> **GymFlow: the gym software that pays for itself.**
> Collect every fee on time, renew more members, and turn more enquiries into joins, all over WhatsApp. See exactly how many rupees GymFlow brought back each month.

| Plan (rename by outcome) | Price | Promise | Includes |
|---|---|---|---|
| **Basic**: "Run my gym" | ₹999/mo | Replace the register | Members, plans, payments, check-in, reminders, member app |
| **Growth**: "Collect & renew" ⭐ recommended | ₹2,499/mo | Stop losing fees | Basic + Money dashboard, renewal and recovery automation, enquiries and trials, AI receptionist on WhatsApp, monthly owner report |
| **Pro**: "Fill my gym" | ₹4,999/mo | Get found online | Growth + Google Maps and reviews, website and landing pages, AI search, competitor watch, multi-branch |

- Offer **annual billing at ~2 months free**, and a **"30-day money-back if GymFlow doesn't recover more than it costs"** guarantee. The data to back that promise already exists.
- Drop "(legacy)" and "(deprioritised)" items from all customer-facing plan lists. Move AI diet and the affiliate store to **optional add-ons** (or hide them).

---

## 3. Current UI audit (why it's a 5/10)

### 3.1 Scorecard

| Dimension | Now | Target | Main reason |
|---|:-:|:-:|---|
| Clarity of navigation | 3 | 9.5 | 52 links, 9 sections, duplicates, daily work hidden |
| First 10 seconds (home) | 4 | 9.5 | 16 equal-weight KPIs, no headline |
| Language / jargon | 3 | 9.5 | Developer terms and data-provenance labels shown to owners |
| Visual identity | 4 | 9 | Default dark slate + Tailwind green; looks AI-generated |
| Mobile experience | 4 | 9.5 | Desktop tables, modals, no bottom nav, no PWA |
| Onboarding / time-to-value | 2 | 9 | None; empty dashboard after sign-up |
| Selling power (ROI visible) | 5 | 10 | The data exists but is buried under "Recovery → History" |
| Consistency | 6 | 9 | Two KPI components, three reports pages, mixed pagers |
| Accessibility | 6 | 9 | Good aria basics; small 11–12px text, low-contrast muted text |
| Trust / honesty | 9 | 9 | Excellent, but surfaced too loudly (see 3.4) |
| **Overall** | **≈5** | **9–9.5** | |

### 3.2 Navigation: the biggest problem
`app/dashboard/layout.tsx` defines **52 nav items** for the owner:

| Section | Items | Issues |
|---|:-:|---|
| Growth dashboard | 4 | "AI growth assistant" duplicates "Business analyst" below |
| SEO & visibility | **10** | 4 of them are just tabs of the same page (`?tab=audits`, `?tab=profile`, `?tab=readiness`) |
| Leads & sales | 6 | "Sales analytics" appears again as "Lead analytics" |
| Trial management | 4 | All four are tabs of one page |
| Revenue recovery | 5 | All five are tabs of one page; "Recovery opportunities" duplicates "Revenue opportunities" |
| AI business intelligence | 5 | 3 overlapping report pages (`/revenue`, `/reports`, `/analytics` "Classic reports") |
| Automation & integrations | 5 | Engineer-facing (Workflow center, Integration health) |
| Gym management (collapsed) | 8 | **Members, Payments, Attendance: the most-used pages, hidden** |
| More (collapsed) | 5 | Settings and Plan are buried here |

**Result:** the owner sees "SEO audits", "GPT readiness" and "Local competitors" before they can find **Members**.

### 3.3 Home page overload
`app/dashboard/overview/page.tsx` renders: a header, **8 business KPIs**, a 7-item action list, an AI ask box with **8 prompt chips**, **4 acquisition KPIs**, 2 charts, a Search Console note, **4 sales KPIs**, **4 recovery KPIs** and recommendations. That's **20 numbers with equal visual weight.** Nothing says "this is what matters today."

### 3.4 Language that confuses (and sometimes scares) the owner

| On screen today | What the owner thinks | Say instead |
|---|---|---|
| "Revenue growth engine" (sidebar subtitle) | ? | Their gym's name |
| "Potential (estimate) – Not revenue" | "So is it money or not?" | "Could collect: ₹42,000" (with a tooltip for the definition) |
| "Recovered … Each backed by a paid payment" | ? | "Brought back by GymFlow" |
| "Link a paid payment record (each payment counts once)" | Confusing | **"Mark as paid"** button (create and link the payment automatically) |
| "Opportunities", "Pipeline", "Lead sources", "Attribution" | Sales jargon | "Renewals due", "Enquiries", "Where enquiries come from" |
| "GPT readiness", "AI-search readiness", "JSON-LD", "Entity consistency" | Meaningless | "Show up when people ask ChatGPT/Google for a gym near them" |
| "Simulation", "configured_not_tested", "Rule engine", "Demo data", "Template draft" | "Is this broken?" | Hide from owners; show only "Connected ✓" or "Connect" |
| "Set ENABLE_SCHEDULER=true (or cron)" (`workflows/page.tsx`) | A developer instruction | Never shown to owners |
| "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET" (`integrations/page.tsx`) | A developer instruction | "Google connection coming soon. We'll set it up for you." |
| "Phone number ID (from Meta)", "approved template name" | Impossible for an owner | "Connect WhatsApp" wizard, or a "We'll do it for you" service |
| "Re-run daily checks", "Refresh opportunities", "Run daily workflows now" | "Why do I have to press it?" | Runs automatically; show "Updated 5 min ago" |
| "Good to see you, IronCore Fitness" | Talking to a building | "Good morning, Rahul" |

> The honesty layer (`SourceBadge`, definitions notes) is **excellent engineering and a selling point**. Keep it, but **move it into tooltips and an "ℹ How we count this" popover.** It shouldn't be printed under every number.

### 3.5 Why it looks "AI-sloppy"
- Default **dark slate + Tailwind `green-500`**, the most common AI-generated dashboard palette.
- **Inter** for everything, small sizes (11–14px), uppercase tracking-wide micro headers on every section.
- Every surface is the same `card` (border, rounded-xl, same padding), so there's no hierarchy.
- A **lucide icon on every one of 52 nav items**, plus `Sparkles` for "AI", `Dumbbell` as the logo and 👋 emoji in the member portal.
- Pill "prompt chips" under an AI input: a recognisable ChatGPT-wrapper pattern.
- Spinners instead of skeletons, no real images, no illustrations, no motion, no brand moments.
- The landing page (`app/page.tsx`) is a centred hero with 4 icon cards: the template look.

### 3.6 Workflow friction
- **Recovery:** to credit a renewal, staff must first record a payment elsewhere and then "link" it in a modal. That's 2 pages and 6 clicks for the most valuable action in the product.
- **Members table:** no days-left, no dues, no WhatsApp button. Those are the three things an owner looks for.
- **Check-in:** a name search only. No phone-number keypad, no QR, no "kiosk" mode for the front desk.
- **Modals inside modals**, with wide forms on mobile (bottom-sheet modals with 3 nested cards in the recovery modal).
- **Two KPI components** (`StatCard`, `Kpi`), **two pagers** (inline in members, `Pager` elsewhere), **three report pages**.
- **Dark theme by default**, which is hard to read in a bright gym and looks "techy" to the buyer.

### 3.7 What's already good (keep it)
- A real **daily action list** (`/growth/actions`), which is exactly the right idea; it just needs to become the home screen.
- **Revenue integrity rules** (collected / recovered / outstanding kept apart). This gives the ROI proof real backing.
- Plan **entitlements** in one place (`core/entitlements.py`), so it's easy to re-bundle plans.
- The **IronCore demo tenant** with realistic data, ideal for sales demos.
- Toasts, confirm dialogs, URL-synced tabs, `en-IN` currency formatting, and basic aria labels.

---

## 4. New information architecture

### 4.1 Owner navigation (5 + 1)

```
┌──────────────────────────┐
│  [logo] IronCore Fitness │  ← gym name, not "Revenue growth engine"
│                          │
│  ● Today                 │  ← home: money + to-do list
│  ● Members               │  ← people, check-in, plans
│  ● Enquiries        (3)  │  ← leads + trials + follow-ups (badge = needs reply)
│  ● Money            (12) │  ← renewals, dues, payments, reports (badge = due)
│  ● Grow                  │  ← Google, reviews, website, AI receptionist
│                          │
│  ─────────────           │
│  ⚙ Settings              │
│  ? Help / WhatsApp us    │
│  [Rahul ▾]               │
└──────────────────────────┘
```
On mobile, the same 5 items become a **bottom tab bar**, with a floating **"+" button** for quick actions: Add member · Take payment · Check in · Add enquiry.

### 4.2 Old page → new home (all 35 dashboard routes)

| New area | Tabs / sections inside | Old routes merged in |
|---|---|---|
| **Today** | (single page) | `overview`, `actions`, `assistant` (becomes the "Ask GymFlow" box + drawer) |
| **Members** | All members · Check-in · Plans & pricing | `members`, `attendance`, `memberships`, `member-portal` (becomes a toggle per member) |
| **Enquiries** | Inbox (list ↔ board toggle) · Trials · Follow-ups | `leads`, `pipeline`, `follow-ups`, `trials` (4 tabs → 1 calendar + list), `lead-sources` + `sales-analytics` (become "Insights" in a side panel) |
| **Money** | Due now · Renewals · Payments · Reports | `recovery` (6 tabs → 2), `payments`, `revenue`, `reports`, `analytics` (all 3 report pages → 1 "Reports" with Month/Day toggle + PDF/WhatsApp share) |
| **Grow** | Online score · Google & reviews · Website · AI receptionist | `seo/*`, `local/*`, `ai-search`, `website-builder`, `seo/landing-pages`, `sales-agent` |
| **Settings** | Gym profile · Team · Reminders · WhatsApp & connections · Subscription · Help | `gym-profile`, `settings`, `trainers`, `automation`, `integrations`, `ai-settings`, `plan` |
| **Hidden / add-on** | Shown only if enabled | `diet-plans` (add-on "Nutrition"), `affiliate` (add-on "Store"), `workflows` (platform admin only), Integration health (platform admin only) |

**52 links → 6.** Nothing is deleted, only regrouped. Routes can be kept with redirects (`next.config.mjs` `redirects()`), so existing links and the AI assistant's `/dashboard/...` links still work.

### 4.3 Trainer navigation
`My members · Check-in · Trials · My tasks`, with the same bottom-bar pattern and no money screens.

### 4.4 Progressive disclosure rules
1. **Default view = the decision**, not the data. Each page opens on its "do this now" list.
2. **Charts and breakdowns live behind "See details"** or in a right-side panel.
3. **Advanced settings** (templates, webhooks, scoring) go under **Settings → Advanced**, collapsed, owner-only.
4. **Plan-locked features are not shown as locked links in the nav.** They appear once, inside Grow, as one tasteful "Unlock with Pro" card with the benefit in ₹.

---

## 5. Key screens (wireframes)

### 5.1 Today (home)

```
Good morning, Rahul                                   Sat, 22 Nov
──────────────────────────────────────────────────────────────────
┌───────────────────────────────┐ ┌──────────────────────────────┐
│ ₹1,24,500                     │ │ GymFlow brought back         │
│ waiting to be collected       │ │ ₹38,500 this month           │
│ 14 overdue · 25 renewals due  │ │ ▲ 15× what you pay for it    │
│ [ Send all reminders ▸ ]      │ │ (₹2,499)        See how ▸    │
└───────────────────────────────┘ └──────────────────────────────┘

 Do these today                                        7 left
 ┌──────────────────────────────────────────────────────────────┐
 │ ○ Amit Shah · membership ends in 2 days · ₹4,000  [WhatsApp]│
 │ ○ Priya K · fee overdue 9 days · ₹1,500          [WhatsApp] │
 │ ○ 3 new enquiries not replied yet                [Reply ▸]  │
 │ ○ Trial today 6 pm · Rohan M                     [Confirm]  │
 │ ○ 2 new Google reviews to answer                 [Reply ▸]  │
 └──────────────────────────────────────────────────────────────┘

 This month   Active 412 (▲8)   New joins 23   Collected ₹3.2L   Check-ins 2,140
 ────────────────────────────────────────────────────────────────
 💬 Ask GymFlow: "Who hasn't come in 2 weeks?"                [ › ]
```
- **2 hero cards + 1 to-do list + 1 slim stats strip + 1 ask box.** That's all.
- Each to-do row has **one primary action inline** (WhatsApp opens a pre-filled message; Confirm marks done). Tick it off, and it animates away with an "Undo" toast.
- The **ROI card** (`recovered / subscription price`) is the single most important sales element in the product.
- Charts move to Money → Reports.

### 5.2 Money → Due now

```
 Money        [Due now] [Renewals] [Payments] [Reports]
 ───────────────────────────────────────────────────────
 ₹1,24,500 due · 39 people          [ WhatsApp all (39) ]

 Overdue (14)                                         ₹52,000
 ┌────────────────────────────────────────────────────────────┐
 │ Priya K     Monthly · ₹1,500 · 9 days late                 │
 │ Reminded 2× (last: yesterday)   [WhatsApp] [Mark paid ▾]   │
 └────────────────────────────────────────────────────────────┘
 Ending this week (11)                                ₹48,000
 Ending in 30 days (14)                               ₹24,500
```
- **"Mark paid ▾"** offers: Cash · UPI · Card. One tap creates the payment, links it to the recovery opportunity and closes it. (Backend: a small endpoint that wraps `mark_paid` + `record-payment`.)
- **"WhatsApp all"** uses the Cloud API if connected; otherwise it opens a queue of `wa.me` deep links one by one. **This works on day one with no Meta approval**, which is a big deal for sales.
- Each message includes a **UPI payment link / QR** (Razorpay link if configured, else the gym's UPI ID).

### 5.3 Members

```
 Members  412 active     [Search name or phone…]      [+ Add member]
 Filters: (All) (Active) (Ending soon) (Expired) (Fee due) (Not coming)
 ┌──────────────────────────────────────────────────────────────────┐
 │ (AS) Amit Shah   Quarterly · 2 days left ⚠   ₹0 due   [💬] [⋯]  │
 │ (PK) Priya K     Monthly   · 18 days left    ₹1,500 ⚠ [💬] [⋯]  │
 └──────────────────────────────────────────────────────────────────┘
```
- Columns that matter: **plan, days left (coloured), dues, last visit, WhatsApp**.
- Clicking a row opens a **right-side sheet** (not a modal) with a timeline: joined, payments, check-ins, messages, plus Renew / Take payment / Freeze.
- On mobile, rows become cards with a swipe action for WhatsApp.

### 5.4 Check-in (front-desk kiosk mode)
- A big numeric keypad: type the last 4 digits of the phone, and the member's face/initials and **days left** appear. Tap to check in.
- If the fee is due, it shows a red "₹1,500 due. Collect now?" with UPI QR.
- "Kiosk mode" locks the tablet to this screen (exit with a PIN).
- Later: QR at the gym entrance, scanned from the member app.

### 5.5 Enquiries

```
 Enquiries   [Inbox] [Trials] [Follow-ups]     (List | Board)   [+ Add]
 Needs reply (3) · Trial booked (5) · Thinking (8) · Joined (9) · Lost
 ┌──────────────────────────────────────────────────────────────────┐
 │ Neha · from Google Maps · 2 h ago · "fees for 3 months?"        │
 │ AI replied ✓  · Hot 🔥                     [WhatsApp] [Book trial]│
 └──────────────────────────────────────────────────────────────────┘
```
- Plain stage names: **Needs reply → Talking → Trial booked → Joined / Lost**. Rename "score" to Hot / Warm / Cold.
- "Where enquiries come from" becomes one small donut in a side panel, not a page.

### 5.6 Grow

```
 Your online score   68 / 100   ▲ 6 this month
 "When people search 'gym near Gotri', you show up 4th."

 Fix these next (each takes < 5 min)
 1. Reply to 2 Google reviews                         [Do it ▸]
 2. Add evening timings to Google profile             [Do it ▸]
 3. Ask 10 happy members for a review (QR ready)      [Send ▸]

 [Google & reviews]  [Website]  [AI receptionist]
```
- Website SEO + Google Maps + AI search = **one score with one prioritised checklist**. The detailed audits live one click deeper.
- Keep the jargon (JSON-LD, entity consistency) in the detail view under "For your web person".

### 5.7 Onboarding wizard (new)
```
Step 1  Your gym        name, city, logo, timings          (pre-filled from sign-up)
Step 2  Your plans      [Monthly ₹1,500] [Quarterly ₹4,000] [+ add]   (smart defaults)
Step 3  Your members    Upload Excel / Google Sheet / photo of register* / add later
Step 4  WhatsApp        Scan QR / "Send from my phone for now" / "Set it up for me"
Step 5  Done 🎉         "You have ₹46,000 in fees due. Send reminders now?"
```
\*Photo-of-register OCR via Claude vision is a strong demo moment (Phase 5).

After the wizard, a **setup checklist card** stays on Today until it's complete (e.g. "4 of 6 done").

### 5.8 Landing page (rebuild `app/page.tsx`)
1. **Hero:** "Stop losing gym fees. GymFlow collects, renews and follows up on WhatsApp, and shows you every rupee it brings back." CTAs: **[See a live demo gym]** (one-click IronCore login) and **[Start 14-day free trial]**.
2. **Product shot:** a real screenshot of the new Today screen inside a phone frame.
3. **ROI calculator:** members × avg fee × "% who renew late" gives "You're losing ~₹X/month."
4. **3 outcome blocks:** Collect fees · Renew members · Get new joins.
5. **"How it works in 10 minutes"** (the wizard steps).
6. **Pricing** (3 plans, Growth highlighted, annual toggle, money-back line).
7. **Trust:** data stays yours, export anytime, Indian servers (if true), WhatsApp support. Use real testimonials only once you have them; never placeholder fakes.
8. **FAQ** in plain language: "Do I need a computer?" "Can my staff use it?" "Hindi?"

---

## 6. Visual design system (de-slop)

### 6.1 Principles
1. **Numbers are the hero.** Large, bold, tabular figures in Indian format (₹1,24,500 / ₹3.2L).
2. **One accent, used rarely.** Colour means something: green = money in, amber = due soon, red = overdue. Brand colour is for actions only.
3. **Hierarchy by size and space, not by borders.** Fewer cards, more whitespace, clear sections.
4. **Light-first** (sunlit gyms, demos on projectors), with a dark toggle.
5. **Human, not robotic.** Real photography in empty states and on the landing page, and friendly owner-voice microcopy. No sparkles.

### 6.2 Tokens (proposed)

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F7F6F3` (warm off-white) | `#0E0F12` | page |
| `--surface` | `#FFFFFF` | `#16181D` | cards, sheets |
| `--ink` | `#14161A` | `#F2F2F0` | text |
| `--muted` | `#5B606B` (≥4.5:1) | `#A3A8B3` | secondary text |
| `--brand` | `#FF5A1F` energetic orange **or** `#2B4BFF` electric blue: pick one | same, tuned | primary buttons, active nav |
| `--money` | `#0F9D58` | `#34C77B` | collected / recovered only |
| `--due` | `#E8A100` | `#F5B83D` | due soon |
| `--overdue` | `#D93025` | `#FF6B5E` | overdue / failed |

- **Fonts:** headings in **"Plus Jakarta Sans"** or **"Manrope"** (600–800 weight, tight tracking); body in **Inter**; numbers in a tabular font. Base size **15–16px** (currently 14px), labels never below **12px**.
- **Radius:** 14px for cards, 10px for inputs/buttons, full for chips. **Elevation:** soft shadows on hero cards only.
- **Icons:** only where they help scanning (nav, actions). Remove icons from table headers and most buttons.
- **Logo:** commission a simple wordmark plus a mark (not the lucide `Dumbbell`).

### 6.3 Components to add or replace
| Need | Recommendation |
|---|---|
| Dialogs, sheets, dropdowns, tooltips, popovers, command palette | **shadcn/ui (Radix primitives)**: accessible, unstyled, fits Tailwind. Use **Sheet** for all detail views |
| Loading | Skeletons per layout instead of the `Loading` spinner |
| KPI | One `<Metric>` component (hero / standard / inline variants) replacing both `StatCard` and `Kpi` |
| Lists | One `<DataList>` that renders a table on desktop and cards on mobile, with one shared pager |
| Empty states | An illustration or photo, one sentence, one button ("Import from Excel") |
| Feedback | Toast with **Undo**; optimistic updates on tick-offs |
| Motion | Count-up on hero numbers, list item exit animation (Framer Motion or CSS); respect `prefers-reduced-motion` |
| "How we count this" | One `<InfoPopover>` that carries all current `Note`/definition text |
| Global search | `Ctrl+K` / a search icon to find any member, enquiry or payment by name/phone |

### 6.4 Microcopy voice
- Talk like a smart gym manager: short, warm, rupee-first. "3 people's fees are late. Want me to remind them?"
- Use the owner's name and the gym's name.
- **i18n-ready from the start** (English → Hindi → Gujarati/Marathi). Use `next-intl`, and keep all strings in message files.

---

## 7. Sales layer (what makes them pay)

| Feature | Why it sells | Effort |
|---|---|---|
| **ROI card on Today** ("brought back ₹X, 15× your plan") | Daily proof of value; renewals of *our* subscription | S (data exists) |
| **Monthly owner report** on WhatsApp + PDF (1st of every month) | The owner shows it to a partner: "GymFlow got us ₹1.1L" | M |
| **One-click demo** ("See a live demo gym" logs into IronCore, guided 60-second tour) | Sales calls, Instagram ads, self-serve | S–M |
| **`wa.me` fallback** for WhatsApp | Works without Meta approval, so the trial delivers value on day one | S |
| **Excel / Google Sheets import** | Removes the #1 switching barrier | M |
| **UPI QR / payment link inside reminders** | Collect money in the same message | S–M |
| **Kiosk check-in** | Visible, physical, impressive in a demo | M |
| **"Set it up for me"** (WhatsApp, Google, import) as a paid onboarding (₹1,999 one-time) | Extra revenue; removes the technical fear | Process |
| **PWA install** ("Add GymFlow to home screen") | Feels like an app, no store needed | S |
| **Referral**: "Give a gym friend 1 month free, get 1 month free" | Owners know other owners | M |
| **Money-back guarantee tied to recovered ₹** | Removes purchase risk; the data proves it | Policy |

---

## 8. Roadmap and score progression

| Phase | Duration | Scope | Score after |
|---|---|---|:-:|
| **0. Quick wins** | 1–2 days | Light theme default; remove dev text (`ENABLE_SCHEDULER`, env names, "Simulation") from owner screens; rename jargon (table in 3.4); hide affiliate, diet, voice and workflow center from owners; remove duplicate nav items; greet by owner name; base font 15px | **6** |
| **1. Navigation & IA** | ~1 week | New 5+1 nav + mobile bottom bar + quick-add "+"; merge pages per 4.2 (tabs inside pages); redirects for old routes; nav badges (due count, needs-reply count); trainer nav | **7** |
| **2. Design system** | ~1 week | New tokens, fonts and logo; shadcn/ui base; `Metric`, `DataList`, `Sheet`, `InfoPopover`, skeletons, empty states; one pager; delete `StatCard` | **7.5** |
| **3. Core screens** | ~2 weeks | Today (hero + ROI + to-do with inline actions); Money (Due now + one-tap Mark paid + WhatsApp all); Members (days left, dues, side sheet); Enquiries (plain stages, list/board); Check-in kiosk; Reports merged with PDF/WhatsApp share | **8.5** |
| **4. Onboarding & selling** | ~1 week | Setup wizard + checklist; Excel import; one-click demo + guided tour; new landing page with ROI calculator; pricing rewrite; plan page in ₹ outcomes | **9** |
| **5. Polish & reach** | ~1–2 weeks | Grow → one online score + checklist; PWA; Hindi; monthly owner report; `wa.me` queue; UPI QR in reminders; motion; accessibility pass (contrast, 44px targets, keyboard); usability test with 3–5 real gym owners and fix what they stumble on | **9.5** |

**Definition of done for 9.5:** a first-time owner, with no help, can (1) find who owes money, (2) send them a reminder, (3) mark a payment and (4) add a member, **each in under 30 seconds on a phone**, and can say what GymFlow earned them this month. Measure this in the Phase 5 usability test.

### Engineering notes
- Mostly frontend work. Backend additions are small: a "mark paid and credit" endpoint, an import endpoint (CSV/XLSX), a "monthly owner report" job, the ROI figure on `/growth/dashboard`, `wa.me` link generation, and optional i18n of server-generated messages.
- Keep all business rules in the backend (they're already right). The UI only changes **presentation and grouping**.
- Add Playwright smoke tests for the 4 "definition of done" flows, plus visual snapshots for Today/Money/Members on mobile and desktop widths.

---

## 9. Environment variables

Grouped by **when you need them**. ✅ = already read by the code today (`app/core/config.py`, frontend `.env.example`). 🆕 = proposed by this plan (needs code).

### 9.1 Backend: `gymflow-backend/.env`

```bash
# ───────────── A. REQUIRED to run anything (demo or production) ─────────────
ENVIRONMENT=production                       # ✅ enforces strong SECRET_KEY
SECRET_KEY=<64 random chars>                 # ✅ python -c "import secrets;print(secrets.token_urlsafe(48))"
DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/gymflow   # ✅ use Postgres (Neon/Supabase/RDS), not SQLite
CORS_ORIGINS=["https://app.yourdomain.in","https://yourdomain.in"]   # ✅
FRONTEND_URL=https://app.yourdomain.in       # ✅ used in links, QR codes, OAuth
PUBLIC_API_URL=https://api.yourdomain.in/api/v1   # ✅
TOKEN_ENCRYPTION_KEY=<another random string> # ✅ encrypts Google/WhatsApp tokens at rest
ENABLE_SCHEDULER=true                        # ✅ exactly ONE API instance; otherwise use cron
TRIAL_DAYS=14                                # ✅
SITES_BASE_DOMAIN=yourdomain.in              # ✅ gym websites: <slug>.yourdomain.in

# ───────────── B. REQUIRED for a convincing sales demo ─────────────
ANTHROPIC_API_KEY=sk-ant-...                 # ✅ AI receptionist, analyst, drafts (otherwise rule engine)
AI_MODEL=claude-opus-5-5                     # ✅ consider claude-sonnet-5-5 for chat to cut cost
RAZORPAY_KEY_ID=rzp_test_...                 # ✅ payment links in reminders (test keys fine for demo)
RAZORPAY_KEY_SECRET=...                      # ✅
RAZORPAY_WEBHOOK_SECRET=...                  # ✅ webhook: {PUBLIC_API_URL}/payments/webhooks/razorpay

# ───────────── C. REQUIRED before the first PAYING gym ─────────────
# WhatsApp Cloud API (Meta Business verification + approved templates take 1–3 weeks: start now)
WHATSAPP_PHONE_NUMBER_ID=...                 # ✅
WHATSAPP_ACCESS_TOKEN=...                    # ✅ use a permanent System User token, not the 24h one
WHATSAPP_VERIFY_TOKEN=<random>               # ✅ webhook verify: {PUBLIC_API_URL}/webhooks/whatsapp
WHATSAPP_APP_SECRET=...                      # ✅ verifies X-Hub-Signature-256
WHATSAPP_API_URL=https://graph.facebook.com/v21.0   # ✅ default; bump when Meta deprecates

# Email: password reset + monthly owner report (gap in README)
EMAIL_PROVIDER=resend                        # 🆕 resend | smtp
RESEND_API_KEY=re_...                        # 🆕
EMAIL_FROM="GymFlow <hello@yourdomain.in>"   # 🆕
SMTP_HOST= SMTP_PORT=587 SMTP_USER= SMTP_PASSWORD=   # 🆕 if EMAIL_PROVIDER=smtp

# SaaS billing for YOUR subscription (Razorpay Subscriptions: not built yet)
RAZORPAY_PLAN_BASIC=plan_...                 # 🆕
RAZORPAY_PLAN_GROWTH=plan_...                # 🆕
RAZORPAY_PLAN_PRO=plan_...                   # 🆕
GST_NUMBER=...                               # 🆕 shown on invoices

# Error monitoring
SENTRY_DSN=https://...                       # 🆕 strongly recommended before customers

# ───────────── D. Growth (Pro plan) features ─────────────
GOOGLE_CLIENT_ID=...apps.googleusercontent.com   # ✅ Search Console + Business Profile
GOOGLE_CLIENT_SECRET=...                     # ✅
GOOGLE_OAUTH_REDIRECT_URI=https://api.yourdomain.in/api/v1/integrations/google/callback  # ✅
# Business Profile API needs Google's access approval (apply early); consent screen needs verification.
KEYWORD_PROVIDER=                            # ✅ optional (e.g. dataforseo)
KEYWORD_PROVIDER_API_KEY=                    # ✅
SEO_MAX_PAGES=25                             # ✅
SEO_REQUEST_TIMEOUT=10                       # ✅

# ───────────── E. Optional / later ─────────────
PUBLIC_RATE_LIMIT_PER_MINUTE=20              # ✅
REDIS_URL=redis://...                        # 🆕 shared rate limiting when you run >1 API replica
N8N_WEBHOOK_BASE_URL=                        # ✅ leave empty unless you use n8n
N8N_API_KEY=                                 # ✅
SMS_PROVIDER=msg91  MSG91_AUTH_KEY=  MSG91_SENDER_ID=   # 🆕 OTP login / SMS fallback (DLT registration needed in India)
VOICE_API_URL=  VOICE_API_KEY=               # ✅ deprioritised; leave empty
AMAZON_ASSOCIATE_TAG=                        # ✅ only if the store add-on is enabled
PLATFORM_SHARE_PCT=20 GYM_SHARE_PCT=30 TRAINER_SHARE_PCT=50   # ✅ store add-on only
DEMO_GYM_SLUG=ironcore-fitness-demo          # 🆕 for one-click demo + nightly reset
DEMO_RESET_CRON="0 3 * * *"                  # 🆕
```

### 9.2 Frontend: `gymflow-frontend/.env.local` (or host env)

```bash
NEXT_PUBLIC_API_URL=https://api.yourdomain.in/api/v1    # ✅
API_URL_INTERNAL=http://api:8000/api/v1                 # ✅ SSR of public gym sites
NEXT_PUBLIC_APP_NAME=GymFlow                            # 🆕 brand in one place
NEXT_PUBLIC_SITE_URL=https://yourdomain.in              # 🆕 canonical/OG tags on landing
NEXT_PUBLIC_DEMO_LOGIN_ENABLED=true                     # 🆕 shows "See a live demo gym"
NEXT_PUBLIC_DEMO_EMAIL=owner@ironcore.demo              # 🆕 demo-only account, safe to expose
NEXT_PUBLIC_SUPPORT_WHATSAPP=91XXXXXXXXXX               # 🆕 "WhatsApp us" button in Help
NEXT_PUBLIC_DEFAULT_LOCALE=en                           # 🆕 en | hi | gu
NEXT_PUBLIC_POSTHOG_KEY=phc_...                         # 🆕 product analytics: funnel from demo → trial → paid
NEXT_PUBLIC_POSTHOG_HOST=https://eu.i.posthog.com       # 🆕 (or self-host)
NEXT_PUBLIC_SENTRY_DSN=https://...                      # 🆕 frontend errors
NEXT_PUBLIC_RAZORPAY_KEY_ID=rzp_live_...                # 🆕 checkout for your SaaS subscription
```
> Don't put the demo **password** in a `NEXT_PUBLIC_*` variable. Have the backend expose a `POST /auth/demo-login` that only issues a token for the demo gym.

### 9.3 Accounts to open now (long lead times)
1. **Meta Business Manager + WhatsApp Business Platform** (business verification, display-name approval, message templates for renewal/payment/trial). Lead time 1–3 weeks.
2. **Razorpay** (KYC for live mode; enable Payment Links and Subscriptions).
3. **Google Cloud project** (OAuth consent screen verification; apply for Business Profile API access).
4. **Domain + DNS** (wildcard `*.yourdomain.in` for gym sites), **managed Postgres** (with backups), and hosting for API + web.
5. **Email domain** (SPF/DKIM via Resend or SES) for password reset and reports.
6. **MSG91 + DLT registration**, only if you want SMS/OTP.

---

## 10. Before / after summary for the pitch

| | Before | After |
|---|---|---|
| First screen | 20 numbers, jargon | "₹1.24L waiting · GymFlow brought back ₹38,500 (15× its cost)" |
| Find who owes money | Gym management → Payments, or Recovery → Outstanding tab | Home, top card, one tap |
| Collect a renewal | Record payment page → Recovery → modal → link | **WhatsApp → Mark paid (UPI)**: 2 taps |
| Menu | 52 links | 5 tabs |
| Setup | None | 10-minute wizard + Excel import |
| WhatsApp | Needs Meta approval before anything works | Works from day one via `wa.me`, upgrades to automatic later |
| Look | Generic AI dark dashboard | Branded, light, number-first, mobile-first |
| Sales story | "We have SEO, CRM, AI agents…" | "We pay for ourselves, and here's the receipt every month." |

---

## 11. Implementation status

_Updated 22 Nov 2026._

| Plan item | Status | Where |
|---|---|---|
| 5+1 navigation, mobile bottom bar, quick-add "+", nav badges | ✅ Done | `components/dashboard/nav.ts`, `AppShell.tsx` |
| Today: money hero, ROI card, person-level to-do list, setup checklist | ✅ Done | `app/dashboard/overview` |
| Money → Due now, one-tap *Mark paid*, WhatsApp reminder queue | ✅ Done | `app/dashboard/money`, `POST /recovery/opportunities/{id}/mark-paid` |
| Members: days left, dues, last visit, WhatsApp; side panel with timeline | ✅ Done | `MemberSheet.tsx`, `GET /members/{id}/timeline` |
| Enquiries: plain stages, Hot/Warm/Cold | ✅ Done | `LeadDrawer.tsx`, leads page |
| Grow: one online score + "fix these next" | ✅ Done | `app/dashboard/grow` |
| Plain-language copy, dev text removed from owner screens | ✅ Done | across pages |
| Design system: light-first tokens, display font, skeletons, Sheet, InfoTip | ✅ Done | `globals.css`, `components/shared/ui.tsx` |
| Landing page, ROI calculator, one-click demo + guided tour | ✅ Done | `app/page.tsx`, `DemoButton.tsx`, Today `DemoTour` |
| Pricing by outcome, referral programme | ✅ Done | `app/dashboard/plan` |
| Setup wizard + Excel/CSV import | ✅ Done | `app/dashboard/setup`, `ImportMembers.tsx`, `POST /members/import` |
| Front-desk check-in kiosk | ✅ Done | `app/kiosk` |
| `wa.me` reminders, Razorpay links, UPI pay page/QR fallback | ✅ Done | `DueRow.tsx`, `app/pay/[slug]` |
| Monthly owner report (WhatsApp / PDF / email) | ✅ Done | `OwnerReport.tsx`, `app/workers/monthly_worker.py` |
| Password reset by email | ✅ Done | `/forgot-password`, `/reset-password` |
| Razorpay SaaS subscription billing | ✅ Done (needs plan ids) | `POST /subscriptions/checkout`, webhook |
| Hindi | 🟡 Partial – navigation, Today, Money | `lib/i18n.ts` |
| PWA | 🟡 Manifest + icon (installable); no offline mode | `public/manifest.webmanifest` |
| Analytics / error monitoring | ✅ Optional, env-gated (PostHog capture API, Sentry) | `lib/analytics.ts`, `app/main.py` |
| Groq for text/agents, Gemini for posts, images, live search | ✅ Done (images need Gemini billing) | `app/integrations/ai/` |
| shadcn/ui adoption | ⏭️ Replaced by our own small Sheet / InfoTip / Skeleton components (no new dependency) | — |
| Hindi on every screen, Gujarati/Marathi | ⬜ Open | extend `lib/i18n.ts` |
| Photo-of-register OCR, Google Sheets live link | ⬜ Open | CSV export from Sheets works today |
| Shared (Redis) rate limiting, SMS/OTP via MSG91 | ⬜ Open | only needed at scale / for OTP login |
| Usability test with 3–5 gym owners | ⬜ Open | needs real owners – the last step to 9.5 |
