"""AI Search / GPT visibility: readiness checklist, entity consistency, structured data, monitoring.

The readiness score is GymFlow's own transparent checklist. It is not a Google, OpenAI or Perplexity
score, and nothing here guarantees that an AI assistant will mention the gym.
"""
import json
import re
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_gym_id
from app.database.models import (
    AiReadinessCheck, AiVisibilityQuery, AiVisibilityResult, BusinessProfileSnapshot, Gym, GymProfile,
    MembershipPlan, SeoAudit, SeoPage, Trainer,
)
from app.database.models.enums import AuditStatus
from app.database.repositories.base import TenantRepository
from app.modules.crm.service import phone_key

LOCAL_TYPES = {"ExerciseGym", "SportsActivityLocation", "LocalBusiness", "HealthClub"}
ALLOWED_TYPES = LOCAL_TYPES | {"Organization", "WebSite", "WebPage", "BreadcrumbList", "Service", "FAQPage",
                               "Person", "Offer", "PostalAddress", "OpeningHoursSpecification", "GeoCoordinates",
                               "ListItem", "Question", "Answer", "ItemList", "Place", "ContactPoint"}
REQUIRED = {
    "ExerciseGym": ["name", "address"], "SportsActivityLocation": ["name", "address"],
    "LocalBusiness": ["name", "address"], "HealthClub": ["name", "address"], "Organization": ["name", "url"],
    "WebSite": ["name", "url"], "WebPage": ["name"], "BreadcrumbList": ["itemListElement"],
    "Service": ["name", "provider"], "FAQPage": ["mainEntity"],
}
FORBIDDEN = {"aggregateRating", "review", "reviews"}
DAY_MAP = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday",
           "sat": "Saturday", "sun": "Sunday"}
DAYS = list(DAY_MAP.values())


def _profile(db: Session) -> GymProfile | None:
    return TenantRepository(GymProfile, db).first()


def _latest_audit(db: Session) -> SeoAudit | None:
    return TenantRepository(SeoAudit, db).first(SeoAudit.status == AuditStatus.COMPLETED,
                                               order_by=SeoAudit.finished_at.desc())


def _contains(text: str, needle: str | None) -> bool:
    return bool(needle) and re.sub(r"\s+", " ", needle.lower()) in text


# ---------------------------------------------------------------- readiness

