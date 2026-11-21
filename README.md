# GymFlow — AI-Powered Gym Revenue Growth Engine

**Discover more customers. Convert more enquiries. Recover more revenue. Grow your gym.**

GymFlow helps independent gyms get found (website SEO, Google Maps, AI search), capture and convert
enquiries (CRM, AI sales agent, trials), protect revenue (renewals, payment recovery) and decide what to
do next (AI business analyst) — all on the gym's own records. See **[docs/GROWTH_ENGINE.md](docs/GROWTH_ENGINE.md)**
for the architecture, feature audit, integration status and known gaps.

| Growth module | What it does |
|---|---|
| **Website SEO** | SSRF-safe crawler that respects robots.txt, evidence-backed findings, audit history, approve-before-apply suggestions, local keyword ideas, landing pages, Search Console (OAuth) |
| **Google Maps SEO** | Business Profile OAuth + audit against your approved profile, review replies (publish via API or copy), policy-safe review requests with QR, competitor comparison, post drafts |
| **AI search visibility** | Transparent readiness checklist, entity consistency, JSON-LD generator/validator (no ratings), content studio, manually sampled visibility monitoring |
| **AI sales agent** | Website chat + WhatsApp agent grounded in approved gym info; qualifies, books trials, escalates and hands over to staff |
| **Lead CRM & pipeline** | One inbox for every channel, evidence-based attribution, de-duplication, explainable scoring, Kanban, follow-ups, campaigns |
| **Trials** | Slot grid with capacity and trainer conflicts, calendar, staff-confirmed no-shows, conversion tracking |
| **Revenue recovery** | Renewal milestones (30/15/7/0/after), outstanding & failed payments, recovery credited only from paid payments |
| **AI business analyst** | Answers questions from deterministic KPIs, evidence-backed recommendations, actions that need confirmation, reports |

The original platform services remain:

| Module | What it does |
|---|---|
| **Automation** | Members, memberships, fees, attendance, expiry/payment reminders over WhatsApp and AI voice calls, n8n hooks, daily/monthly reports |
| **AI Nutrition** | Diet plans from height, weight, goal, diet type and restrictions (Claude), reviewed and assigned by trainers |
| **Affiliate Store** | Platform product catalogue, trackable trainer/gym links, commission split platform / gym / trainer |
| **Website Builder** | Drag-and-drop gym website with live plans and trainers, publish, custom domain, lead capture |

```
gymflow-backend/    FastAPI + SQLAlchemy 2 + Alembic (PostgreSQL in prod, SQLite for dev/tests)
gymflow-frontend/   Next.js 15 App Router + Tailwind
docker-compose.yml  postgres + api + n8n + web
```

## Quick start (local)

**Backend** (Python 3.10+)

```bash
cd gymflow-backend
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                 # set SECRET_KEY; everything else is optional
alembic upgrade head
python -m app.seed                                   # platform admin, small demo gym, IronCore Fitness demo
uvicorn app.main:app --reload                        # http://localhost:8000/docs
pytest                                               # 79 tests
```

**Frontend** (Node 20+)

```bash
cd gymflow-frontend
npm install
cp .env.example .env.local
npm run dev                                          # http://localhost:3000
```

Demo logins (from `app.seed`):

| Role | Email | Password |
|---|---|---|
| Platform admin | admin@gymflow.app | admin12345 |
| Gym owner (small demo) | owner@demo-gym.com | owner12345 |
| **IronCore Fitness owner** (full growth demo, Pro plan) | owner@ironcore.demo | ironcore123 |
| IronCore manager / trainer | manager@ironcore.demo / trainer@ironcore.demo | ironcore123 |

Or run everything with Docker: `docker compose up --build` (create `gymflow-backend/.env` first).

## How multi-tenancy works

Every gym is a tenant (`gyms` table). Gym-scoped tables carry `gym_id`.

- `core/permissions.tenant_user()` resolves the caller's gym from their JWT (platform admins pass `X-Gym-ID`) and stores it in a ContextVar (`core/tenant_context.py`).
- `database/repositories/base.TenantRepository` adds `WHERE gym_id = :current` to every query and stamps it on every insert, so module code cannot read or write another gym's rows. `tests/test_auth_and_tenancy.py` covers this.
- Webhooks and workers have no logged-in user, so they use `tenant_scope(gym_id)` explicitly.

