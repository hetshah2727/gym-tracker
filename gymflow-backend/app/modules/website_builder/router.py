import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import GYM_STAFF, tenant_user
from app.core.tenant_context import get_current_gym_id, tenant_scope
from app.database.models import Gym, Lead, MembershipPlan, Trainer, Website
from app.database.models.enums import LeadStatus
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.core import rate_limit
from app.database.models import LandingPage
from app.database.models.enums import ContentStatus
from app.modules.crm import service as crm
from app.modules.common import ORMModel, get_or_404, slugify, unique_slug
from app.modules.website_builder.templates import BLOCK_TYPES, TEMPLATES, default_blocks

router = APIRouter(prefix="/websites", tags=["Website builder"])
public_router = APIRouter(prefix="/public/sites", tags=["Public gym sites"])
leads_router = APIRouter(prefix="/leads", tags=["Leads"])


class WebsiteCreate(BaseModel):
    name: str
    template: str = "classic"
    slug: str | None = None


class WebsiteUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    template: str | None = None
    theme: dict | None = None
    blocks: list[dict] | None = None
    seo: dict | None = None
    custom_domain: str | None = None

    @field_validator("blocks")
    @classmethod
    def known_block_types(cls, blocks):
        for block in blocks or []:
            if block.get("type") not in BLOCK_TYPES:
                raise ValueError(f"Unknown block type: {block.get('type')}")
        return blocks


class WebsiteOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    template: str
    theme: dict
    blocks: list
    seo: dict
    custom_domain: str | None
    is_published: bool
    published_at: datetime | None
    updated_at: datetime


class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(None, max_length=32)
    email: EmailStr | None = None
    message: str | None = Field(None, max_length=2000)
    # Qualification (optional) - no health information is collected.
    fitness_interest: str | None = Field(None, max_length=120)
    interested_plan_id: uuid.UUID | None = None
    preferred_joining_date: date | None = None
    wants_trial: bool = False
    whatsapp_opt_in: bool = False
    # Attribution evidence captured by the page (only what the browser actually saw).
    utm_source: str | None = Field(None, max_length=100)
    utm_medium: str | None = Field(None, max_length=100)
    utm_campaign: str | None = Field(None, max_length=100)
    utm_content: str | None = Field(None, max_length=100)
    referrer: str | None = Field(None, max_length=1000)
    landing_page: str | None = Field(None, max_length=160)
    website: str | None = Field(None, max_length=200, description="Honeypot - must stay empty")


class LeadOut(ORMModel):
    id: uuid.UUID
    website_id: uuid.UUID | None
    name: str
    phone: str | None
    email: str | None
    message: str | None
    source: str
    status: LeadStatus
    created_at: datetime


def _slug_taken(db: Session, slug: str, exclude: uuid.UUID | None = None) -> bool:
    stmt = select(Website.id).where(Website.slug == slug)
    if exclude:
        stmt = stmt.where(Website.id != exclude)
    return db.scalar(stmt) is not None


# ---- Editor API ----

@router.get("/templates")
def list_templates(_=Depends(tenant_user(*GYM_STAFF))):
    return {"templates": TEMPLATES, "block_types": BLOCK_TYPES}


