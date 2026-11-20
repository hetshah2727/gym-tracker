# GymFlow AI

Multi-tenant gym management and business-automation SaaS. One platform, four services:

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
python -m app.seed                                   # demo gym + platform admin
uvicorn app.main:app --reload                        # http://localhost:8000/docs
pytest                                               # 20 tests
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
| Gym owner | owner@demo-gym.com | owner12345 |

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
| `app.workers.notification_worker` | every minute | delivers queued WhatsApp / voice / SMS / email |

Set `ENABLE_SCHEDULER=true` to run them inside the API (one instance only), or run `python -m app.workers.<name>` from cron or an n8n Cron node. Reminders are de-duplicated, so re-running a job never double-messages a member.

## Integrations

All integrations are optional. When one is not configured it runs in **dev mode**: messages and calls are logged instead of sent, payments get fake order ids, and diet plans come from a built-in template. The admin console (*Integrations*) shows what is connected.

| Service | Env vars | Notes |
|---|---|---|
| Claude | `ANTHROPIC_API_KEY`, `AI_MODEL` | `integrations/ai/diet_generator.py`. Calorie/macro targets are computed in code (Mifflin-St Jeor), Claude builds the meals as validated structured output. Server-side refusal fallback is enabled. |
| WhatsApp Cloud API | `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN` | Business-initiated messages need approved templates in production; see `send_template()`. |
| AI voice calls | `VOICE_API_URL`, `VOICE_API_KEY` | Provider-agnostic `POST /calls`; adapt the payload in `integrations/voice/client.py`. |
| Razorpay | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | Webhook: `POST /api/v1/payments/webhooks/razorpay` (`payment.captured`, `order.paid`). |
| n8n | `N8N_WEBHOOK_BASE_URL`, `N8N_API_KEY` | Outbound events: `member.created`, `membership.created`, `payment.paid`, `lead.created`, plus per-rule workflows. Inbound: `POST /api/v1/automation/n8n/send` with `X-N8N-Key`. |
| Amazon Associates | `AMAZON_ASSOCIATE_TAG` | Links carry `ascsubtag=<link code>` so report rows map back to gym and trainer. |

## Known gaps / next steps

- Password reset only returns 202; email/WhatsApp delivery of a reset token isn't built yet.
- Plan changes in *Settings → Subscription* switch the plan directly; Razorpay subscription billing and proration are TODOs.
- Affiliate conversions are recorded by the platform admin (from network reports); there's no automated report import.
- Custom domains are stored and served via `GET /public/sites/by-domain`; DNS/TLS provisioning and host-based routing in the frontend aren't wired up.
- The frontend stores the JWT in a JS-readable cookie so middleware can route by role. For production, consider an httpOnly cookie set by the API.
