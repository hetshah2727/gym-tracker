# Deploying GymFlow on Vercel

GymFlow is two Vercel projects from the same GitHub repo:

| Project | Root directory | What it is |
|---|---|---|
| `gymflow-web` | `gymflow-frontend` | Next.js app (landing page, dashboard, member app, gym websites) |
| `gymflow-api` | `gymflow-backend` | FastAPI as a Python serverless function (`api/index.py`), plus a daily Vercel Cron |

> **Keep the GitHub repo private.** GitHub → repo → Settings → General → Danger zone → *Change visibility* →
> Private. Vercel deploys private repos normally. Secrets never go in the repo – only in Vercel's Environment Variables.

## 1. Database (once)

Serverless functions have no permanent disk, so the API needs PostgreSQL. The simplest option is
**Vercel → Storage → Create → Neon (Postgres)**, connected to the `gymflow-api` project. Copy its connection
string and use the `postgresql+psycopg://` form:

```
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

## 2. API project (`gymflow-api`)

1. Vercel → *Add New Project* → import the repo → **Root Directory: `gymflow-backend`** → Framework preset: *Other*.
2. Environment variables (Production):

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` (hides `/docs` and `/openapi.json`) |
| `SECRET_KEY` | 64 random characters – `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `DATABASE_URL` | from step 1 |
| `CORS_ORIGINS` | `["https://<your-web-domain>"]` |
| `FRONTEND_URL` | `https://<your-web-domain>` |
| `PUBLIC_API_URL` | `https://<your-api-domain>/api/v1` |
| `CRON_SECRET` | another long random string (Vercel Cron sends it automatically) |
| `ENABLE_SCHEDULER` | `false` (Vercel Cron runs the jobs instead) |
| `GROQ_API_KEY`, `GEMINI_API_KEY` | your AI keys |
| `DEMO_LOGIN_ENABLED` | `true` to offer "See a live demo gym" |
| optional | `RAZORPAY_*`, `RESEND_API_KEY` / `SMTP_*`, `TOKEN_ENCRYPTION_KEY`, `SENTRY_DSN`, WhatsApp, Google – see `gymflow-backend/.env.example` |

3. Deploy. Check `https://<api-domain>/health` returns `{"status":"ok"}`.
4. Create the tables (and optionally the demo gym) once:

```bash
curl -H "Authorization: Bearer $CRON_SECRET" "https://<api-domain>/api/v1/cron/setup"
# Demo data (admin + IronCore sample gym). Takes a while; if it times out, run it from your computer instead:
curl -H "Authorization: Bearer $CRON_SECRET" "https://<api-domain>/api/v1/cron/setup?seed=true"
#   or locally:  DATABASE_URL=<neon url> alembic upgrade head && DATABASE_URL=<neon url> python -m app.seed
```

`vercel.json` schedules `/api/v1/cron/daily` at 09:00 IST: expiries, overdue fees, renewal follow-ups, queued
messages, the monthly owner report (on the 1st) and the nightly demo reset. On Vercel Pro you can add
`/api/v1/cron/notifications` every few minutes for faster automatic WhatsApp delivery (the *Remind* buttons
work instantly regardless).

## 3. Web project (`gymflow-web`)

1. *Add New Project* → same repo → **Root Directory: `gymflow-frontend`** → Framework: Next.js.
2. Environment variables:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://<api-domain>/api/v1` |
| `API_URL_INTERNAL` | same as above |
| `NEXT_PUBLIC_APP_NAME` | `GymFlow` |
| `NEXT_PUBLIC_DEMO_LOGIN_ENABLED` | `true` (matches the API) |
| `NEXT_PUBLIC_PAYMENT_LINK` | `https://rzp.io/rzp/05mrQLg` (your Razorpay payment link for now) |
| optional | `NEXT_PUBLIC_SUPPORT_WHATSAPP`, `NEXT_PUBLIC_POSTHOG_KEY` |

3. Deploy, then put the web domain into the API's `CORS_ORIGINS` and `FRONTEND_URL` and redeploy the API.

## 4. Webhooks

| Service | URL |
|---|---|
| Razorpay | `https://<api-domain>/api/v1/payments/webhooks/razorpay` – events `payment.captured`, `payment.failed`, `payment_link.paid`, `subscription.*` |
| WhatsApp (Meta) | `https://<api-domain>/api/v1/webhooks/whatsapp` |
| Google OAuth redirect | `https://<api-domain>/api/v1/integrations/google/callback` |

## What is hidden in production

* API docs and schema (`/docs`, `/redoc`, `/openapi.json`) return 404.
* Unexpected errors return a generic message; details only go to the server logs (and Sentry if set).
* The browser gets minified code only – no source maps, no `X-Powered-By` header.
* `/cron/*` returns 404 without the secret.
* All API keys stay on the API project; the web project only has `NEXT_PUBLIC_*` values that are safe to be public.
