"""Google Maps & local visibility: profile audit, reviews, review requests, posts, competitors."""
import io
import re
from datetime import datetime, timedelta, timezone

import segno
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_gym_id
from app.database.models import (
    BusinessProfileSnapshot, Competitor, Gym, GymProfile, Member, Review, ReviewRequest, User,
)
from app.database.models.enums import Channel, MemberStatus, ReplyStatus
from app.database.repositories.base import TenantRepository
from app.modules.crm.service import phone_key
from app.modules.integrations import google
from app.modules.notifications import service as notifications
from app.services import content, events

# Words that would turn a review request into an incentive (against Google's review policy).
INCENTIVE_RE = re.compile(r"\b(discount|free|gift|cashback|reward|coupon|voucher|offer|prize|paid|win)\b", re.I)

COMPLETENESS_FIELDS = [
    ("name", "Business name", 10), ("primary_category", "Primary category", 15), ("description", "Description", 10),
    ("address", "Address", 10), ("phone", "Phone number", 10), ("website", "Website", 10),
    ("hours", "Opening hours", 15), ("services", "Services", 10), ("additional_categories", "Extra categories", 5),
    ("review_count", "Reviews", 5),
]


def _digits(v: str | None) -> str:
    return phone_key(v) or ""


def _norm(v: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (v or "").lower())


def audit_profile(db: Session, data: dict, source: str) -> BusinessProfileSnapshot:
    """Audit Business Profile data (from the API, or typed in by the owner) against the approved gym profile."""
    profile = TenantRepository(GymProfile, db).first()
    findings: list[dict] = []

    def add(code, issue, priority, explanation, recommendation, suggestion=None):
        findings.append({"code": code, "issue": issue, "priority": priority, "explanation": explanation,
                         "recommendation": recommendation, "suggested_correction": suggestion,
                         "requires_approval": True, "basis": "observed" if suggestion is None else
                         "observed + suggestion"})

    earned, total = 0, sum(w for *_, w in COMPLETENESS_FIELDS)
    for key, label, weight in COMPLETENESS_FIELDS:
        value = data.get(key)
        if value not in (None, "", []):
            earned += weight
        elif value is None and key in ("review_count",) and source != "manual":
            pass
        else:
            add(f"missing_{key}", f"{label} is missing", "high" if weight >= 10 else "medium",
                f"The profile has no {label.lower()}.", f"Add the {label.lower()} in Business Profile.")
    desc = data.get("description") or ""
    if desc and len(desc) < 250:
        suggestion, _, _ = content.business_description(db)
        add("weak_description", "Description is short", "medium", f"Only {len(desc)} characters (up to 750 allowed).",
            "Describe services, facilities, area and who the gym is for.", suggestion)
    elif not desc:
        suggestion, _, _ = content.business_description(db)
        for f in findings:
            if f["code"] == "missing_description":
                f["suggested_correction"] = suggestion
    category = (data.get("primary_category") or "").lower()
    if category and not any(w in category for w in ("gym", "fitness", "health club", "personal trainer")):
        add("category_mismatch", "Primary category may not match a gym", "high",
            f'Primary category is "{data.get("primary_category")}".', 'Consider "Gym" or "Fitness center".', "Gym")
    if profile:
        if data.get("name") and profile.business_name and _norm(data["name"]) != _norm(profile.business_name):
            add("name_inconsistent", "Name differs from your website profile", "high",
                f'Profile: "{data["name"]}" vs GymFlow profile: "{profile.business_name}".',
                "Use the exact same business name everywhere (no extra keywords).", profile.business_name)
        if data.get("phone") and profile.phone and _digits(data["phone"]) != _digits(profile.phone):
            add("phone_inconsistent", "Phone number differs", "high",
                f"Profile: {data['phone']} vs GymFlow profile: {profile.phone}.", "Use one primary number.",
                profile.phone)
        if data.get("website") and profile.website_url and _norm(data["website"]).rstrip("/") != \
                _norm(profile.website_url).rstrip("/"):
            add("website_inconsistent", "Website link differs", "medium",
                f"Profile: {data['website']} vs GymFlow profile: {profile.website_url}.",
                "Point the profile at your main website (optionally with a tracking link).", profile.website_url)
        if profile.services and data.get("services") is not None:
            listed = {_norm(s) for s in data.get("services") or [] if s}
            missing = [s for s in profile.services if _norm(s) not in listed]
            if missing:
                add("services_missing", "Services not listed on the profile", "medium",
                    f"Not on profile: {', '.join(missing[:6])}.", "Add each service you offer.", ", ".join(missing))
    if data.get("hours") and not data.get("special_hours_count") and source != "manual":
        add("no_special_hours", "No special/holiday hours", "low", "No special hours are set.",
            "Add hours for Diwali, Uttarayan and other holidays so people don't arrive to a closed gym.")
    if data.get("review_count") is not None and data["review_count"] < 20:
        add("few_reviews", "Few reviews", "medium", f"{data['review_count']} reviews.",
            "Ask every member for an honest review (Review requests).")
    snapshot = TenantRepository(BusinessProfileSnapshot, db).add(
        source=source, data=data, completeness=round(earned * 100 / total), findings=findings)
    db.commit()
    return snapshot


