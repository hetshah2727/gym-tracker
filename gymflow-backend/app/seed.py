"""Create a platform admin and a demo gym with sample data.

    python -m app.seed
"""
from datetime import date, timedelta

from sqlalchemy import select

from app.core.security import hash_password
from app.core.tenant_context import tenant_scope
from app.database.models import AffiliateProduct, Member, MembershipPlan, Trainer, User
from app.database.models.enums import DietPreference, FitnessGoal, Gender, Role
from app.database.repositories.base import TenantRepository
from app.database.session import SessionLocal
from app.modules.authentication.schemas import RegisterGymRequest
from app.modules.authentication.service import register_gym
from app.modules.memberships.service import assign_membership
from app.modules.subscriptions.service import ensure_default_plans

ADMIN = ("admin@gymflow.app", "admin12345")
OWNER = ("owner@demo-gym.com", "owner12345")

PRODUCTS = [
    ("Whey Protein 1kg (Chocolate)", "supplements", 2499, 8),
    ("Creatine Monohydrate 250g", "supplements", 899, 8),
    ("Adjustable Dumbbells 20kg", "equipment", 3999, 6),
    ("Resistance Bands Set", "equipment", 799, 6),
    ("Shaker Bottle 700ml", "accessories", 349, 10),
]


def main() -> None:
    with SessionLocal() as db:
        ensure_default_plans(db)
        if not db.scalar(select(User).where(User.email == ADMIN[0])):
            db.add(User(email=ADMIN[0], hashed_password=hash_password(ADMIN[1]), full_name="Platform Admin",
                        role=Role.PLATFORM_ADMIN))
        if not db.scalar(select(AffiliateProduct.id).limit(1)):
            for name, cat, price, rate in PRODUCTS:
                db.add(AffiliateProduct(name=name, category=cat, price=price, commission_rate_pct=rate,
                                        external_url="https://www.amazon.in/s?k=" + name.replace(" ", "+")))
        db.commit()

        if db.scalar(select(User).where(User.email == OWNER[0])):
            print("Demo data already present.")
            return
        token = register_gym(db, RegisterGymRequest(gym_name="Demo Fitness Club", owner_name="Demo Owner",
                                                    email=OWNER[0], password=OWNER[1], phone="9876543210",
                                                    city="Ahmedabad"))
        with tenant_scope(token.user.gym_id):
            trainer = TenantRepository(Trainer, db).create(full_name="Karan Mehta", specialization="Strength")
            plans = TenantRepository(MembershipPlan, db).list(order_by=MembershipPlan.duration_days)
            people = [("Aarav Shah", Gender.MALE, FitnessGoal.WEIGHT_GAIN, DietPreference.VEG, -20),
                      ("Diya Patel", Gender.FEMALE, FitnessGoal.WEIGHT_LOSS, DietPreference.EGGETARIAN, -27),
                      ("Vihaan Joshi", Gender.MALE, FitnessGoal.MAINTENANCE, DietPreference.NON_VEG, -40)]
            for i, (name, gender, goal, diet, started) in enumerate(people):
                member = TenantRepository(Member, db).create(
                    full_name=name, phone=f"98000000{i:02d}", gender=gender, height_cm=170 - i * 4,
                    weight_kg=70 + i * 3, fitness_goal=goal, diet_preference=diet, trainer_id=trainer.id)
                assign_membership(db, member, plans[0], start_date=date.today() + timedelta(days=started),
                                  paid=i != 1)
    print(f"Seeded.\n  Platform admin: {ADMIN[0]} / {ADMIN[1]}\n  Gym owner:      {OWNER[0]} / {OWNER[1]}")


if __name__ == "__main__":
    main()