@router.get("", response_model=list[WebsiteOut])
def list_sites(db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    return TenantRepository(Website, db).list(limit=50)


@router.post("", response_model=WebsiteOut, status_code=status.HTTP_201_CREATED)
def create_site(data: WebsiteCreate, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    if data.template not in TEMPLATES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown template")
    gym = db.get(Gym, get_current_gym_id())
    slug = unique_slug(data.slug or gym.slug, lambda s: _slug_taken(db, s))
    return TenantRepository(Website, db).create(
        name=data.name, slug=slug, template=data.template, theme=TEMPLATES[data.template]["theme"],
        blocks=default_blocks(gym), seo={"title": gym.name, "description": f"{gym.name} - gym in {gym.city or ''}"},
    )


@router.get("/{site_id}", response_model=WebsiteOut)
def get_site(site_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    return get_or_404(TenantRepository(Website, db), site_id, "Website")


@router.put("/{site_id}", response_model=WebsiteOut)
def save_site(site_id: uuid.UUID, data: WebsiteUpdate, db: Session = Depends(get_db),
              _=Depends(tenant_user(*GYM_STAFF))):
    """Save the editor's draft. Visitors keep seeing the last published version."""
    repo = TenantRepository(Website, db)
    site = get_or_404(repo, site_id, "Website")
    updates = data.model_dump(exclude_unset=True)
    if "slug" in updates:
        updates["slug"] = slugify(updates["slug"])
        if _slug_taken(db, updates["slug"], exclude=site.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "That site address is taken")
    if updates.get("custom_domain"):
        updates["custom_domain"] = updates["custom_domain"].lower().strip()
        taken = db.scalar(select(Website.id).where(Website.custom_domain == updates["custom_domain"],
                                                   Website.id != site.id))
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, "That domain is already connected to another site")
    return repo.update(site, updates)


@router.post("/{site_id}/publish", response_model=WebsiteOut)
def publish(site_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    repo = TenantRepository(Website, db)
    site = get_or_404(repo, site_id, "Website")
    return repo.update(site, {"is_published": True, "published_blocks": list(site.blocks),
                              "published_at": datetime.now(timezone.utc)})


@router.post("/{site_id}/unpublish", response_model=WebsiteOut)
def unpublish(site_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    repo = TenantRepository(Website, db)
    return repo.update(get_or_404(repo, site_id, "Website"), {"is_published": False})


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_site(site_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    repo = TenantRepository(Website, db)
    repo.delete(get_or_404(repo, site_id, "Website"))


# ---- Public site rendering & lead capture ----

def _published_site(db: Session, slug: str | None = None, domain: str | None = None) -> Website:
    stmt = select(Website).where(Website.is_published.is_(True))
    stmt = stmt.where(Website.slug == slug) if slug else stmt.where(Website.custom_domain == domain)
    site = db.scalar(stmt)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    gym = db.get(Gym, site.gym_id)
    if not gym or not gym.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
    return site


def _render_payload(db: Session, site: Website) -> dict:
    gym = db.get(Gym, site.gym_id)
    with tenant_scope(site.gym_id):
        plans = TenantRepository(MembershipPlan, db).list(MembershipPlan.is_active.is_(True),
                                                         order_by=MembershipPlan.duration_days)
        trainers = TenantRepository(Trainer, db).list(Trainer.is_active.is_(True), order_by=Trainer.full_name)
    with tenant_scope(site.gym_id):
        pages = TenantRepository(LandingPage, db).list(LandingPage.website_id == site.id,
                                                      LandingPage.status == ContentStatus.PUBLISHED, limit=100)
    return {
        "site": {"name": site.name, "slug": site.slug, "template": site.template, "theme": site.theme,
                 "seo": site.seo, "blocks": site.published_blocks},
        "landing_pages": [{"slug": p.slug, "title": p.h1} for p in pages],
        "gym": {"name": gym.name, "phone": gym.phone, "email": gym.email, "address": gym.address,
                "city": gym.city, "logo_url": gym.logo_url, "currency": gym.currency},
        "plans": [{"id": str(p.id), "name": p.name, "duration_days": p.duration_days, "price": float(p.price),
                   "description": p.description} for p in plans],
        "trainers": [{"id": str(t.id), "name": t.full_name, "specialization": t.specialization,
                      "bio": t.bio, "photo_url": t.photo_url} for t in trainers],
    }


@public_router.get("/by-domain")
def get_site_by_domain(domain: str = Query(...), db: Session = Depends(get_db)):
    return _render_payload(db, _published_site(db, domain=domain.lower()))


@public_router.get("/{slug}")
def get_public_site(slug: str, db: Session = Depends(get_db)):
    return _render_payload(db, _published_site(db, slug=slug))


@public_router.post("/{slug}/leads", status_code=status.HTTP_201_CREATED,
                   dependencies=[Depends(rate_limit.public_limit("public_lead", 10))])
def submit_lead(slug: str, data: LeadIn, db: Session = Depends(get_db)):
    """Workflow 1: enquiry -> validate -> duplicate check -> lead -> attribution -> score -> task -> notify."""
    if data.website:  # honeypot filled in: a bot. Pretend success, store nothing.
        return {"detail": "Thanks! The gym will contact you shortly."}
    if not data.phone and not data.email:
        raise HTTPException(422, "Phone or email is required")
    site = _published_site(db, slug=slug)
    with tenant_scope(site.gym_id):
        attribution = crm.attribute(
            db, declared_source=None, referrer=data.referrer, landing_page_slug=data.landing_page,
            utm={k: getattr(data, k) for k in ("utm_source", "utm_medium", "utm_campaign", "utm_content")})
        crm.capture_lead(db, crm.LeadInput(
            name=data.name, phone=data.phone, email=data.email, message=data.message,
            fitness_interest=data.fitness_interest, interested_plan_id=data.interested_plan_id,
            preferred_joining_date=data.preferred_joining_date, wants_trial=data.wants_trial,
            whatsapp_opt_in=data.whatsapp_opt_in, website_id=site.id), attribution, actor="public")
    return {"detail": "Thanks! The gym will contact you shortly."}


# ---- Leads inbox ----

@leads_router.get("", response_model=list[LeadOut])
def list_leads(status_: LeadStatus | None = Query(None, alias="status"), db: Session = Depends(get_db),
               _=Depends(tenant_user(*GYM_STAFF))):
    filters = [Lead.status == status_] if status_ else []
    return TenantRepository(Lead, db).list(*filters, limit=1000)


@leads_router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: uuid.UUID, new_status: LeadStatus, lost_reason: str | None = None,
                db: Session = Depends(get_db), user=Depends(tenant_user(*GYM_STAFF))):
    """Legacy endpoint (kept for compatibility); uses the same validated pipeline rules as /crm."""
    lead = get_or_404(TenantRepository(Lead, db), lead_id, "Lead")
    crm.change_status(db, lead, new_status, user, lost_reason=lost_reason or ("Not specified" if new_status ==
                                                                              LeadStatus.LOST else None))
    db.refresh(lead)
    return lead
