"""Import every model so Base.metadata (and Alembic) sees all tables."""
from app.database.models.affiliate import AffiliateConversion, AffiliateLink, AffiliateProduct
from app.database.models.ai import AgentConfig, AgentRun, AIConversation, AIMessage, PendingAction
from app.database.models.automation import AutomationRule, Notification
from app.database.models.diet_plan import DietPlan
from app.database.models.growth import (
    Campaign, EventLog, FollowUpTask, LeadInteraction, RecoveryOpportunity, TrialBooking,
)
from app.database.models.gym import Gym
from app.database.models.local import (
    AiReadinessCheck, AiVisibilityQuery, AiVisibilityResult, BusinessProfileSnapshot, Competitor, GymProfile,
    Review, ReviewRequest,
)
from app.database.models.member import Member, Trainer
from app.database.models.membership import Attendance, Membership, MembershipPlan, Payment
from app.database.models.platform import IntegrationConnection, SubscriptionEvent, UsageCounter, WebhookEvent
from app.database.models.seo import (
    ContentSuggestion, GrowthReport, LandingPage, SearchPerformance, SeoAudit, SeoFinding, SeoKeyword, SeoPage,
)
from app.database.models.subscription import GymSubscription, SubscriptionPlan, SupportTicket
from app.database.models.user import User
from app.database.models.website import Lead, Website

__all__ = [
    "AffiliateConversion", "AffiliateLink", "AffiliateProduct", "AgentConfig", "AgentRun", "AIConversation",
    "AIMessage", "AiReadinessCheck", "AiVisibilityQuery", "AiVisibilityResult", "Attendance", "AutomationRule",
    "BusinessProfileSnapshot", "Campaign", "Competitor", "ContentSuggestion", "DietPlan", "EventLog",
    "FollowUpTask", "GrowthReport", "Gym", "GymProfile", "GymSubscription", "IntegrationConnection",
    "LandingPage", "Lead", "LeadInteraction", "Member", "Membership", "MembershipPlan", "Notification", "Payment",
    "PendingAction", "RecoveryOpportunity", "Review", "ReviewRequest", "SearchPerformance", "SeoAudit",
    "SeoFinding", "SeoKeyword", "SeoPage", "SubscriptionEvent", "SubscriptionPlan", "SupportTicket", "Trainer",
    "TrialBooking", "UsageCounter", "User", "WebhookEvent", "Website",
]
