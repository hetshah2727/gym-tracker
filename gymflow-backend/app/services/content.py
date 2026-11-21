"""Content generation (SEO copy, FAQs, landing pages, review replies, profile posts) + claims guard.

Everything is built from the owner-approved GymProfile and live plans/trainers. With Claude configured
the copy is written by the model (``generated_by="ai"``); without it a deterministic template is used
(``generated_by="template"``). Either way the claims guard flags unsupported or risky statements, and
nothing is published until the owner approves it.
"""
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_gym_id
from app.database.models import Gym, GymProfile, MembershipPlan, Trainer
from app.database.repositories.base import TenantRepository
from app.integrations.ai import claude

# Phrases we never let through silently: superlatives we can't prove, guarantees, health/medical claims.
CLAIM_PATTERNS = [
    (r"\b(best|top[- ]rated|no\.? ?1|number one|#1|leading|most trusted)\b", "Unverifiable superlative"),
    (r"\bguarantee[ds]?\b|\b100 ?%", "Guarantee / absolute claim"),
    (r"\b(lose|drop|burn)\s+\d+\s*(kg|kgs|kilos|pounds|lbs)\b", "Specific weight-loss promise"),
    (r"\bin (just )?\d+ (days|weeks)\b", "Time-bound result promise"),
    (r"\b(cure|cures|treat|treats|heal|heals|reverse|reverses)\b", "Medical claim"),
    (r"\b(diabetes|thyroid|pcos|pcod|blood pressure|hypertension|arthritis|depression)\b",
     "Health condition mentioned - needs professional review"),
    (r"\b(doctor|clinically|scientifically)[- ](approved|proven|recommended)\b", "Unsupported endorsement"),
    (r"\b(certified|award[- ]winning)\b", "Credential claim - confirm it is true"),
]


def check_claims(text: str, allowed: set[str] | None = None) -> list[str]:
    """Return human-readable warnings for risky phrases (``allowed`` = phrases the owner has verified)."""
    warnings = []
    lowered = (text or "").lower()
    for pattern, label in CLAIM_PATTERNS:
        for match in re.finditer(pattern, lowered):
            phrase = match.group(0)
            if allowed and phrase in allowed:
                continue
            warnings.append(f'{label}: "{phrase}"')
    return sorted(set(warnings))


@dataclass
class Facts:
    gym: str
    area: str | None
    city: str | None
    phone: str | None
    address: str | None
    website: str | None
    description: str | None
    services: list[str]
    facilities: list[str]
    service_areas: list[str]
    hours: list[dict]
    trial: dict
    plans: list[dict]
    trainers: list[dict]
    faqs: list[dict]
    currency: str = "INR"
    offers: list = field(default_factory=list)

    def as_prompt(self) -> str:
        hours = "; ".join(f"{h.get('days')}: {h.get('opens')}-{h.get('closes')}" for h in self.hours) or "not provided"
        plans = "; ".join(f"{p['name']} {self.currency} {p['price']:,.0f} ({p['days']} days)" for p in self.plans)
        trainers = "; ".join(f"{t['name']} ({t['specialization'] or 'trainer'})" for t in self.trainers)
        return (f"Gym: {self.gym}\nArea: {self.area or '-'}, City: {self.city or '-'}\nAddress: {self.address or '-'}\n"
                f"Phone: {self.phone or '-'}\nWebsite: {self.website or '-'}\nDescription: {self.description or '-'}\n"
                f"Services: {', '.join(self.services) or '-'}\nFacilities: {', '.join(self.facilities) or '-'}\n"
                f"Service areas: {', '.join(self.service_areas) or '-'}\nHours: {hours}\n"
                f"Trial offer: {self.trial if self.trial.get('enabled') else 'none'}\nPlans: {plans or '-'}\n"
                f"Trainers: {trainers or '-'}\nOffers: {self.offers or 'none'}")