def sync_from_google(db: Session) -> BusinessProfileSnapshot:
    try:
        location = google.fetch_location(db)
        reviews = google.fetch_reviews(db)
    except google.GoogleAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    data = google.normalize_location(location, reviews)
    upsert_reviews(db, reviews.get("reviews", []), source="google_business_profile")
    if data.get("new_review_uri"):
        profile = ensure_profile(db)
        profile.review_url = profile.review_url or data["new_review_uri"]
    snap = audit_profile(db, data, source="google_business_profile")
    conn = google.connection(db, "google_business_profile")
    conn.last_sync_at = datetime.now(timezone.utc)
    db.commit()
    return snap


def ensure_profile(db: Session) -> GymProfile:
    repo = TenantRepository(GymProfile, db)
    profile = repo.first()
    if profile is None:
        gym = db.get(Gym, get_current_gym_id())
        profile = repo.add(business_name=gym.name, city=gym.city, phone=gym.phone, email=gym.email,
                           address_line=gym.address, opening_hours=[], services=[], facilities=[], service_areas=[],
                           target_audience=[], social_profiles={}, trial_offer={"enabled": True, "price": 0,
                                                                                 "duration_minutes": 60},
                           offers=[], faqs=[])
    return profile


# ---------------------------------------------------------------- reviews

STAR = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


def sentiment_for(rating: int | None) -> str | None:
    if rating is None:
        return None
    return "positive" if rating >= 4 else "neutral" if rating == 3 else "negative"


def upsert_reviews(db: Session, items: list[dict], source: str) -> int:
    repo = TenantRepository(Review, db)
    count = 0
    for item in items:
        ext = item.get("reviewId") or item.get("name") or item.get("external_id")
        if not ext:
            continue
        rating = STAR.get(item.get("starRating")) if isinstance(item.get("starRating"), str) else item.get("rating")
        existing = repo.first(Review.source == source, Review.external_id == ext)
        when = item.get("createTime") or item.get("review_date")
        reply = (item.get("reviewReply") or {}).get("comment") or item.get("existing_reply")
        values = dict(author=(item.get("reviewer") or {}).get("displayName") or item.get("author"), rating=rating,
                      text=item.get("comment") or item.get("text"),
                      review_date=datetime.fromisoformat(when.replace("Z", "+00:00")) if isinstance(when, str) else when,
                      sentiment=sentiment_for(rating), sentiment_basis="rating", existing_reply=reply)
        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
            if reply and existing.reply_status in (ReplyStatus.NONE, ReplyStatus.DRAFTED):
                existing.reply_status = ReplyStatus.PUBLISHED
        else:
            repo.add(source=source, external_id=ext, reply_status=ReplyStatus.PUBLISHED if reply else ReplyStatus.NONE,
                     **values)
            count += 1
    db.flush()
    return count


def draft_reply(db: Session, review: Review) -> Review:
    text, by = content.review_reply(db, author=review.author, rating=review.rating, text=review.text)
    review.draft_reply, review.draft_generated_by = text, by
    if review.reply_status == ReplyStatus.NONE:
        review.reply_status = ReplyStatus.DRAFTED
    db.commit()
    return review


def approve_reply(db: Session, review: Review, user: User, text: str, publish: bool) -> dict:
    """Owner approves. Publishing goes through the official API when connected; otherwise copy-ready text."""
    if not text.strip():
        raise HTTPException(422, "Reply text is empty")
    review.draft_reply = text.strip()
    review.approved_by_id = user.id
    review.reply_status = ReplyStatus.APPROVED
    result = {"published": False, "copy_ready": review.draft_reply}
    if publish:
        if review.source != "google_business_profile":
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "This review was not synced from Google, so it can't be replied to through the API. "
                                "Copy the reply and post it yourself.")
        try:
            google.reply_to_review(db, review.external_id, review.draft_reply)
        except google.GoogleAPIError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Google rejected the reply: {exc}")
        review.reply_status, review.replied_at = ReplyStatus.PUBLISHED, datetime.now(timezone.utc)
        review.existing_reply = review.draft_reply
        result = {"published": True, "copy_ready": None}
    events.emit(db, "review.reply_approved", entity_type="review", entity_id=review.id, actor_user_id=user.id,
                payload={"published": result["published"], "rating": review.rating})
    return result


def mark_copied(db: Session, review: Review, user: User) -> Review:
    review.reply_status, review.replied_at = ReplyStatus.COPIED, datetime.now(timezone.utc)
    review.existing_reply = review.draft_reply
    review.approved_by_id = user.id
    db.commit()
    return review


# ---------------------------------------------------------------- review requests

def review_link(db: Session) -> str | None:
    profile = TenantRepository(GymProfile, db).first()
    return profile.review_url if profile and profile.review_url else None


