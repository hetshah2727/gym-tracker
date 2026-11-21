import enum


class Role(str, enum.Enum):
    PLATFORM_ADMIN = "platform_admin"
    GYM_OWNER = "gym_owner"
    GYM_MANAGER = "gym_manager"
    TRAINER = "trainer"
    MEMBER = "member"


class MemberStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class FitnessGoal(str, enum.Enum):
    WEIGHT_LOSS = "weight_loss"
    WEIGHT_GAIN = "weight_gain"
    MAINTENANCE = "maintenance"


class DietPreference(str, enum.Enum):
    VEG = "veg"
    NON_VEG = "non_veg"
    EGGETARIAN = "eggetarian"
    VEGAN = "vegan"


class MembershipStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    FROZEN = "frozen"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    UPI = "upi"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    ONLINE = "online"


class Channel(str, enum.Enum):
    WHATSAPP = "whatsapp"
    VOICE = "voice"
    SMS = "sms"
    EMAIL = "email"


class NotificationStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class AutomationTrigger(str, enum.Enum):
    MEMBERSHIP_EXPIRING = "membership_expiring"
    MEMBERSHIP_EXPIRED = "membership_expired"
    PAYMENT_DUE = "payment_due"
    BIRTHDAY = "birthday"
    INACTIVE_MEMBER = "inactive_member"


class DietPlanStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    ASSIGNED = "assigned"


class ConversionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    REJECTED = "rejected"


class LeadStatus(str, enum.Enum):
    """Sales pipeline stage. ``converted`` is shown as "Joined" (kept for backwards compatibility)."""
    NEW = "new"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    TRIAL_BOOKED = "trial_booked"
    TRIAL_ATTENDED = "trial_attended"
    NEGOTIATION = "negotiation"
    CONVERTED = "converted"
    LOST = "lost"


OPEN_LEAD_STATUSES = (LeadStatus.NEW, LeadStatus.CONTACTED, LeadStatus.INTERESTED, LeadStatus.TRIAL_BOOKED,
                      LeadStatus.TRIAL_ATTENDED, LeadStatus.NEGOTIATION)


class LeadSource(str, enum.Enum):
    WEBSITE = "website"
    WEBSITE_CHAT = "website_chat"
    SEO_LANDING_PAGE = "seo_landing_page"
    ORGANIC_SEARCH = "organic_search"
    AI_SEARCH = "ai_search"
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    WALK_IN = "walk_in"
    GOOGLE_BUSINESS_PROFILE = "google_business_profile"
    REFERRAL = "referral"
    QR_CODE = "qr_code"
    PAID_CAMPAIGN = "paid_campaign"
    CORPORATE = "corporate"
    MANUAL = "manual"
    OTHER = "other"


class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(str, enum.Enum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskKind(str, enum.Enum):
    FOLLOW_UP = "follow_up"
    RENEWAL = "renewal"
    PAYMENT = "payment"
    NO_SHOW = "no_show"
    ESCALATION = "escalation"
    REVIEW = "review"
    SEO = "seo"
    OTHER = "other"


class TrialStatus(str, enum.Enum):
    BOOKED = "booked"
    PENDING_REVIEW = "pending_review"  # slot passed, attendance not recorded yet
    ATTENDED = "attended"
    NO_SHOW = "no_show"                # confirmed by staff
    CANCELLED = "cancelled"


ACTIVE_TRIAL_STATUSES = (TrialStatus.BOOKED, TrialStatus.PENDING_REVIEW)


class OpportunityType(str, enum.Enum):
    UPCOMING_RENEWAL = "upcoming_renewal"
    EXPIRED_MEMBERSHIP = "expired_membership"
    OUTSTANDING_PAYMENT = "outstanding_payment"
    FAILED_PAYMENT = "failed_payment"
    TRIAL_NO_SHOW = "trial_no_show"
    UNCONTACTED_LEAD = "uncontacted_lead"
    OVERDUE_FOLLOW_UP = "overdue_follow_up"


class OpportunityStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WON = "won"
    LOST = "lost"
    DISMISSED = "dismissed"


OPEN_OPPORTUNITY_STATUSES = (OpportunityStatus.OPEN, OpportunityStatus.IN_PROGRESS)


class AuditStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Severity(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class ContentStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"


class ConnectionStatus(str, enum.Enum):
    NOT_CONNECTED = "not_connected"
    PENDING = "pending"          # OAuth done, location/property not selected yet
    CONNECTED = "connected"
    EXPIRED = "expired"
    ERROR = "error"


class ConversationStatus(str, enum.Enum):
    AI_ACTIVE = "ai_active"
    HUMAN = "human"              # staff took over; AI stays silent
    CLOSED = "closed"


class ReplyStatus(str, enum.Enum):
    NONE = "none"
    DRAFTED = "drafted"
    APPROVED = "approved"
    PUBLISHED = "published"      # posted through the official API
    COPIED = "copied"            # owner posted it manually


class ActionStatus(str, enum.Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    REJECTED = "rejected"
    FAILED = "failed"


class SubscriptionStatus(str, enum.Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
