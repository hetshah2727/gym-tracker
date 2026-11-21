"""IronCore Fitness - an isolated, reconciling demo tenant (Gotri, Vadodara).

    python -m app.demo.ironcore            # create if missing
    python -m app.demo.ironcore --reset    # delete and rebuild the demo tenant only

Every number shown in the product is derived from these records: revenue = paid payments, active
members = members with a current membership, recovered revenue = WON opportunities each linked to a
paid payment, conversions = leads linked to real memberships. Data that would normally come from an
external integration (SEO crawl, Business Profile, reviews) is stored with source "demo_simulated"
and is labelled as such in the UI. No Search Console metrics are invented.
"""
import argparse
import random
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.tenant_context import tenant_scope
from app.database.models import (
    AiVisibilityQuery, AiVisibilityResult, Attendance, AutomationRule, Campaign, Competitor, FollowUpTask, Gym,
    GymProfile, GymSubscription, Lead, LeadInteraction, LandingPage, Member, Membership, MembershipPlan, Payment,
    RecoveryOpportunity, Review, SeoAudit, SeoFinding, SeoPage, SubscriptionPlan, Trainer, TrialBooking, User,
    Website,
)
from app.database.models.enums import (
    AuditStatus, AutomationTrigger, Channel, ContentStatus, DietPreference, FitnessGoal, Gender, LeadStatus,
    MembershipStatus, MemberStatus, OpportunityStatus, OpportunityType, PaymentMethod, PaymentStatus, Priority,
    ReplyStatus, Role, Severity, SubscriptionStatus, TaskKind, TaskStatus, TrialStatus,
)
from app.database.session import Base, SessionLocal

DEMO_SLUG = "ironcore-fitness-demo"
OWNER = ("owner@ironcore.demo", "ironcore123")
MANAGER = ("manager@ironcore.demo", "ironcore123")
TRAINER_LOGIN = ("trainer@ironcore.demo", "ironcore123")
SITE_SLUG = "ironcore-fitness"
UTC = timezone.utc
IST = ZoneInfo("Asia/Kolkata")

PLANS = [("Monthly", 30, 1500), ("Quarterly", 90, 4000), ("Half-Yearly", 180, 7000), ("Yearly", 365, 12000)]
FIRST = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krish", "Ishaan", "Dhruv", "Kabir",
         "Rudra", "Parth", "Harsh", "Yash", "Jay", "Meet", "Dev", "Nisarg", "Hetvik", "Aanya", "Diya", "Saanvi",
         "Ananya", "Pari", "Kavya", "Myra", "Riya", "Ira", "Khushi", "Krupa", "Hetal", "Nidhi", "Pooja", "Jinal",
         "Foram", "Bhavya", "Dhwani", "Tanvi", "Mansi", "Rahul", "Karan", "Nikhil", "Rohan", "Sahil", "Mihir",
         "Chirag", "Hardik", "Ketan", "Sneha"]
LAST = ["Patel", "Shah", "Desai", "Mehta", "Joshi", "Parikh", "Trivedi", "Pandya", "Bhatt", "Vyas", "Modi",
        "Thakkar", "Chauhan", "Rana", "Solanki", "Panchal", "Gandhi", "Dave", "Kapadia", "Amin", "Iyer", "Nair",
        "Sharma", "Verma", "Singh"]


def _dt(d: date, hour: int = 10, minute: int = 0) -> datetime:
    return datetime.combine(d, time(hour, minute), tzinfo=UTC)


def _delete_gym(db: Session, gym_id) -> None:
    """Remove every row belonging to one tenant (works without DB-level cascades, e.g. SQLite)."""
    for table in reversed(Base.metadata.sorted_tables):
        if "gym_id" in table.c and table.name != "gyms":
            db.execute(delete(table).where(table.c.gym_id == gym_id))
    db.execute(delete(Gym.__table__).where(Gym.__table__.c.id == gym_id))
    db.commit()


def reset(db: Session) -> dict:
    gym = db.scalar(select(Gym).where(Gym.slug == DEMO_SLUG))
    if gym is not None:
        if not (gym.settings or {}).get("is_demo"):
            raise RuntimeError("Refusing to delete a gym that is not flagged as demo")
        _delete_gym(db, gym.id)
    return build(db)


def build(db: Session, seed: int = 2027) -> dict:
    from app.modules.subscriptions.service import ensure_default_plans

    if db.scalar(select(Gym).where(Gym.slug == DEMO_SLUG)):
        return {"status": "exists"}
    rnd = random.Random(seed)
    today = date.today()
    now = datetime.now(UTC)
    ensure_default_plans(db)
    gym = Gym(name="IronCore Fitness", slug=DEMO_SLUG, email="hello@ironcore.demo", phone="9824012345",
              address="2nd Floor, Shivam Complex, Gotri Road, Gotri, Vadodara 390021", city="Vadodara",
              timezone="Asia/Kolkata", currency="INR",
              settings={"is_demo": True, "crm": {"first_response_minutes": 15, "uncontacted_after_hours": 2}})
    db.add(gym)
    db.flush()
    pro = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == "pro"))
    db.add(GymSubscription(gym_id=gym.id, plan_id=pro.id, status=SubscriptionStatus.ACTIVE,
                           current_period_end=now + timedelta(days=30)))
    with tenant_scope(gym.id):
        counts = _populate(db, gym, rnd, today, now)
    db.commit()
    return {"status": "created", "gym_id": str(gym.id), **counts}


