import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permissions import GYM_STAFF_AND_TRAINERS, tenant_user
from app.database.models import DietPlan, Gym, Member, User
from app.database.models.enums import Channel, DietPlanStatus, DietPreference, FitnessGoal
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.integrations.ai import diet_generator as ai
from app.modules.common import ORMModel, get_or_404
from app.modules.members.router import trainer_profile_id
from app.modules.notifications import service as notifications

router = APIRouter(prefix="/diet-plans", tags=["AI diet plans"])


class GenerateRequest(BaseModel):
    member_id: uuid.UUID
    goal: FitnessGoal | None = None
    diet_type: DietPreference | None = None
    meals_per_day: int = Field(5, ge=3, le=7)
    cuisine: str = "Indian"
    trainer_notes: str | None = Field(None, max_length=1000)


class DietPlanUpdate(BaseModel):
    title: str | None = None
    daily_calories: int | None = Field(None, gt=800, lt=6000)
    macros: dict | None = None
    meals: list | None = None
    notes: str | None = None


class DietPlanOut(ORMModel):
    id: uuid.UUID
    member_id: uuid.UUID
    created_by_id: uuid.UUID | None
    title: str
    goal: FitnessGoal
    diet_type: DietPreference
    daily_calories: int
    macros: dict
    meals: list
    notes: str | None
    status: DietPlanStatus
    ai_generated: bool
    created_at: datetime
    updated_at: datetime


def _member_for(db: Session, user: User, member_id: uuid.UUID) -> Member:
    member = get_or_404(TenantRepository(Member, db), member_id, "Member")
    own = trainer_profile_id(db, user)
    if own and member.trainer_id != own:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return member


def _plan_for(db: Session, user: User, plan_id: uuid.UUID) -> DietPlan:
    plan = get_or_404(TenantRepository(DietPlan, db), plan_id, "Diet plan")
    _member_for(db, user, plan.member_id)
    return plan


@router.post("/generate", response_model=DietPlanOut, status_code=status.HTTP_201_CREATED)
def generate(data: GenerateRequest, db: Session = Depends(get_db),
             user: User = Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    """Generate a draft plan from the member's profile. A trainer reviews it before assigning."""
    member = _member_for(db, user, data.member_id)
    goal = data.goal or member.fitness_goal
    diet_type = data.diet_type or member.diet_preference
    missing = [name for name, value in (("height_cm", member.height_cm), ("weight_kg", member.weight_kg),
                                        ("fitness_goal", goal), ("diet_preference", diet_type)) if not value]
    if missing:
        raise HTTPException(422,
                            f"Update the member's profile first; missing: {', '.join(missing)}")
    age = None
    if member.date_of_birth:
        today = date.today()
        dob = member.date_of_birth
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    profile = ai.MemberProfile(
        name=member.full_name.split()[0], gender=member.gender.value if member.gender else None, age=age,
        height_cm=member.height_cm, weight_kg=member.weight_kg, goal=goal.value, diet_type=diet_type.value,
        restrictions=member.dietary_restrictions, meals_per_day=data.meals_per_day, cuisine=data.cuisine,
        trainer_notes=data.trainer_notes,
    )
    try:
        draft, ai_generated = ai.generate_diet_plan(profile)
    except ai.DietGenerationError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    return TenantRepository(DietPlan, db).create(
        member_id=member.id, created_by_id=user.id, title=draft.title, goal=goal, diet_type=diet_type,
        daily_calories=draft.daily_calories, macros=draft.macros.model_dump(),
        meals=[m.model_dump() for m in draft.meals], notes=draft.notes,
        status=DietPlanStatus.DRAFT, ai_generated=ai_generated,
    )


@router.get("", response_model=list[DietPlanOut])
def list_plans(member_id: uuid.UUID | None = None, status_: DietPlanStatus | None = Query(None, alias="status"),
               db: Session = Depends(get_db), user: User = Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    filters = []
    if member_id:
        _member_for(db, user, member_id)
        filters.append(DietPlan.member_id == member_id)
    elif own := trainer_profile_id(db, user):
        own_members = TenantRepository(Member, db).query().with_only_columns(Member.id).where(
            Member.trainer_id == own)
        filters.append(DietPlan.member_id.in_(own_members))
    if status_:
        filters.append(DietPlan.status == status_)
    return TenantRepository(DietPlan, db).list(*filters, limit=500)


@router.get("/{plan_id}", response_model=DietPlanOut)
def get_plan(plan_id: uuid.UUID, db: Session = Depends(get_db),
             user: User = Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    return _plan_for(db, user, plan_id)


@router.patch("/{plan_id}", response_model=DietPlanOut)
def update_plan(plan_id: uuid.UUID, data: DietPlanUpdate, db: Session = Depends(get_db),
                user: User = Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    """Trainer customisation of meals, calories or notes."""
    plan = _plan_for(db, user, plan_id)
    return TenantRepository(DietPlan, db).update(plan, data.model_dump(exclude_unset=True))


@router.post("/{plan_id}/approve", response_model=DietPlanOut)
def approve(plan_id: uuid.UUID, db: Session = Depends(get_db),
            user: User = Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    plan = _plan_for(db, user, plan_id)
    return TenantRepository(DietPlan, db).update(plan, {"status": DietPlanStatus.APPROVED})


@router.post("/{plan_id}/assign", response_model=DietPlanOut)
def assign(plan_id: uuid.UUID, notify: bool = True, db: Session = Depends(get_db),
           user: User = Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    """Make this the member's active plan (any previously assigned plan is moved back to approved)."""
    repo = TenantRepository(DietPlan, db)
    plan = _plan_for(db, user, plan_id)
    for other in repo.list(DietPlan.member_id == plan.member_id, DietPlan.status == DietPlanStatus.ASSIGNED,
                           DietPlan.id != plan.id):
        other.status = DietPlanStatus.APPROVED
    plan = repo.update(plan, {"status": DietPlanStatus.ASSIGNED})
    if notify:
        member = TenantRepository(Member, db).get(plan.member_id)
        gym = db.get(Gym, plan.gym_id)
        n = notifications.enqueue(
            db, member, Channel.WHATSAPP,
            f"Hi {member.full_name.split()[0]}, your trainer at {gym.name} has shared a new diet plan "
            f"({plan.daily_calories} kcal/day). Open the GymFlow member app to view it.",
            category="diet_plan",
        )
        if n:
            notifications.dispatch(db, n)
    return plan


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: uuid.UUID, db: Session = Depends(get_db),
                user: User = Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    TenantRepository(DietPlan, db).delete(_plan_for(db, user, plan_id))