def load_facts(db: Session) -> Facts:
    gym = db.get(Gym, get_current_gym_id())
    profile = TenantRepository(GymProfile, db).first() or GymProfile()
    plans = TenantRepository(MembershipPlan, db).list(MembershipPlan.is_active.is_(True),
                                                      order_by=MembershipPlan.duration_days)
    trainers = TenantRepository(Trainer, db).list(Trainer.is_active.is_(True), order_by=Trainer.full_name)
    return Facts(
        gym=profile.business_name or gym.name, area=profile.area, city=profile.city or gym.city,
        phone=profile.phone or gym.phone, address=profile.address_line or gym.address, website=profile.website_url,
        description=profile.description, services=list(profile.services or []),
        facilities=list(profile.facilities or []), service_areas=list(profile.service_areas or []),
        hours=list(profile.opening_hours or []), trial=dict(profile.trial_offer or {}),
        plans=[{"name": p.name, "price": float(p.price), "days": p.duration_days} for p in plans],
        trainers=[{"name": t.full_name, "specialization": t.specialization} for t in trainers],
        faqs=[f for f in (profile.faqs or []) if f.get("approved")], currency=gym.currency,
        offers=list(profile.offers or []),
    )


SYSTEM = """You write marketing and SEO copy for an independent gym in India, inside the GymFlow app.
Rules (strict):
- Use ONLY the facts provided. Never invent prices, offers, facilities, awards, certifications, ratings or results.
- If a fact is missing, leave it out rather than guessing.
- No superlatives you cannot prove ("best", "No.1"), no guarantees, no weight-loss or medical promises.
- Write plainly for local people; British/Indian English spelling; no keyword stuffing.
The owner reviews everything before it is published."""


def _ai_or_template(schema: type[BaseModel], prompt: str, template_fn) -> tuple[BaseModel, str]:
    if claude.is_configured():
        try:
            result, _usage = claude.parse(SYSTEM, prompt, schema, effort="low")
            return result, "ai"
        except claude.AIError:
            pass  # fall back to the deterministic template
    return template_fn(), "template"


def _join(items: list[str], n: int = 3) -> str:
    items = [i for i in items if i][:n]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut.rstrip(",;:-") + "…"


# ---------------------------------------------------------------- page meta

class MetaSuggestion(BaseModel):
    title: str = Field(description="SEO title, max 60 characters")
    meta_description: str = Field(description="Meta description, 140-160 characters")
    h1: str = Field(description="Single H1 heading")
    reason: str = Field(description="One sentence: why this is better for local search")


def page_meta(db: Session, *, page_url: str, current_title: str | None, current_description: str | None,
              page_topic: str | None = None) -> tuple[MetaSuggestion, str, list[str]]:
    f = load_facts(db)
    place = ", ".join(x for x in (f.area, f.city) if x)
    topic = page_topic or (f.services[0] if f.services else "Gym & fitness centre")

    def template() -> MetaSuggestion:
        title = _clip(f"{topic} in {place} | {f.gym}" if place else f"{topic} | {f.gym}", 60)
        trial = " Book a free trial." if f.trial.get("enabled") and not f.trial.get("price") else ""
        desc = _clip(f"{f.gym} offers {_join(f.services) or 'gym training'} in {place or 'your area'}."
                     f"{trial}" + (f" Call {f.phone}." if f.phone else ""), 158)
        return MetaSuggestion(title=title, meta_description=desc, h1=_clip(f"{topic} in {place or f.gym}", 70),
                              reason="Puts the service and neighbourhood people search for at the start, "
                                     "adds a clear call to action, and stays within display limits.")

    prompt = (f"{f.as_prompt()}\n\nPage: {page_url}\nTopic: {topic}\nCurrent title: {current_title or '(none)'}\n"
              f"Current meta description: {current_description or '(none)'}\nWrite an improved title, meta "
              "description and H1 for local search.")
    result, by = _ai_or_template(MetaSuggestion, prompt, template)
    warnings = check_claims(" ".join([result.title, result.meta_description, result.h1]))
    return result, by, warnings


def alt_text(facts: Facts, image_src: str) -> str:
    name = re.sub(r"[-_]+", " ", image_src.rsplit("/", 1)[-1].rsplit(".", 1)[0]).strip()
    name = re.sub(r"\b(img|image|dsc|photo|pic)\s*\d*\b", "", name, flags=re.I).strip()
    place = facts.area or facts.city or ""
    subject = name if len(name) > 3 and not name.isdigit() else "Training area"
    return _clip(f"{subject.capitalize()} at {facts.gym}" + (f", {place}" if place else ""), 120)


# ---------------------------------------------------------------- FAQs