def _populate(db: Session, gym: Gym, rnd: random.Random, today: date, now: datetime) -> dict:
    gid = gym.id
    owner = User(gym_id=gid, email=OWNER[0], hashed_password=hash_password(OWNER[1]), full_name="Rakesh Patel",
                 phone="9824012345", role=Role.GYM_OWNER)
    manager = User(gym_id=gid, email=MANAGER[0], hashed_password=hash_password(MANAGER[1]),
                   full_name="Komal Shah", phone="9824012346", role=Role.GYM_MANAGER)
    trainer_user = User(gym_id=gid, email=TRAINER_LOGIN[0], hashed_password=hash_password(TRAINER_LOGIN[1]),
                        full_name="Vikram Rathod", phone="9824012347", role=Role.TRAINER)
    db.add_all([owner, manager, trainer_user])
    db.flush()
    staff = [owner, manager]

    plans = []
    for name, days, price in PLANS:
        p = MembershipPlan(gym_id=gid, name=name, duration_days=days, price=price,
                           description=f"{name} gym access with trainer guidance")
        db.add(p)
        plans.append(p)
    pt = MembershipPlan(gym_id=gid, name="Personal Training (12 sessions)", duration_days=30, price=6000,
                        description="One-on-one coaching, 12 sessions in a month")
    db.add(pt)
    db.flush()
    for name, trigger, offset, template in [
        ("Expiry reminder - 7 days", AutomationTrigger.MEMBERSHIP_EXPIRING, 7,
         "Hi {name}, your {gym} membership expires on {end_date}. Renew to keep training!"),
        ("Payment due", AutomationTrigger.PAYMENT_DUE, 0, "Hi {name}, {currency} {amount} is due on {due_date} at {gym}.")]:
        db.add(AutomationRule(gym_id=gid, name=name, trigger=trigger, offset_days=offset, channel=Channel.WHATSAPP,
                              template=template))

    trainer_specs = [("Vikram Rathod", "Strength & powerlifting", trainer_user.id),
                     ("Neha Solanki", "Fat loss & functional training", None),
                     ("Imran Sheikh", "Bodybuilding", None), ("Pooja Vyas", "Women's fitness & mobility", None),
                     ("Ankit Bhatt", "Personal training & rehab-safe workouts", None)]
    trainers = []
    for name, spec, uid in trainer_specs:
        t = Trainer(gym_id=gid, user_id=uid, full_name=name, specialization=spec, phone=f"98250{rnd.randint(10000, 99999)}",
                    bio=f"{name.split()[0]} coaches {spec.lower()} at IronCore.")
        db.add(t)
        trainers.append(t)
    db.flush()

    # ---------------------------------------------------------------- members, memberships, payments
    used_phones: set[str] = set()

    def phone() -> str:
        while True:
            p = f"{rnd.choice('6789')}{rnd.randint(100000000, 999999999)}"
            if p not in used_phones:
                used_phones.add(p)
                return p

    def plan_pick(min_days=0):
        options = [p for p in plans if p.duration_days >= min_days]
        weights = {30: 40, 90: 30, 180: 15, 365: 15}
        return rnd.choices(options, [weights[p.duration_days] for p in options])[0]

    categories = ["renewal"] * 25 + ["overdue"] * 14 + ["failed"] * 3 + ["inactive"] * 25
    categories += ["active"] * (420 - len(categories))
    rnd.shuffle(categories)
    members, current_payment = [], {}
    renewal_wins = []
    for i, cat in enumerate(categories):
        gender = rnd.choice([Gender.MALE, Gender.MALE, Gender.FEMALE])
        first = rnd.choice(FIRST[:20] + FIRST[40:]) if gender == Gender.MALE else rnd.choice(FIRST[20:40] + ["Sneha"])
        m = Member(gym_id=gid, full_name=f"{first} {rnd.choice(LAST)}", phone=phone(), gender=gender,
                   trainer_id=rnd.choice(trainers).id, height_cm=rnd.randint(152, 188), weight_kg=rnd.randint(50, 98),
                   fitness_goal=rnd.choice(list(FitnessGoal)), diet_preference=rnd.choice(list(DietPreference)),
                   date_of_birth=date(rnd.randint(1975, 2006), rnd.randint(1, 12), rnd.randint(1, 28)))
        if cat == "renewal":
            plan = plan_pick()
            end = today + timedelta(days=rnd.randint(1, 29))
        elif cat in ("overdue", "failed"):
            plan = plan_pick(90)
            end = today - timedelta(days=rnd.randint(5, 25)) + timedelta(days=plan.duration_days - 1)
        elif cat == "inactive":
            plan = plan_pick()
            end = today - timedelta(days=rnd.randint(8, 120))
        else:
            plan = plan_pick(90)
            end = today + timedelta(days=rnd.randint(31, plan.duration_days - 1))
        start = end - timedelta(days=plan.duration_days - 1)
        chain = [(plan, start, end)]
        prior_count = rnd.choices([0, 1, 2, 3], [25, 35, 25, 15])[0]
        cursor = start
        for _ in range(prior_count):
            pp = plan_pick()
            p_end = cursor - timedelta(days=1)
            p_start = p_end - timedelta(days=pp.duration_days - 1)
            if p_start < today - timedelta(days=540):
                break
            chain.append((pp, p_start, p_end))
            cursor = p_start
        chain.reverse()
        m.joined_on = chain[0][1]
        m.status = MemberStatus.ACTIVE if cat != "inactive" else rnd.choice([MemberStatus.EXPIRED] * 4 + [MemberStatus.INACTIVE])
        db.add(m)
        db.flush()
        members.append((m, cat))
        prev_ms = None
        for idx, (pl, s, e) in enumerate(chain):
            is_current = idx == len(chain) - 1
            ms = Membership(gym_id=gid, member_id=m.id, plan_id=pl.id, start_date=s, end_date=e, amount=pl.price,
                            status=MembershipStatus.ACTIVE if e >= today else MembershipStatus.EXPIRED,
                            created_at=_dt(s, 9))
            db.add(ms)
            db.flush()
            pay = Payment(gym_id=gid, member_id=m.id, membership_id=ms.id, amount=pl.price, due_date=s,
                          created_at=_dt(s, 9))
            if is_current and cat == "overdue":
                pay.status = PaymentStatus.OVERDUE
            elif is_current and cat == "failed":
                pay.status, pay.failure_reason = PaymentStatus.FAILED, rnd.choice(
                    ["UPI transaction declined by bank", "Card authentication failed", "Payment timed out"])
                pay.failed_at, pay.gateway_order_id = _dt(s, 11), f"order_demo_{uuid.uuid4().hex[:10]}"
            else:
                paid_day = min(s + timedelta(days=rnd.choice([0, 0, 0, 1, 2])), today)
                pay.status, pay.paid_at = PaymentStatus.PAID, _dt(paid_day, rnd.randint(7, 20), rnd.randint(0, 59))
                pay.method = rnd.choice([PaymentMethod.UPI] * 5 + [PaymentMethod.CASH] * 3 + [PaymentMethod.CARD])
                pay.verified_by = "demo"
            db.add(pay)
            db.flush()
            if is_current:
                current_payment[m.id] = pay
                # A renewal paid in the last ~60 days that GymFlow chased -> genuinely recovered revenue.
                if prev_ms is not None and pay.status == PaymentStatus.PAID and \
                        (today - s).days <= 60 and len(renewal_wins) < 18:
                    renewal_wins.append((m, prev_ms, pay))
            prev_ms = ms

    for m, prev_ms, pay in renewal_wins:
        db.add(RecoveryOpportunity(
            gym_id=gid, type=OpportunityType.UPCOMING_RENEWAL, status=OpportunityStatus.WON, priority=Priority.HIGH,
            title=f"Renewal due: {m.full_name}", reason=f"Membership ended {prev_ms.end_date:%d %b %Y}",
            member_id=m.id, membership_id=prev_ms.id, potential_revenue=float(prev_ms.amount),
            due_date=prev_ms.end_date - timedelta(days=3), milestones=["15", "7"], contact_count=rnd.randint(1, 3),
            last_contacted_at=_dt(prev_ms.end_date - timedelta(days=5)), outcome="Renewed and paid",
            recovered_revenue=float(pay.amount), recovered_payment_id=pay.id, closed_at=pay.paid_at,
            dedup_key=f"renewal:{prev_ms.id}", created_at=_dt(prev_ms.end_date - timedelta(days=15))))
    lost_reasons = ["Moved to another city", "Joined a gym closer to office", "Exams - will return later",
                    "Price too high"]
    for m, cat in [x for x in members if x[1] == "inactive"][:6]:
        ms = db.scalar(select(Membership).where(Membership.member_id == m.id).order_by(Membership.end_date.desc()))
        if (today - ms.end_date).days <= 45:
            continue
        db.add(RecoveryOpportunity(
            gym_id=gid, type=OpportunityType.EXPIRED_MEMBERSHIP, status=OpportunityStatus.LOST, priority=Priority.MEDIUM,
            title=f"Expired membership: {m.full_name}", reason=f"Expired {ms.end_date:%d %b %Y}", member_id=m.id,
            membership_id=ms.id, potential_revenue=float(ms.amount), milestones=["7", "0", "after"], contact_count=2,
            outcome=rnd.choice(lost_reasons), closed_at=_dt(ms.end_date + timedelta(days=10)),
            dedup_key=f"renewal:{ms.id}", created_at=_dt(ms.end_date - timedelta(days=30))))

    # attendance: active members over the last 30 days
    rows = []
    for m, cat in members:
        if cat == "inactive":
            continue
        visits = rnd.choice([0, 2, 4, 6, 8, 10, 12, 14, 16]) if cat != "renewal" else rnd.choice([0, 1, 3, 6])
        for d in rnd.sample(range(1, 31), visits):
            day = today - timedelta(days=d)
            if day < m.joined_on:
                continue
            hour = rnd.choice([6, 6, 7, 7, 8, 18, 19, 19, 20, 21])
            local = datetime.combine(day, time(hour, rnd.randint(0, 59)), tzinfo=IST)
            rows.append(Attendance(gym_id=gid, member_id=m.id, check_in_at=local.astimezone(UTC), source="qr"))
    db.add_all(rows)
    db.flush()

    _profile_and_site(db, gym, plans, trainers)
    lead_counts = _leads_and_trials(db, gym, rnd, today, now, staff, trainers, plans, used_phones)
    _visibility(db, gym, rnd, today, now, owner)

    # Recovery sync builds open opportunities from the records above (renewals, dues, failures, leads).
    db.commit()
    from app.modules.growth.reports import build_report
    from app.modules.recovery.service import sync_all

    sync_all(db, today)
    from app.modules.ai_search.service import readiness_audit

    readiness_audit(db)
    build_report(db, "daily_growth", generated_by="system", dedup=True)
    db.commit()
    return {"members": len(members) + lead_counts["joined"], "leads": lead_counts["leads"],
            "trials": lead_counts["trials"], "attendance_rows": len(rows), "renewal_wins": len(renewal_wins)}