def readiness_audit(db: Session) -> AiReadinessCheck:
    gym = db.get(Gym, get_current_gym_id())
    profile = _profile(db)
    audit = _latest_audit(db)
    pages = TenantRepository(SeoPage, db).list(SeoPage.audit_id == audit.id, limit=200) if audit else []
    text = " ".join((p.text_excerpt or "") + " " + (p.title or "") for p in pages).lower()
    urls = " ".join(p.url.lower() for p in pages)
    schemas = [obj for p in pages for obj in (p.structured_data or [])]
    schema_types = {t for obj in schemas for t in _types(obj)}
    site_phones = {ph for p in pages for ph in (p.phones_found or [])}
    trainers = TenantRepository(Trainer, db).list(Trainer.is_active.is_(True), limit=50)
    plans = TenantRepository(MembershipPlan, db).list(MembershipPlan.is_active.is_(True), limit=20)
    name = (profile.business_name if profile else None) or gym.name
    checks: list[dict] = []

    def check(key, label, weight, passed, evidence, fix):
        checks.append({"key": key, "label": label, "weight": weight, "passed": bool(passed), "evidence": evidence,
                       "fix": None if passed else fix})

    no_site = "No completed website audit yet - run one in Website SEO."
    check("entity_profile", "Gym entity profile is complete", 10,
          profile and all([profile.business_name, profile.address_line, profile.phone, profile.opening_hours,
                           profile.services, profile.description]),
          "Profile fields filled: " + (", ".join(k for k in ("business_name", "address_line", "phone",
                                                             "opening_hours", "services", "description")
                                                 if profile and getattr(profile, k)) or "none"),
          "Complete the Gym Profile (name, address, phone, hours, services, description).")
    if not pages:
        for key, label in (("name_on_site", "Business name on website"), ("address_on_site", "Address on website"),
                           ("phone_on_site", "Phone on website"), ("services_on_site", "Services explained"),
                           ("structured_data", "Local business structured data"),
                           ("ai_crawlers", "AI crawlers allowed in robots.txt")):
            check(key, label, 8, False, no_site, "Run a website audit.")
    else:
        check("name_on_site", "Business name used consistently on the website", 10, _contains(text, name),
              f'"{name}" {"found" if _contains(text, name) else "not found"} in crawled page text.',
              "Use the exact business name in the site header, footer and title.")
        addr_bits = [b for b in [(profile.postal_code if profile else None), (profile.area if profile else None)] if b]
        found_addr = [b for b in addr_bits if b.lower() in text]
        check("address_on_site", "Address published on the website", 10, addr_bits and len(found_addr) == len(addr_bits),
              f"Looked for {addr_bits or 'area/postcode (not in profile)'}: found {found_addr or 'none'}.",
              "Show the full street address with area and PIN code in text on the contact page and footer.")
        prof_phone = phone_key(profile.phone) if profile else None
        check("phone_on_site", "Phone number on the website matches the profile", 10,
              prof_phone and prof_phone in site_phones,
              f"Profile phone {prof_phone or '-'}; numbers on site: {sorted(site_phones) or 'none'}.",
              "Show your main number as text on every page.")
        services = list(profile.services or []) if profile else []
        covered = [s for s in services if s.lower() in text]
        check("services_on_site", "Every service is described on the website", 10,
              services and len(covered) == len(services),
              f"{len(covered)}/{len(services)} services mentioned: missing {[s for s in services if s not in covered]}.",
              "Write a short section (or page) for each service.")
        loc = [x for x in [(profile.area if profile else None), (profile.city if profile else gym.city)] if x]
        check("location_on_site", "Neighbourhood and city mentioned", 8, loc and all(x.lower() in text for x in loc),
              f"Looked for {loc}.", "Mention the area and city naturally in page copy.")
        check("hours_on_site", "Opening hours published", 8, bool(re.search(r"\b\d{1,2}[:.]\d{2}\s*(am|pm)?\b", text)),
              "Time pattern " + ("found" if re.search(r"\b\d{1,2}[:.]\d{2}", text) else "not found") + " in page text.",
              "List timings for each day in text.")
        check("about_page", "About page", 6, "about" in urls, "Crawled URLs " + ("include" if "about" in urls else
                                                                                 "do not include") + " /about.",
              "Add an About page: story, owner/coaches, what makes the gym different.")
        tnames = [t.full_name for t in trainers]
        on_site = [t for t in tnames if t.lower() in text]
        check("trainers_on_site", "Trainer profiles", 6, bool(on_site),
              f"{len(on_site)}/{len(tnames)} trainers named on the site.",
              "Add trainer bios (experience, specialisation) - only real, verifiable details.")
        facilities = list(profile.facilities or []) if profile else []
        fac_found = [f for f in facilities if f.lower() in text]
        check("facilities_on_site", "Facilities described", 6, facilities and len(fac_found) >= max(1, len(facilities) // 2),
              f"{len(fac_found)}/{len(facilities)} facilities mentioned.", "Describe equipment and amenities.")
        priced = bool(re.search(r"(₹|rs\.?|inr)\s?\d", text))
        check("pricing_on_site", "Membership pricing published (if you choose to)", 5, priced or not plans,
              "Price pattern " + ("found" if priced else "not found") + " on the site.",
              "Publishing at least starting prices helps AI answers about cost.")
        has_faq = "faqpage" in {t.lower() for t in schema_types} or "frequently asked" in text or "faq" in urls
        check("faq_content", "FAQ content", 7, has_faq, "FAQ section/page " + ("found" if has_faq else "not found") + ".",
              "Publish answers to common questions (Content Studio can draft them).")
        check("structured_data", "Local business structured data", 8, bool(LOCAL_TYPES & schema_types),
              f"JSON-LD types found: {sorted(schema_types) or 'none'}.",
              "Add ExerciseGym JSON-LD (Structured Data Assistant).")
        crawlers = (audit.summary or {}).get("robots_txt", {}).get("ai_crawlers", {})
        blocked = [ua for ua, ok in crawlers.items() if not ok]
        check("ai_crawlers", "AI search crawlers allowed in robots.txt", 6, not blocked,
              f"Blocked: {blocked}" if blocked else "No AI crawler is blocked.",
              "Allow OAI-SearchBot / PerplexityBot etc. if you want to appear in their answers.")
    total = sum(c["weight"] for c in checks)
    score = round(100 * sum(c["weight"] for c in checks if c["passed"]) / total) if total else 0
    gaps = [{"key": c["key"], "label": c["label"], "fix": c["fix"]} for c in checks if not c["passed"]]
    row = TenantRepository(AiReadinessCheck, db).add(score=score, checklist=checks,
                                                     inconsistencies=entity_inconsistencies(db, pages, schemas),
                                                     content_gaps=gaps, audit_id=audit.id if audit else None,
                                                     created_at=datetime.now(timezone.utc))
    db.commit()
    return row


def _types(obj) -> list[str]:
    out = []
    if isinstance(obj, dict):
        t = obj.get("@type")
        out += [t] if isinstance(t, str) else [str(x) for x in t or []]
        for v in obj.values():
            if isinstance(v, (dict, list)):
                out += _types(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _types(v)
    return out


def entity_inconsistencies(db: Session, pages: list[SeoPage], schemas: list) -> list[dict]:
    """Compare the approved profile with what the website and Business Profile actually say."""
    profile = _profile(db)
    if profile is None:
        return []
    out = []
    pkey = phone_key(profile.phone)
    site_phones = sorted({ph for p in pages for ph in (p.phones_found or [])})
    if pkey and site_phones and pkey not in site_phones:
        out.append({"field": "phone", "profile": profile.phone, "other_source": "website", "value": site_phones})
    for obj in schemas:
        if not isinstance(obj, dict) or not (LOCAL_TYPES & set(_types(obj))):
            continue
        if obj.get("name") and profile.business_name and obj["name"].strip().lower() != profile.business_name.lower():
            out.append({"field": "name", "profile": profile.business_name, "other_source": "website JSON-LD",
                        "value": obj["name"]})
        if obj.get("telephone") and pkey and phone_key(str(obj["telephone"])) != pkey:
            out.append({"field": "phone", "profile": profile.phone, "other_source": "website JSON-LD",
                        "value": obj["telephone"]})
    snap = TenantRepository(BusinessProfileSnapshot, db).first(order_by=BusinessProfileSnapshot.fetched_at.desc())
    if snap:
        d = snap.data or {}
        if d.get("name") and profile.business_name and d["name"].strip().lower() != profile.business_name.lower():
            out.append({"field": "name", "profile": profile.business_name, "other_source": f"Business Profile ({snap.source})",
                        "value": d["name"]})
        if d.get("phone") and pkey and phone_key(d["phone"]) != pkey:
            out.append({"field": "phone", "profile": profile.phone, "other_source": f"Business Profile ({snap.source})",
                        "value": d["phone"]})
    return out


# ---------------------------------------------------------------- structured data

def _hours_spec(hours: list[dict]) -> list[dict]:
    specs = []
    for h in hours:
        days = _expand_days(h.get("days", ""))
        if days and h.get("opens") and h.get("closes"):
            specs.append({"@type": "OpeningHoursSpecification", "dayOfWeek": days, "opens": h["opens"],
                          "closes": h["closes"]})
    return specs


def _expand_days(text: str) -> list[str]:
    if "," in text:
        return [d for part in text.split(",") for d in _expand_days(part)]
    parts = [p.strip()[:3].lower() for p in re.split(r"\s*(?:-|–|\bto\b)\s*", text.lower()) if p.strip()]
    if len(parts) == 2 and parts[0] in DAY_MAP and parts[1] in DAY_MAP:
        a, b = DAYS.index(DAY_MAP[parts[0]]), DAYS.index(DAY_MAP[parts[1]])
        return DAYS[a:b + 1] if a <= b else DAYS[a:] + DAYS[:b + 1]
    return [DAY_MAP[p] for p in parts if p in DAY_MAP]


def generate_schema(db: Session, kind: str, page_url: str | None = None) -> dict:
    gym = db.get(Gym, get_current_gym_id())
    p = _profile(db)
    if p is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Fill in the Gym Profile first")
    url = p.website_url or page_url
    address = {"@type": "PostalAddress", "streetAddress": p.address_line, "addressLocality": p.city or gym.city,
               "addressRegion": p.state, "postalCode": p.postal_code, "addressCountry": p.country or "IN"}
    address = {k: v for k, v in address.items() if v}
    if kind == "local_business":
        data = {"@context": "https://schema.org", "@type": "ExerciseGym", "name": p.business_name or gym.name,
                "url": url, "telephone": p.phone, "email": p.email, "address": address,
                "description": p.description, "openingHoursSpecification": _hours_spec(p.opening_hours or []),
                "areaServed": [{"@type": "Place", "name": a} for a in (p.service_areas or [])] or None,
                "sameAs": [v for v in (p.social_profiles or {}).values() if v] or None,
                "amenityFeature": None, "priceRange": None}
        plans = TenantRepository(MembershipPlan, db).list(MembershipPlan.is_active.is_(True), limit=10)
        if plans:
            data["priceRange"] = f"{gym.currency} {min(float(x.price) for x in plans):,.0f}–{max(float(x.price) for x in plans):,.0f}"
    elif kind == "organization":
        data = {"@context": "https://schema.org", "@type": "Organization", "name": p.business_name or gym.name,
                "url": url, "logo": gym.logo_url, "sameAs": [v for v in (p.social_profiles or {}).values() if v] or None,
                "contactPoint": {"@type": "ContactPoint", "telephone": p.phone, "contactType": "customer service"}
                if p.phone else None}
    elif kind == "website":
        data = {"@context": "https://schema.org", "@type": "WebSite", "name": p.business_name or gym.name, "url": url}
    elif kind == "faq":
        faqs = [f for f in (p.faqs or []) if f.get("approved")]
        if not faqs:
            raise HTTPException(status.HTTP_409_CONFLICT, "Approve some FAQs in the Gym Profile first")
        data = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in faqs]}
    elif kind == "services":
        data = [{"@context": "https://schema.org", "@type": "Service", "name": s, "serviceType": s,
                 "provider": {"@type": "ExerciseGym", "name": p.business_name or gym.name},
                 "areaServed": p.city or gym.city} for s in (p.services or [])]
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown schema kind")
    return _prune(data)


