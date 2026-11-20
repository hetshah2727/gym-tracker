"""Import every model so Base.metadata (and Alembic) sees all tables."""
from app.database.models.affiliate import AffiliateConversion, AffiliateLink, AffiliateProduct
from app.database.models.automation import AutomationRule, Notification
from app.database.models.diet_plan import DietPlan
from app.database.models.gym import Gym
from app.database.models.member import Member, Trainer
from app.database.models.membership import Attendance, Membership, MembershipPlan, Payment
from app.database.models.subscription import GymSubscription, SubscriptionPlan, SupportTicket
from app.database.models.user import User
from app.database.models.website import Lead, Website

__all__ = [
    "AffiliateConversion", "AffiliateLink", "AffiliateProduct", "Attendance", "AutomationRule",
    "DietPlan", "Gym", "GymSubscription", "Lead", "Member", "Membership", "MembershipPlan",
    "Notification", "Payment", "SubscriptionPlan", "SupportTicket", "Trainer", "User", "Website",
]
