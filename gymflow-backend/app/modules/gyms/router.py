from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import tenant_user
from app.core.tenant_context import get_current_gym_id
from app.database.models import Gym
from app.database.models.enums import Role
from app.database.session import get_db
from app.modules.gyms.schemas import GymOut, GymUpdate

router = APIRouter(prefix="/gym", tags=["Gym settings"])


@router.get("", response_model=GymOut)
def get_my_gym(db: Session = Depends(get_db), _=Depends(tenant_user())):
    return db.get(Gym, get_current_gym_id())


@router.patch("", response_model=GymOut)
def update_my_gym(data: GymUpdate, db: Session = Depends(get_db), _=Depends(tenant_user(Role.GYM_OWNER))):
    gym = db.get(Gym, get_current_gym_id())
    updates = data.model_dump(exclude_unset=True)
    if "settings" in updates:  # merge rather than replace
        updates["settings"] = {**(gym.settings or {}), **updates["settings"]}
    for key, value in updates.items():
        setattr(gym, key, value)
    db.commit()
    db.refresh(gym)
    return gym