def _prune(obj):
    if isinstance(obj, dict):
        return {k: _prune(v) for k, v in obj.items() if v not in (None, "", [], {})}
    if isinstance(obj, list):
        return [_prune(v) for v in obj]
    return obj


def validate_schema(db: Session, raw) -> dict:
    """Syntax + vocabulary + required properties + consistency with the profile. No ratings allowed."""
    errors, warnings = [], []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            return {"valid": False, "errors": [f"Invalid JSON: {exc}"], "warnings": []}
    items = raw if isinstance(raw, list) else [raw]
    profile = _profile(db)
    for i, obj in enumerate(items):
        where = f"item {i + 1}"
        if not isinstance(obj, dict):
            errors.append(f"{where}: must be a JSON object")
            continue
        if "schema.org" not in str(obj.get("@context", "")):
            errors.append(f'{where}: "@context" must be "https://schema.org"')
        t = obj.get("@type")
        types = [t] if isinstance(t, str) else list(t or [])
        if not types:
            errors.append(f'{where}: missing "@type"')
        for typ in types:
            if typ not in ALLOWED_TYPES:
                warnings.append(f"{where}: type {typ} is not one GymFlow generates; check it on validator.schema.org")
            for prop in REQUIRED.get(typ, []):
                if not obj.get(prop):
                    errors.append(f'{where}: {typ} needs "{prop}"')
        _forbidden(obj, where, errors)
        if "FAQPage" in types:
            warnings.append("Google shows FAQ rich results only for a few authoritative sites; the markup is still "
                            "valid structured Q&A. Only mark up FAQs that are visible on the page.")
            for q in obj.get("mainEntity") or []:
                if not (isinstance(q, dict) and q.get("@type") == "Question" and (q.get("acceptedAnswer") or {}).get("text")):
                    errors.append(f"{where}: every FAQ entry needs a Question with acceptedAnswer.text")
                    break
        if profile and LOCAL_TYPES & set(types):
            if obj.get("name") and profile.business_name and obj["name"] != profile.business_name:
                warnings.append(f'{where}: name "{obj["name"]}" differs from the Gym Profile "{profile.business_name}"')
            if obj.get("telephone") and profile.phone and phone_key(str(obj["telephone"])) != phone_key(profile.phone):
                warnings.append(f"{where}: telephone differs from the Gym Profile")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def _forbidden(obj, where, errors):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in FORBIDDEN:
                errors.append(f'{where}: "{key}" is not allowed - GymFlow never adds ratings/reviews to structured '
                              "data (self-serving review markup is against Google's guidelines).")
            _forbidden(value, where, errors)
    elif isinstance(obj, list):
        for v in obj:
            _forbidden(v, where, errors)