class FaqItem(BaseModel):
    q: str
    a: str


class FaqSet(BaseModel):
    faqs: list[FaqItem]


def generate_faqs(db: Session, topic: str | None = None) -> tuple[list[dict], str, list[str]]:
    f = load_facts(db)

    def template() -> FaqSet:
        items = []
        if f.hours:
            items.append(FaqItem(q=f"What are {f.gym}'s timings?",
                                 a="; ".join(f"{h['days']}: {h['opens']}–{h['closes']}" for h in f.hours) + "."))
        if f.plans:
            items.append(FaqItem(q="How much does a membership cost?",
                                 a="Current plans: " + "; ".join(f"{p['name']} – {f.currency} {p['price']:,.0f}"
                                                                for p in f.plans) + "."))
        if f.trial.get("enabled"):
            price = f.trial.get("price") or 0
            items.append(FaqItem(q="Can I try the gym before joining?",
                                 a=("Yes, we offer a free trial session." if not price else
                                    f"Yes, a trial session costs {f.currency} {price}.")
                                 + " Book it online or call us."))
        if f.services:
            items.append(FaqItem(q="Do you offer personal training?",
                                 a=("Yes. " if any("personal" in s.lower() for s in f.services) else "")
                                 + f"Our services include {_join(f.services, 6)}."))
        if f.facilities:
            items.append(FaqItem(q="What facilities are available?", a=f"{_join(f.facilities, 8)}."))
        if f.address:
            items.append(FaqItem(q=f"Where is {f.gym} located?",
                                 a=f"{f.address}." + (f" Call {f.phone} for directions." if f.phone else "")))
        return FaqSet(faqs=items)

    prompt = f"{f.as_prompt()}\n\nWrite 5-8 FAQs a prospective member would ask" + (
        f" about {topic}" if topic else "") + ". Answer only from the facts."
    result, by = _ai_or_template(FaqSet, prompt, template)
    faqs = [{"q": i.q, "a": i.a, "approved": False} for i in result.faqs]
    return faqs, by, check_claims(" ".join(i["q"] + " " + i["a"] for i in faqs))


# ---------------------------------------------------------------- landing pages

class LandingSection(BaseModel):
    heading: str
    body: str


class LandingDraft(BaseModel):
    seo_title: str
    meta_description: str
    h1: str
    intro: str
    sections: list[LandingSection]
    faqs: list[FaqItem]
    cta: str


def landing_page(db: Session, service: str, area: str) -> tuple[LandingDraft, str, list[str]]:
    f = load_facts(db)
    city = f.city or ""

    def template() -> LandingDraft:
        trainers = [t for t in f.trainers if service.split()[0].lower() in (t["specialization"] or "").lower()] \
            or f.trainers
        sections = [LandingSection(heading=f"{service} at {f.gym}",
                                   body=(f.description or f"{f.gym} is a gym serving {area}{', ' + city if city else ''}.")
                                   + f" We offer {service.lower()} with guidance from our coaches.")]
        if f.facilities:
            sections.append(LandingSection(heading="Facilities", body=f"{_join(f.facilities, 10)}."))
        if trainers:
            sections.append(LandingSection(heading="Coaches", body="; ".join(
                f"{t['name']}" + (f" – {t['specialization']}" if t["specialization"] else "") for t in trainers[:4]) + "."))
        if f.hours:
            sections.append(LandingSection(heading="Timings", body="; ".join(
                f"{h['days']}: {h['opens']}–{h['closes']}" for h in f.hours) + "."))
        if f.plans:
            sections.append(LandingSection(heading="Membership plans", body="; ".join(
                f"{p['name']}: {f.currency} {p['price']:,.0f}" for p in f.plans) + "."))
        if f.address:
            sections.append(LandingSection(heading=f"Getting here from {area}",
                                           body=f"We are at {f.address}." + (f" Call {f.phone}." if f.phone else "")))
        faqs = [FaqItem(q=x["q"], a=x["a"]) for x in generate_faqs(db)[0][:4]] if not claude.is_configured() else []
        return LandingDraft(
            seo_title=_clip(f"{service} in {area}, {city} | {f.gym}" if city else f"{service} in {area} | {f.gym}", 60),
            meta_description=_clip(f"{service} near {area}{', ' + city if city else ''} at {f.gym}. "
                                   + ("Book a free trial session. " if f.trial.get("enabled") else "")
                                   + (f"Call {f.phone}." if f.phone else ""), 158),
            h1=f"{service} in {area}" + (f", {city}" if city else ""),
            intro=f"Looking for {service.lower()} near {area}? {f.gym} is close by"
                  + (f" at {f.address}" if f.address else "") + ".",
            sections=sections, faqs=faqs,
            cta="Book a free trial" if f.trial.get("enabled") else "Enquire now")

    prompt = (f"{f.as_prompt()}\n\nWrite a genuinely useful local landing page for '{service}' for people in "
              f"'{area}'. Explain practical details (what is included, coaches, timings, plans, how to reach from "
              f"{area}). 4-6 sections, 3-5 FAQs. Do not repeat the area name unnaturally.")
    result, by = _ai_or_template(LandingDraft, prompt, template)
    text = " ".join([result.seo_title, result.meta_description, result.h1, result.intro]
                    + [s.heading + " " + s.body for s in result.sections] + [q.q + " " + q.a for q in result.faqs])
    return result, by, check_claims(text)


