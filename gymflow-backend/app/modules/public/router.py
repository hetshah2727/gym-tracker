"""Public endpoints used by GymFlow-hosted gym websites: landing pages, chat, trial booking, sitemap."""
import re
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.agents import runtime
from app.core import entitlements, rate_limit
from app.core.config import settings
from app.core.tenant_context import tenant_scope
from app.database.models import Gym, LandingPage
from app.database.models.enums import ContentStatus
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.crm import service as crm
from app.modules.trials import service as trials
from app.modules.website_builder.router import _published_site, _render_payload, public_router

router = public_router  # same /public/sites prefix


class Attribution(BaseModel):
    utm_source: str | None = Field(None, max_length=100)
    utm_medium: str | None = Field(None, max_length=100)
    utm_campaign: str | None = Field(None, max_length=100)
    utm_content: str | None = Field(None, max_length=100)
    referrer: str | None = Field(None, max_length=1000)
    landing_page: str | None = Field(None, max_length=160)

    def utm(self) -> dict:
        return {k: getattr(self, k) for k in ("utm_source", "utm_medium", "utm_campaign", "utm_content")}


class ChatIn(Attribution):
    session_id: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    message: str = Field(min_length=1, max_length=1000)


class PublicTrialIn(Attribution):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=10, max_length=20)
    email: EmailStr | None = None
    starts_at: datetime
    fitness_interest: str | None = Field(None, max_length=120)
    whatsapp_opt_in: bool = False
    website: str | None = Field(None, description="Honeypot")


@router.get("/{slug}/pages/{page_slug}")
def landing_page(slug: str, page_slug: str, db: Session = Depends(get_db)):
    site = _published_site(db, slug=slug)
    with tenant_scope(site.gym_id):
        page = TenantRepository(LandingPage, db).first(LandingPage.slug == page_slug, LandingPage.website_id == site.id,
                                                      LandingPage.status == ContentStatus.PUBLISHED)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Page not found")
    payload = _render_payload(db, site)
    payload["page"] = {"slug": page.slug, "service": page.service, "area": page.area, "seo_title": page.seo_title,
                       "meta_description": page.meta_description, "h1": page.h1, "content": page.content,
                       "json_ld": page.json_ld}
    return payload


def _gym_with(db: Session, slug: str, feature: str):
    site = _published_site(db, slug=slug)
    if not entitlements.resolve(db, site.gym_id).has(feature):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not available")
    return site


@router.get("/{slug}/trial-slots", dependencies=[Depends(rate_limit.public_limit("public_slots", 30))])
def trial_slots(slug: str, db: Session = Depends(get_db)):
    site = _gym_with(db, slug, "trials")
    with tenant_scope(site.gym_id):
        gym = db.get(Gym, site.gym_id)
        if not trials.config(gym).get("public_booking", True):
            return {"enabled": False, "slots": []}
        tz = trials._tz(gym)
        slots = trials.available_slots(db, date.today(), 7)
    return {"enabled": True, "timezone": str(tz), "slots": [
        {"starts_at": s["starts_at"].isoformat(), "label": s["starts_at"].astimezone(tz).strftime("%a %d %b, %I:%M %p")}
        for s in slots[:60]]}


@router.post("/{slug}/trials", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit.public_limit("public_trial", 5))])
def book_trial(slug: str, data: PublicTrialIn, db: Session = Depends(get_db)):
    if data.website:
        return {"booked": True}
    site = _gym_with(db, slug, "trials")
    with tenant_scope(site.gym_id):
        gym = db.get(Gym, site.gym_id)
        if not trials.config(gym).get("public_booking", True):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Online trial booking is off")
        attribution = crm.attribute(db, declared_source=None, utm=data.utm(), referrer=data.referrer,
                                    landing_page_slug=data.landing_page)
        lead, _ = crm.capture_lead(db, crm.LeadInput(
            name=data.name, phone=data.phone, email=data.email, fitness_interest=data.fitness_interest,
            wants_trial=True, whatsapp_opt_in=data.whatsapp_opt_in, website_id=site.id), attribution, actor="public")
        trial = trials.book(db, lead, data.starts_at, source="website", actor="public")
        when = trials._fmt_local(gym, trial.starts_at)
    return {"booked": True, "when": when, "message": f"Your trial at {gym.name} is booked for {when}."}


@router.post("/{slug}/chat", dependencies=[Depends(rate_limit.public_limit("public_chat", 20))])
def chat(slug: str, data: ChatIn, db: Session = Depends(get_db)):
    site = _published_site(db, slug=slug)
    if not entitlements.resolve(db, site.gym_id).has("ai_sales_agent"):
        return {"reply": None, "status": "disabled"}
    with tenant_scope(site.gym_id):
        conv = runtime.get_or_create_conversation(db, agent_key="lead_conversion", channel="website_chat",
                                                  external_ref=f"web:{data.session_id}")
        if not conv.state:
            conv.state = {"utm": {k: v for k, v in data.utm().items() if v}, "referrer": data.referrer,
                          "landing_page": data.landing_page}
            db.commit()
        reply = runtime.run_agent(db, agent_key="lead_conversion", message=data.message, channel="website_chat",
                                  conversation=conv)
    return {"reply": reply.text, "status": reply.status}


@router.get("/{slug}/sitemap.xml")
def sitemap(slug: str, db: Session = Depends(get_db)):
    site = _published_site(db, slug=slug)
    base = f"{settings.FRONTEND_URL.rstrip('/')}/sites/{site.slug}"
    with tenant_scope(site.gym_id):
        pages = TenantRepository(LandingPage, db).list(LandingPage.website_id == site.id,
                                                      LandingPage.status == ContentStatus.PUBLISHED, limit=500)
    urls = [(base, site.published_at)] + [(f"{base}/{p.slug}", p.published_at) for p in pages]
    body = "".join(f"<url><loc>{_xml(u)}</loc>" + (f"<lastmod>{d.date().isoformat()}</lastmod>" if d else "")
                   + "</url>" for u, d in urls)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    return Response(xml, media_type="application/xml")


def _xml(value: str) -> str:
    return re.sub(r"[<>&'\"]", lambda m: {"<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;"}[m.group()],
                  value)


__all__ = ["router", "timezone"]