def _profile_and_site(db: Session, gym: Gym, plans, trainers) -> None:
    gid = gym.id
    db.add(GymProfile(
        gym_id=gid, business_name="IronCore Fitness", website_url="https://ironcorefitness.example",
        description="IronCore Fitness is a strength-focused gym in Gotri, Vadodara with experienced coaches, a full "
                    "free-weights floor and small-group classes for beginners and regular lifters.",
        address_line="2nd Floor, Shivam Complex, Gotri Road", area="Gotri", city="Vadodara", state="Gujarat",
        postal_code="390021", phone="9824012345", whatsapp="9824012345", email="hello@ironcore.demo",
        opening_hours=[{"days": "Mon-Sat", "opens": "05:30", "closes": "22:30"},
                       {"days": "Sun", "opens": "07:00", "closes": "12:00"}],
        services=["Personal training", "Weight training", "Fat loss programme", "Functional training",
                  "Women's batch"],
        facilities=["Free weights up to 50 kg", "Power racks", "Cardio zone", "Functional turf", "Steam room",
                    "Lockers", "Two-wheeler parking"],
        service_areas=["Gotri", "Vasna-Bhayli", "Sevasi", "Alkapuri"], target_audience=["Beginners", "Working professionals", "Students"],
        social_profiles={"instagram": "https://instagram.com/ironcore.demo"},
        trial_offer={"enabled": True, "price": 0, "duration_minutes": 60, "notes": "One free supervised session"},
        offers=[{"title": "Quarterly plan", "details": "Pay for 3 months at ₹4,000", "valid_until": None}],
        rules="Carry a towel and indoor shoes. Re-rack weights after use.",
        faqs=[{"q": "Is there parking at the gym?", "a": "Yes, free two-wheeler parking in the complex.", "approved": True},
              {"q": "Do you have a separate women's batch?", "a": "Yes, a women's batch runs 10:00-12:00, Mon-Sat.", "approved": True},
              {"q": "Can beginners join?", "a": "Yes. Every new member gets an orientation session with a coach.", "approved": True},
              {"q": "Do you sell supplements?", "a": "No, we don't sell supplements at the gym.", "approved": False}],
        review_url="https://g.page/r/ironcore-demo/review", approved_at=datetime.now(UTC)))
    from app.modules.website_builder.templates import TEMPLATES, default_blocks

    site = Website(gym_id=gid, name="IronCore Fitness", slug=SITE_SLUG, template="bold", theme=TEMPLATES["bold"]["theme"],
                   blocks=default_blocks(gym), seo={"title": "IronCore Fitness | Gym in Gotri, Vadodara",
                                                    "description": "Strength gym in Gotri, Vadodara. Free trial session."},
                   is_published=True, published_at=datetime.now(UTC))
    site.published_blocks = list(site.blocks)
    db.add(site)
    db.flush()
    db.add(LandingPage(
        gym_id=gid, website_id=site.id, slug="personal-training-gotri", service="Personal Training", area="Gotri",
        city="Vadodara", seo_title="Personal Training in Gotri, Vadodara | IronCore Fitness",
        meta_description="One-on-one personal training near Gotri, Vadodara at IronCore Fitness. Book a free trial session.",
        h1="Personal Training in Gotri, Vadodara",
        content={"intro": "Looking for personal training near Gotri? IronCore Fitness is on Gotri Road.",
                 "sections": [{"heading": "What you get", "body": "12 coached sessions a month, a written plan and progress check-ins."},
                              {"heading": "Coaches", "body": "; ".join(f"{t.full_name} – {t.specialization}" for t in trainers[:3])},
                              {"heading": "Timings", "body": "Mon-Sat 05:30–22:30; Sun 07:00–12:00."}],
                 "faqs": [{"q": "How much is personal training?", "a": "₹6,000 for 12 sessions in a month."}],
                 "cta": "Book a free trial"},
        json_ld=[], status=ContentStatus.PUBLISHED, generated_by="template", warnings=[], published_at=datetime.now(UTC)))
    db.add(LandingPage(
        gym_id=gid, website_id=site.id, slug="womens-gym-alkapuri", service="Women's Gym", area="Alkapuri",
        city="Vadodara", seo_title="Women's Gym near Alkapuri, Vadodara | IronCore Fitness",
        meta_description="Women's batch with female coach near Alkapuri, Vadodara.", h1="Women's Gym near Alkapuri",
        content={"intro": "A dedicated women's batch, 10:00–12:00.", "sections": [], "faqs": [], "cta": "Enquire now"},
        json_ld=[], status=ContentStatus.DRAFT, generated_by="template", warnings=[]))


