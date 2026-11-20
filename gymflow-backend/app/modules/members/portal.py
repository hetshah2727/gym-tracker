"""Member-app endpoints: a logged-in member sees only their own data."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import tenant_user
from app.database.models import AffiliateLink, AffiliateProduct, DietPlan, Gym, Member, Membership, Payment, User
from app.database.models.enums import DietPlanStatus, Role
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.affiliate.router import ProductOut, _share_url
from app.modules.diet_plans.router import DietPlanOut
from app.modules.gyms.schemas import GymOut
from app.modules.members.schemas import MemberOut
from app.modules.memberships.schemas import MembershipOut
from app.modules.memberships.service import with_days_left
from app.modules.payments.router import PaymentOut

router = APIRouter(prefix="/me", tags=["Member portal"])

member_user = tenant_user(Role.MEMBER)


def current_member(db: Session = Depends(get_db), user: User = Depends(member_user)) -> Member:
    rows = TenantRepository(Member, db).list(Member.user_id == user.id, limit=1)
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No member profile linked to this login")
    return rows[0]


@router.get("/profile", response_model=MemberOut)
def profile(member: Member = Depends(current_member)):
    return member


@router.get("/gym", response_model=GymOut)
def my_gym(member: Member = Depends(current_member), db: Session = Depends(get_db)):
    return db.get(Gym, member.gym_id)


@router.get("/memberships", response_model=list[MembershipOut])
def my_memberships(member: Member = Depends(current_member), db: Session = Depends(get_db)):
    rows = TenantRepository(Membership, db).list(Membership.member_id == member.id,
                                                 order_by=Membership.end_date.desc())
    return [with_days_left(m) for m in rows]


@router.get("/payments", response_model=list[PaymentOut])
def my_payments(member: Member = Depends(current_member), db: Session = Depends(get_db)):
    return TenantRepository(Payment, db).list(Payment.member_id == member.id)


@router.get("/diet-plans", response_model=list[DietPlanOut])
def my_diet_plans(member: Member = Depends(current_member), db: Session = Depends(get_db)):
    """Only plans a trainer has assigned are visible to the member."""
    return TenantRepository(DietPlan, db).list(DietPlan.member_id == member.id,
                                               DietPlan.status == DietPlanStatus.ASSIGNED)


@router.get("/products")
def my_products(member: Member = Depends(current_member), db: Session = Depends(get_db)):
    """Products recommended by the member's trainer first, then the rest of the gym's picks."""
    links = TenantRepository(AffiliateLink, db).list(limit=1000)
    products = {p.id: p for p in db.scalars(select(AffiliateProduct).where(
        AffiliateProduct.id.in_([link.product_id for link in links]),
        AffiliateProduct.is_active.is_(True))).all()}
    links.sort(key=lambda link: link.trainer_id != member.trainer_id)
    seen, result = set(), []
    for link in links:
        if link.product_id in products and link.product_id not in seen:
            seen.add(link.product_id)
            result.append({**ProductOut.model_validate(products[link.product_id]).model_dump(mode="json"),
                           "buy_url": _share_url(link.code),
                           "recommended_by_trainer": link.trainer_id == member.trainer_id and link.trainer_id is not None})
    return result
