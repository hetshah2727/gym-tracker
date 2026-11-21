"""Google Maps SEO & local visibility API."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.entitlements import gym_feature
from app.core.permissions import GYM_STAFF
from app.database.models import BusinessProfileSnapshot, Competitor, Review, ReviewRequest, SeoKeyword, User
from app.database.models.enums import ReplyStatus, Role
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.common import ORMModel, get_or_404
from app.modules.growth import metrics
from app.modules.integrations import google
from app.modules.local_seo import service
from app.services import content, events

router = APIRouter(prefix="/local", tags=["Google Maps & local SEO"])
staff = gym_feature("local_seo", *GYM_STAFF)
owner = gym_feature("local_seo", Role.GYM_OWNER)


class ReviewOut(ORMModel):
    id: uuid.UUID
    source: str
    external_id: str
    author: str | None
    rating: int | None
    text: str | None
    review_date: datetime | None
    sentiment: str | None
    sentiment_basis: str | None
    reply_status: ReplyStatus
    existing_reply: str | None
    draft_reply: str | None
    draft_generated_by: str | None
    replied_at: datetime | None


class ManualReviewIn(BaseModel):
    author: str | None = Field(None, max_length=200)
    rating: int = Field(ge=1, le=5)
    text: str | None = Field(None, max_length=4000)
    review_date: datetime | None = None


class ApproveIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    publish: bool = False


class ManualProfileIn(BaseModel):
    name: str | None = None
    primary_category: str | None = None
    additional_categories: list[str] = []
    description: str | None = Field(None, max_length=750)
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    hours: list[dict] = []
    services: list[str] = []
    review_count: int | None = Field(None, ge=0)
    rating: float | None = Field(None, ge=1, le=5)


class RequestIn(BaseModel):
    message: str = Field(service.DEFAULT_REQUEST, max_length=1000)
    member_ids: list[uuid.UUID] | None = None
    all_active_members: bool = False


class ReviewLinkIn(BaseModel):
    review_url: str = Field(min_length=10, max_length=1000, pattern=r"^https://")


class CompetitorIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    website: str | None = None
    maps_url: str | None = None
    area: str | None = None
    distance_km: float | None = Field(None, ge=0)
    categories: list[str] = []
    services: list[str] = []
    description: str | None = None
    rating: float | None = Field(None, ge=1, le=5)
    review_count: int | None = Field(None, ge=0)
    reviews_last_90_days: int | None = Field(None, ge=0)
    price_notes: str | None = None
    notes: str | None = None


class CompetitorOut(CompetitorIn, ORMModel):
    id: uuid.UUID
    source: str
    observed_at: datetime | None


class PostDraftIn(BaseModel):
    kind: str = Field("update", pattern="^(update|offer|event|service)$")
    details: str | None = Field(None, max_length=500)


class PostPublishIn(BaseModel):
    text: str = Field(min_length=10, max_length=1500)
    call_to_action: str | None = Field(None, pattern="^(BOOK|CALL|LEARN_MORE|SIGN_UP)$")
    url: str | None = None


@router.get("/overview")
def overview(db: Session = Depends(get_db), _=Depends(staff)):
    acq = metrics.acquisition(db, *metrics.month_range())
    snaps = TenantRepository(BusinessProfileSnapshot, db).list(limit=12, order_by=BusinessProfileSnapshot.fetched_at.desc())
    reviews = TenantRepository(Review, db).list(limit=2000)
    by_month: dict = {}
    for r in reviews:
        if r.review_date:
            key = r.review_date.strftime("%Y-%m")
            by_month[key] = by_month.get(key, 0) + 1
    rated = [r.rating for r in reviews if r.rating]
    return {
        **acq["google_business_profile"],
        "configured": google.is_configured(),
        "latest_audit": {"id": str(snaps[0].id), "source": snaps[0].source, "completeness": snaps[0].completeness,
                         "findings": snaps[0].findings, "data": snaps[0].data,
                         "fetched_at": snaps[0].fetched_at.isoformat()} if snaps else None,
        "completeness_history": [{"at": s.fetched_at.isoformat(), "completeness": s.completeness, "source": s.source}
                                 for s in reversed(snaps)],
        "reviews": {"total_recorded": len(reviews), "average_recorded_rating": round(sum(rated) / len(rated), 2)
                    if rated else None, "by_month": dict(sorted(by_month.items())),
                    "sentiment": {k: sum(1 for r in reviews if r.sentiment == k) for k in ("positive", "neutral", "negative")}},
        "website_enquiries_this_month": acq["website_enquiries"],
        "gbp_tracked_enquiries_this_month": acq["lead_sources"].get("google_business_profile", 0),
        "engagement_metrics": "Unavailable: Business Profile performance metrics are not connected.",
        "review_url": service.review_link(db),
    }


@router.post("/profile-audit/manual")
def manual_audit(data: ManualProfileIn, db: Session = Depends(get_db), _=Depends(staff)):
    snap = service.audit_profile(db, data.model_dump(), source="manual")
    return {"id": str(snap.id), "completeness": snap.completeness, "findings": snap.findings, "source": snap.source}


@router.post("/profile-audit/sync")
def sync_audit(db: Session = Depends(get_db), _=Depends(staff)):
    snap = service.sync_from_google(db)
    return {"id": str(snap.id), "completeness": snap.completeness, "findings": snap.findings, "source": snap.source}


@router.post("/profile/description")
def description(db: Session = Depends(get_db), _=Depends(staff)):
    text, by, warnings = content.business_description(db)
    return {"text": text, "generated_by": by, "warnings": warnings}


# ---------------------------------------------------------------- reviews

@router.get("/reviews", response_model=list[ReviewOut])
def list_reviews(reply_status: ReplyStatus | None = None, sentiment: str | None = None,
                 db: Session = Depends(get_db), _=Depends(staff)):
    f = []
    if reply_status:
        f.append(Review.reply_status == reply_status)
    if sentiment:
        f.append(Review.sentiment == sentiment)
    return TenantRepository(Review, db).list(*f, limit=500, order_by=Review.review_date.desc())


@router.post("/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def add_review(data: ManualReviewIn, db: Session = Depends(get_db), _=Depends(staff)):
    """Record a review by hand (e.g. copied from Google while the API isn't connected)."""
    return TenantRepository(Review, db).create(
        source="manual", external_id=uuid.uuid4().hex, author=data.author, rating=data.rating, text=data.text,
        review_date=data.review_date or datetime.now(timezone.utc), sentiment=service.sentiment_for(data.rating),
        sentiment_basis="rating", reply_status=ReplyStatus.NONE)


@router.post("/reviews/sync")
def sync_reviews(db: Session = Depends(get_db), _=Depends(staff)):
    try:
        data = google.fetch_reviews(db, page_size=50)
    except google.GoogleAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    new = service.upsert_reviews(db, data.get("reviews", []), "google_business_profile")
    db.commit()
    return {"new": new, "total_on_google": data.get("totalReviewCount"), "average_rating": data.get("averageRating")}


@router.post("/reviews/{review_id}/draft", response_model=ReviewOut)
def draft(review_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    return service.draft_reply(db, get_or_404(TenantRepository(Review, db), review_id, "Review"))


@router.post("/reviews/{review_id}/approve")
def approve(review_id: uuid.UUID, data: ApproveIn, db: Session = Depends(get_db), user: User = Depends(owner)):
    return service.approve_reply(db, get_or_404(TenantRepository(Review, db), review_id, "Review"), user, data.text,
                                 data.publish)


@router.post("/reviews/{review_id}/copied", response_model=ReviewOut)
def copied(review_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(staff)):
    return service.mark_copied(db, get_or_404(TenantRepository(Review, db), review_id, "Review"), user)


# ---------------------------------------------------------------- review requests

@router.put("/review-link")
def set_review_link(data: ReviewLinkIn, db: Session = Depends(get_db), _=Depends(staff)):
    profile = service.ensure_profile(db)
    profile.review_url = data.review_url
    db.commit()
    return {"review_url": profile.review_url}


@router.get("/review-qr.svg")
def review_qr(db: Session = Depends(get_db), _=Depends(staff)):
    link = service.review_link(db)
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No review link set")
    return Response(service.qr_svg(link), media_type="image/svg+xml")


@router.post("/review-requests")
def send_requests(data: RequestIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    return service.send_review_requests(db, user, data.message, data.member_ids, data.all_active_members)


@router.get("/review-requests")
def list_requests(db: Session = Depends(get_db), _=Depends(staff)):
    rows = TenantRepository(ReviewRequest, db).list(limit=500)
    return {"total": len(rows), "queued_or_sent": sum(1 for r in rows if r.status in ("queued", "sent")),
            "items": [{"id": str(r.id), "member_id": str(r.member_id) if r.member_id else None, "status": r.status,
                       "created_at": r.created_at.isoformat(), "remind_after": r.remind_after.isoformat()
                       if r.remind_after else None} for r in rows[:200]],
            "policy": "Every selected member gets the same request; GymFlow never filters by satisfaction or offers "
                      "incentives for reviews."}


# ---------------------------------------------------------------- posts

@router.post("/posts/draft")
def draft_post(data: PostDraftIn, db: Session = Depends(get_db), _=Depends(staff)):
    post, by, warnings = content.profile_post(db, data.kind, data.details)
    return {**post, "generated_by": by, "warnings": warnings}


class PostImageIn(BaseModel):
    text: str = Field(min_length=3, max_length=1500)
    style: str | None = Field(None, max_length=200)


@router.post("/posts/image")
def post_image(data: PostImageIn, db: Session = Depends(get_db), _=Depends(staff)):
    """Gemini image for a Google / Instagram post. Returned as a data URL for the owner to download and use."""
    from app.core import entitlements as ent
    from app.integrations.ai import gemini

    if not gemini.is_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Image creation isn't switched on yet")
    ent.enforce_limit(db, "content_generations")
    facts = content.load_facts(db)
    prompt = (f"A bright, realistic, high-quality square photo for a social media post by {facts.gym}, an Indian gym"
              f"{' in ' + facts.city if facts.city else ''}. Post: \"{data.text}\". "
              f"{'Style: ' + data.style + '. ' if data.style else ''}"
              "Show a modern gym with real-looking people training. No text, no logos, no watermarks, "
              "no before/after body comparisons.")
    try:
        img = gemini.image(prompt)
    except gemini.AIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    ent.record_usage(db, "content_generations")
    return {"image": img.data_url, "mime_type": img.mime_type, "generated_by": "gemini"}


@router.post("/posts/publish")
def publish_post(data: PostPublishIn, db: Session = Depends(get_db), user: User = Depends(owner)):
    try:
        result = google.create_local_post(db, data.text, data.call_to_action, data.url)
    except google.GoogleAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    events.emit(db, "gbp.post_published", actor_user_id=user.id, payload={"name": result.get("name")})
    return {"published": True, "name": result.get("name")}


# ---------------------------------------------------------------- competitors & keywords

@router.get("/competitors", response_model=list[CompetitorOut])
def list_competitors(db: Session = Depends(get_db), _=Depends(staff)):
    return TenantRepository(Competitor, db).list(limit=100, order_by=Competitor.name)


@router.post("/competitors", response_model=CompetitorOut, status_code=status.HTTP_201_CREATED)
def add_competitor(data: CompetitorIn, db: Session = Depends(get_db), _=Depends(staff)):
    return TenantRepository(Competitor, db).create(**data.model_dump(), source="user_supplied",
                                                   observed_at=datetime.now(timezone.utc))


@router.patch("/competitors/{competitor_id}", response_model=CompetitorOut)
def update_competitor(competitor_id: uuid.UUID, data: CompetitorIn, db: Session = Depends(get_db), _=Depends(staff)):
    repo = TenantRepository(Competitor, db)
    return repo.update(get_or_404(repo, competitor_id, "Competitor"),
                       {**data.model_dump(), "observed_at": datetime.now(timezone.utc)})


@router.delete("/competitors/{competitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_competitor(competitor_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    repo = TenantRepository(Competitor, db)
    repo.delete(get_or_404(repo, competitor_id, "Competitor"))


@router.get("/competitors/report")
def competitor_report(db: Session = Depends(get_db), _=Depends(staff)):
    return service.competitor_report(db)


@router.get("/keywords")
def local_keywords(location: str | None = Query(None), db: Session = Depends(get_db), _=Depends(staff)):
    f = [SeoKeyword.intent.in_(["local", "transactional", "commercial"])]
    if location:
        f.append(SeoKeyword.location == location)
    rows = TenantRepository(SeoKeyword, db).list(*f, limit=500, order_by=SeoKeyword.keyword)
    return {"keywords": [{"id": str(k.id), "keyword": k.keyword, "location": k.location, "category": k.category,
                          "source": k.source, "metrics_verified": k.metrics_verified} for k in rows],
            "note": "Suggestions based on your profile. No map-pack rankings or search volumes are claimed."}