# ---------------------------------------------------------------- reviews & profile posts

class ReplyDraft(BaseModel):
    reply: str


def review_reply(db: Session, *, author: str | None, rating: int | None, text: str | None) -> tuple[str, str]:
    f = load_facts(db)
    first = (author or "").split(" ")[0] or "there"

    def template() -> ReplyDraft:
        if rating is not None and rating >= 4:
            body = f"Thank you {first} for the kind words! We're glad you enjoy training at {f.gym}. See you soon."
        elif rating == 3:
            body = (f"Thanks for the feedback, {first}. We'd love to know what would make your experience better – "
                    f"please speak to us at the front desk" + (f" or call {f.phone}." if f.phone else "."))
        else:
            body = (f"Hi {first}, we're sorry to hear about your experience. This isn't the standard we aim for. "
                    "Please contact us" + (f" on {f.phone}" if f.phone else "") + " so we can understand and fix it.")
        return ReplyDraft(reply=body)

    prompt = (f"Gym: {f.gym}. Phone: {f.phone or '-'}.\nReview by {author or 'a customer'} ({rating}/5): "
              f"\"{text or ''}\"\nWrite a short, sincere public reply (max 60 words). Do not offer discounts or "
              "gifts, do not argue, do not reveal private details, invite offline contact for complaints.")
    result, by = _ai_or_template(ReplyDraft, prompt, template)
    return result.reply, by


class PostDraft(BaseModel):
    text: str = Field(description="Google Business Profile post, max 1500 characters")
    call_to_action: str = Field(description="One of BOOK, CALL, LEARN_MORE, SIGN_UP")


def profile_post(db: Session, kind: str, details: str | None) -> tuple[dict, str, list[str]]:
    f = load_facts(db)

    def template() -> PostDraft:
        base = {
            "update": f"New at {f.gym}: {details or 'fresh training programmes this month'}.",
            "offer": f"{details or 'Ask us about our current membership plans'} at {f.gym}.",
            "event": f"Join us at {f.gym}: {details or 'community workout this weekend'}.",
            "service": f"{details or (f.services[0] if f.services else 'Personal training')} at {f.gym}"
                       + (f", {f.area}" if f.area else "") + ".",
        }.get(kind, details or f"News from {f.gym}.")
        tail = " Book a free trial today." if f.trial.get("enabled") else " Call us to know more."
        return PostDraft(text=_clip(base + tail, 1500), call_to_action="BOOK" if f.trial.get("enabled") else "CALL")

    prompt = f"{f.as_prompt()}\n\nWrite a Google Business Profile '{kind}' post. Details from the owner: {details or '-'}"
    result, by = _ai_or_template(PostDraft, prompt, template)
    return {"text": result.text, "call_to_action": result.call_to_action}, by, check_claims(result.text)