Roles: `platform_admin`, `gym_owner`, `gym_manager`, `trainer` (sees only assigned members), `member` (member app at `/member`).

## Background jobs

| Job | Schedule | Does |
|---|---|---|
| `app.workers.expiry_worker` | daily | expires lapsed memberships; runs expiring / expired / birthday / inactive rules |
| `app.workers.payment_worker` | daily | marks unpaid fees overdue; runs payment-due rules |
| `app.workers.growth_worker` | daily | flags past trials for attendance review, syncs renewal/payment/lead recovery opportunities, saves the daily growth report |
| `app.workers.notification_worker` | every minute | delivers queued WhatsApp / voice / SMS / email |

Set `ENABLE_SCHEDULER=true` to run them inside the API (one instance only), or run `python -m app.workers.<name>` from cron or an n8n Cron node. Reminders are de-duplicated, so re-running a job never double-messages a member.

## Integrations

All integrations are optional. When one is not configured it runs in **dev mode**: messages and calls are logged instead of sent, payments get fake order ids, and diet plans come from a built-in template. The admin console (*Integrations*) shows what is connected.

| Service | Env vars | Notes |
|---|---|---|
| Groq (default text model) | `GROQ_API_KEY`, `GROQ_MODEL`, `LLM_PROVIDER` | Agents' tool loop (OpenAI-compatible tool calling), content drafts and diet plans. `LLM_PROVIDER=auto` uses Groq when its key is set, else Claude. Small accounts have an 8K tokens/minute limit; requests are sized for it and fall back to the rule engine when rate-limited. |
| Gemini | `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_IMAGE_MODEL` | Google/social post drafts, post pictures (`POST /local/posts/image`, needs billing on the key) and live Google Search checks for AI visibility (`POST /ai-search/visibility/queries/{id}/check`). |
| Claude | `ANTHROPIC_API_KEY`, `AI_MODEL` | `integrations/ai/diet_generator.py`. Calorie/macro targets are computed in code (Mifflin-St Jeor), Claude builds the meals as validated structured output. Server-side refusal fallback is enabled. |
| WhatsApp Cloud API | `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN` | Business-initiated messages need approved templates in production; see `send_template()`. |
| AI voice calls | `VOICE_API_URL`, `VOICE_API_KEY` | Provider-agnostic `POST /calls`; adapt the payload in `integrations/voice/client.py`. |
| Razorpay | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | Webhook: `POST /api/v1/payments/webhooks/razorpay` (`payment.captured`, `order.paid`, `payment.failed`, `payment_link.paid`). WhatsApp reminders on *Money → Due now* carry a payment link (rzp.io) when keys are set; a paid renewal link creates the renewal automatically. |
| n8n | `N8N_WEBHOOK_BASE_URL`, `N8N_API_KEY` | Outbound events: `member.created`, `membership.created`, `payment.paid`, `lead.created`, plus per-rule workflows. Inbound: `POST /api/v1/automation/n8n/send` with `X-N8N-Key`. |
| Amazon Associates | `AMAZON_ASSOCIATE_TAG` | Links carry `ascsubtag=<link code>` so report rows map back to gym and trainer. |

## Known gaps / next steps

See also [docs/GROWTH_ENGINE.md](docs/GROWTH_ENGINE.md#5-known-gaps).

- Password reset only returns 202; email/WhatsApp delivery of a reset token isn't built yet.
- Plan changes (*Plan & usage*) switch the plan directly and are logged; Razorpay subscription billing and proration are not implemented.
- Affiliate conversions are recorded by the platform admin (from network reports); there's no automated report import.
- Custom domains are stored and served via `GET /public/sites/by-domain`; DNS/TLS provisioning and host-based routing in the frontend aren't wired up.
- The frontend stores the JWT in a JS-readable cookie so middleware can route by role. For production, consider an httpOnly cookie set by the API.
