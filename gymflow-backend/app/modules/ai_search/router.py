"""AI Search / GPT visibility API and the Gym Profile (knowledge base / entity profile) API."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.core import entitlements
from app.core.entitlements import gym_feature
from app.core.permissions import GYM_STAFF, GYM_STAFF_AND_TRAINERS, tenant_user
from app.database.models import AiReadinessCheck, AiVisibilityQuery, AiVisibilityResult, GymProfile, User, Website
from app.database.models.enums import Role
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.ai_search import service
from app.modules.common import ORMModel, get_or_404
from app.modules.local_seo.service import ensure_profile
from app.services import content, events

router = APIRouter(prefix="/ai-search", tags=["AI search visibility"])
profile_router = APIRouter(prefix="/gym-profile", tags=["Gym profile & knowledge base"])
staff = gym_feature("ai_search_readiness", *GYM_STAFF)


# ---------------------------------------------------------------- gym profile

class Hours(BaseModel):
    days: str = Field(max_length=40)
    opens: str = Field(pattern=r"^\d{2}:\d{2}$")
    closes: str = Field(pattern=r"^\d{2}:\d{2}$")


class Faq(BaseModel):
    q: str = Field(min_length=3, max_length=300)
    a: str = Field(min_length=1, max_length=2000)
    approved: bool = False


class ProfileIn(BaseModel):
    business_name: str | None = Field(None, max_length=200)
    website_url: str | None = Field(None, max_length=500)
    description: str | None = Field(None, max_length=2000)
    address_line: str | None = Field(None, max_length=500)
    area: str | None = Field(None, max_length=120)
    city: str | None = Field(None, max_length=120)
    state: str | None = Field(None, max_length=120)
    postal_code: str | None = Field(None, max_length=16)
    phone: str | None = Field(None, max_length=32)
    whatsapp: str | None = Field(None, max_length=32)
    email: EmailStr | None = None
    opening_hours: list[Hours] | None = None
    services: list[str] | None = None
    facilities: list[str] | None = None
    service_areas: list[str] | None = None
    target_audience: list[str] | None = None
    social_profiles: dict[str, str] | None = None
    trial_offer: dict | None = None
    offers: list[dict] | None = None
    rules: str | None = Field(None, max_length=4000)
    faqs: list[Faq] | None = None
    review_url: str | None = Field(None, max_length=1000)


class ProfileOut(ORMModel):
    business_name: str | None
    website_url: str | None
    description: str | None
    address_line: str | None
    area: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str
    phone: str | None
    whatsapp: str | None
    email: str | None
    opening_hours: list
    services: list
    facilities: list
    service_areas: list
    target_audience: list
    social_profiles: dict
    trial_offer: dict
    offers: list
    rules: str | None
    faqs: list
    review_url: str | None
    approved_at: datetime | None
    updated_at: datetime


@profile_router.get("", response_model=ProfileOut)
def get_profile(db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    profile = ensure_profile(db)
    db.commit()
    return profile


@profile_router.put("", response_model=ProfileOut)
def put_profile(data: ProfileIn, db: Session = Depends(get_db), user: User = Depends(tenant_user(*GYM_STAFF))):
    profile = ensure_profile(db)
    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(profile, key, value)
    profile.approved_at = None  # edits need re-approval before the agent treats them as approved
    events.emit(db, "gym_profile.updated", entity_type="gym_profile", entity_id=profile.id, actor_user_id=user.id,
                payload={"fields": sorted(updates)})
    db.refresh(profile)
    return profile


@profile_router.post("/approve", response_model=ProfileOut)
def approve_profile(db: Session = Depends(get_db), user: User = Depends(tenant_user(Role.GYM_OWNER))):
    profile = ensure_profile(db)
    profile.approved_at, profile.approved_by_id = datetime.now(timezone.utc), user.id
    db.commit()
    return profile


@profile_router.post("/faqs/generate")
def generate_faqs(db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    entitlements.enforce_limit(db, "content_generations")
    faqs, by, warnings = content.generate_faqs(db)
    entitlements.record_usage(db, "content_generations")
    return {"faqs": faqs, "generated_by": by, "warnings": warnings,
            "note": "Drafts. Edit and approve each FAQ before the sales agent or website uses it."}


# ---------------------------------------------------------------- readiness

class CheckOut(ORMModel):
    id: uuid.UUID
    score: int
    checklist: list
    inconsistencies: list
    content_gaps: list
    audit_id: uuid.UUID | None
    created_at: datetime


@router.post("/readiness", response_model=CheckOut)
def run_readiness(db: Session = Depends(get_db), _=Depends(staff)):
    return service.readiness_audit(db)


@router.get("/readiness")
def readiness(db: Session = Depends(get_db), _=Depends(staff)):
    rows = TenantRepository(AiReadinessCheck, db).list(limit=12, order_by=AiReadinessCheck.created_at.desc())
    return {"latest": CheckOut.model_validate(rows[0]).model_dump(mode="json") if rows else None,
            "history": [{"score": r.score, "at": r.created_at.isoformat()} for r in reversed(rows)],
            "disclaimer": "GymFlow's own transparent checklist. It is not a Google, OpenAI or Perplexity score and "
                          "does not guarantee mentions in AI answers."}


# ---------------------------------------------------------------- structured data

class SchemaGenIn(BaseModel):
    kind: str = Field("local_business", pattern="^(local_business|organization|website|faq|services)$")


class SchemaIn(BaseModel):
    json_ld: dict | list | str


class SchemaPublishIn(BaseModel):
    website_id: uuid.UUID
    json_ld: list[dict]


@router.post("/schema/generate")
def gen_schema(data: SchemaGenIn, db: Session = Depends(get_db), _=Depends(staff)):
    schema = service.generate_schema(db, data.kind)
    return {"json_ld": schema, "validation": service.validate_schema(db, schema)}


@router.post("/schema/validate")
def val_schema(data: SchemaIn, db: Session = Depends(get_db), _=Depends(staff)):
    return service.validate_schema(db, data.json_ld)


@router.post("/schema/publish")
def publish_schema(data: SchemaPublishIn, db: Session = Depends(get_db),
                   user: User = Depends(gym_feature("ai_search_readiness", Role.GYM_OWNER))):
    result = service.validate_schema(db, data.json_ld)
    if not result["valid"]:
        raise HTTPException(422, {"message": "Fix the errors first", **result})
    site = get_or_404(TenantRepository(Website, db), data.website_id, "Website")
    site.seo = {**(site.seo or {}), "json_ld": data.json_ld}
    events.emit(db, "schema.published", entity_type="website", entity_id=site.id, actor_user_id=user.id,
                payload={"types": [str(o.get("@type")) for o in data.json_ld]})
    return {"published": True, "website_id": str(site.id), "note": "Live on your GymFlow site after you republish it."}


# ---------------------------------------------------------------- content studio

class StudioIn(BaseModel):
    kind: str
    topic: str | None = Field(None, max_length=200)


@router.post("/content")
def studio(data: StudioIn, db: Session = Depends(get_db), _=Depends(staff)):
    if data.kind not in content.STUDIO_KINDS and data.kind != "faqs":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown content type")
    entitlements.enforce_limit(db, "content_generations")
    if data.kind == "faqs":
        faqs, by, warnings = content.generate_faqs(db, data.topic)
        out = {"title": "FAQs", "faqs": faqs}
    else:
        out, by, warnings = content.studio(db, data.kind, data.topic)
    entitlements.record_usage(db, "content_generations")
    return {**out, "generated_by": by, "warnings": warnings, "status": "draft"}


@router.get("/content/types")
def studio_types(_=Depends(staff)):
    return {"faqs": "Structured FAQs from approved information", **content.STUDIO_KINDS}


# ---------------------------------------------------------------- monitoring

class QueryIn(BaseModel):
    question: str = Field(min_length=5, max_length=500)
    is_active: bool = True


class ResultIn(BaseModel):
    provider: str = Field(pattern="^(chatgpt|gemini|perplexity|copilot|google_ai_overview|claude|other)$")
    mentioned: bool
    position: int | None = Field(None, ge=1, le=50)
    citation_urls: list[str] = []
    competitors_mentioned: list[str] = []
    excerpt: str | None = Field(None, max_length=4000)
    observed_at: datetime | None = None


monitor = gym_feature("ai_search_monitoring", *GYM_STAFF)


@router.get("/visibility")
def visibility(db: Session = Depends(get_db), _=Depends(monitor)):
    return service.visibility_summary(db)


@router.post("/visibility/queries", status_code=status.HTTP_201_CREATED)
def add_query(data: QueryIn, db: Session = Depends(get_db), _=Depends(monitor)):
    q = TenantRepository(AiVisibilityQuery, db).create(**data.model_dump())
    return {"id": str(q.id), "question": q.question}


@router.delete("/visibility/queries/{query_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_query(query_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(monitor)):
    repo = TenantRepository(AiVisibilityQuery, db)
    repo.delete(get_or_404(repo, query_id, "Query"))


@router.post("/visibility/queries/{query_id}/results", status_code=status.HTTP_201_CREATED)
def add_result(query_id: uuid.UUID, data: ResultIn, db: Session = Depends(get_db), user: User = Depends(monitor)):
    get_or_404(TenantRepository(AiVisibilityQuery, db), query_id, "Query")
    r = TenantRepository(AiVisibilityResult, db).create(
        query_id=query_id, method="manual_research", recorded_by_id=user.id,
        **{**data.model_dump(), "observed_at": data.observed_at or datetime.now(timezone.utc)})
    return {"id": str(r.id), "method": r.method}