# ---------------------------------------------------------------- monitoring

def visibility_summary(db: Session) -> dict:
    queries = TenantRepository(AiVisibilityQuery, db).list(limit=100, order_by=AiVisibilityQuery.created_at)
    results = TenantRepository(AiVisibilityResult, db).list(limit=2000, order_by=AiVisibilityResult.observed_at.desc())
    by_query = defaultdict(list)
    for r in results:
        by_query[r.query_id].append(r)
    providers = defaultdict(lambda: {"runs": 0, "mentioned": 0})
    competitor_counts = defaultdict(int)
    for r in results:
        providers[r.provider]["runs"] += 1
        providers[r.provider]["mentioned"] += int(r.mentioned)
        for c in r.competitors_mentioned or []:
            competitor_counts[c] += 1
    return {
        "queries": [{"id": str(q.id), "question": q.question, "is_active": q.is_active,
                     "runs": len(by_query[q.id]), "mentioned": sum(r.mentioned for r in by_query[q.id]),
                     "last": _result_out(by_query[q.id][0]) if by_query[q.id] else None} for q in queries],
        "providers": {k: {**v, "mention_rate": round(v["mentioned"] / v["runs"], 2) if v["runs"] else None}
                      for k, v in providers.items()},
        "top_competitors": sorted(competitor_counts.items(), key=lambda kv: -kv[1])[:8],
        "sample_size": len(results),
        "limitations": "Each result is one sample: a live Google Search check by Gemini, or an answer your team "
                       "recorded. AI answers vary by person, place, wording and time, so treat these as spot checks, "
                       "not a ranking – they do not measure all answers.",
    }


def _result_out(r: AiVisibilityResult) -> dict:
    return {"id": str(r.id), "provider": r.provider, "method": r.method, "mentioned": r.mentioned,
            "position": r.position, "citation_urls": r.citation_urls, "competitors_mentioned": r.competitors_mentioned,
            "excerpt": r.excerpt, "observed_at": r.observed_at.isoformat()}


def find_mentions(db, text: str) -> dict:
    """Is the gym named in an AI answer, at which list position, and which tracked competitors appear?"""
    import re

    from app.database.models import Competitor, Gym
    from app.core.tenant_context import get_current_gym_id

    gym = db.get(Gym, get_current_gym_id())
    low = text.lower()
    name = gym.name.lower()
    mentioned = name in low
    position = None
    if mentioned:
        items = [ln for ln in text.splitlines() if re.match(r"^\s*(\d+[.)]|[-*•])\s+", ln)]
        for i, ln in enumerate(items, start=1):
            if name in ln.lower():
                position = i
                break
    competitors = [c.name for c in TenantRepository(Competitor, db).list(limit=100) if c.name.lower() in low]
    return {"mentioned": mentioned, "position": position, "competitors": competitors}
