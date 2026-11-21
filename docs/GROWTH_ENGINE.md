# GymFlow Growth Engine (Phase 1)

GymFlow helps an independent gym **discover → capture → convert → recover → optimize**. This document
describes what was built in Phase 1, how the parts connect, and what is still missing.

## 1. Feature audit of the original app

| Feature | State found | Decision | Notes |
|---|---|---|---|
| Members, memberships, attendance, trainers | Working, tested | **Keep & improve** | Membership payments now go through one `mark_paid` path so recovery and revenue stay consistent. |
| Payments + Razorpay orders/webhook | Working (dev-mode orders) | **Keep & improve** | Added `payment.failed`, `payment_link.paid`, webhook event de-duplication, `verified_by`. |
| Automation rules + notification queue | Working | **Keep & improve** | Added 30/15-day expiry rules for new gyms; notifications can target leads and use approved WhatsApp templates. |
| WhatsApp client (outbound) | Working in dev mode | **Expand** | Inbound webhook, signature check, opt-out, delivery receipts, 24-hour window policy. |
| Website builder + public site + leads | Working | **Keep & improve** | Leads now flow into the CRM with attribution; landing pages, sitemap, JSON-LD, chat and trial booking added. |
| Multi-tenancy (`TenantRepository`, `tenant_scope`) | Working, tested | **Preserved** | Every new table is gym-scoped; every new query goes through the repository. |
| Roles / permissions | Working | **Strengthened** | Plan entitlements per endpoint, agent tool permissions, owner-only connect/approve actions. |
| Workers + APScheduler | Working | **Extended** | New daily `growth_worker` (trials review, recovery sync, daily report). |
| n8n | Optional event sink | **Kept optional** | Fed by the new event bus; no core flow depends on it. |
| Subscriptions | Plans + direct switch | **Improved** | Central entitlements, usage limits, history. Razorpay subscription billing still not implemented. |
| AI Nutrition | Working | **Kept, secondary** | Moved under "More". |
| Affiliate store | Working | **Hidden from primary nav** | Route and data untouched ("More → Affiliate store (legacy)"). |
| AI voice calls | Provider stub | **Deprioritised** | Not used by any core workflow. |
| Custom domains | Stored only | **Unchanged** | DNS/TLS provisioning still not built. |
| Member portal | Working | **Kept** | Linked from Gym management. |

Nothing was deleted. One migration (`0002_growth_engine`) adds 31 tables and new nullable/defaulted
columns to `leads`, `notifications` and `payments`; existing rows stay valid. `LeadStatus` gained
pipeline stages; `converted` is kept (shown as "Joined") so old data and the legacy `/leads` API still work.

## 2. Architecture

```
app/
  core/entitlements.py     plan features + usage limits (single source; frontend reads /subscriptions/entitlements)
  core/crypto.py           Fernet encryption for OAuth tokens
  core/rate_limit.py       per-IP limiter for public endpoints
  services/events.py       event bus: EventLog row + in-process handlers + n8n forward
  services/handlers.py     payment.paid -> close recovery; payment.failed -> open recovery
  services/messaging.py    WhatsApp policy (opt-in/opt-out, 24h window, templates, else staff draft)
  services/content.py      grounded copy generation (Claude or template) + unsupported-claims guard
  agents/                  registry (tools, roles, features, approvals), rule engines, Claude tool loop
  modules/crm | trials | recovery | seo | local_seo | ai_search | growth | integrations | public | ai_agents
  demo/ironcore.py         isolated demo tenant + reset
```

Deterministic code owns every number: payments, expiry, revenue, scoring, slots, permissions, KPIs.
The LLM is only used for conversation, copy drafts and phrasing answers from tool results.

### Module connections

| Connection | Path |
|---|---|
| A. SEO → CRM | Landing page form sends `landing_page` → lead source `seo_landing_page`, `landing_page_id` set |
| B. Maps → CRM | Only tracked links (`utm_source=google&utm_medium=gbp` or a GBP campaign) become `google_business_profile` |
| C. AI search → CRM | `utm_source=chatgpt.com` or an AI-assistant referrer → `ai_search`; otherwise not claimed |
| D. Agent → CRM | `save_lead_details` → `capture_lead` (dedupe, score, task) → `book_trial` |
| E. CRM → Trial | `trials.book` validates slot/capacity/trainer/lead and advances the stage |
| F. Trial → Membership | `convert_lead` creates member + membership + payment; trial gets `converted_membership_id` |
| G. Membership → Recovery | Daily sync creates/advances renewal & payment opportunities; `payment.paid` closes them once |
| H. All → Analyst | `growth/metrics.py` + `growth/insights.py` read the same tables; agents call them as tools |