def _leads_and_trials(db: Session, gym: Gym, rnd, today, now, staff, trainers, plans, used_phones) -> dict:
    from app.modules.crm.service import phone_key, score_lead
    from app.modules.trials.service import day_slots

    gid = gym.id
    campaigns = {
        "diwali_2026": Campaign(gym_id=gid, name="Diwali Fitness Drive", code="diwali_2026", source="paid_campaign",
                                channel="instagram_ads", status="ended", start_date=today - timedelta(days=40),
                                end_date=today - timedelta(days=20), budget=8000),
        "gbp_link": Campaign(gym_id=gid, name="Google Business Profile website link", code="gbp_link",
                             source="google_business_profile", channel="gbp", status="active"),
        "reels_nov": Campaign(gym_id=gid, name="Instagram reels - November", code="reels_nov", source="instagram",
                              channel="instagram", status="active", start_date=today - timedelta(days=20), budget=3000),
    }
    db.add_all(campaigns.values())
    db.flush()
    # (status, count)
    plan_of_status = [(LeadStatus.NEW, 8), (LeadStatus.CONTACTED, 8), (LeadStatus.INTERESTED, 6),
                      (LeadStatus.TRIAL_BOOKED, 4), (LeadStatus.TRIAL_ATTENDED, 3), (LeadStatus.NEGOTIATION, 3),
                      (LeadStatus.CONVERTED, 9), (LeadStatus.LOST, 9)]
    sources = [("google_business_profile", {"utm_source": "google", "utm_medium": "gbp", "utm_campaign": "gbp_link"}, "utm"),
               ("website", {}, "unknown"), ("organic_search", {"referrer": "https://www.google.com/"}, "referrer"),
               ("instagram", {"utm_source": "instagram", "utm_medium": "social", "utm_campaign": "reels_nov"}, "utm"),
               ("paid_campaign", {"utm_source": "instagram", "utm_medium": "paid_social", "utm_campaign": "diwali_2026"}, "utm"),
               ("walk_in", {}, "staff"), ("referral", {}, "staff"), ("whatsapp", {"channel": "whatsapp_inbound"}, "declared"),
               ("website_chat", {}, "unknown"), ("ai_search", {"referrer": "https://chatgpt.com/"}, "referrer"),
               ("seo_landing_page", {"landing_page": "personal-training-gotri"}, "landing_page"), ("qr_code", {"utm_source": "qr"}, "utm")]
    weights = [9, 7, 5, 8, 6, 7, 6, 5, 3, 2, 3, 2]
    interests = ["weight loss", "strength", "general fitness", "muscle gain", "personal training", "women's batch"]
    lost_reasons = ["Too far from home", "Price too high", "Joined another gym", "Not responding", "Timing doesn't suit"]
    leads, trials_made, joined = [], 0, 0
    slots_past = []
    for back in range(2, 28):
        slots_past += [s for s, _ in day_slots(gym, today - timedelta(days=back))]
    for status_, count in plan_of_status:
        for _ in range(count):
            src, evidence, method = rnd.choices(sources, weights)[0]
            age_days = rnd.randint(0, 2) if status_ == LeadStatus.NEW else rnd.randint(3, 45)
            created = now - timedelta(days=age_days, hours=rnd.randint(0, 10))
            first = rnd.choice(FIRST)
            while True:
                ph = f"9{rnd.randint(100000000, 999999999)}"
                if ph not in used_phones:
                    used_phones.add(ph)
                    break
            lead = Lead(gym_id=gid, name=f"{first} {rnd.choice(LAST)}", phone=ph, phone_key=phone_key(ph), source=src,
                        status=status_, attribution={"method": method, **({"utm": {k: v for k, v in evidence.items()
                                                                                  if k.startswith("utm")}}
                                                                         if any(k.startswith("utm") for k in evidence) else {}),
                                                     **{k: v for k, v in evidence.items() if not k.startswith("utm")}},
                        campaign_id=campaigns[evidence["utm_campaign"]].id if evidence.get("utm_campaign") else None,
                        fitness_interest=rnd.choice(interests), wants_trial=status_ in (
                            LeadStatus.TRIAL_BOOKED, LeadStatus.TRIAL_ATTENDED) or rnd.random() < 0.3,
                        interested_plan_id=rnd.choice(plans).id if rnd.random() < 0.6 else None,
                        assigned_to_id=rnd.choice(staff).id, whatsapp_opt_in=src in ("whatsapp", "website_chat") or rnd.random() < 0.3,
                        created_at=created, updated_at=created, priority=Priority.MEDIUM, score=0, score_reasons=[])
            db.add(lead)
            db.flush()
            db.add(LeadInteraction(gym_id=gid, lead_id=lead.id, kind="system", direction="in",
                                   body=f"Enquiry received via {src.replace('_', ' ')}", created_at=created,
                                   data={"attribution": evidence, "method": method}))
            uncontacted = status_ == LeadStatus.NEW and rnd.random() < 0.75
            if not uncontacted:
                contact_at = created + timedelta(minutes=rnd.choice([6, 12, 25, 45, 90, 180]))
                lead.first_response_at = lead.last_contacted_at = min(contact_at, now)
                db.add(LeadInteraction(gym_id=gid, lead_id=lead.id, kind=rnd.choice(["call", "whatsapp"]), direction="out",
                                       user_id=lead.assigned_to_id, is_contact=True, created_at=lead.first_response_at,
                                       body=rnd.choice(["Shared plans and timings", "Explained the free trial",
                                                        "Asked about preferred batch timing"])))
            if status_ == LeadStatus.LOST:
                lead.lost_reason = rnd.choice(lost_reasons)
            # tasks
            if uncontacted:
                db.add(FollowUpTask(gym_id=gid, title=f"Contact new enquiry: {lead.name}", kind=TaskKind.FOLLOW_UP,
                                    priority=Priority.HIGH, lead_id=lead.id, assigned_to_id=lead.assigned_to_id,
                                    due_at=created + timedelta(minutes=15), source="workflow",
                                    dedup_key=f"lead_first_contact:{lead.id}"))
            elif status_ in (LeadStatus.CONTACTED, LeadStatus.INTERESTED, LeadStatus.NEGOTIATION):
                due = now + timedelta(hours=rnd.randint(-60, 48))
                lead.next_follow_up_at = due
                db.add(FollowUpTask(gym_id=gid, title=f"Follow up: {lead.name}", kind=TaskKind.FOLLOW_UP,
                                    priority=Priority.MEDIUM, lead_id=lead.id, assigned_to_id=lead.assigned_to_id,
                                    due_at=due, source="manual",
                                    draft_message=f"Hi {first}, just checking if you'd like to start this week?"))
            leads.append(lead)

    # trials: 4 upcoming (trial_booked), 6 attended (3 trial_attended + 3 of the converted), 7 confirmed no-shows,
    # 1 awaiting attendance review
    future = []
    for ahead in range(1, 6):
        future += [s for s, _ in day_slots(gym, today + timedelta(days=ahead))]
    by_status = lambda st: [l for l in leads if l.status == st]  # noqa: E731
    attended_leads = by_status(LeadStatus.TRIAL_ATTENDED) + by_status(LeadStatus.CONVERTED)[:3]
    noshow_leads = by_status(LeadStatus.CONTACTED)[:4] + by_status(LeadStatus.LOST)[:3]
    review_leads = by_status(LeadStatus.INTERESTED)[:1]

    def trial(lead, start, status_, trainer):
        nonlocal trials_made
        trials_made += 1
        t = TrialBooking(gym_id=gid, lead_id=lead.id, trainer_id=trainer.id, starts_at=start,
                         ends_at=start + timedelta(hours=1), status=status_, source=rnd.choice(["staff", "website", "ai_agent"]),
                         attended_at=start + timedelta(minutes=5) if status_ == TrialStatus.ATTENDED else None,
                         created_at=min(start - timedelta(days=2), now))
        db.add(t)
        db.flush()
        return t

    for lead, start in zip(by_status(LeadStatus.TRIAL_BOOKED), rnd.sample(future, 4)):
        trial(lead, start, TrialStatus.BOOKED, rnd.choice(trainers))
    taken: set = set()

    def past_slot(lead):
        """A free past slot after the enquiry (trials never precede the lead that booked them)."""
        options = [x for x in slots_past if x > lead.created_at + timedelta(hours=20) and x not in taken] or             [x for x in slots_past if x > lead.created_at and x not in taken]
        pick = rnd.choice(options) if options else (now - timedelta(hours=26)).replace(minute=30, second=0, microsecond=0)
        taken.add(pick)
        return pick

    attended_trials = {}
    for lead in attended_leads:
        attended_trials[lead.id] = trial(lead, past_slot(lead), TrialStatus.ATTENDED, rnd.choice(trainers))
    for lead in noshow_leads:
        start = past_slot(lead)
        t = trial(lead, start, TrialStatus.NO_SHOW, rnd.choice(trainers))
        if lead.status != LeadStatus.LOST:
            db.add(RecoveryOpportunity(
                gym_id=gid, type=OpportunityType.TRIAL_NO_SHOW, status=OpportunityStatus.OPEN, priority=Priority.MEDIUM,
                title=f"Trial no-show: {lead.name}", reason=f"Missed trial on {start:%d %b}", lead_id=lead.id,
                trial_id=t.id, potential_revenue=1500, next_action="Call to rebook the trial", due_date=today,
                milestones=[], dedup_key=f"trial_no_show:{t.id}"))
            db.add(FollowUpTask(gym_id=gid, title=f"Rebook no-show: {lead.name}", kind=TaskKind.NO_SHOW, lead_id=lead.id,
                                trial_id=t.id, priority=Priority.MEDIUM, due_at=now + timedelta(hours=3), source="workflow",
                                draft_message=f"Hi {lead.name.split()[0]}, we missed you at your trial. Want to pick another time?",
                                dedup_key=f"no_show_task:{t.id}"))
    for lead in review_leads:
        trial(lead, now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=3), TrialStatus.PENDING_REVIEW,
              rnd.choice(trainers))

    # converted leads -> real members with memberships and paid payments
    for lead in by_status(LeadStatus.CONVERTED):
        plan = db.get(MembershipPlan, lead.interested_plan_id) if lead.interested_plan_id else None
        if plan is None or plan.duration_days < 90:
            plan = plans[1]  # Quarterly
            lead.interested_plan_id = plan.id
        join_day = (lead.created_at + timedelta(days=rnd.randint(1, 4))).date()
        if lead.id in attended_trials:  # joined after attending the trial
            join_day = max(join_day, attended_trials[lead.id].starts_at.date() + timedelta(days=1))
        join_day = min(join_day, today)
        m = Member(gym_id=gid, full_name=lead.name, phone=lead.phone, joined_on=join_day, status=MemberStatus.ACTIVE,
                   trainer_id=rnd.choice(trainers).id, notes=f"Converted from lead ({lead.source})")
        db.add(m)
        db.flush()
        ms = Membership(gym_id=gid, member_id=m.id, plan_id=plan.id, start_date=join_day,
                        end_date=join_day + timedelta(days=plan.duration_days - 1), amount=plan.price,
                        status=MembershipStatus.ACTIVE if join_day + timedelta(days=plan.duration_days - 1) >= today
                        else MembershipStatus.EXPIRED, created_at=_dt(join_day))
        db.add(ms)
        db.flush()
        db.add(Payment(gym_id=gid, member_id=m.id, membership_id=ms.id, amount=plan.price, due_date=join_day,
                       status=PaymentStatus.PAID, paid_at=_dt(join_day, 18), method=PaymentMethod.UPI, verified_by="demo"))
        lead.converted_member_id, lead.converted_membership_id = m.id, ms.id
        lead.converted_at = _dt(join_day, 18)
        if lead.id in attended_trials:
            attended_trials[lead.id].converted_membership_id = ms.id
        db.add(LeadInteraction(gym_id=gid, lead_id=lead.id, kind="stage_change", body=f"Joined: {plan.name}",
                               data={"from": "negotiation", "to": "converted"}, created_at=_dt(join_day, 18)))
        joined += 1
    db.flush()
    for lead in leads:
        lead.score, lead.score_reasons, lead.priority = score_lead(db, lead)
    return {"leads": len(leads), "trials": trials_made, "joined": joined}


