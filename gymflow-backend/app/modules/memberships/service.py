from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.database.models import Member, Membership, MembershipPlan, Payment
from app.database.models.enums import MembershipStatus, MemberStatus, PaymentMethod, PaymentStatus
from app.database.repositories.base import TenantRepository
from app.integrations.n8n import client as n8n


def assign_membership(
    db: Session,
    member: Member,
    plan: MembershipPlan,
    start_date: date | None = None,
    amount: float | None = None,
    paid: bool = False,
    payment_method: PaymentMethod | None = None,
    auto_renew: bool = False,
) -> Membership:
    """Create a membership and its fee record, and mark the member active."""
    start = start_date or date.today()
    price = float(plan.price) if amount is None else amount
    membership = TenantRepository(Membership, db).create(
        member_id=member.id, plan_id=plan.id, start_date=start,
        end_date=start + timedelta(days=plan.duration_days - 1),
        amount=price, status=MembershipStatus.ACTIVE, auto_renew=auto_renew,
    )
    TenantRepository(Payment, db).create(
        member_id=member.id, membership_id=membership.id, amount=price, due_date=start,
        status=PaymentStatus.PAID if paid else PaymentStatus.PENDING,
        method=payment_method if paid else None,
        paid_at=datetime.now(timezone.utc) if paid else None,
    )
    if member.status != MemberStatus.ACTIVE:
        TenantRepository(Member, db).update(member, {"status": MemberStatus.ACTIVE})
    n8n.trigger("membership.created", {
        "membership_id": str(membership.id), "member_id": str(member.id), "gym_id": str(member.gym_id),
        "end_date": membership.end_date.isoformat(), "amount": price, "paid": paid,
    })
    return membership


def renewal_start(current: Membership) -> date:
    """A renewal continues from the old end date, or starts today if already lapsed."""
    return max(current.end_date + timedelta(days=1), date.today())


def with_days_left(membership: Membership) -> dict:
    data = {c.name: getattr(membership, c.name) for c in membership.__table__.columns}
    data["days_left"] = (membership.end_date - date.today()).days
    return data
