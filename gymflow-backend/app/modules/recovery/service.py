"""Membership renewal & revenue recovery (deterministic).

Accounting rules:
* ``potential_revenue`` is an estimate of what an opportunity could bring in. It is never revenue.
* An opportunity is WON only by a PAID payment record (``close_with_payment``). ``recovered_revenue`` is
  that payment's amount, and ``recovered_payment_id`` is unique, so each payment is credited once.
* Opportunities are keyed by ``dedup_key`` so re-running the daily sync never duplicates them.
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_gym_id
from app.database.models import (
    FollowUpTask, Gym, Lead, Member, Membership, MembershipPlan, Payment, RecoveryOpportunity, User,
)
from app.database.models.enums import (
    OPEN_OPPORTUNITY_STATUSES, LeadStatus, MembershipStatus, OpportunityStatus, OpportunityType, PaymentStatus,
    Priority, TaskKind, TaskStatus,
)
from app.database.repositories.base import TenantRepository
from app.modules.crm import service as crm
from app.services import events

RENEWAL_MILESTONES = (30, 15, 7, 0)          # days before expiry
EXPIRED_LOOKBACK_DAYS = 45
UNPAID = (PaymentStatus.PENDING, PaymentStatus.OVERDUE, PaymentStatus.FAILED)


def upsert_opportunity(db: Session, *, dedup_key: str, type: OpportunityType, title: str, reason: str,
                       potential_revenue: float, priority: Priority = Priority.MEDIUM, **fields) -> RecoveryOpportunity:
    """Create the opportunity or refresh an open one with the same key. Never reopens closed ones. Flushes only."""
    repo = TenantRepository(RecoveryOpportunity, db)
    opp = repo.first(RecoveryOpportunity.dedup_key == dedup_key)
    if opp is None:
        try:
            with db.begin_nested():
                return repo.add(dedup_key=dedup_key, type=type, title=title[:255], reason=reason,
                                potential_revenue=round(potential_revenue, 2), priority=priority,
                                milestones=[], **fields)
        except IntegrityError:
            opp = repo.first(RecoveryOpportunity.dedup_key == dedup_key)
    if opp.status in OPEN_OPPORTUNITY_STATUSES:
        opp.type, opp.title, opp.reason, opp.priority = type, title[:255], reason, priority
        opp.potential_revenue = round(potential_revenue, 2)
        for key in ("due_date", "next_action"):
            if key in fields:
                setattr(opp, key, fields[key])
        db.flush()
    return opp


def _renewal_price(db: Session, membership: Membership) -> float:
    plan = db.get(MembershipPlan, membership.plan_id) if membership.plan_id else None
    return float(plan.price) if plan and plan.is_active else float(membership.amount)


def _has_later_membership(db: Session, membership: Membership) -> Membership | None:
    return TenantRepository(Membership, db).first(
        Membership.member_id == membership.member_id, Membership.id != membership.id,
        Membership.start_date > membership.start_date,
        Membership.status.in_([MembershipStatus.ACTIVE, MembershipStatus.FROZEN]))


def _milestone(days_left: int) -> str | None:
    if days_left < 0:
        return "after"
    hit = [m for m in RENEWAL_MILESTONES if days_left <= m]
    return str(min(hit)) if hit else None


def sync_renewals(db: Session, today: date) -> int:
    """Workflow 5 - one opportunity per membership, advancing through 30/15/7/0/after milestones."""
    gym = db.get(Gym, get_current_gym_id())
    members = TenantRepository(Member, db)
    rows = TenantRepository(Membership, db).list(
        Membership.end_date <= today + timedelta(days=max(RENEWAL_MILESTONES)),
        Membership.end_date >= today - timedelta(days=EXPIRED_LOOKBACK_DAYS),
        Membership.status.in_([MembershipStatus.ACTIVE, MembershipStatus.EXPIRED]), limit=20_000)
    touched = 0
    for ms in rows:
        key = f"renewal:{ms.id}"
        later = _has_later_membership(db, ms)
        if later:
            _settle_renewed(db, key, later)
            continue
        member = members.get(ms.member_id)
        if member is None:
            continue
        days_left = (ms.end_date - today).days
        milestone = _milestone(days_left)
        if milestone is None:
            continue
        expired = days_left < 0
        price = _renewal_price(db, ms)
        plan = db.get(MembershipPlan, ms.plan_id) if ms.plan_id else None
        title = (f"Expired membership: {member.full_name}" if expired
                 else f"Renewal due in {days_left}d: {member.full_name}" if days_left else
                 f"Membership ends today: {member.full_name}")
        reason = (f"{plan.name if plan else 'Membership'} "
                  f"{'expired' if expired else 'ends'} on {ms.end_date.strftime('%d %b %Y')}; "
                  "no renewal recorded.")
        priority = Priority.HIGH if days_left <= 7 else Priority.MEDIUM
        opp = upsert_opportunity(
            db, dedup_key=key, type=OpportunityType.EXPIRED_MEMBERSHIP if expired else OpportunityType.UPCOMING_RENEWAL,
            title=title, reason=reason, potential_revenue=price, priority=priority, member_id=member.id,
            membership_id=ms.id, due_date=max(ms.end_date - timedelta(days=3), today) if not expired else today,
            next_action="Win back with a renewal offer" if expired else "Contact member about renewal")
        if opp.status in OPEN_OPPORTUNITY_STATUSES and milestone not in (opp.milestones or []):
            opp.milestones = [*(opp.milestones or []), milestone]
            message = renewal_message(gym, member, ms, price)
            label = "after expiry" if milestone == "after" else f"{milestone} days before expiry" \
                if milestone != "0" else "on expiry day"
            crm.create_task(db, title=f"Renewal follow-up ({label}): {member.full_name}", kind=TaskKind.RENEWAL,
                            member_id=member.id, opportunity_id=opp.id, priority=priority,
                            due_at=datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
                            + timedelta(hours=10), source="workflow", draft_message=message,
                            dedup_key=f"renewal_task:{ms.id}:{milestone}")
            touched += 1
    db.flush()
    return touched


def _settle_renewed(db: Session, key: str, later: Membership) -> None:
    """The member renewed. Close as WON when the renewal payment is PAID, else mark in progress."""
    opp = TenantRepository(RecoveryOpportunity, db).first(RecoveryOpportunity.dedup_key == key)
    if opp is None or opp.status not in OPEN_OPPORTUNITY_STATUSES:
        return
    paid = TenantRepository(Payment, db).first(Payment.membership_id == later.id, Payment.status == PaymentStatus.PAID)
    if paid:
        close_with_payment(db, opp, paid, outcome="Renewed and paid")
    else:
        opp.status = OpportunityStatus.IN_PROGRESS
        opp.outcome = "Renewed - payment pending"


def renewal_message(gym: Gym, member: Member, ms: Membership, price: float) -> str:
    first = member.full_name.split()[0]
    when = ms.end_date.strftime("%d %b")
    verb = "ended" if ms.end_date < date.today() else "ends"
    return (f"Hi {first}, your {gym.name} membership {verb} on {when}. Renew for {gym.currency} {price:,.0f} "
            f"to keep training without a break. Reply here or visit the front desk.")


def payment_message(gym: Gym, member: Member, payment: Payment) -> str:
    return (f"Hi {member.full_name.split()[0]}, a payment of {gym.currency} {float(payment.amount):,.0f} is pending "
            f"at {gym.name}. Please pay at the desk or reply for a payment link.")


# ---------------------------------------------------------------- "who owes money" list for the owner

MONEY_TYPES = (OpportunityType.UPCOMING_RENEWAL, OpportunityType.EXPIRED_MEMBERSHIP,
               OpportunityType.OUTSTANDING_PAYMENT, OpportunityType.FAILED_PAYMENT)


def due_list(db: Session, today: date | None = None, limit: int = 500) -> dict:
    """Open money opportunities as a plain, bucketed list: overdue / ending this week / ending later.

    Amounts are what the member owes or what a renewal costs (the opportunity's potential) - not revenue.
    """
    from urllib.parse import urlencode

    from app.core.config import settings
    from app.integrations.payments import razorpay

    today = today or date.today()
    gym = db.get(Gym, get_current_gym_id())
    # Without Razorpay, reminders can still carry a UPI pay page (QR + "open UPI app") for the gym's own UPI ID.
    upi_page = None
    if not razorpay.is_configured() and (gym.settings or {}).get("upi_id"):
        upi_page = f"{settings.FRONTEND_URL.rstrip('/')}/pay/{gym.slug}"
    opps = TenantRepository(RecoveryOpportunity, db).list(
        RecoveryOpportunity.type.in_(MONEY_TYPES), RecoveryOpportunity.status.in_(OPEN_OPPORTUNITY_STATUSES),
        limit=limit, order_by=RecoveryOpportunity.due_date)
    items = []
    for o in opps:
        member = db.get(Member, o.member_id) if o.member_id else None
        if member is None:
            continue
        ms = db.get(Membership, o.membership_id) if o.membership_id else None
        plan = db.get(MembershipPlan, ms.plan_id) if ms and ms.plan_id else None
        payment = db.get(Payment, o.payment_id) if o.payment_id else None
        if payment is not None:
            days = (payment.due_date - today).days if payment.due_date else 0
            message = payment_message(gym, member, payment)
            kind = "failed" if o.type == OpportunityType.FAILED_PAYMENT else "unpaid"
        else:
            days = (ms.end_date - today).days if ms else 0
            message = renewal_message(gym, member, ms, float(o.potential_revenue)) if ms else None
            kind = "renewal"
        if upi_page and message:
            query = urlencode({"amount": f"{float(o.potential_revenue):.0f}", "note": f"{gym.name} - {member.full_name}"[:60]})
            message += f"\n\nPay by UPI: {upi_page}?{query}"
        bucket = "overdue" if (payment is not None and days <= 0) or days < 0 else "this_week" if days <= 7 else "later"
        items.append({
            "id": str(o.id), "kind": kind, "bucket": bucket, "member_id": str(member.id),
            "name": member.full_name, "phone": member.phone, "plan": plan.name if plan else None,
            "amount": float(o.potential_revenue), "days": days, "message": message,
            "contact_count": o.contact_count,
            "can_pay_online": payment is not None or (ms is not None and kind == "renewal"),
            "last_contacted_at": o.last_contacted_at.isoformat() if o.last_contacted_at else None,
        })
    order = {"overdue": 0, "this_week": 1, "later": 2}
    items.sort(key=lambda i: (order[i["bucket"]], i["days"]))
    buckets = {b: {"count": sum(1 for i in items if i["bucket"] == b),
                   "amount": round(sum(i["amount"] for i in items if i["bucket"] == b), 2)} for b in order}
    return {"currency": gym.currency, "total": round(sum(i["amount"] for i in items), 2), "count": len(items),
            "buckets": buckets, "items": items, "payment_links": razorpay.is_configured(),
            "upi_payments": upi_page is not None}


def sync_payments(db: Session, today: date) -> int:
    """Workflow 6 - outstanding / failed payments -> recovery opportunities."""
    members = TenantRepository(Member, db)
    count = 0
    for p in TenantRepository(Payment, db).list(Payment.status.in_(UNPAID), limit=20_000):
        if p.status != PaymentStatus.FAILED and p.due_date and p.due_date > today:
            continue
        member = members.get(p.member_id)
        if member is None:
            continue
        failed = p.status == PaymentStatus.FAILED
        overdue_days = (today - p.due_date).days if p.due_date else 0
        upsert_opportunity(
            db, dedup_key=f"payment:{p.id}",
            type=OpportunityType.FAILED_PAYMENT if failed else OpportunityType.OUTSTANDING_PAYMENT,
            title=f"{'Failed' if failed else 'Outstanding'} payment: {member.full_name}",
            reason=(f"Payment attempt failed{': ' + p.failure_reason if p.failure_reason else ''}" if failed
                    else f"Due {p.due_date.strftime('%d %b %Y') if p.due_date else 'now'}"
                    + (f", {overdue_days} days overdue" if overdue_days > 0 else "")),
            potential_revenue=float(p.amount), member_id=member.id, payment_id=p.id,
            membership_id=p.membership_id,
            priority=Priority.HIGH if failed or overdue_days > 7 else Priority.MEDIUM,
            due_date=today, next_action="Send payment reminder" if not failed else "Help member retry payment")
        count += 1
    db.flush()
    return count


def sync_leads(db: Session, now: datetime) -> int:
    """Uncontacted enquiries and overdue lead follow-ups -> opportunities (values are estimates)."""
    from app.modules.trials.service import _lead_value

    gym = db.get(Gym, get_current_gym_id())
    hours = float(((gym.settings or {}).get("crm") or {}).get("uncontacted_after_hours", 2))
    count = 0
    for lead in TenantRepository(Lead, db).list(Lead.status == LeadStatus.NEW, Lead.first_response_at.is_(None),
                                                Lead.created_at < now - timedelta(hours=hours), limit=5000):
        upsert_opportunity(db, dedup_key=f"lead_uncontacted:{lead.id}", type=OpportunityType.UNCONTACTED_LEAD,
                           title=f"Uncontacted enquiry: {lead.name}",
                           reason=f"No response recorded since {crm.aware(lead.created_at):%d %b %H:%M} UTC",
                           potential_revenue=_lead_value(db, lead), lead_id=lead.id, priority=Priority.HIGH,
                           due_date=now.date(), next_action="Call or WhatsApp the lead")
        count += 1
    for task in TenantRepository(FollowUpTask, db).list(
            FollowUpTask.status == TaskStatus.OPEN, FollowUpTask.lead_id.is_not(None),
            FollowUpTask.kind == TaskKind.FOLLOW_UP, FollowUpTask.due_at < now - timedelta(hours=24), limit=5000):
        lead = db.get(Lead, task.lead_id)
        if lead is None or lead.status in (LeadStatus.CONVERTED, LeadStatus.LOST) or lead.first_response_at is None:
            continue
        upsert_opportunity(db, dedup_key=f"task_overdue:{task.id}", type=OpportunityType.OVERDUE_FOLLOW_UP,
                           title=f"Overdue follow-up: {lead.name}", reason=f"'{task.title}' was due "
                           f"{crm.aware(task.due_at):%d %b}", potential_revenue=_lead_value(db, lead),
                           lead_id=lead.id, priority=Priority.MEDIUM, due_date=now.date(),
                           next_action=task.title)
        count += 1
    # Lead opportunities resolve themselves once the lead is handled (no revenue is credited for that).
    for opp in TenantRepository(RecoveryOpportunity, db).list(
            RecoveryOpportunity.status.in_(OPEN_OPPORTUNITY_STATUSES),
            RecoveryOpportunity.type.in_([OpportunityType.UNCONTACTED_LEAD, OpportunityType.OVERDUE_FOLLOW_UP]),
            limit=5000):
        lead = db.get(Lead, opp.lead_id) if opp.lead_id else None
        resolved = lead is None or lead.status in (LeadStatus.CONVERTED, LeadStatus.LOST) or (
            opp.type == OpportunityType.UNCONTACTED_LEAD and lead.first_response_at is not None)
        if opp.type == OpportunityType.OVERDUE_FOLLOW_UP and not resolved:
            task_id = opp.dedup_key.split(":", 1)[1]
            task = db.scalar(select(FollowUpTask).where(FollowUpTask.id == _uuid(task_id)))
            resolved = task is None or task.status != TaskStatus.OPEN
        if resolved:
            opp.status, opp.outcome, opp.closed_at = OpportunityStatus.DISMISSED, "Resolved: lead handled", now
    db.flush()
    return count


def _uuid(value: str):
    import uuid

    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def sync_all(db: Session, today: date | None = None) -> dict:
    today = today or date.today()
    now = datetime.now(timezone.utc)
    result = {"renewals": sync_renewals(db, today), "payments": sync_payments(db, today), "leads": sync_leads(db, now)}
    db.commit()
    return result


# ---------------------------------------------------------------- closing

def close_with_payment(db: Session, opp: RecoveryOpportunity, payment: Payment, outcome: str,
                       user: User | None = None) -> RecoveryOpportunity:
    if payment.status != PaymentStatus.PAID:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a paid payment can close an opportunity as recovered")
    if opp.member_id and payment.member_id != opp.member_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment belongs to a different member")
    already = TenantRepository(RecoveryOpportunity, db).first(RecoveryOpportunity.recovered_payment_id == payment.id)
    if already and already.id != opp.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "This payment has already been credited to another opportunity")
    if opp.status == OpportunityStatus.WON:
        return opp
    opp.status = OpportunityStatus.WON
    opp.recovered_revenue = float(payment.amount)
    opp.recovered_payment_id = payment.id
    opp.outcome = outcome
    opp.closed_at = datetime.now(timezone.utc)
    db.flush()
    _close_opp_tasks(db, opp)
    events.emit(db, "recovery.won", entity_type="recovery_opportunity", entity_id=opp.id, commit=False,
                actor="system" if user is None else "user", actor_user_id=user.id if user else None,
                payload={"type": opp.type.value, "recovered": float(payment.amount), "payment_id": payment.id})
    return opp


def _close_opp_tasks(db: Session, opp: RecoveryOpportunity) -> None:
    for task in TenantRepository(FollowUpTask, db).list(FollowUpTask.opportunity_id == opp.id,
                                                        FollowUpTask.status == TaskStatus.OPEN, limit=100):
        crm.complete_task(db, task, None, "Opportunity closed")


def on_payment_paid(db: Session, payment: Payment) -> RecoveryOpportunity | None:
    """Workflow 6 tail - a confirmed payment closes the matching opportunity (once)."""
    if TenantRepository(RecoveryOpportunity, db).first(RecoveryOpportunity.recovered_payment_id == payment.id):
        return None
    opps = TenantRepository(RecoveryOpportunity, db)
    opp = opps.first(RecoveryOpportunity.payment_id == payment.id,
                     RecoveryOpportunity.status.in_(OPEN_OPPORTUNITY_STATUSES))
    if opp:
        return close_with_payment(db, opp, payment, outcome="Payment received")
    if payment.membership_id:
        new_ms = db.get(Membership, payment.membership_id)
        if new_ms:
            prior = opps.first(RecoveryOpportunity.member_id == payment.member_id,
                               RecoveryOpportunity.type.in_([OpportunityType.UPCOMING_RENEWAL,
                                                             OpportunityType.EXPIRED_MEMBERSHIP]),
                               RecoveryOpportunity.status.in_(OPEN_OPPORTUNITY_STATUSES),
                               RecoveryOpportunity.membership_id != new_ms.id,
                               order_by=RecoveryOpportunity.created_at.desc())
            if prior:
                return close_with_payment(db, prior, payment, outcome="Renewed and paid")
    return None


def mark_paid_now(db: Session, opp: RecoveryOpportunity, user: User | None, method, reference: str | None = None,
                  gateway_payment_id: str | None = None) -> RecoveryOpportunity:
    """One-tap "Mark paid" for the owner.

    * Unpaid/failed fee: marks that payment PAID (payment.paid closes the opportunity).
    * Renewal/expired: creates the renewal membership for the same plan, paid now; its payment closes the
      opportunity. Revenue is still credited only through a real PAID payment record.
    """
    from app.modules.memberships.service import assign_membership, renewal_start
    from app.modules.payments.service import mark_paid

    if opp.status not in OPEN_OPPORTUNITY_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "This has already been closed")
    if opp.payment_id:
        payment = db.get(Payment, opp.payment_id)
        if payment.status != PaymentStatus.PAID:
            mark_paid(db, payment, method, reference=reference, actor_user_id=user.id if user else None,
                      gateway_payment_id=gateway_payment_id, verified_by="gateway" if gateway_payment_id else "manual")
    elif opp.type in (OpportunityType.UPCOMING_RENEWAL, OpportunityType.EXPIRED_MEMBERSHIP) and opp.membership_id:
        ms = db.get(Membership, opp.membership_id)
        member = db.get(Member, opp.member_id)
        plan = db.get(MembershipPlan, ms.plan_id) if ms and ms.plan_id else None
        if plan is None or member is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "The plan for this membership no longer exists. Renew from the member's page.")
        new_ms = assign_membership(db, member, plan, start_date=renewal_start(ms), amount=_renewal_price(db, ms),
                                   paid=True, payment_method=method)
        payment = TenantRepository(Payment, db).first(Payment.membership_id == new_ms.id)
        if payment is not None:
            payment.reference = reference or payment.reference
            if gateway_payment_id:
                payment.gateway_payment_id, payment.verified_by = gateway_payment_id, "gateway"
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing to collect for this item")
    db.refresh(opp)
    if opp.status != OpportunityStatus.WON and payment is not None and payment.status == PaymentStatus.PAID:
        close_with_payment(db, opp, payment, outcome="Paid online" if gateway_payment_id else "Paid at the desk",
                           user=user)
    db.commit()
    return opp


def record_contact(db: Session, opp: RecoveryOpportunity, user: User, note: str | None) -> RecoveryOpportunity:
    if opp.status not in OPEN_OPPORTUNITY_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Opportunity is closed")
    opp.status = OpportunityStatus.IN_PROGRESS
    opp.contact_count += 1
    opp.last_contacted_at = datetime.now(timezone.utc)
    if note:
        opp.outcome = note[:255]
    if opp.lead_id and (lead := db.get(Lead, opp.lead_id)):
        crm.record_interaction(db, lead, "call", note or "Contacted (recovery)", direction="out", user=user)
    events.emit(db, "recovery.contacted", entity_type="recovery_opportunity", entity_id=opp.id,
                actor_user_id=user.id, payload={"note": note})
    return opp


def close_without_revenue(db: Session, opp: RecoveryOpportunity, user: User, *, lost: bool,
                          outcome: str) -> RecoveryOpportunity:
    if opp.status not in OPEN_OPPORTUNITY_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Opportunity is already closed")
    opp.status = OpportunityStatus.LOST if lost else OpportunityStatus.DISMISSED
    opp.outcome = outcome[:255]
    opp.closed_at = datetime.now(timezone.utc)
    _close_opp_tasks(db, opp)
    events.emit(db, "recovery.closed", entity_type="recovery_opportunity", entity_id=opp.id,
                actor_user_id=user.id, payload={"status": opp.status.value, "outcome": outcome})
    return opp


RENEWAL_LINK_PREFIX = "rnw_"


def payment_link(db: Session, opp: RecoveryOpportunity) -> dict:
    """Razorpay payment link for the outstanding payment (only when Razorpay is configured)."""
    from app.integrations.payments import razorpay

    if opp.status not in OPEN_OPPORTUNITY_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "This has already been closed")
    renewal = opp.payment_id is None and opp.membership_id is not None and opp.type in (
        OpportunityType.UPCOMING_RENEWAL, OpportunityType.EXPIRED_MEMBERSHIP)
    if not opp.payment_id and not renewal:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This opportunity has no payment to collect")
    payment = db.get(Payment, opp.payment_id) if opp.payment_id else None
    if payment is not None and payment.status == PaymentStatus.PAID:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment is already paid")
    if not razorpay.is_configured():
        return {"configured": False, "url": None,
                "detail": "Connect Razorpay to send payment links. Until then, collect at the desk and mark paid."}
    member = db.get(Member, opp.member_id)
    gym = db.get(Gym, opp.gym_id)
    if payment is not None:
        amount, reference, label = float(payment.amount), str(payment.id), "membership fee"
    else:
        # Renewal: the link points at the opportunity; the signed webhook creates the renewal once it's paid.
        amount, reference, label = float(opp.potential_revenue), RENEWAL_LINK_PREFIX + opp.id.hex, "membership renewal"
    try:
        link = razorpay.create_payment_link(amount, reference_id=reference,
                                            description=f"{gym.name} {label}", currency=gym.currency,
                                            customer={"name": member.full_name, "contact": member.phone},
                                            notes={"gym_id": str(gym.id), "opportunity_id": str(opp.id)})
    except razorpay.PaymentGatewayError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Payment gateway error: {exc}")
    # The webhook (payment_link.paid) finds the payment again through reference_id.
    return {"configured": True, "url": link.get("short_url"), "id": link.get("id")}
