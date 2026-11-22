import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings

if settings.SENTRY_DSN:  # optional error monitoring; only when the DSN is set and sentry-sdk is installed
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.SENTRY_DSN, environment=settings.ENVIRONMENT, traces_sample_rate=0.05,
                        send_default_pii=False)
    except ImportError:
        logging.getLogger(__name__).warning("SENTRY_DSN is set but sentry-sdk is not installed")
from app.core.tenant_context import TenantNotSetError
from app.modules.affiliate.router import router as affiliate_router
from app.modules.analytics.router import router as analytics_router
from app.modules.attendance.router import router as attendance_router
from app.modules.authentication.router import router as auth_router
from app.modules.automation.router import router as automation_router
from app.modules.diet_plans.router import router as diet_router
from app.modules.gyms.router import router as gym_router
from app.modules.members.portal import router as portal_router
from app.modules.members.router import router as members_router
from app.modules.memberships.router import plans_router, router as memberships_router
from app.modules.notifications.router import router as notifications_router
from app.modules.payments.router import router as payments_router
from app.modules.subscriptions.router import router as subscriptions_router
from app.modules.support.router import router as support_router
from app.modules.tenants.router import router as tenants_router
from app.modules.trainers.router import router as trainers_router
from app.modules.users.router import router as users_router
from app.modules.website_builder.router import leads_router, public_router, router as websites_router
from app.modules.public.router import router as _public_extras  # noqa: F401  (adds chat/trials/pages to public_router)
from app.modules.ai_agents.router import router as ai_router
from app.modules.ai_search.router import profile_router, router as ai_search_router
from app.modules.crm.router import router as crm_router
from app.modules.growth.router import router as growth_router
from app.modules.integrations.router import router as integrations_router
from app.modules.integrations.whatsapp_webhook import router as whatsapp_webhook_router
from app.modules.local_seo.router import router as local_router
from app.modules.recovery.router import router as recovery_router
from app.modules.seo.router import router as seo_router
from app.modules.trials.router import router as trials_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = None
    if settings.ENABLE_SCHEDULER:
        from app.workers.scheduler import create_scheduler

        scheduler = create_scheduler()
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.APP_NAME, version="1.0.0", lifespan=lifespan,
              description="GymFlow - AI-powered gym revenue growth engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(TenantNotSetError)
async def tenant_not_set(_: Request, exc: TenantNotSetError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


for r in (
    auth_router, tenants_router, gym_router, users_router, members_router, portal_router, trainers_router,
    plans_router, memberships_router, payments_router, attendance_router, automation_router,
    notifications_router, diet_router, affiliate_router, websites_router, public_router, leads_router,
    analytics_router, subscriptions_router, support_router,
    growth_router, crm_router, trials_router, recovery_router, seo_router, local_router, ai_search_router,
    profile_router, ai_router, integrations_router, whatsapp_webhook_router,
):
    app.include_router(r, prefix=settings.API_PREFIX)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "app": settings.APP_NAME}