### Revenue rules

- **Collected** = PAID payments in the period. **Recovered** = WON opportunities, each linked to one PAID
  payment (`recovered_payment_id` is unique). **Outstanding** = unpaid payment records now.
  **Potential** = estimated value of open opportunities (never revenue). **Forecast** = unpaid due in 30
  days + open renewals × historical renewal rate (needs ≥5 closed renewals, otherwise 0 is added).
- Staff cannot mark an opportunity "won" without linking a paid payment.

### Agents

Eight agents share one tool registry (`app/agents/tools.py`). Each tool declares input schema,
allowed roles (`public` for website/WhatsApp visitors), required plan feature, and whether it is
consequential. Consequential tools (`send_message_to_lead`, `run_seo_audit`) create a `PendingAction`
that a staff user must confirm; permissions are re-checked at confirmation. Public tools only act on
the visitor's own conversation/lead. Every invocation is logged in `ai_agent_runs` (engine, tools,
tokens, estimated cost).

- With `ANTHROPIC_API_KEY`: manual Messages-API tool loop (`claude-opus-5-5`, effort low for sales,
  medium for analysis, server-side refusal fallback enabled).
- Without it: rule engines (`app/agents/rules.py`) that answer only from approved data and tool output.
  The UI labels which engine answered.

## 3. Integration status

| Integration | Status in this environment | What's needed |
|---|---|---|
| Claude | Not configured → rule engine + templates | `ANTHROPIC_API_KEY`. Tool loop is unit-tested with a mocked client only. |
| Google Search Console | Implemented, **not configured / never live-tested** | Google OAuth client, consent screen, `webmasters.readonly` scope. |
| Google Business Profile | Implemented, **not configured / never live-tested** | OAuth client + Google's Business Profile API access approval. Insights/metrics API not integrated. |
| WhatsApp Cloud API | **Simulation** (messages logged) | `WHATSAPP_PHONE_NUMBER_ID/ACCESS_TOKEN`, webhook token/secret, approved templates. |
| Razorpay | **Simulation** (fake order ids); webhook verification tested | Keys + webhook secret. Payment links need keys. Subscription billing not implemented. |
| n8n | Not configured (optional) | `N8N_WEBHOOK_BASE_URL`. |
| Keyword metrics provider | **Not implemented** | Adapter to a licensed provider. |
| AI answer monitoring provider | **Not implemented** | Manual research samples only (labelled). |
| Email / SMS | **Not implemented** | Logged only. |

## 4. Demo tenant (IronCore Fitness, Gotri, Vadodara)

`python -m app.seed` creates it (or `python -m app.demo.ironcore --reset`; platform admins can call
`POST /api/v1/platform/demo/reset`, the demo owner can call `POST /api/v1/growth/demo/reset`). Only the
gym with slug `ironcore-fitness-demo` **and** `settings.is_demo=true` is ever deleted.

Logins: `owner@ironcore.demo`, `manager@ironcore.demo`, `trainer@ironcore.demo` — password `ironcore123`.

~429 members (25 renewals due in 30 days, 14 overdue + 3 failed payments, 25 inactive), 5 trainers, 5
plans (₹1,500 / ₹4,000 / ₹7,000 / ₹12,000 + PT), ~2,900 check-ins, 50 enquiries with interactions and
tasks, 18 trials (7 confirmed no-shows, 1 awaiting review), 9 conversions with real memberships, 18
renewals recovered via real payments, campaigns, keywords, a landing page, reviews, competitors and AI
visibility samples. SEO audit, Business Profile audit and reviews are stored as `demo_simulated` and
badged "Demo data" in the UI. No Search Console numbers are generated.

## 5. Known gaps

- Razorpay subscription billing / proration (plan changes are immediate, billed outside GymFlow).
- Live verification of Google and WhatsApp integrations (needs real credentials and app review).
- Business Profile performance metrics, photos and attributes endpoints (reported as unavailable).
- Keyword volume/difficulty and automated AI-answer monitoring providers.
- Rate limiting is in-process (use a shared limiter with several API replicas).
- The crawler checks the connected peer address but does not pin DNS; a hostile DNS server could
  still race a lookup (requests to a private address are refused before the body is read).
- Not verified here: Docker image builds and running migrations on PostgreSQL (no Docker on the build
  machine); tests and migrations ran on SQLite.
- Password-reset delivery and custom-domain provisioning remain from the original backlog.