def _visibility(db: Session, gym: Gym, rnd, today, now, owner) -> None:
    """External-integration data, clearly marked demo_simulated (not live Google data)."""
    from app.modules.local_seo.service import audit_profile, sentiment_for
    from app.modules.seo.service import keyword_ideas

    gid = gym.id
    base = "https://ironcorefitness.example"
    audit = SeoAudit(gym_id=gid, url=base + "/", status=AuditStatus.COMPLETED, requested_by_id=owner.id,
                     started_at=now - timedelta(days=3), finished_at=now - timedelta(days=3, minutes=-2), max_pages=25,
                     pages_crawled=6, score=61, data_source="demo_simulated",
                     summary={"progress": "Completed", "host": "ironcorefitness.example", "demo": True,
                              "robots_txt": {"found": True, "status": 200, "ai_crawlers": {"GPTBot": True, "OAI-SearchBot": True,
                                                                                          "PerplexityBot": True}},
                              "sitemap": {"found": False, "status": 404}, "https": {"available": True,
                                                                                    "http_redirects_to_https": True},
                              "counts": {"critical": 0, "high": 3, "medium": 6, "low": 5, "info": 0},
                              "score_method": "100 minus a penalty per issue type (critical 20, high 10, medium 5, low 2) "
                                              "plus 1 per extra affected page (max 4). GymFlow checklist, not a Google score.",
                              "comparison": None})
    db.add(audit)
    db.flush()
    pages = [("/", "IronCore Fitness", None, ["IronCore Fitness Gotri"], 420),
             ("/about", "IronCore Fitness", "About IronCore Fitness, Vadodara.", ["About us"], 310),
             ("/plans", "Plans", None, [], 180), ("/trainers", "Our Trainers | IronCore Fitness",
                                                   "Meet the coaches at IronCore Fitness.", ["Trainers", "Coaches"], 260),
             ("/contact", "Contact IronCore Fitness", "Call 98240 12345 or visit us on Gotri Road.", ["Contact"], 150),
             ("/gallery", "Gallery", None, ["Gallery"], 40)]
    for path, title, desc, h1, words in pages:
        db.add(SeoPage(gym_id=gid, audit_id=audit.id, url=base + path, final_url=base + path, status_code=200,
                       load_ms=rnd.randint(700, 3400), size_bytes=rnd.randint(40_000, 180_000), title=title,
                       meta_description=desc, canonical=base + path, has_viewport=True, lang="en",
                       headings={"h1": h1, "h2": []}, word_count=words,
                       images=[{"src": f"{base}/img/{path.strip('/') or 'home'}-{i}.jpg", "alt": None if i else "IronCore gym floor",
                                "bytes": 520_000 if i == 2 else 140_000} for i in range(3)],
                       internal_links=[base + p[0] for p in pages], structured_data=[], open_graph={},
                       phones_found=["9824012345"] if path in ("/", "/contact") else [],
                       text_excerpt=("IronCore Fitness Gotri Vadodara strength gym personal training weight training "
                                     "free weights cardio zone Vikram Rathod Neha Solanki timings 05:30 22:30 call 98240 12345 "
                                     "390021 Gotri Road" if path in ("/", "/contact") else
                                     "about IronCore Fitness coaches" if path == "/about" else "")))
    findings = [
        ("missing_meta_description", "on_page", Severity.MEDIUM, "Missing meta description", "/",
         'No <meta name="description"> content.', "Write a 140-160 character description that invites a trial."),
        ("missing_meta_description", "on_page", Severity.MEDIUM, "Missing meta description", "/plans",
         'No <meta name="description"> content.', "Describe plans and prices."),
        ("missing_meta_description", "on_page", Severity.MEDIUM, "Missing meta description", "/gallery",
         'No <meta name="description"> content.', "Describe the gym floor and equipment."),
        ("duplicate_title", "on_page", Severity.MEDIUM, "Duplicate titles", "/",
         '"ironcore fitness" is used on 2 pages: / and /about', "Give each page its own title."),
        ("title_too_short", "on_page", Severity.LOW, "Title is very short", "/plans", '5 characters: "Plans"',
         "Include the service, area and gym name."),
        ("missing_h1", "on_page", Severity.MEDIUM, "No H1 heading", "/plans", "No <h1> with text on the page.",
         "Add one H1 such as 'Gym membership plans in Gotri'."),
        ("multiple_h1", "on_page", Severity.LOW, "Several H1 headings", "/trainers", "2 H1s: Trainers | Coaches",
         "Use a single H1."),
        ("images_missing_alt", "on_page", Severity.MEDIUM, "Images without alt text", "/",
         "2 of 3 images have no alt attribute.", "Describe each image."),
        ("large_images", "technical", Severity.MEDIUM, "Large images", "/", "1 image over 300 KB, largest 507 KB.",
         "Compress images to WebP under 200 KB."),
        ("sitemap_missing", "technical", Severity.MEDIUM, "No XML sitemap found", None,
         "https://ironcorefitness.example/sitemap.xml returned 404.", "Publish a sitemap and submit it."),
        ("slow_response", "technical", Severity.MEDIUM, "Slow page response", "/gallery",
         "Full HTML took 3,400 ms to download.", "Improve hosting and caching."),
        ("thin_content", "content", Severity.LOW, "Very little text", "/gallery", "About 40 words of visible text.",
         "Add captions describing facilities."),
        ("missing_local_schema", "local", Severity.HIGH, "No local business structured data", None,
         "No LocalBusiness / ExerciseGym JSON-LD on crawled pages.", "Add ExerciseGym JSON-LD."),
        ("missing_open_graph", "on_page", Severity.LOW, "Incomplete Open Graph tags", "/", "Missing og:title, og:image",
         "Add og tags so WhatsApp shares show a preview."),
        ("broken_internal_links", "technical", Severity.HIGH, "Broken internal links", None,
         "1 linked page failed: https://ironcorefitness.example/offers -> 404", "Fix or remove the link."),
        ("missing_canonical", "technical", Severity.LOW, "No canonical tag", "/gallery", "No rel=canonical.",
         "Add a self-referencing canonical."),
        ("phone_not_on_homepage", "local", Severity.HIGH, "Phone shown only as an image in the header", "/plans",
         "No phone number pattern found in text.", "Show the number as text on every page."),
    ]
    for code, cat, sev, title, path, ev, rec in findings:
        url = base + path if path else None
        db.add(SeoFinding(gym_id=gid, audit_id=audit.id, page_url=url, code=code, category=cat, severity=sev,
                          title=title, evidence=f"[Demo data] {ev}", recommendation=rec, basis="observed",
                          fingerprint=f"{code}|{url or '*'}"))
    db.flush()
    keyword_ideas(db)

    audit_profile(db, {"name": "IronCore Fitness Gym Gotri", "primary_category": "Gym",
                       "additional_categories": ["Fitness center"], "description": "Gym in Gotri.",
                       "address": "2nd Floor, Shivam Complex, Gotri Road, Vadodara 390021", "phone": "098240 12345",
                       "website": "https://ironcorefitness.example", "hours": [{"day": "MONDAY", "opens": "05:30", "closes": "22:30"}],
                       "special_hours_count": 0, "services": ["Weight training", "Personal training"], "review_count": 12,
                       "rating": 4.3}, source="demo_simulated")
    review_texts = [
        (5, "Vikram sir's strength programme is excellent. Clean equipment."), (5, "Great coaches, friendly crowd."),
        (4, "Good gym, evening batch is crowded."), (5, "Women's batch timing is perfect for me."),
        (2, "AC was not working for a week in October."), (4, "Value for money quarterly plan."),
        (3, "Decent, but parking fills up after 7 pm."), (5, "Lost 6 kg in 3 months with Neha ma'am's plan."),
        (1, "Front desk didn't call back after my enquiry."), (4, "Steam room is a nice bonus."),
        (5, "Best trainers in Gotri!"), (4, "Spacious free-weights area.")]
    for i, (rating, text) in enumerate(review_texts):
        replied = i % 3 == 0
        db.add(Review(gym_id=gid, source="demo_simulated", external_id=f"demo-review-{i}", author=f"{rnd.choice(FIRST)} {rnd.choice(LAST)[0]}.",
                      rating=rating, text=text, review_date=now - timedelta(days=5 + i * 9), sentiment=sentiment_for(rating),
                      sentiment_basis="rating", reply_status=ReplyStatus.PUBLISHED if replied else ReplyStatus.NONE,
                      existing_reply="Thank you for the feedback!" if replied else None))
    for name, area, rating, count, services in [
        ("FitZone Gotri", "Gotri", 4.4, 286, ["Zumba", "Weight training", "Yoga"]),
        ("Muscle Factory", "Vasna-Bhayli", 4.1, 132, ["Weight training", "CrossFit"]),
        ("Shakti Ladies Gym", "Alkapuri", 4.6, 98, ["Women's batch", "Aerobics"])]:
        db.add(Competitor(gym_id=gid, name=name, area=area, rating=rating, review_count=count, services=services,
                          categories=["Gym"], source="user_supplied", observed_at=now - timedelta(days=2),
                          notes="Demo competitor - figures entered by hand"))
    for q, results in [("Best gyms in Gotri, Vadodara", [("chatgpt", False, None, ["FitZone Gotri"]),
                                                          ("perplexity", True, 3, ["FitZone Gotri", "Muscle Factory"])]),
                       ("Personal training centres in Vadodara", [("gemini", False, None, ["Muscle Factory"])]),
                       ("Women's gym near Alkapuri", [])]:
        query = AiVisibilityQuery(gym_id=gid, question=q, is_active=True)
        db.add(query)
        db.flush()
        for provider, mentioned, pos, comps in results:
            db.add(AiVisibilityResult(gym_id=gid, query_id=query.id, provider=provider, method="manual_research",
                                      mentioned=mentioned, position=pos, competitors_mentioned=comps,
                                      excerpt="[Demo data] Sample answer recorded during manual research.",
                                      recorded_by_id=owner.id, observed_at=now - timedelta(days=4)))
    db.flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Delete and rebuild the demo tenant")
    args = parser.parse_args()
    with SessionLocal() as db:
        result = reset(db) if args.reset else build(db)
    print(result)
    print(f"Demo logins: {OWNER[0]} / {OWNER[1]} (owner), {MANAGER[0]} (manager), {TRAINER_LOGIN[0]} (trainer)")


if __name__ == "__main__":
    main()