def business_description(db: Session) -> tuple[str, str, list[str]]:
    f = load_facts(db)

    def template() -> ReplyDraft:
        place = ", ".join(x for x in (f.area, f.city) if x)
        text = (f"{f.gym} is a gym{' in ' + place if place else ''} offering {_join(f.services, 5) or 'fitness training'}."
                + (f" Facilities include {_join(f.facilities, 6)}." if f.facilities else "")
                + (f" Open {f.hours[0]['days']} {f.hours[0]['opens']}–{f.hours[0]['closes']}." if f.hours else "")
                + (" Free trial sessions available." if f.trial.get("enabled") and not f.trial.get("price") else ""))
        return ReplyDraft(reply=_clip(text, 750))

    prompt = f"{f.as_prompt()}\n\nWrite a Google Business Profile description (max 750 characters, no URLs)."
    result, by = _ai_or_template(ReplyDraft, prompt, template)
    return result.reply, by, check_claims(result.reply)


# ---------------------------------------------------------------- AI search content studio

STUDIO_KINDS = {
    "service_explanation": "Explain one service: who it is for, what a session includes, coaches, timings, price.",
    "trainer_profile": "A factual trainer profile using only the trainer's listed specialisation.",
    "facility_description": "Describe the facilities and equipment that are listed.",
    "location_content": "Explain where the gym is and how to reach it from the given area.",
    "membership_explanation": "Explain the membership plans, what they include and how to join.",
    "comparison_page": "Help someone choose between the gym's own plans/services (never compare to named competitors).",
    "fitness_guide": "A practical, general beginner's guide related to the topic (no medical advice).",
}


class StudioDraft(BaseModel):
    title: str
    body_markdown: str


def studio(db: Session, kind: str, topic: str | None) -> tuple[dict, str, list[str]]:
    if kind not in STUDIO_KINDS:
        raise ValueError("Unknown content type")
    f = load_facts(db)

    def template() -> StudioDraft:
        place = ", ".join(x for x in (f.area, f.city) if x)
        if kind == "trainer_profile":
            t = next((t for t in f.trainers if topic and topic.lower() in t["name"].lower()), f.trainers[0] if f.trainers else None)
            body = (f"**{t['name']}** coaches at {f.gym}" + (f" and focuses on {t['specialization']}" if t and t["specialization"] else "")
                    + ".\n\n_Add verified experience and qualifications before publishing._") if t else "No trainers listed yet."
            return StudioDraft(title=f"{t['name'] if t else 'Trainer'} – {f.gym}", body_markdown=body)
        if kind == "membership_explanation":
            rows = "\n".join(f"| {p['name']} | {p['days']} days | {f.currency} {p['price']:,.0f} |" for p in f.plans)
            return StudioDraft(title=f"Membership plans at {f.gym}", body_markdown=(
                "| Plan | Duration | Price |\n|---|---|---|\n" + rows + "\n\n"
                + ("You can book a free trial before joining. " if f.trial.get("enabled") else "")
                + (f"Call {f.phone} or visit us at {f.address}." if f.phone else "")))
        if kind == "facility_description":
            return StudioDraft(title=f"Facilities at {f.gym}", body_markdown="\n".join(f"- {x}" for x in f.facilities)
                               or "No facilities listed yet.")
        if kind == "location_content":
            return StudioDraft(title=f"How to reach {f.gym}" + (f" from {topic}" if topic else ""), body_markdown=(
                f"{f.gym} is at {f.address or place}." + (f" We serve {_join(f.service_areas, 6)}." if f.service_areas else "")
                + "\n\n_Add landmarks and travel times you have verified._"))
        subject = topic or (f.services[0] if f.services else "Training")
        return StudioDraft(title=f"{subject} at {f.gym}", body_markdown=(
            f"{f.gym}{' in ' + place if place else ''} offers {subject.lower()}.\n\n"
            + (f"**Coaches:** {', '.join(t['name'] for t in f.trainers[:4])}\n\n" if f.trainers else "")
            + ("**Timings:** " + "; ".join(f"{h['days']} {h['opens']}–{h['closes']}" for h in f.hours) + "\n\n" if f.hours else "")
            + "_Template draft – expand with real details before publishing._"))

    prompt = f"{f.as_prompt()}\n\nContent type: {kind} – {STUDIO_KINDS[kind]}\nTopic: {topic or '-'}\nWrite it in markdown."
    result, by = _ai_or_template(StudioDraft, prompt, template)
    return {"title": result.title, "body_markdown": result.body_markdown}, by, check_claims(result.body_markdown)