def qr_svg(url: str) -> str:
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=6, border=2, dark="#111827")
    return buf.getvalue().decode()


def validate_request_message(message: str) -> None:
    if INCENTIVE_RE.search(message):
        raise HTTPException(422,
                            "Review requests can't mention discounts, freebies or rewards - offering incentives for "
                            "reviews breaks Google's policy.")
    if "{link}" not in message:
        raise HTTPException(422, "The message must include {link}")


DEFAULT_REQUEST = ("Hi {name}, thank you for training with {gym}. If you have a minute, we'd appreciate an honest "
                   "review on Google - good or bad, it helps us improve: {link}")


def send_review_requests(db: Session, user: User, message: str, member_ids: list | None,
                         all_active: bool) -> dict:
    """Same request to everyone selected - never filtered by satisfaction (no review gating)."""
    link = review_link(db)
    if not link:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Add your Google review link first (Business Profile → 'Ask for reviews', or connect "
                            "Google Business Profile).")
    validate_request_message(message)
    gym = db.get(Gym, get_current_gym_id())
    members_repo = TenantRepository(Member, db)
    if all_active:
        members = members_repo.list(Member.status == MemberStatus.ACTIVE, limit=5000)
    elif member_ids:
        members = members_repo.list(Member.id.in_(member_ids), limit=len(member_ids))
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose members or all active members")
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    repo = TenantRepository(ReviewRequest, db)
    sent = skipped = 0
    for m in members:
        if repo.first(ReviewRequest.member_id == m.id, ReviewRequest.created_at >= recent_cutoff):
            skipped += 1  # don't nag the same person more than once a quarter
            continue
        text = message.replace("{name}", m.full_name.split()[0]).replace("{gym}", gym.name).replace("{link}", link)
        n = notifications.enqueue(db, m, Channel.WHATSAPP, text, category="review_request",
                                  dedup_key=f"review_request:{m.id}:{datetime.now(timezone.utc):%Y-%m}")
        repo.add(member_id=m.id, channel="whatsapp", message=text, review_url=link,
                 status="queued" if n else "failed", notification_id=n.id if n else None,
                 remind_after=datetime.now(timezone.utc) + timedelta(days=5))
        sent += 1 if n else 0
    db.commit()
    events.emit(db, "review.requests_sent", actor_user_id=user.id, payload={"queued": sent, "skipped": skipped})
    return {"queued": sent, "skipped_recently_asked": skipped, "review_url": link}


# ---------------------------------------------------------------- competitors

def competitor_report(db: Session) -> dict:
    """Compare only what we actually know. Every competitor value is user-supplied unless labelled."""
    snap = TenantRepository(BusinessProfileSnapshot, db).first(order_by=BusinessProfileSnapshot.fetched_at.desc())
    profile = TenantRepository(GymProfile, db).first()
    reviews = TenantRepository(Review, db)
    ours = {
        "name": (profile.business_name if profile else None) or db.get(Gym, get_current_gym_id()).name,
        "rating": (snap.data.get("rating") if snap else None),
        "review_count": (snap.data.get("review_count") if snap else None) or reviews.count() or None,
        "reviews_last_90_days": reviews.count(Review.review_date >= datetime.now(timezone.utc) - timedelta(days=90)),
        "services": list(profile.services or []) if profile else [],
        "categories": [c for c in [snap.data.get("primary_category") if snap else None,
                                   *((snap.data.get("additional_categories") or []) if snap else [])] if c],
        "profile_completeness": snap.completeness if snap else None,
        "source": snap.source if snap else "not available",
    }
    rows, opportunities = [], []
    for c in TenantRepository(Competitor, db).list(limit=50, order_by=Competitor.name):
        rows.append({"id": str(c.id), "name": c.name, "rating": c.rating, "review_count": c.review_count,
                     "reviews_last_90_days": c.reviews_last_90_days, "services": c.services,
                     "categories": c.categories, "area": c.area, "distance_km": c.distance_km,
                     "website": c.website, "source": c.source,
                     "observed_at": c.observed_at.isoformat() if c.observed_at else None})
        if c.review_count and ours["review_count"] is not None and c.review_count > ours["review_count"]:
            opportunities.append(f"{c.name} shows {c.review_count} reviews vs your {ours['review_count']} "
                                 "(user-supplied figure). Ask every member for an honest review.")
        missing = [s for s in (c.services or []) if _norm(s) not in {_norm(x) for x in ours["services"]}]
        if missing:
            opportunities.append(f"{c.name} lists services you don't: {', '.join(missing[:4])}. "
                                 "Add them to your profile if you offer them.")
        if c.categories and ours["categories"]:
            extra = [x for x in c.categories if _norm(x) not in {_norm(y) for y in ours["categories"]}]
            if extra:
                opportunities.append(f"{c.name} uses categories {', '.join(extra[:3])}; check whether they apply to you.")
    return {"ours": ours, "competitors": rows, "opportunities": opportunities,
            "note": "Rankings and map-pack positions are not measured. Competitor figures are as entered by you."}
